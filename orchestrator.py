"""AIOrchestrator —— 多智能体调度中心（全部真实 AI 调用）。

流程：
    User → 意图路由（router.py）
         → 并行调用 1~3 个真实 AI Agent（agent.py）
         → Coordinator（真实 LLM）整合去重、标注冲突
         → 流式输出最终回答 + 快捷追问

统一输出格式：
    {
        "type": "final",
        "trigger_mode": "指定"|"自适应",
        "agents": ["food", ...],
        "agent_replies": [{agent, agent_name, avatar, result, cards, error}, ...],
        "cards": [合并去重后的卡片],
        "follow_ups": [快捷追问],
        "image_desc": 图片分析结果,
        "debug": {...},
        "coordinator_messages": [...]   # 供真流式输出
    }

原则：
1. 多 Agent 并行执行，失败隔离（单个失败不影响其他）。
2. Coordinator 真实调用 LLM 做整合，不是简单拼接。
3. 所有回答动态生成，没有任何固定模板。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from agent import BaseAgent, get_default_agents
from router import route, AGENT_KEY_MAP
from llm import LLMClient, LLMError, get_default_client
from memory import TravelContext
from tools import ToolManager


# Agent key → 中文名
AGENT_DISPLAY = {
    "food": "美食达人",
    "travel": "旅行规划师",
    "culture": "文化向导",
}

_COORDINATOR_SYSTEM = """你是《食游记》的金牌总导游（Coordinator）。
多位专家 Agent 分别回答了用户的问题，请把它们的回答**整合成一个连贯的最终回答**。

整合规则：
1. 【长度自适应】：
   - 简单问答（如「哪家好吃」「怎么去」）→ 控制在150字以内，直给重点。
   - 行程规划/Tour 请求（如「三日游」「怎么安排」「帮我规划」「行程」）→ 输出详细计划，不限字数，
     必须用 Markdown 表格展示以下内容：

     | 项目 | 内容 |
     |------|------|
     | 时间段 | 每天按小时列出（如 08:00 早餐 → 09:00-11:30 游览XX → 12:00-13:30 午餐） |
     | 交通细节 | 地铁几号线/打车/步行 + 时长 + 票价 |
     | 酒店推荐 | 区域 + 品牌 + 价格 + 理由 |
     | 费用估算 | 门票 + 餐饮 + 交通分项 + 每日小计 + 总预算 |
     | 景点详情 | 每个景点的门票价格、建议游览时长、最佳游览时间 |
2. 不是简单拼接：去掉重复内容，按用户问题的逻辑重新组织。
3. 多位专家信息冲突时，都保留并标注：信息仅供参考，出行前请核实。
4. 语言生动通俗、适合游客，不要学术腔，不要客套话。
5. 只依据专家提供的真实内容整合，不要自行编造专家没说的实时信息（营业/余票/房价等）。
6. 直接输出整合后的回答正文，不要加「以下是整合回答」之类的开场白。
7. 图片由系统自动配好展示，禁止说「无法提供/生成图片」「建议去某平台搜图」之类的话。
8. 【禁止使用 HTML 标签】只使用纯 Markdown 格式，禁止生成 <br>、<b>、<i> 等 HTML 标签。
   换行直接用两个空格加换行符，加粗用 **文字**，列表用 - 或数字。
9. 【Tour 整合】如果专家给出了行程/酒店/交通信息，整合成一份连贯的 Tour 计划：
   - 按天组织，标注时间段（如 09:00-11:30）
   - 交通方式具体化（如「地铁2号线，30分钟，4元」）
   - 酒店推荐具体化（如「住五一广场，全季酒店，约400元/晚」）
   - 估算每日费用和总预算
   - 用 Markdown 表格清晰展示（表格内不用 <br>，每行一个要点）
10. 【图片地点】禁止凭空猜测城市；用户已说明城市时，结合画面特征直接判断地标；
    用户没说城市且画面无法定位时，只描述画面并请用户告知城市。
"""

_FOLLOWUP_TEMPLATES = {
    "food": "🍜 {city}有什么必吃的老字号？",
    "travel": "🗺️ {city}两日游怎么安排？",
    "culture": "🏮 {city}有什么历史故事？",
}

_COMMON_FOLLOWUPS = ["🎒 帮我做个预算规划", "📷 有什么拍照打卡点？"]


class AIOrchestrator:
    """统一协调器。"""

    def __init__(self, agents: Optional[Dict[str, BaseAgent]] = None,
                 client: Optional[LLMClient] = None,
                 tool_manager: Optional[ToolManager] = None,
                 travel_context: Optional[TravelContext] = None) -> None:
        self.agents = agents or get_default_agents()
        self.client = client or get_default_client()
        self.tool_manager = tool_manager or ToolManager()
        for a in self.agents.values():
            if a.tool_manager is None:
                a.tool_manager = self.tool_manager
        self.travel_context = travel_context or TravelContext()

    # =================================================================
    # 第一步：路由 + 并行调用 Agent（不做最终整合）
    # =================================================================
    def prepare(self, user_text: str, image: Optional[bytes] = None,
                specified_agent: str = "",
                travel_context: Optional[TravelContext] = None,
                history: Optional[List[Dict]] = None) -> Dict:
        """路由 → 并行调用 Agent → 返回 prepared 结果（待 Coordinator 整合）。"""
        if travel_context is not None:
            self.travel_context = travel_context
        history = history or []

        # ---- 图片理解（真实 vision 调用）----
        image_desc = ""
        image_place_sure = False
        if image:
            image_desc = self.client.chat_with_image(
                user_text or "这是我在旅行中拍摄的图片，请描述内容（地点/美食/建筑）。",
                image,
                system_prompt="你是旅行图片分析助手。只描述图片中肉眼可见的内容："
                              "物体/建筑外观、颜色、造型、招牌文字、自然环境（80字内）。"
                              "关于城市和具体地标：除非你能清楚看到地名文字，"
                              "否则一律不要猜测城市名或地标名，直接写『地点无法从画面确定』。"
                              "严禁编造城市和地标。")
            image_place_sure = ("无法" not in image_desc and "不能确定" not in image_desc)

        combined_text = user_text
        if image_desc:
            if image_place_sure:
                combined_text = f"{user_text}\n[用户上传了图片，图片内容：{image_desc}]"
            else:
                combined_text = (f"{user_text}\n[用户上传了图片，画面内容：{image_desc}。"
                                 "重要：图片的拍摄城市无法仅从画面确定，禁止凭空猜测城市。"
                                 "若用户已说明城市，请结合该城市与画面特征判断具体地标，"
                                 "特征吻合度高时直接指出地标（如红色螺旋雕塑+青岛→五四广场五月的风）；"
                                 "若用户没说城市或仍无法判断，只描述画面外观并请用户告知城市。]")

        # ---- 意图路由 ----
        route_result = route(
            combined_text,
            specified_agent=specified_agent,
            context_summary=self.travel_context.to_summary(),
            memory_messages=history,
            llm_client=self.client,
        )

        # ---- 上下文槽位更新 ----
        extracted = route_result.get("extracted", {})
        if extracted:
            self.travel_context.update_from_extraction(extracted)

        # ---- 需要澄清 → 不调用 Agent ----
        if route_result.get("needs_clarification"):
            return {
                "type": "clarify",
                "trigger_mode": route_result["trigger_mode"],
                "agents": [],
                "agent_replies": [],
                "cards": [],
                "clarification_question": route_result.get("clarification_question")
                                          or "能再告诉我一些细节吗？比如目的地、天数或预算？",
                "image_desc": image_desc,
                "debug": {"route_reason": route_result.get("reason", ""),
                          "intent": route_result.get("intent", ""),
                          "extracted": extracted, "tools_used": []},
                "coordinator_messages": [],
            }

        # ---- 并行调用 Agent（失败隔离）----
        agent_keys = route_result.get("agent_keys", [])
        agent_replies = self._call_agents_parallel(agent_keys, combined_text, history)

        # ---- 合并去重卡片 ----
        all_cards = []
        seen_titles = set()
        for r in agent_replies:
            for card in r.get("cards", []):
                t = card.get("title", "")
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    all_cards.append(card)

        tools_used = sorted({t for r in agent_replies for t in r.get("tools_used", [])})

        # ---- Coordinator 消息（真实整合，稍后流式执行）----
        valid = [r for r in agent_replies if not r.get("error") and r.get("result")]
        errors = [r for r in agent_replies if r.get("error")]
        results_text = "\n\n".join(
            f"【{r.get('agent_name')}】的回答：\n{r.get('result', '')}"
            for r in valid) or "（无专家回答）"
        coord_messages = [
            {"role": "system", "content": _COORDINATOR_SYSTEM},
            *history[-8:],
            {"role": "user",
             "content": f"用户问题：{user_text}\n\n专家回答：\n{results_text}\n\n"
                        f"请整合为最终回答。"},
        ]

        city = self._extract_city(user_text) or (self.travel_context.destination or "目的地")
        return {
            "type": "final",
            "trigger_mode": route_result["trigger_mode"],
            "agents": agent_keys,
            "agent_replies": agent_replies,
            "cards": all_cards,
            "follow_ups": self._follow_ups(agent_keys, city),
            "image_desc": image_desc,
            "errors": [{"agent": r["agent"], "message": r["error"]} for r in errors],
            "debug": {"route_reason": route_result.get("reason", ""),
                      "intent": route_result.get("intent", ""),
                      "extracted": extracted, "tools_used": tools_used},
            "coordinator_messages": coord_messages,
        }

    # =================================================================
    # 第二步：Coordinator 整合（真流式）
    # =================================================================
    def stream_final(self, prepared: Dict, temperature: float = 0.7):
        """流式执行 Coordinator 整合，逐段 yield 文本。"""
        msgs = prepared.get("coordinator_messages") or []
        if not msgs:
            yield "你好！我是游伴星球的金牌导游 🧳 想去哪里玩，问我就好～"
            return
        gen = self.client.chat(msgs, stream=True, temperature=temperature)
        for chunk in gen:
            if chunk:
                yield chunk

    def finalize(self, prepared: Dict, full_answer: str) -> Dict:
        """把流式输出累积的完整答案并入 prepared，返回最终 result。"""
        prepared["answer"] = full_answer
        prepared.pop("coordinator_messages", None)
        return prepared

    def handle(self, user_text: str, image: Optional[bytes] = None,
               specified_agent: str = "",
               travel_context: Optional[TravelContext] = None,
               history: Optional[List[Dict]] = None) -> Dict:
        """非流式一次性完成（兼容旧调用方式）。"""
        prepared = self.prepare(user_text, image, specified_agent,
                                travel_context, history)
        if prepared["type"] != "final":
            return prepared
        answer = "".join(self.stream_final(prepared))
        return self.finalize(prepared, answer)

    # =================================================================
    # 内部：并行调用 Agent
    # =================================================================
    def _call_agents_parallel(self, agent_keys: List[str], user_text: str,
                              history: List[Dict]) -> List[Dict]:
        context = {"travel_summary": self.travel_context.to_summary()}
        results: Dict[str, Dict] = {}

        def _run(key: str) -> Dict:
            agent = self.agents.get(key)
            if not agent:
                return {"agent": key, "agent_name": AGENT_DISPLAY.get(key, key),
                        "avatar": "⚠️", "input": user_text, "tools_used": [],
                        "cards": [], "result": "",
                        "error": f"未知 Agent：{key}"}
            try:
                return agent.respond(user_text, context=context, history=history)
            except LLMError as e:
                return {"agent": key, "agent_name": AGENT_DISPLAY.get(key, key),
                        "avatar": "⚠️", "input": user_text, "tools_used": [],
                        "cards": [], "result": "", "error": e.friendly}
            except Exception as e:
                return {"agent": key, "agent_name": AGENT_DISPLAY.get(key, key),
                        "avatar": "⚠️", "input": user_text, "tools_used": [],
                        "cards": [], "result": "",
                        "error": f"AI 服务暂时无法连接，请稍后再试。（{type(e).__name__}）"}

        if not agent_keys:
            return []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(_run, k): k for k in agent_keys}
            for fut in as_completed(futures):
                results[futures[fut]] = fut.result()

        return [results[k] for k in agent_keys if k in results]

    # =================================================================
    # 内部：辅助
    # =================================================================
    @staticmethod
    def _extract_city(text: str) -> str:
        for city in ["北京", "上海", "广州", "深圳", "成都", "重庆", "杭州",
                     "西安", "南京", "武汉", "苏州", "厦门", "青岛", "昆明",
                     "大理", "桂林", "三亚", "长沙", "天津", "哈尔滨"]:
            if city in (text or ""):
                return city
        return ""

    def _follow_ups(self, agent_keys: List[str], city: str) -> List[str]:
        opts = [_FOLLOWUP_TEMPLATES[k].format(city=city)
                for k in ("food", "travel", "culture") if k in agent_keys]
        opts += _COMMON_FOLLOWUPS[:2] if len(opts) < 3 else _COMMON_FOLLOWUPS[:1]
        return opts[:4]
