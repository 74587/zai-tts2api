import os
import io
import json
import wave
import logging
import aiohttp
from base64 import b64decode

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

BASE_URL = os.getenv("BASE_URL") or "https://audio.z.ai"
USER_AGENT = os.getenv("USER_AGENT") or "Mozilla/5.0 AppleWebKit/537.36 Chrome/143 Safari/537"

ZAI_TOKEN = os.getenv("ZAI_AUDIO_TOKEN") or os.getenv("ZAI_TOKEN", "")
ZAI_USERID = os.getenv("ZAI_AUDIO_USERID") or os.getenv("ZAI_USERID", "")
DEFAULT_VOICE = os.getenv("ZAI_DEFAULT_VOICE", "system_002")

class Client:
    all_voices = None

    def __init__(self, session: aiohttp.ClientSession, logger: logging.Logger = None):
        self.session = session
        self.log = logger or LOGGER

    async def api_request(self, api, json=None, headers=None, **kwargs):
        self.log.info("%s: %s", api, json)
        token = kwargs.pop("token") or ZAI_TOKEN
        method = kwargs.pop("method", "POST")
        return await self.session.request(
            method, api,
            json=json,
            headers={
                aiohttp.hdrs.AUTHORIZATION: f"Bearer {token}",
                aiohttp.hdrs.USER_AGENT: USER_AGENT,
                aiohttp.hdrs.REFERER: f"{BASE_URL}/",
                aiohttp.hdrs.ORIGIN: BASE_URL,
                **(headers or {}),
            },
            **kwargs,
        )

    async def get_voices(self, token=None, user_id=None):
        token = get_token(token)
        params = {
            "page": 1,
            "page_size": 200,
            "user_id": user_id or ZAI_USERID,
        }
        res = await self.api_request(
            "/api/v1/z-audio/voices/list_system",
            method="GET",
            params=params,
            token=token,
        )
        voices = (await res.json()).get("data") or []
        res = await self.api_request(
            "/api/v1/z-audio/voices/list",
            method="GET",
            params=params,
            token=token,
        )
        if res.status == 200:
            voices.extend((await res.json()).get("data") or [])
        else:
            self.log.warning("Got voices fail: %s", [res.status, await res.text(), res.request_info])
        return voices

    async def get_voice_info(self, voice_id):
        if self.all_voices is None:
            voices = await self.get_voices()
            self.all_voices = {
                v["voice_id"]: v
                for v in voices
            }
        return self.all_voices.get(voice_id) or {}

    async def audio_speech(self, payload: dict, token=None):
        voice_id = payload.get("voice") or DEFAULT_VOICE
        voice_name = (await self.get_voice_info(voice_id)).get("voice_name", "")
        res = await self.api_request(
            "/api/v1/z-audio/tts/create",
            json={
                "voice_name": voice_name,
                "voice_id": voice_id,
                "user_id": payload.get("user_id") or ZAI_USERID,
                "input_text": payload.get("input", ""),
                "speed": int(float(payload.get("speed", 1)) * 10) / 10,
                "volume": int(payload.get("volume", 1)),
            },
            headers={
                aiohttp.hdrs.ACCEPT: "text/event-stream",
            },
            timeout=aiohttp.ClientTimeout(total=None, sock_read=None, sock_connect=60),
            token=get_token(token),
        )
        res.raise_for_status()

        wav_header_sent = False
        async for line in get_event_stream(res):
            if not line.startswith("data:"):
                if line:
                    self.log.debug("New line: %s", line)
                continue
            text = line[5:].strip()
            if text == "[DONE]":
                self.log.debug("Done")
                break
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                self.log.warning("Not json: %s ... %s", text[0:100], text[-100:])
                continue
            if not (b64audio := data.get("audio")):
                self.log.warning("No audio: %s", text)
                continue
            audio_bytes = b64decode(b64audio)
            if audio_bytes.startswith(b"RIFF"):
                with io.BytesIO(audio_bytes) as f, wave.open(f, 'rb') as w:
                    audio_bytes = w.readframes(w.getnframes())
                    if not wav_header_sent:
                        header_buf = io.BytesIO()
                        with wave.open(header_buf, 'wb') as out_w:
                            out_w.setparams(w.getparams())
                            out_w.setnframes(0)
                        header = bytearray(header_buf.getvalue())
                        header[4:8] = b'\xff\xff\xff\xff'
                        header[40:44] = b'\xff\xff\xff\xff'
                        audio_bytes = header + audio_bytes
                        wav_header_sent = True
            self.log.debug("Audio bytes (%s): %s", len(audio_bytes), audio_bytes[:64].hex())
            yield audio_bytes


def get_token(token):
    if token is None:
        token = ""
    if token.startswith("Bearer "):
        token = token[7:]
    if token.lower() in ["none", "null"]:
        token = ""
    return token.strip() or ZAI_TOKEN

async def get_event_stream(res):
    buffer = b""
    async for chunk in res.content.iter_any():
        buffer += chunk
        if b"\n" not in chunk:
            continue
        lines = buffer.split(b"\n")
        buffer = lines.pop()
        for line_bytes in lines:
            if line_bytes:
                yield line_bytes.decode().strip()
    if buffer:
        yield buffer.decode().strip()
