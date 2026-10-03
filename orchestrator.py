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

import re
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
10. 【图片地点】系统已通过地标库核对的，直接围绕该城市地标作答，开头自然点出城市与地标名；
    未核对出的，禁止凭空猜测城市，只描述画面并请用户告知城市。
11. 【多日行程必须完整】多日行程必须逐天输出「第1天」一直到「第N天」，
    一天都不能少、不能合并、严禁「后面几天以此类推/同理」之类省略。
    为保证完整，每条安排用短句直给，不写客套和重复铺垫；最后给出总预算。
"""

_FOLLOWUP_TEMPLATES = {
    "food": "🍜 {city}有什么必吃的老字号？",
    "travel": "🗺️ {city}两日游怎么安排？",
    "culture": "🏮 {city}有什么历史故事？",
}

# 中国热门城市标志性地标库（城市, 地标, 视觉特征）——
# 视觉小模型直接回忆地名会乱猜，但「画面 vs 候选」比对很准，
# 故上传图片后让 vision 模型只做核对选择题。
_LANDMARK_CANDIDATES = [
    ("青岛", "五四广场「五月的风」", "鲜红色螺旋上升的火炬/旋风造型巨型钢结构雕塑，立于广场草坪，背景现代高楼"),
    ("青岛", "栈桥回澜阁", "伸入海中的长栈桥尽头有一座中式双层八角凉亭，周围海面"),
    ("北京", "天安门", "红墙黄瓦城楼，正中挂毛泽东画像，门前金水桥与广场"),
    ("北京", "故宫角楼", "临水的九梁十八柱复杂木结构角楼，黄瓦屋顶"),
    ("北京", "鸟巢", "灰色钢条交错编织成的椭圆形鸟巢状体育场"),
    ("北京", "水立方", "蓝色半透明水泡肌理的方形游泳馆"),
    ("北京", "天坛祈年殿", "蓝色三重圆攒尖顶的圆形木构大殿，白石基座"),
    ("北京", "八达岭长城", "沿山脊蜿蜒的灰色砖砌长城与烽火台"),
    ("上海", "东方明珠", "大小紫红圆球串成的高塔，立于黄浦江边"),
    ("上海", "外滩", "江边一排欧式老建筑与对岸陆家嘴天际线"),
    ("上海", "上海中心大厦", "扭转上升的超高层玻璃摩天楼"),
    ("广州", "广州塔（小蛮腰）", "中部收窄的网状钢结构细腰高塔"),
    ("广州", "五羊石像", "五只山羊组成的灰色石雕"),
    ("深圳", "拓荒牛", "奋力拉犁的铜色公牛雕塑"),
    ("成都", "IFS爬墙熊猫", "高楼外墙上趴着一只巨大的熊猫雕塑"),
    ("重庆", "解放碑", "城市商圈中心的高大方形钟塔纪念碑"),
    ("重庆", "洪崖洞", "依山而建的层层叠叠吊脚楼建筑群，夜景暖黄灯光"),
    ("西安", "大雁塔", "七层方形灰色砖塔，唐代风格"),
    ("西安", "钟楼", "方形基座上的三重檐木构城楼，位于十字路口中心"),
    ("西安", "兵马俑", "土坑中成排的真人大小陶土士兵俑"),
    ("杭州", "三潭印月", "湖面上三座葫芦形小石塔"),
    ("杭州", "雷峰塔", "五层八面的金色塔顶楼阁，立于湖边山上"),
    ("南京", "中山陵", "长长的石阶通向蓝瓦白墙牌坊式陵寝"),
    ("武汉", "黄鹤楼", "五层黄色琉璃瓦飞檐楼阁，立于蛇山"),
    ("苏州", "东方之门（大秋裤）", "门形连体双塔，中间一条弧线开口的玻璃超高层"),
    ("长沙", "橘子洲青年毛泽东雕像", "巨大的青年毛泽东肩部以上石像，面向湘江"),
    ("三亚", "南山海上观音", "海边高约百米的白色三面观音立像，立于莲花台"),
    ("拉萨", "布达拉宫", "红白色相间、依山垒砌的巨型宫殿群"),
    ("澳门", "大三巴牌坊", "石头雕刻的西式教堂前壁遗迹，前有长台阶"),
    ("哈尔滨", "圣索菲亚大教堂", "绿色洋葱头穹顶的红砖俄式教堂"),
]


def _recognize_landmark(client, image: bytes, user_text: str):
    """让 vision 模型把画面与地标库做核对选择题。

    返回 (city, landmark, visual_desc)；未命中返回 (None, None, 画面描述)。"""
    lines = [f"{i + 1}. {c}·{n}（{hint}）"
             for i, (c, n, hint) in enumerate(_LANDMARK_CANDIDATES)]
    none_idx = len(_LANDMARK_CANDIDATES) + 1
    lines.append(f"{none_idx}. 都不是 / 无法确定")
    prompt = (
        "这是游客在中国旅行时拍摄的照片。请完成两件事：\n"
        "任务一：对照下面的地标候选，选出与画面主体的造型、颜色、环境"
        "明确吻合的一个。只有特征确实吻合才选；拿不准一律选最后一项，严禁猜测。\n"
        + "\n".join(lines) + "\n"
        "任务二：用一句中文客观描述画面（60字内，说明主体是建筑/雕塑/美食/自然中的哪类，"
        "以及颜色、造型、环境）。\n"
        "严格按此格式输出，不要输出其他内容：\n"
        "编号：<数字>\n描述：<一句话画面描述>"
    )
    if user_text:
        prompt += f"\n（游客附言：{user_text}）"
    raw = client.chat_with_image(
        prompt, image,
        system_prompt="你是中国地标核对员，只把画面与候选逐一比对。"
                      "必须且只能按「编号：数字」「描述：文字」两行格式输出。")
    import re
    m_no = re.search(r"编号[：:]\s*(\d+)", raw)
    m_desc = re.search(r"描述[：:]\s*(.+)", raw)
    desc = m_desc.group(1).strip() if m_desc else raw.strip()[:120]
    if m_no:
        idx = int(m_no.group(1))
        if 1 <= idx <= len(_LANDMARK_CANDIDATES):
            city, name, _ = _LANDMARK_CANDIDATES[idx - 1]
            return city, name, desc
    return None, None, desc


_COMMON_FOLLOWUPS = ["🎒 帮我做个预算规划", "📷 有什么拍照打卡点？"]

# 多日行程识别：从「3天」「三日游」「七天+」提取天数（支持阿拉伯/中文数字）
_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_TOUR_DAYS_RE = re.compile(r"(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*(?:天|日)")
_TOUR_WEEK_RE = re.compile(r"一周|一个星期|一個星期|一个禮拜|一個禮拜")
_TOUR_KW_RE = re.compile(
    r"行程|旅行计划|旅游计划|tour|攻略|怎么安排|怎么玩|几日游|日游|日程|规划")


def _cn_to_int(s: str) -> int:
    """把「3」「三」「十二」「十四」等转成数字；非数字返回 0。"""
    if s.isdigit():
        return int(s)
    if s in _CN_NUM:
        return _CN_NUM[s]
    if "十" in s:
        left, _, right = s.partition("十")
        tens = _CN_NUM.get(left, 1) if left else 1
        ones = _CN_NUM.get(right, 0) if right else 0
        return tens * 10 + ones
    return 0


def _detect_tour_days(text: str) -> int:
    """识别多日行程请求并返回天数（2~14），非行程请求返回 0。"""
    t = text or ""
    m = _TOUR_DAYS_RE.search(t)
    if m:
        days = _cn_to_int(m.group(1))
    elif _TOUR_WEEK_RE.search(t):
        days = 7
    else:
        days = 0
    if days <= 1:
        return 0
    if not _TOUR_KW_RE.search(t):
        return 0
    return min(14, days)


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

        # ---- 图片理解：视觉核对地标库（一次 vision 调用，同时完成识别+描述）----
        image_desc = ""
        if image:
            lm_city, lm_name, visual_desc = _recognize_landmark(
                self.client, image, user_text)
            if lm_city:
                image_desc = (f"经画面与地标库核对，该地标是{lm_city}·{lm_name}。"
                              f"画面：{visual_desc}")
            else:
                image_desc = f"地点无法从画面确定。画面：{visual_desc}"

        combined_text = user_text
        if image_desc:
            if image_desc.startswith("经画面与地标库核对"):
                combined_text = (f"{user_text}\n[用户上传了图片，{image_desc}。"
                                 "请直接围绕该城市和地标作答（介绍/历史/玩法/周边等），"
                                 "不要再反问用户在哪个城市。]")
            else:
                combined_text = (f"{user_text}\n[用户上传了图片，{image_desc}。"
                                 "重要：图片的拍摄城市无法仅从画面确定，禁止凭空猜测城市。"
                                 "若用户已说明城市，请结合该城市与画面特征判断具体地标；"
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

        # ---- 多日行程识别（决定输出长度配额 + 完整性要求）----
        tour_days = _detect_tour_days(combined_text)

        # ---- 并行调用 Agent（失败隔离）----
        agent_keys = route_result.get("agent_keys", [])
        # 行程请求时专家只提供精炼素材（配额留给总导游写完整逐日计划）
        agent_max_tokens = 800 if tour_days else None
        agent_replies = self._call_agents_parallel(
            agent_keys, combined_text, history,
            max_tokens=agent_max_tokens)

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
        if tour_days:
            coord_messages.append({
                "role": "system",
                "content": f"【硬性完整性要求】本次必须输出完整的 {tour_days} 天行程："
                           f"从「第1天」逐天写到「第{tour_days}天」，一天都不能少、不能合并，"
                           "严禁用「以此类推/后面同理」省略任何一天。"
                           "每天都要有时间段安排、交通与餐饮；最后用表格给出总预算。",
            })

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
            "tour_days": tour_days,
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
        # 多日行程按天数扩容输出，避免计划写到一半被截断
        days = int(prepared.get("tour_days") or 0)
        max_tokens = min(7000, 1700 + days * 1100) if days else None
        gen = self.client.chat(msgs, stream=True, temperature=temperature,
                               max_tokens=max_tokens)
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
                              history: List[Dict],
                              max_tokens: Optional[int] = None) -> List[Dict]:
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
                return agent.respond(user_text, context=context, history=history,
                                     max_tokens=max_tokens)
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
