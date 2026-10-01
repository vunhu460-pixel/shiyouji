"""会话记忆与结构化旅行上下文。

核心两块：
1. `ConversationMemory` —— 多轮对话历史（messages 列表），供 LLM 上下文。
   解决旧版 `self.history` 从不被填充的 bug，让 AI 真正能多轮记忆。
2. `TravelContext` —— 结构化旅行偏好槽位（目的地/天数/预算/兴趣/不喜欢 等）。
   支持增量更新：用户分多轮说「我想去杭州」「3天」「预算1500」「喜欢拍照」
   「不喜欢博物馆」「预算改成2000」，每次只更新对应字段，不覆盖已存信息。

设计原则：
- 用户每说出新的有效信息就更新 Context，不覆盖之前仍有效的信息。
- 用户修改条件（如「预算从1000改成1500」）只改对应字段。
- `to_summary()` 给 LLM 当上下文，让 AI 知道用户已告诉过什么，不重复询问。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# =====================================================================
# 一、多轮对话记忆
# =====================================================================
class ConversationMemory:
    """多轮对话历史，供 LLM 读取近 N 轮上下文。"""

    def __init__(self, max_turns: int = 12) -> None:
        # max_turns: 保留最近多少条消息（user+assistant 算 2 条）
        self.messages: List[Dict[str, str]] = []
        self.max_turns = max_turns

    def add_user(self, text: str) -> None:
        """记录用户消息。"""
        if text and text.strip():
            self.messages.append({"role": "user", "content": text.strip()})
            self._trim()

    def add_assistant(self, text: str) -> None:
        """记录 AI 回复。"""
        if text and text.strip():
            self.messages.append({"role": "assistant", "content": text.strip()})
            self._trim()

    def get_messages(self, last_n: Optional[int] = None) -> List[Dict[str, str]]:
        """取最近 N 条消息，用于拼进 LLM messages。last_n=None 取全部（受 max_turns 限）。"""
        msgs = self.messages
        if last_n is not None:
            msgs = msgs[-last_n:]
        return list(msgs)

    def clear(self) -> None:
        self.messages = []

    def _trim(self) -> None:
        """超过 max_turns 条只保留最近部分。"""
        if len(self.messages) > self.max_turns:
            self.messages = self.messages[-self.max_turns:]

    def to_list(self) -> List[Dict[str, str]]:
        return list(self.messages)


# =====================================================================
# 二、结构化旅行上下文（槽位）
# =====================================================================
@dataclass
class TravelContext:
    """旅行偏好槽位。增量合并：非空才覆盖，list 追加去重。"""
    destination: str = ""            # 目的地：杭州
    duration: str = ""              # 天数：3天 / 两天
    date: str = ""                  # 出发日期：国庆 / 10月1日
    budget: str = ""                # 预算：1500元
    travelers: str = ""             # 人数/类型：一个人 / 情侣 / 亲子
    interests: List[str] = field(default_factory=list)   # 兴趣：摄影/美食/历史
    dislikes: List[str] = field(default_factory=list)    # 不喜欢：博物馆
    food_preferences: List[str] = field(default_factory=list)  # 饮食偏好：吃辣/素食
    transportation: str = ""        # 交通：高铁 / 自驾
    hotel_preferences: str = ""     # 住宿：市中心 / 民宿
    current_location: str = ""     # 当前所在地（用于「附近」指代）
    last_topic: str = ""            # 上一轮讨论的核心实体（用于「第一个」「那里」指代）
    conversation_summary: str = ""  # 简要对话摘要

    # ------------------------------------------------------------------
    # 增量更新：从 LLM 抽取的结构化 dict 合并
    # ------------------------------------------------------------------
    def update_from_extraction(self, extraction: Dict[str, Any]) -> None:
        """从 Intent Router 抽取的结构化槽位增量合并。

        标量字段：extraction 里非空才覆盖（支持「预算改成2000」只改 budget）。
        列表字段：追加去重（兴趣/不喜欢/饮食偏好累积）。
        """
        if not extraction:
            return

        # 标量字段映射
        scalar_map = {
            "destination": "destination",
            "duration": "duration",
            "date": "date",
            "budget": "budget",
            "travelers": "travelers",
            "transportation": "transportation",
            "hotel_preferences": "hotel_preferences",
            "current_location": "current_location",
            "last_topic": "last_topic",
            "conversation_summary": "conversation_summary",
        }
        for ext_key, ctx_key in scalar_map.items():
            val = extraction.get(ext_key)
            if val and isinstance(val, str) and val.strip():
                # 显式修改信号（"改成"/"换成"/"不要"）才覆盖，否则保留已有
                cur = getattr(self, ctx_key, "")
                setattr(self, ctx_key, val.strip())

        # 列表字段：追加去重
        list_map = {
            "interests": "interests",
            "dislikes": "dislikes",
            "food_preferences": "food_preferences",
        }
        for ext_key, ctx_key in list_map.items():
            val = extraction.get(ext_key)
            if isinstance(val, list):
                cur = getattr(self, ctx_key, [])
                for v in val:
                    if isinstance(v, str) and v.strip() and v.strip() not in cur:
                        cur.append(v.strip())
                setattr(self, ctx_key, cur)
            elif isinstance(val, str) and val.strip():
                # 单字符串也追加
                cur = getattr(self, ctx_key, [])
                if val.strip() not in cur:
                    cur.append(val.strip())
                setattr(self, ctx_key, cur)

    # ------------------------------------------------------------------
    # 给 LLM 的上下文摘要
    # ------------------------------------------------------------------
    def to_summary(self) -> str:
        """生成给 LLM 的「已知旅行信息」摘要。空上下文返回空串。"""
        if self.is_empty():
            return ""
        parts: List[str] = []
        if self.destination:
            parts.append(f"目的地：{self.destination}")
        if self.duration:
            parts.append(f"天数：{self.duration}")
        if self.date:
            parts.append(f"日期：{self.date}")
        if self.budget:
            parts.append(f"预算：{self.budget}")
        if self.travelers:
            parts.append(f"出行人：{self.travelers}")
        if self.interests:
            parts.append(f"兴趣：{','.join(self.interests)}")
        if self.dislikes:
            parts.append(f"不喜欢：{','.join(self.dislikes)}")
        if self.food_preferences:
            parts.append(f"饮食偏好：{','.join(self.food_preferences)}")
        if self.transportation:
            parts.append(f"交通：{self.transportation}")
        if self.hotel_preferences:
            parts.append(f"住宿：{self.hotel_preferences}")
        if self.current_location:
            parts.append(f"当前位置：{self.current_location}")
        if self.last_topic:
            parts.append(f"上一轮主题：{self.last_topic}")
        if self.conversation_summary:
            parts.append(f"对话摘要：{self.conversation_summary}")
        return "；".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "destination": self.destination,
            "duration": self.duration,
            "date": self.date,
            "budget": self.budget,
            "travelers": self.travelers,
            "interests": list(self.interests),
            "dislikes": list(self.dislikes),
            "food_preferences": list(self.food_preferences),
            "transportation": self.transportation,
            "hotel_preferences": self.hotel_preferences,
            "current_location": self.current_location,
            "last_topic": self.last_topic,
            "conversation_summary": self.conversation_summary,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TravelContext":
        c = cls()
        c.destination = d.get("destination", "") or ""
        c.duration = d.get("duration", "") or ""
        c.date = d.get("date", "") or ""
        c.budget = d.get("budget", "") or ""
        c.travelers = d.get("travelers", "") or ""
        c.interests = list(d.get("interests", []) or [])
        c.dislikes = list(d.get("dislikes", []) or [])
        c.food_preferences = list(d.get("food_preferences", []) or [])
        c.transportation = d.get("transportation", "") or ""
        c.hotel_preferences = d.get("hotel_preferences", "") or ""
        c.current_location = d.get("current_location", "") or ""
        c.last_topic = d.get("last_topic", "") or ""
        c.conversation_summary = d.get("conversation_summary", "") or ""
        return c

    def is_empty(self) -> bool:
        """是否完全没有已知信息。"""
        return not any([
            self.destination, self.duration, self.date, self.budget,
            self.travelers, self.interests, self.dislikes,
            self.food_preferences, self.transportation,
            self.hotel_preferences, self.current_location,
            self.last_topic, self.conversation_summary,
        ])
