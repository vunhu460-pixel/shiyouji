"""《食游记》意图路由 —— 指定/自适应双触发。

两种触发模式：
  1. **指定回答**：用户用 @语法 或侧栏锁定指定 Agent
     「@美食达人 上海有什么本帮菜」→ 只调用 food Agent
  2. **自适应回答**：自然语言提问 → LLM 意图分析（无 Key 时关键词兜底，仅用于路由，
     不生成回答内容）→ 选择 1 个或多个 Agent 协作

Agent key：
    food    美食达人 🍜
    travel  旅行规划师 🗺️
    culture 文化向导 🏮
"""
from __future__ import annotations

import json as _json
from typing import List, Dict, Any, Optional

from llm import LLMClient, LLMError, get_default_client


# 支持的意图类型
INTENT_TYPES = [
    "food_recommendation",          # 美食推荐
    "restaurant_recommendation",    # 餐厅推荐
    "attraction_recommendation",    # 景点推荐
    "itinerary_planning",           # 行程规划
    "transportation",               # 交通
    "hotel",                        # 住宿
    "budget_planning",              # 预算
    "culture",                      # 文化
    "history",                      # 历史
    "local_customs",                # 民俗
    "weather",                      # 天气
    "image_analysis",               # 图片分析
    "travel_comparison",            # 旅行比较
    "travel_tips",                  # 旅行贴士
    "follow_up_question",           # 追问
    "casual_conversation",          # 闲聊
    "clarification",                # 需要澄清
    "other",                        # 其他
]


# Agent 中文名 → 内部 key
AGENT_KEY_MAP = {
    "美食达人": "food",
    "旅行规划师": "travel",
    "文化向导": "culture",
}

# @语法 别名 → Agent 中文名
MENTION_MAP = {
    "美食达人": "美食达人", "美食": "美食达人", "吃货": "美食达人",
    "food": "美食达人",
    "旅行规划师": "旅行规划师", "旅行": "旅行规划师", "规划师": "旅行规划师",
    "旅游": "旅行规划师", "travel": "旅行规划师",
    "文化向导": "文化向导", "文化": "文化向导", "向导": "文化向导",
    "culture": "文化向导",
}

# 无 LLM 时的路由关键词兜底（只用于选 Agent，不用于生成回答）
KEYWORD_MAP = {
    "food": ["吃", "美食", "辣", "小吃", "特产", "味道", "做法", "火锅", "菜",
             "餐厅", "饿", "喝", "面", "鸭", "鱼", "茶", "馆子", "本帮菜", "早点",
             "店", "铺子", "饭馆"],
    "travel": ["景点", "路线", "玩", "怎么去", "去哪", "行程", "几天", "一日游",
               "门票", "打卡", "逛", "地铁", "交通", "住", "酒店", "预算",
               "攻略", "机场", "车站", "附近", "周边", "毗邻", "在哪里", "多远",
               "相邻", "旁边", "地图", "方位", "位置", "周边城市"],
    "culture": ["历史", "文化", "故事", "风俗", "传说", "由来", "典故", "古迹",
                "博物馆", "民俗", "节日", "建筑", "朝代", "礼仪", "春联"],
}

# LLM 意图路由的 System Prompt
_INTENT_SYSTEM = """你是《食游记》多智能体旅游助手的意图路由器。
分析用户最新输入（结合对话历史与已知偏好），输出严格 JSON，不要任何额外文字。

可调用的专家 Agent（key）：
- food   美食达人：美食/餐厅/菜品/口味/饮食文化/吃饭预算
- travel 旅行规划师：景点/行程/交通/路线/酒店区域/天数安排/旅行预算
- culture 文化向导：历史/民俗/节日/建筑/博物馆/城市文化/旅行礼仪

输出格式：
{
  "intent": "意图类型（如 food_recommendation / itinerary_planning / culture / casual_conversation / follow_up_question / clarification / other）",
  "needsAgents": ["food"|"travel"|"culture", ...],
  "extracted": {
    "destination": "",      // 目的地城市，未提及留空
    "duration": "",         // 天数，如"3天"
    "budget": "",           // 预算，如"1000元"
    "interests": [],        // 兴趣，如["拍照","美食"]
    "dislikes": []          // 不喜欢，如["博物馆"]
  },
  "needs_clarification": false,
  "clarification_question": ""
}

needsAgents 判断规则：
- 纯闲聊/追问指代/澄清：空数组
- 单领域问题只选对应 1 个 Agent
- 复合问题选多个，如「上海三日游+本帮菜+文化景点」→ ["travel","food","culture"]
- 最多 3 个，宁缺勿滥
- **追问继承上文领域**：用户说「推荐几个店」「还有呢」「哪家好吃」等短追问时，看【最近对话】的话题领域选 Agent（上文聊美食→food，聊行程→travel），不要因为「店」字就选 travel

extracted 槽位：只填用户明确说出的信息，未提及留空/空数组。

**重要：不要过度澄清（needs_clarification 默认 false）**
- 用户问「哪个城市好吃」「哪里好玩」「有什么推荐」等开放式问题 → 直接回答，推荐 2-3 个具体城市/景点，不要反问
- 用户问「臭豆腐在哪里吃」→ 直接推荐 2-3 个城市（如长沙、绍兴、南京），不要问"您想去哪个城市"
- 只有用户输入完全无法理解（如乱码、无意义字符）时才 needs_clarification=true
"""


def parse_mention(text: str) -> str:
    """解析 @专家 语法，命中返回 Agent 中文名，未命中返回空串。

    支持同时 @ 多个：「@美食达人 @文化向导 西安怎么玩」→ 取第一个，
    多 @ 的情况由 parse_mentions 处理。
    """
    if not text:
        return ""
    for m in parse_mentions(text):
        return m
    return ""


def parse_mentions(text: str) -> List[str]:
    """解析全部 @专家 语法（支持同时指定多个 Agent）。"""
    if not text:
        return []
    found: List[str] = []
    seen = set()
    for alias, name in MENTION_MAP.items():
        if f"@{alias}" in text and name not in seen:
            seen.add(name)
            found.append(name)
    return found


def route_specified(agent_name: str) -> List[str]:
    """指定触发：返回 Agent key 列表。"""
    if not agent_name:
        return []
    key = AGENT_KEY_MAP.get(agent_name)
    return [key] if key else []


def route_adaptive(user_text: str) -> List[str]:
    """自适应触发（关键词兜底）：无 LLM 时用关键词选 Agent（不生成回答）。"""
    if not user_text:
        return ["travel"]
    triggered = [key for key, kws in KEYWORD_MAP.items()
                 if any(kw in user_text for kw in kws)]
    return triggered or ["travel"]


def analyze_intent(user_text: str, context_summary: str = "",
                   memory_messages: Optional[List[Dict]] = None,
                   llm_client: Optional[LLMClient] = None) -> Dict[str, Any]:
    """LLM 意图分析。无 Key / 调用失败 / JSON 解析失败 → 关键词兜底。"""
    client = llm_client or get_default_client()

    # --- 无 Key：关键词兜底（仅路由） ---
    if not client.config.is_configured:
        needs = route_adaptive(user_text)
        return {"intent": "keyword_routed", "needsAgents": needs,
                "extracted": {}, "needs_clarification": False,
                "clarification_question": "", "source": "keyword"}

    # --- LLM 意图分析（真实调用） ---
    user_block = f"【用户最新输入】{user_text}"
    if context_summary:
        user_block += f"\n【已知偏好】{context_summary}"
    if memory_messages:
        hist = "\n".join(f"{m['role']}: {m['content'][:80]}"
                         for m in memory_messages[-6:])
        user_block += f"\n【最近对话】\n{hist}"
    user_block += "\n\n请输出 JSON。"

    messages = [
        {"role": "system", "content": _INTENT_SYSTEM},
        {"role": "user", "content": user_block},
    ]
    try:
        data = client.chat_json(messages, temperature=0.1)
    except LLMError:
        data = {}
    if not data:
        needs = route_adaptive(user_text)
        return {"intent": "keyword_routed", "needsAgents": needs,
                "extracted": {}, "needs_clarification": False,
                "clarification_question": "", "source": "keyword_fallback"}

    needs = data.get("needsAgents", [])
    if not isinstance(needs, list):
        needs = []
    needs = [n for n in needs if n in ("food", "travel", "culture")]
    ext = data.get("extracted", {})
    if not isinstance(ext, dict):
        ext = {}
    return {
        "intent": data.get("intent", "other"),
        "needsAgents": needs,
        "extracted": ext,
        "needs_clarification": bool(data.get("needs_clarification")),
        "clarification_question": data.get("clarification_question", ""),
        "source": "llm",
    }


def route(user_text: str, specified_agent: str = "",
          context_summary: str = "",
          memory_messages: Optional[List[Dict]] = None,
          llm_client: Optional[LLMClient] = None) -> Dict[str, Any]:
    """统一路由入口。

    返回：
        {
          "trigger_mode": "指定" | "自适应",
          "agents": [中文名, ...],        # 供 UI 展示
          "agent_keys": ["food", ...],    # 供调度
          "intent": "...",
          "extracted": {...},
          "needs_clarification": bool,
          "clarification_question": str,
          "reason": "...",
          "source": "llm" | "keyword" | "specified",
        }
    """
    # 1) @语法（可多个）
    mentions = parse_mentions(user_text)
    if mentions:
        keys = [AGENT_KEY_MAP[n] for n in mentions if n in AGENT_KEY_MAP]
        return {
            "trigger_mode": "指定",
            "agents": mentions,
            "agent_keys": keys,
            "intent": "specified",
            "extracted": {},
            "needs_clarification": False,
            "clarification_question": "",
            "reason": f"检测到 @{ ' @'.join(mentions) } 语法，指定触发",
            "source": "specified",
        }

    # 2) 侧栏锁定的 Agent
    if specified_agent:
        key = AGENT_KEY_MAP.get(specified_agent, "")
        return {
            "trigger_mode": "指定",
            "agents": [specified_agent],
            "agent_keys": [key] if key else [],
            "intent": "specified",
            "extracted": {},
            "needs_clarification": False,
            "clarification_question": "",
            "reason": f"侧栏锁定 {specified_agent}，指定触发",
            "source": "specified",
        }

    # 3) 自适应：LLM 意图分析
    analysis = analyze_intent(user_text, context_summary, memory_messages, llm_client)
    agent_keys = analysis.get("needsAgents", [])
    key_to_name = {v: k for k, v in AGENT_KEY_MAP.items()}
    agent_names = [key_to_name[k] for k in agent_keys if k in key_to_name]

    # 非闲聊但没路由到 Agent → 兜底交给全部专家（复合处理）
    if not agent_names and analysis.get("intent") not in (
            "casual_conversation", "follow_up_question",
            "clarification", "other"):
        agent_names = ["美食达人", "旅行规划师", "文化向导"]
        agent_keys = ["food", "travel", "culture"]

    # 最终兜底：任何旅游相关提问都不允许"无 Agent 回答"
    if not agent_names and analysis.get("intent") not in (
            "casual_conversation", "follow_up_question"):
        agent_names = ["旅行规划师"]
        agent_keys = ["travel"]

    return {
        "trigger_mode": "自适应",
        "agents": agent_names,
        "agent_keys": agent_keys,
        "intent": analysis.get("intent", "other"),
        "extracted": analysis.get("extracted", {}),
        # 兜底：如果 LLM 误判需要澄清但用户问题明显可回答（含"哪里/哪个/什么"等疑问词），
        # 强制不澄清，让 Agent 直接回答
        "needs_clarification": (
            analysis.get("needs_clarification", False)
            and not any(kw in user_text for kw in ["哪里", "哪个", "什么", "推荐", "好吃", "好玩"])
        ),
        "clarification_question": analysis.get("clarification_question", ""),
        "reason": (f"LLM 意图={analysis.get('intent')}"
                   if analysis.get("source") == "llm"
                   else f"关键词路由（{analysis.get('source')}）"),
        "source": analysis.get("source", "keyword"),
    }
