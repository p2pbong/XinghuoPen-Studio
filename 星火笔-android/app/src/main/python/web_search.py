# -*- coding: utf-8 -*-
"""联网搜索（v1.06 多源中文搜索：搜狗主源 → Bing 中国 → 360 → DuckDuckGo 兜底；均无需 API Key）。

供主AI在不确知剧情走向时检索灵感 / AI 对话页联网搜索：输入查询词，
返回若干条「标题 + 摘要 + 链接」文本。网络不可用或解析失败时返回空列表，
调用方静默降级（不影响正常生成）。

v1.06 修复：实测 Bing 中国对长中文查询会被降级分词成单字（查「黑神话悟空 剧情设计」
返回「黑字词条/黑色壁纸」等无关结果）——主源改为搜狗（国内可达、中文相关度好）；
搜索超时封顶 20 秒（不再跟随设置页 300 秒的请求超时，避免生成管线被搜索挂死）。
"""
import re

import requests

import config

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
_MAX_RESULTS = 6
# v1.06 搜索专用超时：封顶 20s（生成管线内同步搜索，不能跟着设置页 300s 请求超时走，否则卡死验收/生成）
_SEARCH_TIMEOUT_CAP = 20.0


def _timeout():
    try:
        val = float(config.load_config().get("request_timeout", 300) or 300)
    except Exception:
        val = 300.0
    return min(val, _SEARCH_TIMEOUT_CAP)


def _clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def _get(url, params):
    return requests.get(url, params=params, headers=_HEADERS,
                        timeout=_timeout(), verify=False)


def _page(resp):
    return resp.content.decode(resp.encoding or "utf-8", errors="replace")


def search(query, max_results=_MAX_RESULTS):
    """搜索查询词，返回 [{"title","snippet","url"}]；异常时返回 []。

    v1.06 多源回退链：搜狗（主，国内可达+中文相关度好）→ Bing 中国 → 360 → DuckDuckGo。
    前一源返回非空即用；注意：源本身可达但结果无关（如 Bing 降级分词）无法程序判别，
    故把相关度最好的搜狗放最前。
    """
    if not (query or "").strip():
        return []
    q = query.strip()
    for fetcher in (_search_sogou, _search_bing, _search_so360, _search_duckduckgo):
        try:
            items = fetcher(q, max_results)
        except Exception:
            items = []
        if items:
            return items
    return []


def _search_sogou(query, max_results):
    """搜狗网页搜索：结果块 <div class="vrwrap">，标题 <h3 class="vr-title"><a href="/link?url=...">，
    摘要 id="cacheresult_summary_N"（部分块无摘要，允许空）。链接为相对路径需补全。"""
    resp = _get("https://www.sogou.com/web", {"query": query})
    if resp.status_code != 200:
        return []
    html = _page(resp)
    out, seen = [], set()
    for block in re.split(r'class="vrwrap"', html)[1:]:
        am = re.search(
            r'<h3[^>]*class="vr-title[^"]*"[^>]*>.*?<a[^>]*href="(/link\?url=[^"]+)"[^>]*>(.*?)</a>',
            block, re.S)
        if not am:
            continue
        url = "https://www.sogou.com" + am.group(1)
        title = _clean(re.sub(r"<[^>]+>", "", am.group(2)))
        if not title or url in seen:
            continue
        sm = re.search(r'id="cacheresult_summary_\d+"[^>]*>(.*?)</div>', block, re.S)
        snippet = _clean(re.sub(r"<[^>]+>", "", sm.group(1))) if sm else ""
        seen.add(url)
        out.append({"title": title, "snippet": snippet, "url": url})
        if len(out) >= max_results:
            break
    return out


def _search_bing(query, max_results):
    """Bing 中国：<li class="b_algo"> 内 h2>a（标题/链接）+ <p>（摘要）。"""
    resp = _get("https://cn.bing.com/search", {"q": query, "mkt": "zh-CN", "setlang": "zh-hans"})
    if resp.status_code != 200:
        return []
    html = _page(resp)
    out = []
    for block in re.split(r'<li class="b_algo"', html)[1:]:
        h2_m = re.search(r"<h2[^>]*>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.S)
        if not h2_m:
            h2_m = re.search(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not h2_m:
            continue
        url = h2_m.group(1)
        title = _clean(re.sub(r"<[^>]+>", "", h2_m.group(2)))
        snip_m = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        snippet = _clean(re.sub(r"<[^>]+>", "", snip_m.group(1))) if snip_m else ""
        if not title:
            continue
        out.append({"title": title, "snippet": snippet, "url": url})
        if len(out) >= max_results:
            break
    return out


def _search_so360(query, max_results):
    """360 搜索：结果块 <li class="res-list"> 内 <h3><a href="...">标题</a></h3> + <p>摘要。"""
    resp = _get("https://www.so.com/s", {"q": query})
    if resp.status_code != 200:
        return []
    html = _page(resp)
    out = []
    for block in re.split(r'class="res-list', html)[1:]:
        h3_m = re.search(r"<h3[^>]*>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.S)
        if not h3_m:
            continue
        url = h3_m.group(1)
        title = _clean(re.sub(r"<[^>]+>", "", h3_m.group(2)))
        snip_m = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        snippet = _clean(re.sub(r"<[^>]+>", "", snip_m.group(1))) if snip_m else ""
        if not title:
            continue
        out.append({"title": title, "snippet": snippet, "url": url})
        if len(out) >= max_results:
            break
    return out


def _search_duckduckgo(query, max_results):
    """DuckDuckGo HTML（国外网络兜底）。"""
    resp = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers=_HEADERS,
        timeout=_timeout(),
        verify=False,
    )
    if resp.status_code != 200:
        return []
    html = _page(resp)
    return _parse_results(html, max_results)


def _parse_results(html, max_results):
    """解析 DuckDuckGo HTML 结果页：提取 result__a（标题/链接）与 result__snippet（摘要）。"""
    out = []
    blocks = re.split(r'class="result\b', html)
    for block in blocks[1:]:
        title_m = re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        snip_m = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        if not title_m:
            continue
        url = title_m.group(1)
        title = _clean(re.sub(r"<[^>]+>", "", title_m.group(2)))
        snippet = _clean(re.sub(r"<[^>]+>", "", snip_m.group(1))) if snip_m else ""
        if "ad_domain" in block or ("ads" in url.lower() and "duckduckgo" not in url):
            continue
        out.append({"title": title, "snippet": snippet, "url": url})
        if len(out) >= max_results:
            break
    return out


def format_results(items):
    """把搜索结果格式化成给 LLM 的文本块；空结果返回空串。"""
    if not items:
        return ""
    lines = ["【联网搜索到的参考资料（仅作灵感参考，若与用户设定冲突以用户设定为准）】"]
    for i, it in enumerate(items, 1):
        lines.append("%d. %s" % (i, it.get("title", "")))
        if it.get("snippet"):
            lines.append("   %s" % it["snippet"])
        if it.get("url"):
            lines.append("   来源：%s" % it["url"])
    return "\n".join(lines)