"""《食游记》多智能体系统 —— 3 个真实 AI Agent（全部走真实大模型 API）。

Agent 清单：
    Agent 1  🍜 美食达人   (food)     —— 美食推荐/餐厅/菜品/饮食文化/预算建议
    Agent 2  🗺️ 旅行规划师 (travel)   —— 景点/行程/交通/路线/酒店区域/时间/预算
    Agent 3  🏮 文化向导   (culture)  —— 中国文化/历史/民俗/节日/建筑/博物馆/礼仪

核心原则：
1. **每个 Agent 都真实调用大模型 API**（system prompt + 多轮 history + user message）。
2. **回答动态生成**：不同城市/天数/预算/兴趣 → 不同回答，没有任何固定模板。
3. **工具增强**：需要实时信息时调用真实公共 API（天气/地图/搜索），失败不伪造。
4. **结构化卡片**：让模型输出 JSON（answer + cards），解析失败自动降级为纯文本。
5. **失败隔离**：单个 Agent 出错不影响其他 Agent 与整体流程。
"""
from __future__ import annotations

import json as _json
import re
import urllib.request
import urllib.parse
from typing import Dict, List, Optional

from llm import LLMClient, LLMError, get_default_client
from tools import ToolManager


# =====================================================================
# 真实数据：Wikipedia 城市简介（城市浏览页用，非 AI 聊天）
# =====================================================================
def _fetch_wiki_intro(city: str) -> str:
    """从 Wikipedia API 拉取真实城市简介（免费公共 API）。失败返回空串。"""
    try:
        url = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
               f"&prop=extracts&exintro&explaintext&titles="
               f"{urllib.parse.quote(city)}&redirects=1")
        req = urllib.request.Request(url, headers={"User-Agent": "ShiYouJi/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = _json.loads(r.read().decode("utf-8"))
        for _pid, page in data.get("query", {}).get("pages", {}).items():
            if _pid != "-1" and page.get("extract"):
                return page["extract"][:300]
    except Exception:
        pass
    return ""


# 城市浏览页支持的城市（点击后由 AI 动态介绍）
CITIES = ["北京", "上海", "成都", "杭州", "西安", "广州", "重庆", "南京"]

# Agent key → 引导提问
CITY_QUESTIONS = {
    "food": "「{city}有什么特色美食和餐厅推荐？」",
    "travel": "「帮我规划{city}三日游行程。」",
    "culture": "「介绍一下{city}的历史文化和必看古迹。」",
}


def get_city_guide(city: str) -> dict:
    """城市浏览页数据：真实 Wikipedia 简介 + 三类追问引导（不伪造内容）。"""
    intro = _fetch_wiki_intro(city)
    sections = [{"type": key, "title": label, "question": q.format(city=city)}
                for key, label, q in [
                    ("food", "🍜 问美食达人", CITY_QUESTIONS["food"]),
                    ("travel", "🗺️ 问旅行规划师", CITY_QUESTIONS["travel"]),
                    ("culture", "🏮 问文化向导", CITY_QUESTIONS["culture"]),
                ]]
    return {"intro": intro, "sections": sections}


# =====================================================================
# 三个 Agent 的 System Prompt
# =====================================================================
CARD_FORMAT_INSTRUCTION = """
【输出格式要求】你必须输出一个 JSON 对象（不要输出任何 JSON 以外的文字）：
{
  "answer": "面向用户的回答。必须简短：3-5句话说清重点，不超过150字，语气生动通俗，使用中文。禁止长篇大论、禁止客套话、禁止说『无法提供图片』之类的废话——图片由系统自动配好，你只负责内容",
  "cards": [
    {
      "title": "条目名称（如菜名/景点名/行程日）",
      "intro": "一句话核心介绍（不超过25字）",
      "story": "一句推荐理由（没有可留空字符串，不超过30字）",
      "tips": "一条最关键的实用贴士；若涉及门票/营业时间/价格等时效信息，末尾加：信息仅供参考，出行前请核实",
      "image_keywords": "用于配图检索的中文关键词（3-8个字，尽量用百科词条名，如『圣索菲亚教堂』『成都火锅』）",
      "tts": "适合语音朗读的一句话摘要（不超过30字）"
    }
  ]
}
cards 数量 1-3 个，只挑最推荐的，按推荐度排序。若问题不适合卡片展示，cards 可为空数组。
"""


class BaseAgent:
    """Agent 基类：真实调用 LLM，支持多轮 history、工具增强、JSON 卡片。"""
    name: str = "Agent"
    avatar: str = "🤖"
    agent_key: str = ""
    system_prompt: str = ""
    tool_keywords: List[str] = []          # 命中则调用真实工具补充上下文

    def __init__(self, client: Optional[LLMClient] = None,
                 tool_manager: Optional[ToolManager] = None) -> None:
        self.client = client or get_default_client()
        self.tool_manager = tool_manager

    # ---------- 工具 ----------
    def _gather_tool_context(self, user_text: str) -> tuple:
        """按关键词调用真实工具，返回 (工具补充信息, 使用过的工具名列表)。"""
        if not self.tool_manager or not self.tool_keywords:
            return "", []
        if not any(k in (user_text or "") for k in self.tool_keywords):
            return "", []
        result = self.tool_manager.call_for_agent(self.agent_key, user_text)
        if result:
            return f"[实时数据（来自公共API，仅供参考）] {result}", ["web_search"]
        return "", []

    # ---------- 消息构建 ----------
    def _build_messages(self, user_text: str, history: List[Dict],
                        tool_context: str, context: Optional[Dict]) -> List[Dict]:
        system = self.system_prompt + CARD_FORMAT_INSTRUCTION
        messages = [{"role": "system", "content": system}]
        ctx = context or {}
        if ctx.get("travel_summary"):
            messages.append({"role": "system",
                             "content": f"【用户已知偏好】{ctx['travel_summary']}"})
        if tool_context:
            messages.append({"role": "system", "content": tool_context})
        if history:
            messages.extend(history[-10:])   # 多轮上下文（最近10条）
        messages.append({"role": "user", "content": user_text})
        return messages

    # ---------- JSON 解析 ----------
    @staticmethod
    def _parse_llm_json(raw: str) -> Optional[Dict]:
        """从模型输出中稳健解析 JSON。失败返回 None（绝不伪造）。"""
        raw = (raw or "").strip()
        if not raw:
            return None
        # 剥掉 ```json ``` 包裹
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
        try:
            data = _json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                data = _json.loads(m.group(0))
                if isinstance(data, dict):
                    return data
            except Exception:
                return None
        return None

    # ---------- 对外入口 ----------
    def respond(self, user_text: str, image: Optional[bytes] = None,
                context: Optional[Dict] = None,
                history: Optional[List[Dict]] = None) -> Dict:
        """真实调用 LLM 生成动态回答。失败抛出 LLMError 由上层统一处理。"""
        tool_context, tools_used = self._gather_tool_context(user_text)
        messages = self._build_messages(user_text, history or [], tool_context, context)

        data = None
        raw = ""
        try:
            raw = self.client.chat(messages, stream=False)
        except LLMError as e:
            # 某些兼容 API 不支持 response_format，先试普通模式再解析
            if "response_format" in e.detail or "400" in e.detail:
                raw = self.client.chat(messages, stream=False)
                data = self._parse_llm_json(raw)
            else:
                raise

        data = data or self._parse_llm_json(raw)
        if data and data.get("answer"):
            answer = str(data["answer"]).strip()
            cards = data.get("cards") if isinstance(data.get("cards"), list) else []
            cards = [c for c in cards if isinstance(c, dict) and c.get("title")]
        else:
            # 模型没按 JSON 输出 → 把原文当回答（仍是真实生成，不伪造）
            answer = raw.strip()
            cards = []

        return {
            "agent": self.agent_key,
            "agent_name": self.name,
            "avatar": self.avatar,
            "input": user_text,
            "tools_used": tools_used,
            "cards": cards[:5],
            "result": answer,
            "error": None,
        }


class FoodAgent(BaseAgent):
    """🍜 美食达人 —— 真实 AI 美食智能体。"""
    name = "美食达人"
    avatar = "🍜"
    agent_key = "food"
    tool_keywords = ["餐厅", "哪家", "去哪吃", "推荐店", "美食街", "夜市"]
    system_prompt = (
        "你是《食游记》的「美食达人」，一位熟悉中国各地味道的本地美食专家，亲切接地气。"
        "你负责：美食推荐、餐厅推荐、菜品介绍、当地特色美食、饮食文化、食物口味、预算建议。"
        "回答规则："
        "1. 只回答美食相关问题；用户问到景点/交通时可一句话带过并建议咨询其他专家；"
        "2. 区分【老字号】和【本地人常去的小店】，分别标注；"
        "3. 主动识别用户忌口（不吃辣/不吃甜/素食/过敏）并给出替代建议；"
        "4. 提到具体餐厅营业状态时注明：店铺信息可能变动，出行前请确认营业时间；"
        "5. 绝不编造『今天营业』『还有位置』等无法证实的实时信息；"
        "6. 被问到推荐店铺/美食时，必须直接列出 2-4 个真实知名的店铺或美食名称并简单介绍"
        "（如『火宫殿』『黑色经典』这类广为人知的老字号），绝不说『暂无推荐』『没有信息』。"
    )


class TravelAgent(BaseAgent):
    """🗺️ 旅行规划师 —— 真实 AI 旅游智能体。"""
    name = "旅行规划师"
    avatar = "🗺️"
    agent_key = "travel"
    tool_keywords = ["天气", "怎么去", "路线", "交通", "地图", "距离",
                     "附近", "周边", "旁边", "毗邻", "在哪里", "多远"]
    system_prompt = (
        "你是《食游记》的「旅行规划师」，一位细心务实的旅行顾问，专注实用出行信息。"
        "你负责：景点推荐、行程规划、交通建议、路线规划、酒店区域建议、一日游/多日游安排、时间安排、旅行预算。"
        "回答规则："
        "1. 只回答旅行规划相关问题；美食/文化问题建议咨询其他专家；"
        "2. 根据用户给定的城市/天数/预算/兴趣动态定制行程，不同条件给不同方案；"
        "3. 行程按天/按时间段组织，给出顺序安排和理由；"
        "4. 门票、班次、价格等时效信息注明：信息仅供参考，请以官方最新公告为准；"
        "5. 绝不编造实时余票、实时房价、实时人流等无法证实的即时数据；"
        "6. 被问到推荐景点/行程时，必须直接列出 2-4 个具体景点或行程建议，绝不说『暂无推荐』；"
        "7. 【Tour 细节要求】用户问行程规划时，必须输出具体可执行的详细计划，每一天都必须有具体时间点："
        "   - 每天按小时列出，必须包含具体时间点（如 08:00 起床早餐 → 09:00-11:30 游览XX → 12:00-13:30 午餐 → 14:00-17:00 游览YY → 18:00 晚餐 → 19:30 夜游）"
        "   - 每段标注交通方式（如『地铁2号线，约30分钟，票价4元』『打车约15分钟，约20元』『步行10分钟』）"
        "   - 推荐具体酒店（如『住五一广场附近，推荐全季/亚朵，约300-500元/晚，理由：交通便利、美食集中』）"
        "   - 估算每日费用明细：门票X元 + 餐饮X元 + 交通X元 = 小计X元，最后给出总预算"
        "   - 每个景点标注：门票价格、建议游览时长、最佳游览时间（如『上午人少』『傍晚看日落』）"
        "   - 禁止使用 HTML 标签如 <br>，只用纯 Markdown"
        "8. 输出格式：用 Markdown 表格或分块列表展示，结构清晰，一目了然。"
    )


class CultureAgent(BaseAgent):
    """🏮 文化向导 —— 真实 AI 文化智能体。"""
    name = "文化向导"
    avatar = "🏮"
    agent_key = "culture"
    tool_keywords = ["历史", "由来", "起源", "传说", "典故", "背景"]
    system_prompt = (
        "你是《食游记》的「文化向导」，一位儒雅亲切的文化学者，擅长把历史文化讲得生动有趣。"
        "你负责：中国文化、历史、民俗、节日、建筑、博物馆、城市文化、旅行礼仪。"
        "回答规则："
        "1. 只回答文化相关问题；美食/行程问题建议咨询其他专家；"
        "2. 语言通俗生动、简短有趣，少用学术晦涩词汇；"
        "3. 讲历史典故时保持可靠，不确定的传说要说明『相传』；"
        "4. 提及博物馆开放安排等时效信息注明：信息仅供参考，出行前请核实；"
        "5. 结合用户提供的图片信息（若有）讲解相关文化背景。"
    )


# =====================================================================
# 注册表
# =====================================================================
def get_default_agents() -> Dict[str, BaseAgent]:
    """创建 3 个真实 AI Agent（共享一个 ToolManager）。"""
    tm = ToolManager()
    return {
        "food": FoodAgent(tool_manager=tm),
        "travel": TravelAgent(tool_manager=tm),
        "culture": CultureAgent(tool_manager=tm),
    }


def reset_agents(client: Optional[LLMClient] = None) -> Dict[str, BaseAgent]:
    tm = ToolManager()
    return {
        "food": FoodAgent(client=client, tool_manager=tm),
        "travel": TravelAgent(client=client, tool_manager=tm),
        "culture": CultureAgent(client=client, tool_manager=tm),
    }
