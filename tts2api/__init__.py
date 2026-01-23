import os
import io
import json
import wave
import logging
import aiohttp
from aiohttp import web
from base64 import b64decode

logging.basicConfig(level=logging.WARNING)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)
BASE_URL = os.getenv("BASE_URL") or "https://audio.z.ai"
HTTP_PORT = int(os.getenv("HTTP_PORT") or 80)
USER_AGENT = os.getenv("USER_AGENT") or "Mozilla/5.0 AppleWebKit/537.36 Chrome/143 Safari/537"

ZAI_TOKEN = os.getenv("ZAI_TOKEN", "")
ZAI_USERID = os.getenv("ZAI_USERID", "")

SESSION = None

async def init_session(app):
    global SESSION
    SESSION = aiohttp.ClientSession(
        base_url=BASE_URL,
    )

async def api_request(api, json=None, headers=None, **kwargs):
    _LOGGER.info("%s: %s", api, json)
    token = kwargs.pop("token") or ZAI_TOKEN
    return await SESSION.post(
        api,
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

async def get_models(request):
    models = [
        {"id": "cog-tts"},
    ]
    return web.json_response({"data": models})

def get_token(request):
    token = request.headers.get("Authorization") or ZAI_TOKEN
    if token.startswith("Bearer "):
        token = token[7:]
    return token.strip()

async def audio_speech(request):
    payload = await request.json() if request.content_type == "application/json" else request.query
    voice_id = payload.get("voice") or "system_001"
    voice_name = {
        "system_001": "活泼女声",
        "system_002": "通用男声",
        "system_003": "温柔女声",
    }.get(voice_id, "")
    res = await api_request(
        "/api/v1/z-audio/tts/create",
        json={
            "voice_name": voice_name,
            "voice_id": voice_id,
            "user_id": payload.get("user_id") or ZAI_USERID,
            "input_text": payload.get("text", ""),
            "speed": int(float(payload.get("speed", 1)) * 10) / 10,
            "volume": int(payload.get("volume", 1)),
        },
        headers={
            aiohttp.hdrs.ACCEPT: "text/event-stream",
        },
        timeout=aiohttp.ClientTimeout(total=None, sock_read=None, sock_connect=60),
        token=get_token(request),
    )
    res.raise_for_status()

    resp = web.StreamResponse(status=res.status, headers={
        aiohttp.hdrs.CONTENT_TYPE: "audio/wav",
    })
    await resp.prepare(request)

    wav_header_sent = False
    async for line in get_event_stream(res):
        if not line.startswith("data:"):
            if line:
                _LOGGER.debug("New line: %s", line)
            continue
        text = line[5:].strip()
        if text == "[DONE]":
            _LOGGER.debug("Done")
            break
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.warning("Not json: %s ... %s", text[0:100], text[-100:])
            continue
        if not (b64audio := data.get("audio")):
            _LOGGER.warning("No audio: %s", text)
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
        _LOGGER.debug("Audio bytes (%s): %s", len(audio_bytes), audio_bytes[:64].hex())
        await resp.write(audio_bytes)

    await resp.write_eof()
    return resp


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


@web.middleware
async def cors_auth_middleware(request, handler):
    request.response_factory = lambda: web.StreamResponse()
    response = await handler(request)
    response.headers[aiohttp.hdrs.ACCESS_CONTROL_ALLOW_ORIGIN] = "*"
    response.headers[aiohttp.hdrs.ACCESS_CONTROL_ALLOW_METHODS] = "GET, POST, OPTIONS"
    response.headers[aiohttp.hdrs.ACCESS_CONTROL_ALLOW_HEADERS] = "Content-Type, Authorization"
    return response

app = web.Application(logger=_LOGGER, middlewares=[cors_auth_middleware])
app.on_startup.append(init_session)

app.router.add_get("/v1/models", get_models)
app.router.add_route("*", "/v1/audio/speech", audio_speech)

async def on_cleanup(app):
    if SESSION:
        await SESSION.close()
app.on_cleanup.append(on_cleanup)

web.run_app(app, host="0.0.0.0", port=HTTP_PORT)
