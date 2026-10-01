"""工具层 —— ToolManager + 多种实时数据工具。

工具设计：
    BaseTool (抽象)
    ├── WebSearchTool       —— 联网搜索（Wikipedia + DuckDuckGo HTML）
    ├── WeatherTool         —— 天气查询（wttr.in 免费 API）
    ├── MapsTool            —— 地图/路线（OpenStreetMap Nominatim）
    ├── PlacesTool          —— 地点/餐厅（Overpass / Wikipedia POI）
    ├── CurrencyTool        —— 汇率查询（exchangerate.host 免费 API）
    └── ImageSearchTool     —— 图片搜索（Wikipedia 图片）

ToolManager：
    - 注册所有工具
    - 根据工具名分发调用
    - 失败隔离：单个工具失败返回空串，绝不返回假数据

所有工具都不依赖付费 API Key，使用免费公共真实 API。
"""
from __future__ import annotations

import json
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


def _http_get(url: str, timeout: int = 8, headers: Optional[Dict] = None) -> str:
    """HTTP GET 请求，失败返回空串。"""
    default_headers = {"User-Agent": "ShiYouji/4.0 (AI Travel Agent)"}
    if headers:
        default_headers.update(headers)
    try:
        req = urllib.request.Request(url, headers=default_headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _http_get_json(url: str, timeout: int = 8) -> Any:
    """HTTP GET JSON，失败返回 None。"""
    raw = _http_get(url, timeout=timeout)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _extract_city(text: str) -> str:
    """从查询文本中提取中国/全球城市名。"""
    import re
    cities = ["北京", "上海", "成都", "杭州", "西安", "广州", "重庆", "南京",
              "长沙", "武汉", "天津", "青岛", "厦门", "苏州", "大理", "丽江",
              "深圳", "香港", "澳门", "哈尔滨", "三亚", "大理", "昆明", "拉萨",
              "郑州", "济南", "大连", "无锡", "宁波", "绍兴", "桂林", "贵阳",
              "兰州", "银川", "西宁", "乌鲁木齐", "呼和浩特", "台北", "高雄",
              "Qingdao", "Hangzhou", "Chengdu", "Beijing", "Shanghai", "Guilin",
              "Nanjing", "Xi'an", "Chongqing", "Guangzhou", "Harbin", "Sanya"]
    for c in cities:
        if c in text:
            return c
    # 匹配 「在/去/到XX」或简单地名
    m = re.search(r"(?:在|去|到|的|如)([\u4e00-\u9fa5]{2,4})"  # 中文
                    r"|([A-Z][a-z]{2,})" , text)  # 英文
    if m:
        return (m.group(1) or m.group(2) or "").strip()
    return text.strip().split()[0] if text.strip() else ""


# =====================================================================
# 工具基类
# =====================================================================
class BaseTool(ABC):
    """所有工具的抽象基类。"""

    name: str = "tool"
    description: str = ""

    @abstractmethod
    def run(self, query: str, **kwargs) -> str:
        """执行工具，返回文本结果。失败返回空串或错误提示。"""

    def safe_run(self, query: str, **kwargs) -> str:
        """带异常隔离的执行。"""
        try:
            return self.run(query, **kwargs)
        except Exception as e:
            return f"[工具 {self.name} 执行失败：{e}]"


# =====================================================================
# Web Search —— Wikipedia + DuckDuckGo
# =====================================================================
class WebSearchTool(BaseTool):
    name = "web_search"
    description = "联网搜索信息，返回 Wikipedia 摘要或 DuckDuckGo 结果。"

    def run(self, query: str, **kwargs) -> str:
        if not query:
            return ""
        # 优先 Wikipedia
        wiki = self._wikipedia(query)
        if wiki:
            return wiki
        # 降级 DuckDuckGo HTML 解析
        return self._duckduckgo(query)

    def _wikipedia(self, query: str) -> str:
        url = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
               f"&prop=extracts&exintro&explaintext&titles="
               f"{urllib.parse.quote(query)}&redirects=1")
        data = _http_get_json(url, timeout=6)
        if not data:
            return ""
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid != "-1" and page.get("extract"):
                return page["extract"][:600]
        return ""

    def _duckduckgo(self, query: str) -> str:
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
        data = _http_get_json(url, timeout=6)
        if not data:
            return ""
        abstract = data.get("AbstractText", "")
        if abstract:
            return abstract[:600]
        # RelatedTopics
        topics = data.get("RelatedTopics", [])
        results = []
        for t in topics[:3]:
            if isinstance(t, dict) and t.get("Text"):
                results.append(t["Text"])
        return "\n".join(results)[:600]


# =====================================================================
# Weather —— wttr.in 免费天气 API
# =====================================================================
class WeatherTool(BaseTool):
    name = "weather"
    description = "查询指定城市的当前天气和未来预报。"

    def run(self, query: str, **kwargs) -> str:
        city = query.strip() or "北京"
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1&lang=zh"
        data = _http_get_json(url, timeout=8)
        if not data:
            return f"暂无 {city} 的天气数据（网络不可用）。"
        try:
            current = data["current_condition"][0]
            desc = current.get("lang_zh", [{}])[0].get("value",
                    current.get("weatherDesc", [{}])[0].get("value", ""))
            temp = current.get("temp_C", "?")
            feels = current.get("FeelsLikeC", "?")
            humidity = current.get("humidity", "?")
            wind = current.get("windspeedKmph", "?")
            result = (f"🌤️ {city} 当前天气：{desc}，温度 {temp}°C"
                      f"（体感 {feels}°C），湿度 {humidity}%，风速 {wind} km/h。")
            # 未来 3 天预报
            forecasts = data.get("weather", [])[:3]
            for f in forecasts:
                date = f.get("date", "")
                max_t = f.get("maxtempC", "?")
                min_t = f.get("mintempC", "?")
                d = f.get("hourly", [{}])[4] if len(f.get("hourly", [])) > 4 else {}
                fd = d.get("lang_zh", [{}])[0].get("value",
                     d.get("weatherDesc", [{}])[0].get("value", ""))
                result += f"\n📅 {date}：{fd}，{min_t}~{max_t}°C"
            return result
        except Exception as e:
            return f"天气数据解析失败：{e}"


# =====================================================================
# Maps —— OpenStreetMap Nominatim 地理编码
# =====================================================================
class MapsTool(BaseTool):
    name = "maps"
    description = "查询地点坐标、地址、路线信息。"

    def run(self, query: str, **kwargs) -> str:
        if not query:
            return ""
        url = (f"https://nominatim.openstreetmap.org/search?"
               f"q={urllib.parse.quote(query)}&format=json&limit=3&accept-language=zh")
        data = _http_get_json(url, timeout=8)
        if not data:
            return f"未找到「{query}」的位置信息。"
        results = []
        for item in data:
            name = item.get("display_name", query)
            lat = item.get("lat", "")
            lon = item.get("lon", "")
            results.append(f"📍 {name}\n   坐标：{lat}, {lon}")
        return "\n\n".join(results)


# =====================================================================
# Places —— 附近景点/餐厅（Overpass API + Wikipedia POI）
# =====================================================================
class PlacesTool(BaseTool):
    name = "places"
    description = "查询指定城市的景点、餐厅、购物地点。"

    def run(self, query: str, **kwargs) -> str:
        city = _extract_city(query) or query.strip() or "北京"
        # 餐厅/美食类 → Wikipedia 搜「城市 美食/老字号/小吃」
        if any(k in query for k in ["餐厅", "饭店", "店", "吃", "美食", "菜", "小吃", "老字号"]):
            food = self._wiki_food(city)
            if food:
                return food
        # 景点类 → Wikipedia 搜「城市 景点」
        wiki = self._wiki_poi(city)
        if wiki:
            return wiki
        return f"暂无 {city} 的实时地点数据。可结合旅行规划师推荐。"

    def _wiki_food(self, city: str) -> str:
        """Wikipedia 搜索城市美食/老字号餐厅，返回真实条目摘要。"""
        import urllib.parse
        # 尝试多个搜索词，取有结果的
        for kw in [f"{city} 美食", f"{city} 小吃", f"{city} 老字号", f"{city} 菜"]:
            url = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
                   f"&list=search&srlimit=6&srsearch={urllib.parse.quote(kw)}")
            data = _http_get_json(url, timeout=8)
            if not data:
                continue
            hits = data.get("query", {}).get("search", [])
            if not hits:
                continue
            lines = [f"🍽️ {city} 美食/餐厅（来自 Wikipedia）："]
            for h in hits:
                title = h.get("title", "")
                snippet = (h.get("snippet", "")
                           .replace('<span class="searchmatch">', "")
                           .replace("</span>", ""))
                if title and snippet:
                    lines.append(f"• {title}：{snippet[:70]}")
            if len(lines) > 1:
                return "\n".join(lines)
        return ""

    def _wiki_poi(self, city: str) -> str:
        url = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
               f"&list=search&srsearch={urllib.parse.quote(city + ' 景点')}"
               f"&srlimit=5")
        data = _http_get_json(url, timeout=6)
        if not data:
            return ""
        results = data.get("query", {}).get("search", [])
        if not results:
            return ""
        lines = [f"🏛️ {city} 相关景点/地标："]
        for r in results:
            title = r.get("title", "")
            snippet = r.get("snippet", "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")
            lines.append(f"• {title}：{snippet[:80]}")
        return "\n".join(lines)


# =====================================================================
# Currency —— 汇率查询
# =====================================================================
class CurrencyTool(BaseTool):
    name = "currency"
    description = "查询货币汇率，支持 CNY/USD/EUR/JPY 等。"

    def run(self, query: str, **kwargs) -> str:
        # 解析："100 USD to CNY" 或 "美元兑人民币"
        import re
        amount = 100.0
        from_cur = "USD"
        to_cur = "CNY"

        m = re.search(r"(\d+\.?\d*)\s*([A-Za-z]{3})", query)
        if m:
            amount = float(m.group(1))
            from_cur = m.group(2).upper()
        if "人民币" in query or "CNY" in query.upper():
            to_cur = "CNY"
        if "美元" in query or "USD" in query.upper():
            if from_cur != "USD":
                to_cur = "USD"
                from_cur = from_cur if from_cur else "CNY"
            else:
                to_cur = "CNY"

        url = f"https://api.exchangerate.host/latest?base={from_cur}&symbols={to_cur}"
        data = _http_get_json(url, timeout=8)
        if not data or not data.get("rates"):
            return "暂无汇率数据（网络不可用）。"
        rate = data["rates"].get(to_cur, 0)
        if not rate:
            return f"未找到 {from_cur} 到 {to_cur} 的汇率。"
        converted = amount * rate
        return (f"💱 汇率：1 {from_cur} = {rate:.4f} {to_cur}\n"
                f"   {amount:.2f} {from_cur} = {converted:.2f} {to_cur}")


# =====================================================================
# Image Search —— Wikipedia 图片
# =====================================================================
class ImageSearchTool(BaseTool):
    name = "image_search"
    description = "搜索相关图片（返回 Wikipedia 图片 URL）。"

    def run(self, query: str, **kwargs) -> str:
        if not query:
            return ""
        url = (f"https://zh.wikipedia.org/w/api.php?format=json&action=query"
               f"&prop=pageimages&titles={urllib.parse.quote(query)}"
               f"&pithumbsize=400&redirects=1")
        data = _http_get_json(url, timeout=6)
        if not data:
            return ""
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            thumb = page.get("thumbnail", {}).get("source", "")
            if thumb:
                return thumb
        return ""


# =====================================================================
# ToolManager —— 工具注册与分发
# =====================================================================
class ToolManager:
    """统一工具管理器。注册所有真实工具（Wikipedia/wttr.in/OSM 等公共 API），
    按名称分发，失败隔离（失败返回空串，由 Agent 决定如何降级措辞）。"""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(WebSearchTool())
        self.register(WeatherTool())
        self.register(MapsTool())
        self.register(PlacesTool())
        self.register(CurrencyTool())
        self.register(ImageSearchTool())

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, str]]:
        """返回所有工具的名称和描述，供 LLM 选择。"""
        return [{"name": t.name, "description": t.description}
                for t in self._tools.values()]

    def call(self, tool_name: str, query: str, **kwargs) -> str:
        """调用指定真实工具。失败返回空串（绝不返回假数据）。"""
        tool = self._tools.get(tool_name)
        if not tool:
            return ""
        try:
            return tool.safe_run(query, **kwargs) or ""
        except Exception:
            return ""

    def call_for_agent(self, agent_name: str, query: str,
                       context: Optional[Dict] = None) -> str:
        """Agent 调用真实工具的便捷方法。
        根据 Agent 类型和查询自动选择合适的工具。"""
        q = query or ""

        # 根据关键词自动选择工具
        if any(k in q for k in ["天气", "下雨", "温度", "穿什么", "weather"]):
            return self.call("weather", q)
        if any(k in q for k in ["汇率", "美元", "人民币", "兑换", "currency"]):
            return self.call("currency", q)
        if any(k in q for k in ["怎么去", "路线", "坐标", "位置", "地址", "map"]):
            return self.call("maps", q)
        if any(k in q for k in ["附近", "餐厅", "景点", "在哪", "place"]):
            return self.call("places", q)
        # 默认 web search
        return self.call("web_search", q)
