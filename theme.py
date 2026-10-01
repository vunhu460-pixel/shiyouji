"""《食游记》主题 —— 可爱旅游美食文化风。

配色三色对应三板块：
  🗺️ 游 · 景区 → 天空蓝  #5DADE2
  🍜 食 · 美食 → 暖橙    #FF8C42
  🏮 文 · 文化 → 抹茶绿  #7FB069
强调金 #FFD23F，背景奶油薄荷渐变。
标题超醒目：ZCOOL KuaiLe 大字号 + 渐变金橙 + 投影。
"""
from __future__ import annotations

# 三板块主色
SECTION_COLORS = {
    "travel":  {"main": "#5DADE2", "dark": "#2E86C1", "bg": "#EAF4FB"},  # 蓝
    "food":    {"main": "#FF8C42", "dark": "#E0601A", "bg": "#FFF1E6"},  # 橙
    "culture": {"main": "#7FB069", "dark": "#5A8A45", "bg": "#EEF6E8"},  # 绿
}

SECTION_META = {
    "travel":  {"emoji": "🗺️", "name": "游", "full": "景区推荐"},
    "food":    {"emoji": "🍜", "name": "食", "full": "美食特产"},
    "culture": {"emoji": "🏮", "name": "文", "full": "文化故事"},
}

GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=ZCOOL+KuaiLe&family=Noto+Sans+SC:wght@400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans SC', system-ui, sans-serif;
}

/* 整体背景：奶油到薄荷的温暖渐变 */
.stApp {
    background: linear-gradient(180deg, #FFF8E7 0%, #F4F9F0 50%, #EAF7F0 100%);
    color: #2C2C2C;  /* 强制正文深色，避免浅字看不清 */
}
.stApp:focus { outline: none; }

/* —— 强制所有正文文字深色（防止系统深色模式导致浅字白底看不清） —— */
.stApp p, .stApp span, .stApp li, .stApp label,
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] div,
.sy-section p, .sy-section span, .sy-section li, .sy-section div {
    color: #2C2C2C !important;
}
/* 例外：副标题保持柔和灰（但加深一档） */
.sy-section .sec-sub { color: #555555 !important; }

/* —— 突出的大标题 —— */
h1, h2, h3 {
    font-family: 'ZCOOL KuaiLe', 'Noto Sans SC', sans-serif !important;
    color: #3A3A3A;
    letter-spacing: 0.5px;
}

/* 魔法按钮（渐变橙金） */
.stButton>button {
    background: linear-gradient(135deg, #FF8C42 0%, #FFD23F 100%);
    color: #fff !important;
    border: none;
    border-radius: 14px;
    padding: 8px 18px;
    font-weight: 700;
    font-size: 14px;
    box-shadow: 0 4px 12px rgba(255, 140, 66, 0.35);
    transition: all 0.2s ease;
}
.stButton>button:hover {
    transform: translateY(-1px) scale(1.01);
    box-shadow: 0 6px 18px rgba(255, 140, 66, 0.5);
}

/* 输入框 */
.stTextArea textarea, .stTextInput input, .stChatInput textarea {
    border-radius: 14px !important;
    border: 2px solid #FFE0B5 !important;
    background: #fff !important;
    color: #3A3A3A !important;
}
.stTextArea textarea:focus, .stTextInput input:focus, .stChatInput textarea:focus {
    border-color: #FF8C42 !important;
    box-shadow: 0 0 0 3px rgba(255, 140, 66, 0.2) !important;
}

/* —— 顶部超醒目横幅（游伴星球风：橙青渐变 + 插画装饰） —— */
.sy-banner {
    background:
        radial-gradient(circle at 20% 30%, rgba(255,255,255,0.4) 0%, transparent 40%),
        radial-gradient(circle at 80% 20%, rgba(46,196,182,0.3) 0%, transparent 45%),
        linear-gradient(135deg, #FF8C42 0%, #FFA94D 35%, #FFC078 60%, #2EC4B6 100%);
    border-radius: 28px;
    padding: 32px 24px 28px 24px;
    text-align: center;
    box-shadow: 0 12px 32px rgba(255,140,66,0.35), 0 4px 10px rgba(46,196,182,0.2);
    margin: 10px 0 20px 0;
    position: relative;
    overflow: hidden;
    border: 3px solid #fff;
}
.sy-banner h1 {
    font-family: 'ZCOOL KuaiLe', 'Noto Sans SC', sans-serif !important;
    font-size: 64px !important;
    color: #ffffff !important;
    margin: 0;
    letter-spacing: 4px;
    line-height: 1.1;
    position: relative;
    z-index: 2;
}
.sy-banner .banner-en {
    font-size: 16px;
    color: rgba(255,255,255,0.85);
    letter-spacing: 3px;
    margin-top: 4px;
    font-weight: 500;
    position: relative;
    z-index: 2;
}
.sy-banner .slogan {
    font-family: 'ZCOOL KuaiLe', sans-serif;
    font-size: 26px;
    color: #fff;
    margin-top: 10px;
    letter-spacing: 4px;
    font-weight: 700;
    position: relative;
    z-index: 2;
}
/* 横幅装饰元素 */
.banner-deco { position: absolute; top: 0; left: 0; right: 0; height: 100%; pointer-events: none; }
.banner-deco span { position: absolute; font-size: 28px; opacity: 0.7; }
.deco-pin { top: 12px; left: 8%; }
.deco-bus { top: 18px; right: 10%; font-size: 32px !important; }
.deco-star { top: 40px; left: 25%; font-size: 20px !important; }
.deco-chat { top: 8px; right: 28%; font-size: 26px !important; }
.banner-illust { margin-top: 18px; display: flex; justify-content: center; gap: 14px; font-size: 36px; position: relative; z-index: 2; }
.banner-illust span { filter: drop-shadow(0 2px 4px rgba(0,0,0,0.15)); }

/* —— 三大功能按钮卡（生成行程/AI对话助手/我的行程） —— */
.sy-func-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 18px 0 10px 0; }
.sy-func-card {
    background: #fff;
    border-radius: 18px;
    padding: 20px 12px 16px 12px;
    text-align: center;
    box-shadow: 0 6px 16px rgba(0,0,0,0.08);
    border: 2px solid #FFE0B5;
    cursor: pointer;
    transition: all 0.2s ease;
}
.sy-func-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 10px 24px rgba(255,140,66,0.25);
    border-color: #FF8C42;
}
.sy-func-card .func-icon { font-size: 38px; margin-bottom: 8px; }
.sy-func-card .func-label { font-size: 16px; font-weight: 700; color: #3A3A3A; }
.sy-func-card .func-tag { font-size: 11px; color: #FF8C42; margin-top: 4px; font-weight: 600; }

/* —— 美食/景点卡片（带图片，游伴星球风） —— */
.sy-item-card {
    display: flex;
    align-items: stretch;
    gap: 14px;
    background: #fff;
    border-radius: 16px;
    padding: 14px;
    margin: 10px 0;
    box-shadow: 0 4px 14px rgba(0,0,0,0.08);
    border: 1px solid rgba(0,0,0,0.05);
    transition: transform 0.15s ease;
}
.sy-item-card:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(0,0,0,0.12); }
.sy-item-card .item-img {
    flex: 0 0 110px;
    width: 110px;
    height: 110px;
    border-radius: 14px;
    object-fit: cover;
    box-shadow: 0 3px 10px rgba(0,0,0,0.15);
}
.sy-item-card .item-body { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.sy-item-card .item-name {
    font-size: 18px;
    font-weight: 700;
    color: #2C2C2C;
    margin-bottom: 6px;
}
.sy-item-card .item-desc {
    font-size: 13px;
    color: #555;
    line-height: 1.6;
    margin-bottom: 8px;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.sy-item-card .item-meta {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: auto;
    font-size: 13px;
}
.sy-item-card .item-area { color: #2EC4B6; font-weight: 600; }
.sy-item-card .item-price {
    background: linear-gradient(135deg, #FF8C42, #FFD23F);
    color: #fff;
    padding: 2px 10px;
    border-radius: 10px;
    font-weight: 700;
    font-size: 12px;
}
.sy-item-card .item-no {
    flex: 0 0 28px;
    width: 28px; height: 28px;
    border-radius: 50%;
    background: linear-gradient(135deg, #FF8C42, #FFD23F);
    color: #fff;
    font-weight: 700;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 2px;
    flex-shrink: 0;
}

/* —— 专家指南卡片（景点/美食/出行，带故事+贴士） —— */
.gc-card {
    background: #fff;
    border-radius: 18px;
    padding: 16px;
    margin: 12px 0;
    box-shadow: 0 4px 14px rgba(0,0,0,0.08);
    border: 1px solid rgba(0,0,0,0.05);
}
.gc-card .item-no {
    display: inline-block;
    width: 28px; height: 28px;
    line-height: 28px;
    text-align: center;
    border-radius: 50%;
    background: linear-gradient(135deg, #FF8C42, #FFD23F);
    color: #fff;
    font-weight: 700;
    font-size: 14px;
    margin-bottom: 10px;
}
.gc-card .gc-img {
    width: 100%;
    height: 160px;
    object-fit: cover;
    border-radius: 14px;
    margin-bottom: 12px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.15);
}
.gc-card .gc-title {
    font-size: 20px;
    font-weight: 700;
    color: #2C2C2C;
    margin-bottom: 10px;
}
.gc-card .gc-intro {
    font-size: 14px;
    color: #555;
    line-height: 1.7;
    margin-bottom: 10px;
}
.gc-card .gc-block {
    font-size: 13px;
    color: #555;
    line-height: 1.7;
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px dashed rgba(0,0,0,0.1);
}
.gc-card .gc-label {
    display: inline-block;
    font-weight: 700;
    color: #FF8C42;
    margin-bottom: 4px;
}

/* —— 三板块卡片（更独立、更分开） —— */
.sy-section {
    border-radius: 22px;
    padding: 26px 24px 22px 24px;
    margin: 28px 0;
    box-shadow: 0 10px 28px rgba(0,0,0,0.12);
    border: 2px solid rgba(0,0,0,0.05);
}
.sy-section .sec-head {
    font-family: 'ZCOOL KuaiLe', sans-serif;
    font-size: 38px;
    margin-bottom: 6px;
    padding-bottom: 10px;
    border-bottom: 3px dashed currentColor;
    line-height: 1.2;
}
.sy-section .sec-sub {
    font-size: 15px;
    color: #6B6B6B;
    margin-bottom: 14px;
    font-style: italic;
}
.sy-section .sec-title {
    font-family: 'ZCOOL KuaiLe', sans-serif;
    font-size: 28px;
    margin: 10px 0 6px 0;
    line-height: 1.3;
}
.sy-section .sec-desc {
    font-size: 15px;
    line-height: 1.75;
    color: #3A3A3A;
}
.sy-section .tips {
    background: rgba(255,255,255,0.7);
    border-radius: 12px;
    padding: 10px 14px;
    margin-top: 10px;
    font-size: 14px;
}
.sy-section .tips li { margin: 4px 0; }

/* —— 餐厅榜单（小红书/豆包风） —— */
.sy-restaurant-list {
    margin: 14px 0 10px 0;
    padding: 0;
    border-radius: 16px;
    background: rgba(255,255,255,0.85);
    box-shadow: 0 4px 14px rgba(0,0,0,0.08);
    overflow: hidden;
}
.sy-restaurant-list .rst-list-title {
    font-family: 'ZCOOL KuaiLe', sans-serif;
    font-size: 20px;
    color: #E0601A;
    background: linear-gradient(135deg, #FF8C42 0%, #FFD23F 100%);
    color: #fff;
    padding: 10px 16px;
    letter-spacing: 1px;
    text-shadow: 0 1px 3px rgba(0,0,0,0.15);
}
.sy-restaurant-list .sy-rst-item {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 12px 16px;
    border-bottom: 1px dashed rgba(0,0,0,0.08);
    transition: background 0.15s ease;
}
.sy-restaurant-list .sy-rst-item:last-child { border-bottom: none; }
.sy-restaurant-list .sy-rst-item:hover { background: rgba(255,140,66,0.08); }
.sy-restaurant-list .rst-no {
    flex: 0 0 28px;
    width: 28px; height: 28px;
    border-radius: 50%;
    background: linear-gradient(135deg, #FF8C42, #FFD23F);
    color: #fff;
    font-weight: 700;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 6px rgba(255,140,66,0.4);
    margin-top: 2px;
}
.sy-restaurant-list .rst-body { flex: 1 1 auto; min-width: 0; }
.sy-restaurant-list .rst-name {
    font-size: 16px;
    font-weight: 700;
    color: #2C2C2C;
    margin-bottom: 4px;
}
.sy-restaurant-list .rst-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    font-size: 13px;
    color: #666;
    margin-bottom: 4px;
}
.sy-restaurant-list .rst-dish { color: #E0601A; font-weight: 600; }
.sy-restaurant-list .rst-area { color: #5A8A45; }
.sy-restaurant-list .rst-price {
    background: #FFF1E6;
    color: #E0601A;
    padding: 1px 8px;
    border-radius: 10px;
    font-weight: 700;
    font-size: 12px;
}
.sy-restaurant-list .rst-highlight {
    font-size: 13px;
    color: #555;
    line-height: 1.5;
}
/* 有榜单时描述精简为一行 */
.sy-section .sec-desc.rst-intro {
    background: rgba(255,255,255,0.6);
    border-radius: 10px;
    padding: 8px 12px;
    margin: 8px 0;
    font-size: 14px;
    color: #555;
}

/* 真实视频卡（HTML5 video 可播放） */
.sy-video-card {
    position: relative;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 6px 18px rgba(0,0,0,0.15);
    margin: 8px 0 12px 0;
    background: #000;
}
.sy-video-card video {
    width: 100%;
    display: block;
    border-radius: 16px;
    max-height: 420px;
    object-fit: cover;
}
.sy-video-card .video-label {
    position: absolute;
    top: 10px; left: 12px;
    background: rgba(0,0,0,0.6);
    color: #fff;
    font-size: 12px;
    padding: 2px 10px;
    border-radius: 10px;
    font-weight: 700;
    z-index: 2;
    pointer-events: none;
}

/* 🔊 朗读按钮（浏览器原生 TTS） */
.sy-speak-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: linear-gradient(135deg, #FF8C42 0%, #FFD23F 100%);
    color: #fff !important;
    border: none;
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    box-shadow: 0 3px 10px rgba(255,140,66,0.35);
    margin: 6px 0;
    transition: all 0.2s ease;
}
.sy-speak-btn:hover { transform: translateY(-1px); box-shadow: 0 5px 14px rgba(255,140,66,0.5); }
.sy-speak-btn.playing { background: linear-gradient(135deg, #7FB069 0%, #5DADE2 100%); }

/* 输入框内 🎤 按钮（像 ChatGPT 一体化输入栏） */
.sy-mic-inbox {
    position: absolute;
    right: 52px;
    bottom: 12px;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: linear-gradient(135deg, #FF6B6B 0%, #FF8C42 100%);
    color: #fff !important;
    border: 2px solid #fff;
    box-shadow: 0 4px 12px rgba(255,107,107,0.45);
    font-size: 16px;
    cursor: pointer;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
}
.sy-mic-inbox:hover { transform: scale(1.08); }
.sy-mic-inbox.listening {
    background: linear-gradient(135deg, #E0601A 0%, #C0392B 100%);
    animation: sy-pulse 1.2s infinite;
}
@keyframes sy-pulse {
    0%, 100% { box-shadow: 0 6px 20px rgba(255,107,107,0.5), 0 0 0 0 rgba(255,107,107,0.5); }
    50% { box-shadow: 0 6px 20px rgba(255,107,107,0.5), 0 0 0 14px rgba(255,107,107,0); }
}

/* 输入框内 📎 图片按钮（在 🎤 左边） */
.sy-clip-inbox {
    position: absolute;
    right: 96px;
    bottom: 12px;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: linear-gradient(135deg, #5DADE2 0%, #7FB069 100%);
    color: #fff !important;
    border: 2px solid #fff;
    box-shadow: 0 4px 12px rgba(93,173,226,0.45);
    font-size: 16px;
    cursor: pointer;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
}
.sy-clip-inbox:hover { transform: scale(1.08); }

/* 隐藏原生文件上传器的视觉（DOM 保留，供 📎 按钮唤起） */
[data-testid="stFileUploader"] { display: none !important; }

/* 输入框内已选图片缩略图（像 ChatGPT 附件小图） */
.sy-img-chip {
    position: absolute;
    left: 12px;
    bottom: 10px;
    width: 40px;
    height: 40px;
    border-radius: 10px;
    object-fit: cover;
    border: 2px solid #fff;
    box-shadow: 0 3px 10px rgba(0,0,0,0.25);
    z-index: 9999;
}

/* 图片卡 */
.sy-image-card {
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 6px 18px rgba(0,0,0,0.12);
    margin: 8px 0 12px 0;
}
.sy-image-card img {
    width: 100%;
    display: block;
    border-radius: 16px;
}

/* 模式徽章 */
.sy-badge {
    display: inline-block;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 700;
    margin: 2px;
}
.sy-badge.mock  { background: #FFF1E6; color: #E0601A; border: 1px solid #FF8C42; }
.sy-badge.live  { background: #EEF6E8; color: #5A8A45; border: 1px solid #7FB069; }

/* 侧边栏 */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FFF8E7 0%, #F4F9F0 100%);
    border-right: 2px solid #FFE0B5;
}
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {
    color: #E0601A;
}

/* 对话气泡 */
[data-testid="stChatMessage"] {
    border-radius: 18px !important;
    border: 1px solid #FFE0B5 !important;
    border-left: 4px solid #FF8C42 !important;
    background: #fff !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06) !important;
    margin: 8px 0 !important;
}
/* 触发模式徽章（🔵 指定 / 🟢 自适应） */
.sy-trigger-badge {
    display: inline-block;
    border-radius: 12px;
    padding: 5px 14px;
    font-size: 14px;
    font-weight: 700;
    margin: 4px 4px 4px 0;
    font-family: 'ZCOOL KuaiLe', sans-serif;
}
.sy-trigger-badge.specified {
    background: #E3F2FD; color: #1565C0; border: 2px solid #5DADE2;
}
.sy-trigger-badge.adaptive {
    background: #E8F5E9; color: #2E7D32; border: 2px solid #7FB069;
}

/* Agent 标签（当前参与 Agent 列表） */
.sy-agent-chip {
    display: inline-block;
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 13px;
    font-weight: 600;
    margin: 3px;
    background: #fff;
    border: 1.5px solid #FFD23F;
    color: #3A3A3A;
}

/* Debug Log 面板 */
.sy-debug-panel {
    background: #FAFAFA;
    border: 2px solid #DDD;
    border-radius: 14px;
    padding: 16px;
    margin: 12px 0;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
    color: #2C2C2C;
    line-height: 1.7;
    max-height: 500px;
    overflow-y: auto;
}
.sy-debug-panel .dbg-line { margin: 2px 0; }
.sy-debug-panel .dbg-round {
    font-weight: 700; color: #E0601A;
    border-bottom: 1px dashed #CCC;
    padding-bottom: 4px; margin-bottom: 6px;
}
.sy-debug-panel .dbg-key { color: #1565C0; }
.sy-debug-panel .dbg-val { color: #2E7D32; }

/* 多 Agent 回复区分（不同头像左边框色） */
[data-testid="stChatMessage"][data-agent-color] {
    border-left: 6px solid var(--agent-color, #FF8C42) !important;
}
</style>
"""

BANNER_HTML = """
<div class="sy-banner">
    <div class="banner-deco">
        <span class="deco-pin">📍</span>
        <span class="deco-bus">🚌</span>
        <span class="deco-star">✨</span>
        <span class="deco-chat">💬</span>
    </div>
    <h1 style="color:#FFFFFF !important; text-shadow:0 2px 8px rgba(0,0,0,0.25); font-family:'ZCOOL KuaiLe','Noto Sans SC',sans-serif; letter-spacing:4px; font-size:64px;">🍲 食游记</h1>
    <div class="banner-en">Travel Pal Planet</div>
    <div class="slogan" style="color:#FFFFFF !important; text-shadow:0 1px 4px rgba(0,0,0,0.2); font-family:'ZCOOL KuaiLe',sans-serif; letter-spacing:4px; font-size:26px; font-weight:700; margin-top:10px;">问一下，就出发</div>
    <div class="banner-illust">
        <span class="illust-tower">🏯</span>
        <span class="illust-mountain">⛰️</span>
        <span class="illust-tea">🍵</span>
        <span class="illust-food">🍖</span>
        <span class="illust-leaf">🍃</span>
    </div>
</div>
"""

# 图片生成 API（必须使用此 URL，prompt 由调用方 URL-encode）
IMAGE_API = "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image"


def image_url(prompt: str, size: str = "landscape_4_3") -> str:
    """构造图片生成 URL。

    参数：
        prompt: 中文图片描述（SDXL 风格）
        size: square_hd | square | portrait_4_3 | portrait_16_9 | landscape_4_3 | landscape_16_9
    """
    from urllib.parse import quote
    return f"{IMAGE_API}?prompt={quote(prompt)}&image_size={size}"


def section_header_html(sec_type: str, subtitle: str) -> str:
    """板块头部 HTML（带主题色）。"""
    c = SECTION_COLORS[sec_type]
    m = SECTION_META[sec_type]
    return (
        f'<div class="sec-head" style="color:{c["main"]}">'
        f'{m["emoji"]} {m["full"]}</div>'
        f'<div class="sec-sub">{subtitle}</div>'
    )


# Agent 元数据
AGENT_META = {
    "美食达人":   {"avatar": "🍜", "section_type": "food",
                  "color": SECTION_COLORS["food"]["main"]},
    "旅行规划师": {"avatar": "🗺️", "section_type": "travel",
                  "color": SECTION_COLORS["travel"]["main"]},
    "文化向导":   {"avatar": "🏮", "section_type": "culture",
                  "color": SECTION_COLORS["culture"]["main"]},
    "总导游":     {"avatar": "🧳", "section_type": "",
                  "color": "#FFD23F"},
}


def trigger_badge_html(trigger_mode: str) -> str:
    """触发模式徽章 HTML。"""
    cls = "specified" if trigger_mode == "指定" else "adaptive"
    icon = "🔵" if trigger_mode == "指定" else "🟢"
    return (f'<span class="sy-trigger-badge {cls}">'
            f'{icon} 当前触发：{trigger_mode}回答</span>')


def agent_chips_html(agent_names: list) -> str:
    """当前参与 Agent 标签 HTML。"""
    chips = []
    for name in agent_names:
        m = AGENT_META.get(name, {})
        avatar = m.get("avatar", "🤖")
        chips.append(f'<span class="sy-agent-chip">{avatar} {name}</span>')
    return "".join(chips)


def _real_image_url(query: str) -> str:
    """从 Wikipedia 免费 API 抓真实图片 URL：先按词条名直查，查不到再全文搜索。抓不到返回空串。"""
    import urllib.request
    import urllib.parse
    import json as _json

    def _get(u: str):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "ShiYouji/4.0"})
            with urllib.request.urlopen(req, timeout=6) as r:
                return _json.loads(r.read().decode("utf-8", errors="ignore"))
        except Exception:
            return None

    def _thumb_of(title: str) -> str:
        u = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
             f"&prop=pageimages&piprop=thumbnail&pithumbsize=400"
             f"&titles={urllib.parse.quote(title)}&redirects=1")
        data = _get(u)
        if not data:
            return ""
        for _, p in data.get("query", {}).get("pages", {}).items():
            thumb = p.get("thumbnail", {}).get("source", "")
            if thumb:
                return thumb
        return ""

    # 1) 直查词条
    url = _thumb_of(query)
    if url:
        return url
    # 2) 全文搜索 → 取第一个结果的配图
    su = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
          f"&list=search&srlimit=1&srsearch={urllib.parse.quote(query)}")
    sdata = _get(su)
    if sdata:
        hits = sdata.get("query", {}).get("search", [])
        if hits:
            return _thumb_of(hits[0].get("title", ""))
    return ""


def _download_b64(url: str) -> str:
    """后端下载图片转 base64 data URL（浏览器无需直连外网，100% 可显示）。失败返回空串。"""
    import base64 as _b64
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ShiYouji/4.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = r.read()
        if len(data) < 2000:      # 太小通常是占位图
            return ""
        return "data:image/jpeg;base64," + _b64.b64encode(data).decode()
    except Exception:
        return ""


from functools import lru_cache as _lru_cache

@_lru_cache(maxsize=256)
def img_data_url(query: str) -> str:
    """按关键词取真实图片的 data URL（带缓存）。抓不到返回空串。"""
    u = _real_image_url(query)
    if not u:
        return ""
    return _download_b64(u)


@_lru_cache(maxsize=64)
def real_image_urls(query: str, n: int = 6) -> tuple:
    """按具体主题取高相关真实照片：直接抓该词条页面里使用的配图。
    例如 query=「北京故宫」→ 故宫百科词条里的实景照片（不会混入无关城市图）。
    页面配图不足时，再用「主题 景点」搜索补充。"""
    import urllib.parse
    import json as _json
    import urllib.request
    import re

    def _get(u: str):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "ShiYouji/4.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                return _json.loads(r.read().decode("utf-8", errors="ignore"))
        except Exception:
            return None

    # 注意：不能过滤 "commons" —— 所有 Wikimedia 图片 URL 都含 /commons/ 路径
    _BAD = re.compile(r"(logo|icon|placeholder|disambig|ambox|\.svg|\.gif|卫星|satellite|地图|map_)", re.I)

    def _resolve_title(subject: str) -> str:
        u = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
             f"&list=search&srlimit=1&srsearch={urllib.parse.quote(subject)}")
        d = _get(u)
        hits = (d or {}).get("query", {}).get("search", [])
        return hits[0]["title"] if hits else subject

    def _page_image_titles(title: str) -> list:
        u = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
             f"&prop=images&imlimit=40&redirects=1"
             f"&titles={urllib.parse.quote(title)}")
        d = _get(u)
        out = []
        for _, p in (d or {}).get("query", {}).get("pages", {}).items():
            for im in p.get("images", []):
                fn = im.get("title", "")
                if re.search(r"\.(jpe?g|png)$", fn, re.I) and not _BAD.search(fn):
                    out.append(fn)
        return out

    def _thumbs(file_titles: list) -> list:
        if not file_titles:
            return []
        u = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
             f"&prop=imageinfo&iiprop=url&iiurlwidth=500&redirects=1"
             f"&titles={urllib.parse.quote('|'.join(file_titles[:12]))}")
        d = _get(u)
        urls = []
        for _, p in (d or {}).get("query", {}).get("pages", {}).items():
            ii = p.get("imageinfo", [{}])[0]
            t = ii.get("thumburl") or ii.get("url", "")
            if t and not _BAD.search(t):
                urls.append(t)
        return urls

    title = _resolve_title(query)
    urls = _thumbs(_page_image_titles(title))

    # 页面配图不足 → 「主题 景点」搜索补充
    if len(urls) < n:
        su = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
              f"&list=search&srlimit={n}&srsearch={urllib.parse.quote(query + ' 景点')}")
        sdata = _get(su)
        titles = [h.get("title", "") for h in (sdata or {}).get("query", {}).get("search", [])]
        if titles:
            pu = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
                  f"&prop=pageimages&piprop=thumbnail&pithumbsize=500"
                  f"&titles={urllib.parse.quote('|'.join(titles))}&redirects=1")
            pdata = _get(pu)
            for _, p in (pdata or {}).get("query", {}).get("pages", {}).items():
                thumb = p.get("thumbnail", {}).get("source", "")
                if thumb and thumb not in urls and not _BAD.search(thumb):
                    urls.append(thumb)
    return tuple(urls[:n])


def guide_card_html(card: dict, index: int = 0, city: str = "", skip_img: bool = False) -> str:
    """渲染专家返回的景点/美食/出行卡片。skip_img=True 时不渲染图片（图片由 st.image 单独处理）。"""
    title = card.get("title", "")
    intro = card.get("intro", "")
    story = card.get("story", "")
    tips = card.get("tips", "")
    no_html = f'<div class="item-no">{index + 1}</div>' if index >= 0 else ""
    sections = ""
    if intro:
        sections += f'<div class="gc-intro">{intro}</div>'
    if story:
        sections += f'<div class="gc-block"><span class="gc-label">📖 故事</span><div>{story}</div></div>'
    if tips:
        sections += f'<div class="gc-block"><span class="gc-label">💡 贴士</span><div>{tips}</div></div>'
    # skip_img 模式下不渲染 <img>，图片由 st.image 单独处理
    img_html = ""
    if not skip_img:
        img_url = img_data_url(card.get("image_keywords") or f"{city}{title}")
        img_html = f'<img class="gc-img" src="{img_url}" alt="{title}"/>' if img_url else ""
    return f"""
<div class="gc-card">
    {no_html}
    {img_html}
    <div class="gc-title">{title}</div>
    {sections}
</div>
"""


def item_card_html(item: dict, index: int = 0, city: str = "") -> str:
    """渲染美食/景点卡片（带图片，游伴星球风格）。"""
    name = item.get("name", "")
    desc = item.get("desc", "")
    area = item.get("area", "")
    price = item.get("price", "")
    img_prompt = item.get("image", f"{city}{name}")
    img_url = image_url(img_prompt, size="square")
    no_html = f'<div class="item-no">{index + 1}</div>' if index >= 0 else ""
    return f"""
<div class="sy-item-card">
    {no_html}
    <img class="item-img" src="{img_url}" alt="{name}" loading="lazy"
         onerror="this.style.display='none'"/>
    <div class="item-body">
        <div class="item-name">{name}</div>
        <div class="item-desc">{desc}</div>
        <div class="item-meta">
            <span class="item-area">📍 {area}</span>
            <span class="item-price">💰 {price}</span>
        </div>
    </div>
</div>
"""


def func_cards_html() -> str:
    """三大功能按钮卡 HTML。"""
    cards = [
        ("📋", "生成行程", "AI定制", "generate"),
        ("💬", "AI对话助手", "问我就好", "chat"),
        ("🎫", "我的行程", "随时查看", "my"),
    ]
    html = '<div class="sy-func-grid">'
    for icon, label, tag, key in cards:
        html += f'''<div class="sy-func-card" onclick="window.dispatchEvent(new CustomEvent('sy-func', {{detail:'{key}'}}))">
            <div class="func-icon">{icon}</div>
            <div class="func-label">{label}</div>
            <div class="func-tag">{tag}</div>
        </div>'''
    html += '</div>'
    return html
