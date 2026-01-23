# 🗣️ ZAI/GLM TTS

## Install / 安装

### 🐳 Docker compose
```shell
mkdir /opt/zai-tts2api
cd /opt/zai-tts2api
echo "ZAI_USERID=xxxx-yyyy" > .env
echo "ZAI_TOKEN=eyJhbGc..." >> .env
wget https://raw.githubusercontent.com/aahl/zai-tts2api/refs/heads/main/docker-compose.yml
docker compose up -d
```
> `ZAI_USERID`和`ZAI_TOKEN`可在`audio.z.ai`登录后，通过F12开发者工具在控制台执行`localStorage['auth-storage']`获取

### 🐳 Docker run
```shell
docker run -d \
  --name zai-tts2api \
  --restart=unless-stopped \
  -p 8823:80 \
  ghcr.nju.edu.cn/aahl/zai-tts2api:main
```

### 🏠 Home Assistant OS Add-on
1. 添加加载项仓库
   * 打开 HomeAssistant，点击左侧菜单的 **配置 (Settings)** -> **加载项 (Add-ons)**
   * 点击右下角的 **加载项商店 (Add-on Store)**
   * 点击右上角的三个点 -> **仓库 (Repositories)**
   * 在输入框填入：`https://gitee.com/hasscc/addons`, 点击添加
   [![添加加载项仓库](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgitee.com%2Fhasscc%2Faddons)

2. **安装加载项**：
   * 刷新页面，找到并点击 **`智谱TTS`**
   * 点击 **安装 (Install)**
   * 切换到 **配置** 标签页，添加`ZAI_USERID`和`ZAI_TOKEN`环境变量
   * 启动并设置开机启动


## 💻 Usage / 使用

### 🌐 CURL调用示例
```shell
curl --request POST \
  --url http://localhost:8823/v1/audio/speech \
  --header 'Content-Type: application/json' \
  --data '{"voice":"system_001", "text":"hello", "speed":1.0, "volume":1}' \
  --output output.wav
```

### 🏠 Home Assistant
1. 安装 AI Conversation 集成
   > 点击这里 [一键安装](https://my.home-assistant.io/redirect/hacs_repository/?category=integration&owner=hasscc&repository=ai-conversation)，安装完记得重启HA
2. [添加 AI Conversation 服务](https://my.home-assistant.io/redirect/config_flow_start/?domain=ai_conversation)，配置模型提供商
   > 服务商: 自定义; 接口: `http://4e0de88e-zai-tts/v1`; 密钥留空
3. 添加TTS模型，模型ID随意
4. 配置语音助手

> 如果想要使用克隆的音色，请在`audio.z.ai`完成音色克隆，并通过F12获取`voice_id`作为`voice`参数值
