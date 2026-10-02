"""LLM 服务层 —— 真实 OpenAI 兼容 API 客户端（无 Mock、无假回复）。

架构：
    LLMConfig   —— 环境变量配置（AI_API_KEY / AI_BASE_URL / AI_MODEL）
    LLMError    —— 分类错误（未配置Key/鉴权失败/限流/超时/网络/模型不存在）
    LLMClient   —— OpenAI 兼容协议客户端（OpenAI/DeepSeek/Qwen/智谱/Moonshot/Kimi 等）

设计原则：
1. **只用真实 API**：没有任何 Mock / 假数据 / 固定回复 / 免费代理降级。
2. **Provider 可换**：统一走 OpenAI-compatible 协议，改 AI_BASE_URL 即可换供应商。
3. **Key 安全**：只从环境变量读取，绝不写死在代码、绝不返回给前端。
4. **多模态**：vision 图片理解（base64 data URL）。
5. **流式**：stream=True 返回真实 token 生成器。
6. **多轮**：messages 数组完整透传（system/user/assistant）。

环境变量（.env）：
    AI_API_KEY=你的密钥            # 必填
    AI_BASE_URL=https://api.openai.com/v1   # 按供应商修改
    AI_MODEL=gpt-4o-mini          # 按供应商修改
    AI_TEMPERATURE=0.7
    AI_MAX_TOKENS=1500
    AI_TIMEOUT=60
"""
from __future__ import annotations

import os
import json as _json
import base64
from dataclasses import dataclass
from typing import Iterator, List, Dict, Optional, Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _st_secret(key: str) -> str:
    """读取 Streamlit Cloud Secrets（部署到 streamlit.app 时由平台注入）。
    本地无 streamlit / 无 secrets 时安全返回空串。"""
    try:
        import streamlit as st
        v = st.secrets.get(key) if hasattr(st, "secrets") else None
        return str(v).strip() if v else ""
    except Exception:
        return ""


def _env(*keys: str, default: str = "") -> str:
    # 优先级：系统环境变量/.env → Streamlit 云端 Secrets → default
    for k in keys:
        v = os.getenv(k, "")
        if v and v.strip():
            return v.strip()
    for k in keys:
        v = _st_secret(k)
        if v:
            return v
    return default


# =====================================================================
# 配置
# =====================================================================
@dataclass
class LLMConfig:
    """大模型配置（全部来自环境变量）。"""
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 3000  # Tour 计划需要更长输出
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            api_key=_env("AI_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"),
            base_url=_env("AI_BASE_URL", "OPENAI_BASE_URL",
                          default="https://api.openai.com/v1"),
            model=_env("AI_MODEL", "OPENAI_MODEL", default="gpt-4o-mini"),
            temperature=float(_env("AI_TEMPERATURE", default="0.7") or "0.7"),
            max_tokens=int(_env("AI_MAX_TOKENS", default="1500") or "1500"),
            timeout=float(_env("AI_TIMEOUT", default="60") or "60"),
        )

    @property
    def is_configured(self) -> bool:
        """是否已配置 API Key（未配置则系统拒绝工作并提示，绝不 Mock）。"""
        return bool(self.api_key.strip())

    def missing_message(self) -> str:
        if self.is_configured:
            return ""
        return ("请先配置 AI_API_KEY：复制 `.env.example` 为 `.env`，"
                "填入你的 API Key 后重启应用。")


# =====================================================================
# 错误类型（分类 → 友好提示）
# =====================================================================
class LLMError(Exception):
    """LLM 调用错误。friendly 为可直接展示给用户的信息。"""

    def __init__(self, friendly: str, detail: str = ""):
        super().__init__(detail or friendly)
        self.friendly = friendly
        self.detail = detail


def _classify_error(e: Exception) -> LLMError:
    """把底层异常翻译成友好中文提示 + 保留原始细节供 console 调试。"""
    s = str(e)
    low = s.lower()
    detail = f"{type(e).__name__}: {s}"

    if "401" in s or "unauthorized" in low or "invalid api key" in low \
            or "invalid_api_key" in low or "authentication" in low:
        return LLMError("API Key 无效或已过期，请检查 .env 中的 AI_API_KEY。", detail)
    if "429" in s or "rate limit" in low or "quota" in low:
        return LLMError("请求过于频繁或额度不足（Rate limit / Quota），请稍后再试。", detail)
    if "402" in s or "insufficient balance" in low:
        return LLMError("账户余额不足：请到服务商开放平台充值后重试"
                        "（如 DeepSeek 平台需充值后才能调用 API）。", detail)
    if "404" in s or "model" in low and ("not found" in low or "does not exist" in low):
        return LLMError(f"模型不存在：请检查 .env 中的 AI_MODEL（当前不可用）。", detail)
    if "timeout" in low or "timed out" in low:
        return LLMError("AI 服务响应超时，请稍后再试。", detail)
    if "connection" in low or "network" in low or "getaddrinfo" in low \
            or "failed to resolve" in low or "ssl" in low:
        return LLMError("AI 服务暂时无法连接（网络错误），请检查网络或 AI_BASE_URL 后再试。", detail)
    if "api key" in low and "not" in low:
        return LLMError("请先配置 AI_API_KEY。", detail)
    # 兜底：附上服务器原始错误摘要（截断），方便定位真实原因
    brief = s[:150].replace("\n", " ").strip()
    if brief:
        return LLMError(f"AI 服务暂时无法连接，请稍后再试。（{brief}）", detail)
    return LLMError("AI 服务暂时无法连接，请稍后再试。", detail)


# =====================================================================
# LLM 客户端（OpenAI 兼容协议）
# =====================================================================
class LLMClient:
    """统一的大模型客户端。所有 Agent 通过它调用真实 AI。"""

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig.from_env()
        self._client: Any = None

    # ---------- 底层 SDK ----------
    def _sdk(self):
        if not self.config.is_configured:
            raise LLMError("请先配置 AI_API_KEY。")
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise LLMError("缺少依赖：请在项目目录执行 `pip install openai python-dotenv`。",
                               f"ImportError: {e}")
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
            )
        return self._client

    # ---------- 文本对话 ----------
    def chat(self, messages: List[Dict[str, str]], *, stream: bool = False,
             json_mode: bool = False, temperature: Optional[float] = None,
             max_tokens: Optional[int] = None) -> Any:
        """多轮对话。非流式返回 str；流式返回 token 生成器。失败抛 LLMError。"""
        client = self._sdk()
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "stream": stream,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = client.chat.completions.create(**kwargs)
        except LLMError:
            raise
        except Exception as e:
            raise _classify_error(e)

        if not stream:
            try:
                content = resp.choices[0].message.content or ""
            except Exception as e:
                raise _classify_error(e)
            if not content.strip():
                raise LLMError("AI 返回了空回答，请稍后再试。", "empty completion")
            return content

        def _gen() -> Iterator[str]:
            try:
                for chunk in resp:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            except Exception as e:
                err = _classify_error(e)
                yield f"\n\n⚠️ {err.friendly}"

        return _gen()

    # ---------- JSON 结构化输出 ----------
    def chat_json(self, messages: List[Dict[str, str]],
                  temperature: Optional[float] = None) -> Dict:
        """让模型输出 JSON 并解析。解析失败返回 {}（不伪造数据）。"""
        raw = self.chat(messages, json_mode=True, temperature=temperature)
        try:
            return _json.loads(raw)
        except Exception:
            pass
        import re
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return _json.loads(m.group(0))
            except Exception:
                return {}
        return {}

    # ---------- 图片理解（vision） ----------
    def chat_with_image(self, text: str, image_bytes: bytes, *,
                        mime_type: str = "image/jpeg",
                        system_prompt: str = "你是一名旅行图片分析助手，用中文描述图片内容。",
                        history: Optional[List[Dict]] = None) -> str:
        """真实 vision 调用。模型不支持图片时抛 LLMError（绝不返回假识别结果）。

        若配置了独立的 vision 渠道（AI_VISION_API_KEY / AI_VISION_BASE_URL /
        AI_VISION_MODEL，例如免费的 GitHub Models gpt-4o-mini），则图片识别走该渠道，
        文字对话仍走主渠道——这样主渠道可用无 vision 的免费模型（如 Groq）。"""
        v_key = _env("AI_VISION_API_KEY")
        if v_key:
            from openai import OpenAI
            client = OpenAI(
                api_key=v_key,
                base_url=_env("AI_VISION_BASE_URL",
                              default="https://models.github.ai/inference"),
                timeout=self.config.timeout,
            )
            model = _env("AI_VISION_MODEL", default="gpt-4o-mini")
        else:
            client = self._sdk()
            model = self.config.model
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        messages: List[Dict] = []
        if history:
            messages.extend(history)
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": text or "请描述这张图片。"},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
            ],
        })
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            content = resp.choices[0].message.content or ""
        except LLMError:
            raise
        except Exception as e:
            err = _classify_error(e)
            if "model" in err.detail.lower() and ("400" in err.detail or "image" in err.detail.lower()):
                raise LLMError("当前模型不支持图片识别，请在 .env 换用支持 vision 的模型（如 gpt-4o-mini、glm-4v）。",
                               err.detail)
            raise err
        if not content.strip():
            raise LLMError("AI 无法识别这张图片，请换一张试试。", "empty vision completion")
        return content

    # ---------- 健康检查 ----------
    def health(self) -> Dict[str, str]:
        if not self.config.is_configured:
            return {"status": "error", "llm": "not_configured",
                    "message": self.config.missing_message()}
        return {"status": "ok", "llm": "configured",
                "message": f"模型 {self.config.model} @ {self.config.base_url}"}


# =====================================================================
# 单例管理
# =====================================================================
_default_client: Optional[LLMClient] = None


def get_default_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def reset_client(config: LLMConfig) -> LLMClient:
    global _default_client
    _default_client = LLMClient(config)
    return _default_client
