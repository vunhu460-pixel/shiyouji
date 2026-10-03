"""《食游记》—— 多智能体真实 AI 旅游助手（Streamlit）。

3 个真实 AI Agent：🍜美食达人 / 🗺️旅行规划师 / 🏮文化向导（全部真实调用大模型 API）
两种触发：🔵 指定回答（Agent Selector / @专家语法） + 🟢 自适应回答（意图路由）
多模态：文本输入 + 图片上传（真实 vision 识别） + 语音录入（浏览器真实 Speech-to-Text）
多轮记忆：ConversationMemory 会话上下文 + TravelContext 偏好槽位
流式输出：Coordinator 真流式生成
无 Mock：未配置 AI_API_KEY 时明确报错提示，绝不返回假数据

启动：
    python -m streamlit run app.py --server.port 8766 --server.address 127.0.0.1
"""
from __future__ import annotations

import io
import re
import json
import base64
from typing import Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as components

from theme import (
    GLOBAL_CSS, BANNER_HTML,
    AGENT_META, trigger_badge_html, agent_chips_html,
    guide_card_html, img_data_url,
)
from agent import get_default_agents, CITIES, get_city_guide
from orchestrator import AIOrchestrator, AGENT_DISPLAY
from router import route, parse_mention
from llm import LLMError
from memory import TravelContext, ConversationMemory


# =====================================================================
# 一、页面配置 & 全局样式
# =====================================================================
st.set_page_config(page_title="食游记 · 多智能体金牌导游", page_icon="🍲",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.markdown(BANNER_HTML, unsafe_allow_html=True)

# =====================================================================
# JS 桥接：注入浏览器原生 Web Speech API（不依赖 gTTS / 网络）
#   window.sySpeak(btn, text)  —— 朗读文本（中文）
#   window.syMic(btn)          —— 语音识别，结果填入 chat_input
#   🎤 按钮注入到聊天输入框内部右侧（像 ChatGPT 一体化输入栏）
# =====================================================================
_WEB_SPEECH_BRIDGE = """
<div id="sy-mic-host"></div>
<script>
(function(){
  // P 指向 streamlit 主窗口（按钮 onclick 在主窗口执行，window === P）
  var P = window.parent ? window.parent : window;
  try{
    // —— 朗读 ——
    P.sySpeak = function(btn, text){
      if(!('speechSynthesis' in P)){ alert('浏览器不支持语音朗读，请用 Chrome/Edge'); return; }
      P.speechSynthesis.cancel();
      var u = new P.SpeechSynthesisUtterance(text);
      u.lang = 'zh-CN'; u.rate = 1.0; u.pitch = 1.0;
      if(btn){ btn.classList.add('playing'); u.onend=function(){btn.classList.remove('playing');}; u.onerror=function(){btn.classList.remove('playing');}; }
      P.speechSynthesis.speak(u);
    };
    // —— 语音识别 → 填入 chat_input ——
    P.syMic = function(btn){
      var SR = P.SpeechRecognition || P.webkitSpeechRecognition;
      if(!SR){ alert('浏览器不支持语音识别，请用 Chrome/Edge 桌面版'); return; }
      var r = new SR();
      r.lang='zh-CN'; r.interimResults=false; r.maxAlternatives=1; r.continuous=false;
      if(btn){ btn.classList.add('listening'); }
      r.onresult=function(e){
        var text = e.results[0][0].transcript;
        var ta = P.document.querySelector('[data-testid="stChatInputTextArea"] textarea')
              || P.document.querySelector('div[data-testid="stChatInput"] textarea')
              || P.document.querySelector('section[data-testid="stChatInput"] textarea')
              || P.document.querySelector('textarea[placeholder]');
        if(ta){
          var nativeSet = Object.getOwnPropertyDescriptor(P.HTMLTextAreaElement.prototype,'value').set;
          nativeSet.call(ta, text);
          ta.dispatchEvent(new Event('input',{bubbles:true}));
          ta.dispatchEvent(new Event('change',{bubbles:true}));
          ta.focus();
        } else {
          prompt('识别结果（复制后粘贴到输入框发送）：', text);
        }
      };
      r.onerror=function(e){ alert('语音识别出错：'+(e.error||'未知错误')+'。请用 Chrome/Edge，并允许麦克风权限。'); };
      r.onend=function(){ if(btn){ btn.classList.remove('listening'); } };
      try{ r.start(); }catch(err){ alert('启动失败：'+err.message); }
    };
    // —— 把 📎（传图）和 🎤（语音）按钮注入聊天输入框内部（像 ChatGPT），重渲染后自动补回 ——
    function injectButtons(){
      var doc = P.document;
      if(!doc) return;
      var box = doc.querySelector('[data-testid="stChatInput"]');
      if(!box) return;
      var cs = P.getComputedStyle(box);
      if(cs.position === 'static'){ box.style.position = 'relative'; }

      // 🎤 语音按钮（右侧，发送键左边）
      var mic = doc.getElementById('sy-mic-inbox');
      if(!(mic && box.contains(mic))){
        if(mic) mic.remove();
        mic = doc.createElement('div');
        mic.id = 'sy-mic-inbox';
        mic.className = 'sy-mic-inbox';
        mic.innerHTML = '🎤';
        mic.title = '点击说话（语音输入，需 Chrome/Edge）';
        mic.onclick = function(){ P.syMic(mic); };
        box.appendChild(mic);
      }

      // 📎 图片按钮（🎤 左边）——点击唤起隐藏的文件选择器
      var clip = doc.getElementById('sy-clip-inbox');
      if(!(clip && box.contains(clip))){
        if(clip) clip.remove();
        clip = doc.createElement('div');
        clip.id = 'sy-clip-inbox';
        clip.className = 'sy-clip-inbox';
        clip.innerHTML = '📎';
        clip.title = '上传图片（景区/美食照片，导游会识别）';
        clip.onclick = function(){
          var fi = doc.querySelector('[data-testid="stFileUploader"] input[type="file"]');
          if(fi){ fi.click(); }
          else { alert('没找到上传组件，请展开输入框上方的「📎 添加图片」手动上传'); }
        };
        box.appendChild(clip);
      }

      // 🖼️ 已选图片缩略图：显示在输入框内左侧（像 ChatGPT 附件）
      var fi2 = doc.querySelector('[data-testid="stFileUploader"] input[type="file"]');
      var chip = doc.getElementById('sy-img-chip');
      var ta2 = box.querySelector('textarea');
      if(fi2 && fi2.files && fi2.files.length){
        if(!chip){
          chip = doc.createElement('img');
          chip.id = 'sy-img-chip';
          chip.className = 'sy-img-chip';
          chip.title = '已选图片，发送提问即识别';
          box.appendChild(chip);
          var rd = new FileReader();
          rd.onload = function(e){ var c = doc.getElementById('sy-img-chip'); if(c) c.src = e.target.result; };
          rd.readAsDataURL(fi2.files[0]);
          if(ta2) ta2.style.paddingLeft = '56px';
        }
      } else if(chip){
        chip.remove();
        if(ta2) ta2.style.paddingLeft = '';
      }
    }
    injectButtons();
    // 桥接 iframe 每次 rerun 都被销毁重建，旧定时器随之失效，
    // 不能用 P.__syMicTimer 判重（残留旧值），每次直接新建即可
    setInterval(injectButtons, 800);
  }catch(e){ /* sandbox 阻止跨窗口访问时静默 */ console.warn('sy bridge failed', e); }
})();
</script>
"""
components.html(_WEB_SPEECH_BRIDGE, height=0)


# =====================================================================
# 二、会话状态（多会话管理，像 ChatGPT/豆包侧栏历史列表）
# =====================================================================
def _new_conversation() -> Dict:
    """创建一个新会话对象（含独立的多轮对话记忆）。"""
    import time as _time
    return {
        "id": f"conv_{int(_time.time()*1000)}",
        "title": "新对话",
        "messages": [],
        "memory": ConversationMemory(),   # 多轮上下文（system/user/assistant）
        "debug_logs": [],
        "round": 0,
        "created_at": _time.time(),
    }


def _init_state() -> None:
    if "agents" not in st.session_state:
        st.session_state.agents = get_default_agents()
    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = AIOrchestrator(
            agents=st.session_state.agents)
    if "travel_context" not in st.session_state:
        st.session_state.travel_context = TravelContext()
    if "conversations" not in st.session_state:
        st.session_state.conversations: List[Dict] = [_new_conversation()]
    if "current_conv_id" not in st.session_state:
        st.session_state.current_conv_id = st.session_state.conversations[0]["id"]
    if "specified_agent" not in st.session_state:
        st.session_state.specified_agent: str = ""  # 锁定的 Agent
    if "page" not in st.session_state:
        st.session_state.page: str = "🌟 中国魅力"  # 当前页面


def _current_conv() -> Dict:
    """取当前会话对象。"""
    cid = st.session_state.current_conv_id
    for c in st.session_state.conversations:
        if c["id"] == cid:
            return c
    # 找不到就用第一个
    return st.session_state.conversations[0]


def _switch_conv(conv_id: str) -> None:
    st.session_state.current_conv_id = conv_id
    st.rerun()


def _create_new_conv() -> None:
    c = _new_conversation()
    st.session_state.conversations.insert(0, c)  # 新会话放最前
    st.session_state.current_conv_id = c["id"]
    st.rerun()


def _delete_conv(conv_id: str) -> None:
    st.session_state.conversations = [c for c in st.session_state.conversations if c["id"] != conv_id]
    if not st.session_state.conversations:
        st.session_state.conversations = [_new_conversation()]
    st.session_state.current_conv_id = st.session_state.conversations[0]["id"]
    st.rerun()


_init_state()


# =====================================================================
# 三、渲染辅助函数（前置定义，避免 NameError）
# =====================================================================
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_HALF_BR_RE = re.compile(r"^<(?:b(?:r(?:\s{0,3}/?>?)?)?)?$", re.IGNORECASE)


def _strip_br(text: str) -> str:
    """把 AI 可能生成的各种 <br> 标签统一换成真正的换行（含 <br/>、<BR> 等）。"""
    if not text:
        return text or ""
    return _BR_RE.sub("\n", text)


def _br_safe_stream(chunks):
    """流式回答清洗：边生成边把 <br> 换成换行。

    <br> 可能被切分到两个 token 里（如 '<b' + 'r>'），
    故把疑似半截标签的末尾留在缓冲区等下一块。"""
    buf = ""
    for ch in chunks:
        if not ch:
            continue
        buf += ch
        out: List[str] = []
        while True:
            m = _BR_RE.search(buf)
            if m:
                out.append(buf[:m.start()])
                out.append("\n")
                buf = buf[m.end():]
                continue
            lt = buf.rfind("<")
            tail_len = len(buf) - lt
            if lt != -1 and tail_len <= 10 and _HALF_BR_RE.match(buf[lt:]):
                out.append(buf[:lt])
                buf = buf[lt:]
            else:
                out.append(buf)
                buf = ""
            break
        piece = "".join(out)
        if piece:
            yield piece
    if buf:
        yield _strip_br(buf)


def _render_tts_button(text: str, key_suffix: str,
                        auto_play: bool = False) -> None:
    """🔊 语音输出：浏览器原生 Web Speech API SpeechSynthesis 朗读。
    不依赖 gTTS / 网络，直接前端朗读。auto_play=True 时自动尝试朗读。"""
    if not text.strip():
        return
    # 文本清理（避免引号/换行破坏 JS 字符串）
    safe_text = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
    # 手动模式：注入 🔊 朗读按钮，onclick 调用桥接函数 sySpeak
    st.markdown(
        f"""<button class="sy-speak-btn" onclick="window.sySpeak && window.sySpeak(this, '{safe_text}')">
            🔊 听导游朗读回答
        </button>""",
        unsafe_allow_html=True,
    )
    # 自动朗读模式：注入隐藏 script 尝试自动触发（首次可能被浏览器策略阻止）
    if auto_play:
        st.components.v1.html(
            f"<script>try{{window.parent.sySpeak(null,'{safe_text}');}}catch(e){{}}</script>",
            height=0,
        )


@st.cache_data(ttl=3600, show_spinner=False)
def _city_guide_cached(city: str) -> Dict:
    """城市简介缓存（真实 Wikipedia 数据，1 小时缓存）。"""
    return get_city_guide(city)


def _render_city_showcase() -> None:
    """主页城市速览：Wikipedia 真实简介 + 点击向 AI 导游追问。"""
    st.markdown("## 🗺️ 城市速览")
    st.caption("城市简介来自维基百科实时数据；点击下方按钮，对应专家 AI 为你详细讲解 👇")

    tabs = st.tabs([f"{c}" for c in CITIES])
    for tab, city in zip(tabs, CITIES):
        with tab:
            guide = _city_guide_cached(city)
            intro = (guide or {}).get("intro", "")
            if intro:
                st.markdown(f"> {intro}")
            else:
                st.caption("暂时没取到该城市的简介（网络原因）。"
                           "可直接点击下方按钮，让 AI 导游为你介绍。")
            secs = (guide or {}).get("sections", [])
            cols = st.columns(max(1, len(secs)))
            for col, sec in zip(cols, secs):
                if col.button(sec.get("title", "问 AI"),
                              key=f"cityq_{city}_{sec.get('type')}",
                              use_container_width=True):
                    st.session_state["quick_question"] = sec.get("question", "")
                    st.session_state.page = "💬 AI导游问答"
                    st.rerun()


def _render_agent_cards() -> None:
    """主页 3 个 Agent 选择卡（点选锁定指定触发）。"""
    st.markdown("## 🧭 选择你的专属导游")
    st.caption("点一个 Agent 锁定它（指定回答），或都不选让系统自适应路由")

    agents = [("美食达人", "🍜"), ("旅行规划师", "🗺️"), ("文化向导", "🏮")]
    cols = st.columns(3)
    for col, (name, avatar) in zip(cols, agents):
        locked = st.session_state.specified_agent == name
        with col:
            btn_label = f"{avatar} {name}{' 🔒' if locked else ''}"
            if st.button(btn_label, key=f"card_{name}", use_container_width=True):
                st.session_state.specified_agent = "" if locked else name
                st.rerun()


def _render_quick_chips() -> None:
    """豆包式快捷话题芯片条（点击直接发起问答，覆盖中国各地不同领域）。"""
    st.markdown("##### 💡 快捷话题（点一下就问）")
    chips = [
        "🗺️ 成都必去景区", "🍜 成都火锅推荐", "🏮 成都文化故事",
        "🗺️ 杭州西湖怎么玩", "🍜 杭州龙井虾仁", "🏮 杭州白蛇传说",
        "🗺️ 西安兵马俑", "🍜 西安羊肉泡馍", "🏮 西安盛唐文化",
        "🗺️ 北京故宫", "🍜 北京烤鸭", "🏮 北京胡同故事",
        "🧳 帮我规划3天成都行程", "🧳 预算1000去杭州怎么玩",
        "🗺️ 上海外滩", "🍜 长沙臭豆腐", "🏮 南京六朝古都",
        "🗺️ 重庆洪崖洞", "🍜 武汉热干面", "🏮 洛阳牡丹传说",
    ]
    # 每行 6 个芯片，用全局唯一索引作 key 避免 emoji 重复
    for i in range(0, len(chips), 6):
        row = chips[i:i + 6]
        cols = st.columns(len(row))
        for col, j, chip in zip(cols, range(len(row)), row):
            if col.button(chip, key=f"chip_{i + j}", use_container_width=True):
                _handle_user_input(chip, input_type="文本")


def _user_wants_images(result: Dict, user_text: str = "") -> bool:
    """判断用户是否主动要求看图片。只有明确要求时才渲染卡片配图。"""
    img_kw = ["图片", "照片", "看图", "实景", "看看图", "有图", "想看图",
              "发图", "配图", "美图", "风景照", "长什么样", "什么样子"]
    # 本轮用户输入中明确提到图片
    if user_text and any(k in user_text for k in img_kw):
        return True
    # 或 result 中标记了要图片（由 orchestrator 解析用户意图时设置）
    if result.get("show_images"):
        return True
    return False


def _render_guide_result(result: Dict, round_num: int,
                         answer_stream=None, user_text: str = "") -> Optional[str]:
    """渲染协调器结果：徽章 + Agent 芯片 + 流式回答 + 卡片 + 快捷追问。

    answer_stream 不为空时走真流式渲染并返回完整文本；否则直接渲染已有 answer。
    """
    trigger_mode = result.get("trigger_mode", "自适应")
    agent_keys = result.get("agents", [])
    agent_names = [AGENT_DISPLAY.get(k, k) for k in agent_keys]
    all_cards = result.get("cards", [])
    show_images = _user_wants_images(result, user_text)

    full_answer = result.get("answer", "")
    with st.chat_message("assistant", avatar="🧳"):
        st.markdown(trigger_badge_html(trigger_mode), unsafe_allow_html=True)
        if agent_names:
            st.markdown(agent_chips_html(agent_names), unsafe_allow_html=True)

        if answer_stream is not None:
            with st.spinner("🤖 专家们正在思考并整合回答…"):
                full_answer = st.write_stream(
                    _br_safe_stream(answer_stream)) or ""
        elif full_answer:
            # 清理 AI 可能生成的 <br> 标签，转换为换行
            full_answer = _strip_br(full_answer)
            st.markdown(full_answer)

        # 专家生成的动态卡片（带配图/故事/贴士）
        if all_cards:
            st.markdown("---")
            city = _extract_city_from_result(result)
            for i, card in enumerate(all_cards):
                # 只有用户明确要求看图片时才渲染配图
                if show_images:
                    img_b64 = img_data_url(card.get("image_keywords") or f"{city}{card.get('title','')}")
                    if img_b64:
                        st.image(base64.b64decode(img_b64.split(",", 1)[1]),
                                 use_container_width=True)
                _render_guide_card(card, index=i)

        # 操作按钮
        btn_cols = st.columns([1, 1, 6])
        if btn_cols[0].button("📋 复制", key=f"copy_{round_num}"):
            st.session_state[f"clipboard_{round_num}"] = full_answer
            st.toast("已复制到剪贴板")
        if btn_cols[1].button("🔄 重新生成", key=f"regen_{round_num}"):
            _regenerate(round_num)

    # 快捷追问选项
    follow_ups = result.get("follow_ups", [])
    if follow_ups:
        st.markdown("**💡 还想问：**")
        fcols = st.columns(len(follow_ups))
        for col, opt in zip(fcols, follow_ups):
            with col:
                if st.button(opt, key=f"fu_{round_num}_{opt[:6]}",
                             use_container_width=True):
                    st.session_state["quick_question"] = opt
                    st.rerun()

    # 各 Agent 的独立回答（可展开查看分工）
    agent_replies = result.get("agent_replies", [])
    if agent_replies:
        with st.expander(f"👥 查看 {len(agent_replies)} 位专家的分工回答",
                         expanded=bool(result.get("errors"))):
            for reply in agent_replies:
                an = reply.get("agent_name", "")
                av = reply.get("avatar", AGENT_META.get(an, {}).get("avatar", "🤖"))
                err = reply.get("error")
                st.markdown(f"**{av} {an}**")
                if err:
                    st.markdown(f"⚠️ {err}")
                else:
                    r = reply.get("result", "")
                    if r:
                        st.markdown(_strip_br(r[:500]) + ("…" if len(r) > 500 else ""))
                tools = reply.get("tools_used", [])
                if tools:
                    st.caption(f"🛠️ 调用真实工具：{', '.join(tools)}")
                st.markdown("---")

    # 语音朗读
    _render_tts_button(full_answer, f"round_{round_num}",
                       auto_play=st.session_state.get("auto_voice", False))
    return full_answer


def _render_guide_card(card: dict, index: int = 0) -> None:
    """用 Streamlit 原生组件渲染专家卡片（图片由调用方单独用 st.image 处理）。"""
    title = card.get("title", "")
    intro = card.get("intro", "")
    story = card.get("story", "")
    tips = card.get("tips", "")
    with st.container(border=True):
        if title:
            st.markdown(f"**{index + 1}. {title}**")
        if intro:
            st.caption(intro)
        if story:
            st.markdown(f"📖 {story}")
        if tips:
            st.markdown(f"💡 {tips}")


def _extract_city_from_result(result: Dict) -> str:
    """从结果中提取城市名（用于卡片图片 prompt）。"""
    for reply in result.get("agent_replies", []):
        inp = reply.get("input", "")
        for city in CITIES:
            if city in inp:
                return city
    return ""


def _extract_city(text: str) -> str:
    """从用户输入提取看图主题。保留具体景点名，如「北京故宫图片」→「北京故宫」；
    只有光秃秃的「北京图片」才退化为城市名「北京」。"""
    import re
    t = re.sub(r"(图片|照片|看图|配图|发图|有图|想看一下|看看图|给我|我想|的|实景|美图|风景|一下|看看|来几张|几张|景点|景区)", "", text).strip()
    return t[:12]


def _render_image_gallery(city: str, imgs_b64: list) -> None:
    """渲染图片集锦（imgs_b64 为纯 base64 字符串列表），两行三列网格。"""
    st.markdown(f"📸 **{city}** 精选实景图")
    if not imgs_b64:
        st.caption("暂无图片，试试文字提问如『青岛有什么好玩的』")
        return
    for i in range(0, len(imgs_b64), 2):
        cols = st.columns(2)
        for col, b64s in zip(cols, imgs_b64[i:i + 2]):
            with col:
                st.image(base64.b64decode(b64s), use_container_width=True)


def _regenerate(round_num: int) -> None:
    """重新生成上一轮回答。"""
    conv = _current_conv()
    # 找到对应的用户消息
    target_user_idx = None
    for i, m in enumerate(conv["messages"]):
        if m.get("round") == round_num and m["role"] == "user":
            target_user_idx = i
            break
    if target_user_idx is not None:
        user_text = conv["messages"][target_user_idx].get("content", "")
        # 去掉前缀标签
        for prefix in ["[📷 图片输入] ", "[🎤 语音转写] "]:
            if user_text.startswith(prefix):
                user_text = user_text[len(prefix):]
        # 删除该轮 assistant 消息 + 记忆中该轮内容（避免重复）
        conv["messages"] = [m for m in conv["messages"]
                            if not (m.get("round") == round_num and m["role"] == "assistant")]
        mem: ConversationMemory = conv["memory"]
        if mem.messages and mem.messages[-1]["role"] == "assistant":
            mem.messages.pop()
        if mem.messages and mem.messages[-1]["role"] == "user":
            mem.messages.pop()
        _handle_user_input(user_text, input_type="文本")
    st.rerun()


def _handle_user_input(user_text: str, image_bytes: Optional[bytes] = None,
                        input_type: str = "文本") -> None:
    """统一处理用户输入：路由 → 多 Agent 真实协作 → 流式渲染 → 记录。"""
    if not user_text.strip() and not image_bytes:
        return

    # 未配置 API Key 时统一拦截（演示按钮等入口也走这里，避免未配置就调用）
    _fa = next(iter(st.session_state.agents.values()), None)
    if not (_fa and _fa.client.config.is_configured):
        st.error("😿 AI 服务暂时未就绪，请稍后再试；如持续如此请联系网站管理员。")
        return

    conv = _current_conv()
    conv["round"] += 1
    rnd = conv["round"]
    if conv["title"] in ("新对话", "") and user_text.strip():
        conv["title"] = user_text.strip()[:18]

    # 用户气泡：图片和文字放一起（小图在上，文字在下，像 ChatGPT）
    user_display = user_text
    if input_type == "语音":
        user_display = f"[🎤] {user_display}"
    conv["messages"].append({
        "role": "user", "content": user_display, "avatar": "🧑", "round": rnd,
        **({"image": base64.b64encode(image_bytes).decode()} if image_bytes else {}),
    })
    with st.chat_message("user", avatar="🧑"):
        if image_bytes:
            st.image(image_bytes, width=260)
        st.markdown(user_display)

    # ═══════════════════════════════════════════════════════════════
    # 看图意图拦截：用户说"图片/照片/看图"→直接展示真实照片，不走 Agent
    # ═══════════════════════════════════════════════════════════════
    look_kw = ["图片", "照片", "看图", "配图", "发图", "有图", "想看一下", "看看图"]
    if any(kw in user_text for kw in look_kw):
        city = _extract_city(user_text) or st.session_state.travel_context.destination
        if city:
            from theme import real_image_urls, _download_b64
            urls = real_image_urls(city, n=6)
            imgs = []
            for u in urls:
                b64 = _download_b64(u)
                if b64:
                    imgs.append(b64.split(",", 1)[1])   # 存纯 base64，便于历史回放
            with st.chat_message("assistant", avatar="🧳"):
                _render_image_gallery(city, imgs)
            conv["messages"].append({
                "role": "assistant", "avatar": "🧳",
                "content": f"📸 **{city}** 精选实景图",
                "gallery": imgs,
                "round": rnd,
            })
            conv["memory"].add_user(user_text)
            conv["memory"].add_assistant(f"展示{city}实景图")
            return
        else:
            st.info("想看哪里的图片？告诉我城市名（如：青岛图片）")
            return

    # 调 AIOrchestrator（真实 API）
    specified = st.session_state.specified_agent
    orchestrator: AIOrchestrator = st.session_state.orchestrator
    memory: ConversationMemory = conv["memory"]

    try:
        prepared = orchestrator.prepare(
            user_text, image=image_bytes,
            specified_agent=specified,
            travel_context=st.session_state.travel_context,
            history=memory.get_messages(),
        )

        if prepared.get("type") == "clarify":
            # 路由判断信息不足 → 追问（这句话由 AI 生成，非固定模板）
            q = prepared.get("clarification_question", "能再说说你的需求吗？")
            with st.chat_message("assistant", avatar="🧳"):
                st.markdown(trigger_badge_html(prepared.get("trigger_mode", "自适应")),
                            unsafe_allow_html=True)
                st.markdown(f"🤔 {q}")
            conv["messages"].append({
                "role": "assistant", "avatar": "🧳", "content": f"🤔 {q}",
                "round": rnd,
            })
            memory.add_user(user_text)
            memory.add_assistant(q)
            return

        # 真流式渲染（Coordinator 实时生成）
        full_answer = _render_guide_result(
            prepared, rnd, user_text=user_text,
            answer_stream=orchestrator.stream_final(prepared)) or ""
        result = orchestrator.finalize(prepared, full_answer)

        # 写入多轮记忆
        memory.add_user(user_text)
        memory.add_assistant(full_answer)

        # 入历史（result 里记录本轮用户原文，供历史回放判断是否显示图片）
        result["_user_text"] = user_text
        conv["messages"].append({
            "role": "assistant", "avatar": "🧳",
            "content": full_answer,
            "guide": result, "round": rnd,
        })

    except LLMError as e:
        # 友好错误提示（console 保留原始错误供调试）
        st.error(f"⚠️ {e.friendly}")
        print(f"[ShiYouJi][LLMError] {e.detail}", flush=True)
        conv["messages"].append({
            "role": "assistant", "avatar": "⚠️",
            "content": f"⚠️ {e.friendly}", "round": rnd,
        })
        return
    except Exception as e:
        st.error("AI 服务暂时无法连接，请稍后再试。")
        print(f"[ShiYouJi][Unexpected] {type(e).__name__}: {e}", flush=True)
        conv["messages"].append({
            "role": "assistant", "avatar": "⚠️",
            "content": "⚠️ AI 服务暂时无法连接，请稍后再试。", "round": rnd,
        })
        return

    # 记录 Debug Log
    conv["debug_logs"].append({
        "round": rnd,
        "input_type": input_type,
        "input_text": user_text,
        "has_image": bool(image_bytes),
        "image_desc": result.get("image_desc", ""),
        "trigger_mode": result.get("trigger_mode", ""),
        "router_reason": result.get("debug", {}).get("route_reason", ""),
        "intent": result.get("debug", {}).get("intent", ""),
        "triggered_agents": result.get("agents", []),
        "tools_used": result.get("debug", {}).get("tools_used", []),
        "agent_replies": [
            {"agent": r.get("agent"), "agent_name": r.get("agent_name"),
             "result": r.get("result", "")[:200], "error": r.get("error")}
            for r in result.get("agent_replies", [])
        ],
        "cards_count": len(result.get("cards", [])),
    })


# =====================================================================
# 四、侧边栏（像 ChatGPT/豆包：会话历史列表 + 底部折叠设置）
# =====================================================================
with st.sidebar:
    # —— 顶部：新建对话 + 标题 ——
    if st.button("➕ 新对话", use_container_width=True, type="primary"):
        _create_new_conv()
    st.caption(f"共 {len(st.session_state.conversations)} 个会话")

    # —— 会话历史列表 ——
    st.markdown("##### 💬 历史会话")
    cur_id = st.session_state.current_conv_id
    for conv in st.session_state.conversations:
        is_current = conv["id"] == cur_id
        title = conv.get("title", "新对话") or "新对话"
        n_msgs = len(conv.get("messages", []))
        label = f"{'● ' if is_current else ''}{title}  ({n_msgs})"
        c_title, c_del = st.columns([5, 1])
        if c_title.button(label, key=f"conv_{conv['id']}",
                          use_container_width=True,
                          type="primary" if is_current else "secondary"):
            _switch_conv(conv["id"])
        if c_del.button("✕", key=f"del_{conv['id']}",
                        help="删除此会话", use_container_width=True):
            _delete_conv(conv["id"])

    st.divider()

    # —— 底部折叠：设置 / 触发模式 / 清空导出 ——
    with st.expander("⚙️ 设置 & 工具", expanded=False):
        # API Key 由服务端统一配置（本地 .env / 云端 Secrets），访客无需也无法修改
        first_agent = next(iter(st.session_state.agents.values()), None)
        cfg = first_agent.client.config if first_agent else None
        if cfg and cfg.is_configured:
            st.markdown('<span class="sy-badge live">🌍 智能导游已就绪</span>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<span class="sy-badge mock">🚫 服务未就绪</span>',
                        unsafe_allow_html=True)
            st.caption("AI 服务配置缺失，请联系管理员在服务端配置 API Key。")

        st.markdown("**🔊 语音对话**")
        st.session_state.auto_voice = st.checkbox(
            "自动朗读导游回答", value=st.session_state.get("auto_voice", False))

        st.markdown("**🎯 触发模式**")
        if st.session_state.specified_agent:
            st.markdown(trigger_badge_html("指定"), unsafe_allow_html=True)
            st.caption(f"锁定 {st.session_state.specified_agent}（点主页卡片取消）")
        else:
            st.markdown(trigger_badge_html("自适应"), unsafe_allow_html=True)
            st.caption("自适应路由，自动选择 Agent")

        # 显示当前旅行上下文（记忆）
        tc = st.session_state.travel_context
        if not tc.is_empty():
            st.markdown("**🧠 旅行记忆**")
            st.caption(tc.to_summary())

        st.markdown("**🎬 一键演示**")
        demo_cols = st.columns(2)
        for col, city in zip(demo_cols, ["成都", "杭州"]):
            if col.button(city, key=f"demo_{city}", use_container_width=True):
                _handle_user_input(f"带我去{city}玩，给我推荐景区美食和文化", input_type="文本")
        demo_cols2 = st.columns(2)
        for col, city in zip(demo_cols2, ["西安", "北京"]):
            if col.button(city, key=f"demo_{city}_2", use_container_width=True):
                _handle_user_input(f"带我去{city}玩，给我推荐景区美食和文化", input_type="文本")

        st.markdown("**🧹 数据**")
        col_clr, col_exp = st.columns(2)
        if col_clr.button("🗑️ 清空当前", use_container_width=True):
            conv = _current_conv()
            conv["messages"] = []
            conv["memory"] = ConversationMemory()
            conv["debug_logs"] = []
            conv["round"] = 0
            conv["title"] = "新对话"
            st.session_state.travel_context = TravelContext()
            st.rerun()
        if col_exp.button("📥 导出Debug", use_container_width=True):
            conv = _current_conv()
            log_json = json.dumps(conv["debug_logs"], ensure_ascii=False, indent=2)
            st.download_button("下载 Debug Log", log_json,
                               file_name="食游记_debug_log.json",
                               mime="application/json")

    st.caption("《食游记》v4.0 · 多智能体 · 一城一味，一路一故事")


# =====================================================================
# 五、主对话区
# =====================================================================

def _render_itinerary_planner() -> None:
    """📋 行程规划页：表单填写 → AI 生成详细 Tour 计划。"""
    st.markdown("## 📋 AI 行程规划")
    st.caption("填写出行信息，AI 为你定制专属 Tour 计划（含时间表、交通、酒店、预算）")

    with st.form("itinerary_form"):
        col1, col2 = st.columns(2)
        with col1:
            destination = st.text_input("📍 目的地", placeholder="如：长沙、西安、成都")
            duration = st.selectbox("📅 天数", ["1天", "2天", "3天", "4天", "5天", "6天", "7天+"])
        with col2:
            budget = st.text_input("💰 预算/人", placeholder="如：1500元、3000元、不限")
            interests = st.multiselect("❤️ 兴趣", ["美食", "历史文化", "自然风光", "购物", "拍照", "夜生活", "亲子"], default=["美食"])
        special = st.text_input("📝 特殊需求", placeholder="如：带老人、不吃辣、想看日出")
        submitted = st.form_submit_button("🚀 生成行程", type="primary", use_container_width=True)

    if submitted and destination:
        st.session_state["quick_question"] = f"请为我定制{destination}{duration}的详细行程，预算{budget or '不限'}，兴趣{','.join(interests)}，{special or '无特殊需求'}。要求输出完整 Tour 计划：每天具体时间表、交通方式、酒店推荐、费用估算。"
        st.session_state.page = "💬 AI导游问答"
        st.rerun()
    elif submitted:
        st.warning("请填写目的地")

    # 显示当前会话中最新的行程计划
    conv = _current_conv()
    tours = [m for m in conv.get("messages", []) if m.get("role") == "assistant" and "行程" in m.get("content", "")[:50]]
    if tours:
        st.markdown("---")
        st.markdown("### 📋 最近的行程计划")
        latest = tours[-1]
        answer = _strip_br(latest.get("content", ""))
        st.markdown(answer)


def _render_my_trips() -> None:
    """🎫 我的行程页：展示所有会话中保存的行程计划。"""
    st.markdown("## 🎫 我的行程")
    st.caption("这里展示你所有会话中生成的行程计划")

    all_tours = []
    for conv in st.session_state.conversations:
        for msg in conv.get("messages", []):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if any(kw in content[:80] for kw in ["行程", "Day", "第一天", "时间表", "预算"]):
                    all_tours.append({
                        "conv_title": conv.get("title", "未命名"),
                        "conv_id": conv.get("id"),
                        "content": content,
                        "time": msg.get("time", ""),
                    })

    if not all_tours:
        st.info("还没有生成过行程计划。去「📋 行程规划」页填写信息，AI 会帮你定制。")
        if st.button("📋 去生成行程", type="primary"):
            st.session_state.page = "📋 行程规划"
            st.rerun()
        return

    for i, tour in enumerate(reversed(all_tours[-10:])):
        with st.expander(f"📋 {tour['conv_title']} — 行程计划", expanded=(i == 0)):
            answer = _strip_br(tour["content"])
            st.markdown(answer)
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("💬 继续对话", key=f"continue_trip_{i}"):
                    st.session_state.current_conv_id = tour["conv_id"]
                    st.session_state.page = "💬 AI导游问答"
                    st.rerun()
            with col2:
                if st.button("📋 复制行程", key=f"copy_trip_{i}"):
                    st.code(tour["content"], language=None)
                    st.caption("已显示纯文本，可全选复制")


# 顶部页面目录（4个独立页面入口）
_nav_cols = st.columns(4)
if _nav_cols[0].button("🌟 中国魅力", use_container_width=True,
                        type="primary" if st.session_state.page == "🌟 中国魅力" else "secondary"):
    st.session_state.page = "🌟 中国魅力"
    st.rerun()
if _nav_cols[1].button("📋 行程规划", use_container_width=True,
                        type="primary" if st.session_state.page == "📋 行程规划" else "secondary"):
    st.session_state.page = "📋 行程规划"
    st.rerun()
if _nav_cols[2].button("💬 AI导游问答", use_container_width=True,
                        type="primary" if st.session_state.page == "💬 AI导游问答" else "secondary"):
    st.session_state.page = "💬 AI导游问答"
    st.rerun()
if _nav_cols[3].button("🎫 我的行程", use_container_width=True,
                        type="primary" if st.session_state.page == "🎫 我的行程" else "secondary"):
    st.session_state.page = "🎫 我的行程"
    st.rerun()
st.markdown("---")

# 按页面分发
_page = st.session_state.page
if _page == "🌟 中国魅力":
    _render_city_showcase()
    st.stop()
elif _page == "📋 行程规划":
    _render_itinerary_planner()
    st.stop()
elif _page == "🎫 我的行程":
    _render_my_trips()
    st.stop()

# 以下只在「AI导游问答」页渲染
# 4 Agent 选择卡（点选锁定指定触发）
_render_agent_cards()

st.markdown("---")

# 回放历史（当前会话的消息）
_conv = _current_conv()
for msg in _conv["messages"]:
    with st.chat_message(msg["role"], avatar=msg.get("avatar")):
        if msg["role"] == "assistant" and "guide" in msg:
            result = msg["guide"]
            trigger_mode = result.get("trigger_mode", "自适应")
            agent_names = [AGENT_DISPLAY.get(k, k) for k in result.get("agents", [])]
            st.markdown(trigger_badge_html(trigger_mode), unsafe_allow_html=True)
            st.markdown(agent_chips_html(agent_names), unsafe_allow_html=True)
            _hist_answer = result.get("answer", "")
            # 清理 AI 可能生成的 <br> 标签
            _hist_answer = _strip_br(_hist_answer)
            st.markdown(_hist_answer)
            # AI 生成的动态卡片
            _hist_show_img = _user_wants_images(result, result.get("_user_text", ""))
            for i, card in enumerate(result.get("cards", [])):
                if _hist_show_img:
                    img_b64 = img_data_url(card.get("image_keywords") or card.get("title", ""))
                    if img_b64:
                        st.image(base64.b64decode(img_b64.split(",", 1)[1]),
                                 use_container_width=True)
                _render_guide_card(card, index=i)
        else:
            if msg.get("image"):
                st.image(base64.b64decode(msg["image"]), width=260)
            st.markdown(msg["content"])
            # 看图回答：回放图集
            if msg.get("gallery"):
                for i in range(0, len(msg["gallery"]), 2):
                    cols = st.columns(2)
                    for col, b64s in zip(cols, msg["gallery"][i:i + 2]):
                        with col:
                            st.image(base64.b64decode(b64s), use_container_width=True)


# =====================================================================
# 六、多模态输入区（豆包式：底部输入框 + 图片附件 + 悬浮麦克风）
# =====================================================================
st.markdown("---")
st.markdown("##### 💬 直接和导游聊：底部输入框打字 / 点输入框里的 🎤 说话 / 📎 传图")

# 图片上传：组件常驻 DOM（CSS 隐藏视觉），由输入框内 📎 按钮唤起；
# 选中后缩略图直接显示在输入框内（JS 注入），发送后自动重置
_up_seq = st.session_state.get("_up_seq", 0)
uploaded = st.file_uploader("上传景区/美食图片", type=["png", "jpg", "jpeg"],
                             label_visibility="collapsed", key=f"img_uploader_{_up_seq}")
img_bytes = uploaded.getvalue() if uploaded else None

# 语音输入提示（🎤 按钮已注入输入框内部右侧，浏览器原生 SpeechRecognition）
st.caption("🎤 语音输入：点输入框里的话筒按钮说话，识别后自动填入（需 Chrome/Edge 桌面版，允许麦克风权限）")

# Agent Selector —— 自动模式 / 指定 Agent
agent_options = ["🤖 自动（自适应）", "🍜 美食达人", "🗺️ 旅行规划师", "🏮 文化向导"]
current_idx = 0
if st.session_state.specified_agent:
    name_to_idx = {"美食达人": 1, "旅行规划师": 2, "文化向导": 3}
    current_idx = name_to_idx.get(st.session_state.specified_agent, 0)
selected = st.radio("选择 Agent 触发模式：", agent_options, index=current_idx,
                    horizontal=True, key="agent_selector_radio")
if selected == "🤖 自动（自适应）":
    if st.session_state.specified_agent:
        st.session_state.specified_agent = ""
else:
    # 提取中文名
    name = selected.split(" ", 1)[1]
    if st.session_state.specified_agent != name:
        st.session_state.specified_agent = name

# 启动检查：未配置 API Key 时明确报错（不提供任何模拟回答）
first_agent = next(iter(st.session_state.agents.values()), None)
_cfg_ready = bool(first_agent and first_agent.client.config.is_configured)
if not _cfg_ready:
    st.error("😿 **AI 服务暂时未就绪。** 请稍后再试；如持续如此，请联系网站管理员检查服务端配置。")

# 快捷追问按钮触发的输入
if st.session_state.get("quick_question"):
    qq = st.session_state.pop("quick_question")
    if _cfg_ready:
        _handle_user_input(qq, image_bytes=None, input_type="文本")

# 底部聊天输入（豆包式：单一输入框，附件/语音按钮独立）
user_input = st.chat_input("想去哪里，问我就好～", disabled=not _cfg_ready)
if user_input:
    _handle_user_input(user_input, image_bytes=img_bytes if img_bytes else None,
                        input_type="文本")
    # 发送后重置上传器（缩略图消失），无论是否带图都更新 _up_seq
    st.session_state["_up_seq"] = st.session_state.get("_up_seq", 0) + 1
    st.rerun()
