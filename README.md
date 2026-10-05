# 🍲 食游记 · 多智能体 AI 旅游助手

一个基于 **Streamlit + 大模型 API** 的多智能体（Multi-Agent）中文旅游助手。
三位 AI 专家并行服务、一位金牌导游实时整合成最终回答，支持文字对话、图片识别、
语音输入/朗读、多日详细行程规划。

- 在线体验：<https://shiyouji.streamlit.app/>
- 开源仓库：<https://github.com/vunhu460-pixel/shiyouji>

## ✨ 功能

- **多智能体协作**：🍜 美食达人 / 🗺️ 旅行规划师 / 🏮 文化向导并行作答，总导游整合去重
- **意图路由**：自动识别问题类型并分派给合适的专家，也可手动 @ 指定
- **多模态图片识别**：上传景区/美食照片，自动与 30+ 中国热门城市地标库核对，直接答出城市与地标
- **语音输入 & 朗读**：浏览器原生 Web Speech API，免费、无需联网 TTS
- **多日行程规划**：识别"3天/三日游/一周"等，逐日输出时间表、交通（地铁线路/票价）、酒店、餐饮与总预算
- **多轮记忆**：会话上下文 + 用户出行偏好
- **四个页面**：🌟 中国魅力 / 📋 行程规划 / 💬 AI 导游问答 / 🎫 我的行程
- **真实流式输出**：回答逐字生成；全程只调用真实 API，无任何假数据

## 🏗️ 多智能体架构

```
用户提问
  └─ router.py        意图识别 → 分派 1~3 个专家
       └─ orchestrator.py   并行调度 + 失败隔离
            ├─ agent.py     FoodAgent / TravelAgent / CultureAgent
            ├─ tools.py     维基百科/天气/地图/汇率等真实公共 API
            └─ llm.py       统一 OpenAI 兼容客户端（文字 + vision 双通道）
       └─ Coordinator（总导游）整合专家素材 → 流式输出最终回答
```

## 📁 源文件说明

| 文件 | 作用 |
|---|---|
| `app.py` | Streamlit 主程序：4 个页面、聊天界面、语音/图片注入、行程展示 |
| `agent.py` | 3 个 AI Agent 定义、提示词、城市数据与维基图片处理 |
| `orchestrator.py` | 多智能体调度中心：并行调用、总导游整合、地标识别、多日行程配额 |
| `router.py` | 意图路由：指定回答（@专家）与自适应分派、澄清反问 |
| `llm.py` | LLM 服务层：OpenAI 兼容协议、错误分类、图片压缩与 vision 调用、云端 Secrets |
| `tools.py` | 免费真实工具：维基百科、天气、地图、汇率等 |
| `memory.py` | 多轮对话记忆 `ConversationMemory` 与出行偏好 `TravelContext` |
| `theme.py` | 页面样式、横幅、卡片与图片渲染 |
| `requirements.txt` | Python 依赖 |
| `.env.example` | 环境变量模板（复制为 `.env` 后填入自己的 Key） |
| `.streamlit/config.toml` | Streamlit 配置 |

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key（复制模板并填入）
cp .env.example .env

# 3. 启动
python -m streamlit run app.py --server.port 8766
```

### 环境变量

采用统一的 OpenAI 兼容协议，可自由切换供应商：

```ini
AI_API_KEY=gsk_xxx                       # 文字模型 Key
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=openai/gpt-oss-120b
AI_VISION_API_KEY=mstrl_xxx              # 图片识别（vision）Key
AI_VISION_BASE_URL=https://api.mistral.ai/v1
AI_VISION_MODEL=pixtral-12b-2409
```

部署到 Streamlit Community Cloud 时，在应用 **Settings → Secrets** 填入同样内容即可，
访客无需也无法看到或修改 Key。

## 🔒 安全说明

- API Key 只从服务端 `.env` 或 Streamlit Secrets 读取，**绝不硬编码、绝不上传 GitHub**
- `.env` 已在 `.gitignore` 中保护

## 📜 License

MIT
