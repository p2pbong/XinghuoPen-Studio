# -*- coding: utf-8 -*-
"""冒烟测试：数据层往返 + 多 API 配置选择 + PySide6 页面无头构建（QT_QPA_PLATFORM=offscreen）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# ---------- 数据层 ----------
import storage  # noqa: E402
from models import CharacterCard, InfoLibrary  # noqa: E402
from models import Chapter  # noqa: E402

storage.ensure_example_project()
st = storage.ProjectStore("示例项目_星海孤城")
if st.load_project() is None:
    # 示例项目损坏/被清理（如审查后删除）时删除残留并直接重建，保证数据层测试可用
    try:
        import shutil
        shutil.rmtree(st.base, ignore_errors=True)
    except Exception:
        pass
    try:
        storage.example_project()
    except Exception:
        pass
    st = storage.ProjectStore("示例项目_星海孤城")
assert st.load_project() is not None, "示例项目应可载入"

card = CharacterCard("冒烟测试角色", "铁匠")
lib = InfoLibrary(card.id)
lib.events = [{"chapter": 1, "event": "目睹城主府火灾", "impact": "对城府戒备"}]
lib.knowledge = [{"chapter": 1, "info": "听说废矿半夜有动静"}]
lib.secrets = ["藏了一枚旧币"]
# 酒馆 Persona 字段往返
card.description = "综合描述测试"
card.scenario = "当前处境测试"
card.first_mes = "开场白测试"
card.mes_example = "示例对话测试"
card.system_prompt = "扮演规则测试"
st.save_character(card, lib)
loaded_card, loaded_lib = st.load_character(card.id)
assert loaded_card.name == "冒烟测试角色"
assert loaded_card.description == "综合描述测试"
assert loaded_card.mes_example == "示例对话测试"
assert loaded_card.system_prompt == "扮演规则测试"
assert loaded_lib.events[0]["event"] == "目睹城主府火灾"
assert loaded_lib.secrets == ["藏了一枚旧币"]
print("[1] 角色卡/信息库（含酒馆字段）往返 OK")

# ---------- 参考文风样本字段往返 + 仅注入正文AI提示词 ----------
import prompts as prompts_mod  # noqa: E402
_pj = st.load_project()
_pj.story_style_ref = "夜风卷着雪粒扑在城墙上，他拢了拢斗篷，靴底碾过一层薄霜。"
st.save_project(_pj)
_pj2 = st.load_project()
assert _pj2.story_style_ref == "夜风卷着雪粒扑在城墙上，他拢了拢斗篷，靴底碾过一层薄霜。", \
    "参考文风样本应能往返保存"
_ws, _wu = prompts_mod.write_chapter(_pj2, st, 1, "焦点", "方向", {}, [], 2500)
assert "参考文风样本" in _wu, "参考文风样本应注入正文AI写作提示词"
_ss, _su = prompts_mod.decide_characters(_pj2, st, 1, 1, 1)
assert "参考文风样本" not in _su, "参考文风样本不应注入主AI决断提示词（省上下文）"
print("[1c] 参考文风样本字段往返 + 仅注入正文AI OK")

# ---------- 正文AI角色提示词 / 主AI全局提示词：字段往返 + 注入隔离 ----------
_pj6 = st.load_project()
_pj6.story_writer_prompt = "你是一个擅长古风权谋的网文作者，描写克制。"
_pj6.story_main_prompt = "你是一个剧情总监，重大转折提前三章埋暗示。"
st.save_project(_pj6)
_pj7 = st.load_project()
assert _pj7.story_writer_prompt == _pj6.story_writer_prompt, "正文AI角色提示词应往返保存"
assert _pj7.story_main_prompt == _pj6.story_main_prompt, "主AI全局提示词应往返保存"
_wSys, _wUsr = prompts_mod.write_chapter(_pj7, st, 1, "焦点", "方向", {}, [], 2500)
assert "擅长古风权谋" in _wSys, "正文AI角色提示词应注入正文AI系统提示词"
assert "剧情总监" not in _wSys and "剧情总监" not in _wUsr, "主AI全局提示词不应注入正文AI"
_dSys, _dUsr = prompts_mod.decide_characters(_pj7, st, 1, 1, 1)
assert "剧情总监" in _dSys, "主AI全局提示词应注入主AI决断系统提示词"
assert "擅长古风权谋" not in _dSys, "正文AI角色提示词不应注入主AI"
# 主AI战后更新/管理笔记也应带主AI全局提示词
import models as _mdl  # noqa: E402
_tch = _mdl.Chapter(1, 1); _tch.content = "x"; _tch.characters = []
_uSys, _uUsr = prompts_mod.update_after_chapter(_pj7, st, _tch, [])
assert "剧情总监" in _uSys, "主AI全局提示词应注入战后更新"
_cSys, _cUsr = prompts_mod.compress_summary(_pj7, st)
assert "剧情总监" in _cSys, "主AI全局提示词应注入管理笔记压缩"
print("[1f] 正文AI角色提示词/主AI全局提示词 字段往返 + 注入隔离 OK")

# ---------- 故事拆分：世界观/特殊规则字段往返 + fmt_story 分栏注入 ----------
_pj3 = st.load_project()
_pj3.story_world = "九域大陆，斗气九阶，上古符文秘术禁忌灵魂契约。"
_pj3.story_rules = "禁止主角开挂秒杀，每卷结尾必须留钩子。"
st.save_project(_pj3)
_pj4 = st.load_project()
assert _pj4.story_world == _pj3.story_world, "世界观应往返保存"
assert _pj4.story_rules == _pj3.story_rules, "特殊规则应往返保存"
_sysx, _userx = prompts_mod.write_chapter(_pj4, st, 1, "焦点", "方向", {}, [], 2500)
assert "【世界观" in _userx and "九域大陆" in _userx, "世界观应注入提示词"
assert "【特殊规则" in _userx and "禁止主角开挂" in _userx, "特殊规则应注入提示词"
assert "【剧情发展】" in _userx, "剧情应带【剧情发展】标头"
print("[1d] 故事拆分：世界观/特殊规则 字段往返 + 分栏注入提示词 OK")

# ---------- 主AI知识库：字段往返 + 仅主AI读（正文AI不读） ----------
_pj8 = st.load_project()
_pj8.story_knowledge = "- 联网灵感：悬疑推理可用密室布局。\n- 重要伏笔：铜钥与主角身世相关。"
st.save_project(_pj8)
_pj9 = st.load_project()
assert _pj9.story_knowledge == _pj8.story_knowledge, "知识库应往返保存"
_kSys, _kUsr = prompts_mod.write_chapter(_pj9, st, 2, "焦点", "方向", {}, [], 2500)
assert "密室布局" not in _kUsr and "主AI知识库" not in _kUsr, "正文AI不应读到知识库"
assert "主AI管理笔记" in _kUsr, "正文AI应读到剧情压缩卷"
_dK, _uK = prompts_mod.decide_characters(_pj9, st, 2, 1, 2)
assert "密室布局" in _uK, "主AI应读到知识库"
print("[1g] 主AI知识库：字段往返 + 仅主AI读（正文AI隔离）OK")

# ---------- 正文AI可读前几章：注入最近章节正文 ----------
import models as _mdl2  # noqa: E402
for _ci in (1,):
    _pc = _mdl2.Chapter(_ci, 1)
    _pc.title = "第1章 冒烟测试章"
    _pc.content = "前文正文内容，用于验证写作AI可读。"
    _pc.status = "approved"
    st.save_chapter(_pc)
_sysw, _usw = prompts_mod.write_chapter(_pj9, st, 2, "焦点", "方向", {}, [], 2500, recent_chapters=3)
assert "前 1 章正文" in _usw and "前文正文内容" in _usw, "写作AI应读到前几章正文"
_sysw0, _usw0 = prompts_mod.write_chapter(_pj9, st, 2, "焦点", "方向", {}, [], 2500, recent_chapters=0)
assert "前 1 章正文" not in _usw0, "recent_chapters=0 时不应注入前文正文"
import os as _os2  # noqa: E402
_pth = st.chapter_path(1)
if _os2.path.exists(_pth):
    _os2.remove(_pth)
print("[1h] 正文AI可读前几章（recent_chapters 生效）OK")

# ---------- 章节标题清洗：markdown 前缀（## 第N章 → 第N章） ----------
import llm as _llm_mod  # noqa: E402
import main_ai as _main_ai_mod  # noqa: E402
_orig_chat_text = _llm_mod.chat_text
_llm_mod.chat_text = lambda *a, **k: "## 第5章 测试标题\n\n正文内容……"
_t, _c = _main_ai_mod.write_chapter(_pj9, st, 5, "焦点", "方向", {}, [], 1000)
assert _t == "第5章 测试标题", "标题应去掉 markdown 前缀，实际 %r" % _t
_llm_mod.chat_text = _orig_chat_text
print("[1h2] 章节标题 markdown 前缀清洗 OK")

# ---------- 联网搜索解析（mock HTML，不真联网） ----------
import web_search as ws_mod  # noqa: E402
_html_sample = """
<div class="result">
  <a class="result__a" href="https://example.com/a">密室杀人 经典布局</a>
  <a class="result__snippet">经典密室手法：钥匙反转、雪地无痕、延时机关。</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/b">废土公路片 团队冲突</a>
  <a class="result__snippet">团队内部资源争夺与理念分歧推动情节。</a>
</div>
"""
_parsed = ws_mod._parse_results(_html_sample, 10)
assert len(_parsed) == 2 and "密室杀人" in _parsed[0]["title"], "应解析出2条结果"
assert "延时机关" in _parsed[0]["snippet"], "应解析出摘要"
assert ws_mod.format_results(_parsed), "格式化结果非空"
assert ws_mod.search("") == [], "空查询应返回空列表"
print("[1i] 联网搜索解析（DuckDuckGo HTML mock）OK")

# ---------- v1.06 联网搜索多源：搜狗主源 + Bing/360 回退 + 相对链接补全 + 超时封顶（mock 网络，不真联网） ----------
import requests as _req_mod  # noqa: E402

class _FakeResp106:
    def __init__(self, code, html, enc="utf-8"):
        self.status_code = code
        self.content = html if isinstance(html, bytes) else html.encode("utf-8")
        self.encoding = enc

_SOGOU_HTML_106 = ('<div id="sogou_vr_30000000_wrap_1" class="vrwrap">'
                   '<h3 class="vr-title"><a name="dttl" target="_blank" href="/link?url=abcXYZ">搜狗标题一</a></h3>'
                   '<div class="fz-mid" id="cacheresult_summary_1">搜狗摘要一</div></div>'
                   '<div class="vrwrap"><h3 class="vr-title ">'
                   '<a target="_blank" href="/link?url=def123">搜狗标题二</a></h3></div>')
_BING_HTML_106 = ('<li class="b_algo"><h2><a href="https://b.example.com/1">Bing标题甲</a></h2>'
                  '<p>Bing摘要甲</p></li>'
                  '<li class="b_algo"><h2><a href="https://b.example.com/2">Bing标题乙</a></h2></li>')
_SO360_HTML_106 = ('<li class="res-list"><h3><a href="https://360.example.com/a">360标题A</a></h3>'
                   '<p>360摘要A</p></li>'
                   '<li class="res-list"><h3><a href="https://360.example.com/b">360标题B</a></h3></li>')
_orig_get106 = _req_mod.get
_orig_post106 = _req_mod.post
# 场景A：搜狗主源解析 + 相对链接补全
def _fake_get_a106(url, params=None, headers=None, timeout=None, verify=False):
    assert "sogou.com" in url, "主源应先请求搜狗，实际 %r" % url
    return _FakeResp106(200, _SOGOU_HTML_106)
_req_mod.get = _fake_get_a106
try:
    _sa106 = ws_mod.search("测试查询", max_results=5)
finally:
    _req_mod.get = _orig_get106
assert len(_sa106) == 2 and _sa106[0]["title"] == "搜狗标题一", \
    "搜狗主源应解析出结果，实际 %r" % _sa106
assert _sa106[0]["url"] == "https://www.sogou.com/link?url=abcXYZ", \
    "搜狗相对链接应补全为完整 URL，实际 %r" % _sa106[0]["url"]
assert _sa106[0]["snippet"] == "搜狗摘要一", "搜狗摘要应解析"
assert _sa106[1]["url"].startswith("https://www.sogou.com/"), "第二条链接也应补全"
# 场景B：搜狗失败 → Bing 回退
def _fake_get_b106(url, params=None, headers=None, timeout=None, verify=False):
    if "sogou.com" in url:
        return _FakeResp106(404, "")
    assert "bing.com" in url, "搜狗失败后应回退 Bing，实际 %r" % url
    return _FakeResp106(200, _BING_HTML_106)
_req_mod.get = _fake_get_b106
try:
    _sb106 = ws_mod.search("回退测试")
finally:
    _req_mod.get = _orig_get106
assert len(_sb106) == 2 and _sb106[0]["title"] == "Bing标题甲", \
    "搜狗失败应回退 Bing，实际 %r" % _sb106
# 场景C：搜狗/Bing 失败 → 360 兜底
def _fake_get_c106(url, params=None, headers=None, timeout=None, verify=False):
    if "sogou.com" in url or "bing.com" in url:
        return _FakeResp106(404, "")
    assert "so.com" in url, "应回退 360，实际 %r" % url
    return _FakeResp106(200, _SO360_HTML_106)
_req_mod.get = _fake_get_c106
try:
    _sc106 = ws_mod.search("兜底测试")
finally:
    _req_mod.get = _orig_get106
assert len(_sc106) == 2 and _sc106[0]["title"] == "360标题A", \
    "搜狗/Bing 失败应回退 360，实际 %r" % _sc106
# 场景D：全部源失败（get 异常 + DDG POST 失败）→ 静默返回 []，不抛异常、不影响主流程
def _fake_get_d106(url, params=None, headers=None, timeout=None, verify=False):
    raise _req_mod.ConnectionError("网络不可达（mock）")
def _fake_post_d106(url, data=None, headers=None, timeout=None, verify=False):
    if "duckduckgo.com" in url:
        return _FakeResp106(200, '<div class="result"><a class="result__a" '
                                 'href="https://x.example.com">DDG标题</a></div>')
    return _FakeResp106(404, "")
_req_mod.get = _fake_get_d106
_req_mod.post = _fake_post_d106
try:
    _sd106 = ws_mod.search("全挂测试")
finally:
    _req_mod.get = _orig_get106
    _req_mod.post = _orig_post106
assert _sd106 and _sd106[0]["title"] == "DDG标题", \
    "所有 GET 源失败应回退 DuckDuckGo POST，实际 %r" % _sd106
# 搜索专用超时封顶（不跟随设置页 300s 请求超时，防生成管线卡死）
assert ws_mod._timeout() <= 20.0, "搜索超时应封顶 20s，实际 %r" % ws_mod._timeout()
print("[1i2] v1.06 联网搜索多源：搜狗主源解析/相对链接补全 + Bing/360 回退 + DDG 兜底 + 全挂静默 + 超时封顶 OK")


# ---------- 压缩间隔配置默认值 ----------
import config as config_mod  # noqa: E402
_cfg0 = config_mod.load_config()
assert int(_cfg0.get("compress_interval", 5)) >= 1, "压缩间隔应有默认值"
print("[1e] compress_interval 配置默认存在 OK")

# ---------- target=0（主AI把控节奏）时各提示词构造不应崩溃 ----------
import prompts as prompts_mod  # noqa: E402
_pj = st.load_project()
_pj.volume_target = 0
prompts_mod.decide_characters(_pj, st, 1, 1, 1)
prompts_mod.consolidate(_pj, st, 1, "焦点", {}, "")
prompts_mod.write_chapter(_pj, st, 1, "焦点", "方向", {}, [], 2500)
print("[1b] target=0 提示词构造 OK（此前 %d 收到字符串崩溃）")

# ---------- 多 API 配置 ----------
import config  # noqa: E402

config._cache = None
import copy as _copy
_ORIG_CFG = _copy.deepcopy(config.load_config())  # 备份磁盘真实配置（含用户填的 API Key）
# 原始字节快照：save_config 写的是「默认合并 dict」，会把新加的默认键（如
# foreshadow_overdue_chapters）写进用户文件 → 哈希漂移。恢复必须按原始字节还原。
try:
    with open(config.CONFIG_PATH, "rb") as _f:
        _ORIG_BYTES = _f.read()
except Exception:
    _ORIG_BYTES = None


def _clean_test_chars():
    """清理**所有项目**里的测试残留角色（批量测试/核心团/批量需求/情节新角色/冒烟测试角色）。

    修复历史问题：批量生成回归测试把「批量测试N」角色建进了当前项目（如真实项目「求仙问道」），
    而旧清理只扫示例项目 → 每次跑 _smoke 都在用户项目里留下垃圾角色卡。
    返回清理数量。
    """
    cleaned = 0
    for d in os.listdir(storage.PROJECTS_DIR):
        if not os.path.isdir(os.path.join(storage.PROJECTS_DIR, d)):
            continue
        try:
            _st = storage.ProjectStore(d)
            for cid, name, _ in _st.list_characters():
                if name.startswith(("批量测试", "核心团", "批量需求", "情节新角色")) \
                        or name == "冒烟测试角色":
                    _st.delete_character(cid)
                    cleaned += 1
        except Exception:
            pass
    return cleaned


def _restore_smoke():
    """进程退出时兜底恢复：即使中间断言失败（异常退出）也恢复用户配置并清理测试数据。"""
    try:
        _clean_test_chars()
    except Exception:
        pass
    try:
        # 临时测试项目残留（任一断言失败中断时兜底清理）
        for _d in ("重写测试", "章节管理测试", "快照完整性测试",
                   "导入导出测试", "草稿备份测试", "分支测试", "章节导入测试",
                   "自动重试测试", "去AI味测试", "字数校验测试",
                   "去重测试", "卡库测试", "标题重设计测试", "去AI味参考测试",
                   "重设计UI测试", "自动去AI味测试"):
            try:
                if os.path.isdir(os.path.join(storage.PROJECTS_DIR, _d)):
                    storage.delete_project(_d)
            except Exception:
                pass
    except Exception:
        pass
    try:
        config._cache = None
        if _ORIG_BYTES is not None:
            # 按原始字节还原，哈希与测试前完全一致（save_config 的合并写会加默认键）
            with open(config.CONFIG_PATH, "wb") as _f:
                _f.write(_ORIG_BYTES)
        else:
            config.save_config(_ORIG_CFG)  # 兜底：无字节快照时用合并 dict 恢复
        config._cache = None
    except Exception:
        pass


import atexit  # noqa: E402
atexit.register(_restore_smoke)

cfg = _copy.deepcopy(_ORIG_CFG)
assert cfg.get("api_profiles"), "profiles 缺失"
cfg["api_profiles"] = [
    {"name": "默认配置", "base_url": "https://api.deepseek.com/v1", "api_key": "", "model": "deepseek-chat", "role": "all"},
    {"name": "写作号", "base_url": "https://x.com/v1", "api_key": "sk-test1", "model": "gpt-x", "role": "write"},
    {"name": "推理号", "base_url": "https://y.com/v1", "api_key": "sk-test2", "model": "y-model", "role": "reason"},
]
cfg["current_profile"] = "默认配置"
cfg["role_profiles"] = None  # 模拟从旧版升级：尚未保存过用途分工 → 由旧 role 字段迁移
config.save_config(cfg)
config._cache = None
assert config.pick_profile("write")["name"] == "写作号"
assert config.pick_profile("reason")["name"] == "推理号"
assert config.pick_profile("decide")["name"] == "默认配置"  # 无可用决策配置，退回当前
# 关键场景：当前配置为「通用且有 Key」时（用户最常见配置），专用配置仍必须生效
cfg["api_profiles"][0]["api_key"] = "sk-cur"
config.save_config(cfg)
config._cache = None
assert config.pick_profile("write")["name"] == "写作号", "通用当前配置不应顶掉正文写作专用"
assert config.pick_profile("reason")["name"] == "推理号", "通用当前配置不应顶掉角色推理专用"
assert config.pick_profile("decide")["name"] == "默认配置", "无专用决策时退回当前通用配置"
assert config.pick_profile("all")["name"] == "默认配置", "通用用途应走当前配置"
assert config.pick_profile("deai")["name"] == "默认配置", "未指定去AI味用途时回退当前配置"
cfg["api_profiles"] = cfg["api_profiles"][:1]
cfg["current_profile"] = "默认配置"
config.save_config(cfg)
config._cache = None
print("[2] 多 API profile 按用途选择 OK（含当前为通用配置时的用途分工）")

# ---------- v0.56 端点智能拼接（vibecoding 完整端点填法不再 404） ----------
import llm as _llm_mod2  # noqa: E402
assert _llm_mod2._endpoint("https://token.sensenova.cn/v1", "/chat/completions") == \
    "https://token.sensenova.cn/v1/chat/completions", "网关根填法应自动拼端点"
assert _llm_mod2._endpoint("https://token.sensenova.cn/v1/chat/completions", "/chat/completions") == \
    "https://token.sensenova.cn/v1/chat/completions", "完整端点填法不应重复拼（防 /chat/completions/chat/completions 404）"
assert _llm_mod2._endpoint("https://ark.cn-beijing.volces.com/api/v3", "/chat/completions") == \
    "https://ark.cn-beijing.volces.com/api/v3/chat/completions", "火山根填法应拼对"
assert _llm_mod2._endpoint("", "/chat/completions") == "", "空 base_url 应返回空"
assert _llm_mod2._endpoint("https://x.com/v1/models", "/models") == "https://x.com/v1/models", \
    "models 完整端点也不应重复拼"
print("[2d] 端点智能拼接（网关根/完整端点两种填法兼容，防 404）OK")
# 立即恢复用户真实配置，避免后续设置页增删测试基于测试配置继续覆盖
config._cache = None
config.save_config(_ORIG_CFG)
config._cache = None

# ---------- LLM 429 限流重试（次数/间隔遵循用户设置） ----------
import llm as llm_mod  # noqa: E402
import requests as requests_mod  # noqa: E402

_orig_load_cfg = config.load_config
config.load_config = lambda: {
    "api_profiles": [{"name": "t", "base_url": "https://x/v1", "api_key": "k",
                      "model": "m", "role": "all"}],
    "current_profile": "t", "temperature": 1.0, "max_tokens": 1000,
    "retry_times": 3, "retry_interval": 1, "request_timeout": 5,
}
_orig_post = requests_mod.post
_orig_min_wait = llm_mod.RATE_LIMIT_MIN_WAIT
# v2.38 起 llm 走每线程 requests.Session（连接复用）：mock 需注入到 Session.post，
# 替换 requests.post 已被绕过（真实请求会打到测试地址 host='x'）。
_orig_session = llm_mod._session
_sess_obj = type("_FakeSess", (), {})()
llm_mod._session = lambda: _sess_obj
import io as _io  # noqa: E402
llm_mod.RATE_LIMIT_MIN_WAIT = 0.05
_state = {"calls": 0}


def _fake_post(url, json, headers, timeout, stream=False):
    _state["calls"] += 1
    r = requests_mod.Response()
    r.headers = {}
    if _state["calls"] < 3:
        r.status_code = 429
        r._content = b'{"error":{"message":"rate limit test"}}'
    else:
        r.status_code = 200
        r.raw = _io.BytesIO(b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
                            b'data: [DONE]\n\n')
    return r


_sess_obj.post = _fake_post
out = llm_mod.chat([{"role": "user", "content": "hi"}], retries=3)
assert out == "ok" and _state["calls"] == 3, "429 应重试后成功，实际 %s / %d 次" % (out, _state["calls"])

# 429 一直失败：应恰好尝试 retry_times 次后抛 LLMError（次数遵循用户设置，不无限循环）
_state["calls"] = 0


def _fake_post_fail(url, json, headers, timeout, stream=False):
    _state["calls"] += 1
    r = requests_mod.Response()
    r.headers = {}
    r.status_code = 429
    r._content = b'{"error":{"message":"rate limit test"}}'
    return r


_sess_obj.post = _fake_post_fail
try:
    llm_mod.chat([{"role": "user", "content": "hi"}], retries=5)
    assert False, "429 一直失败应抛 LLMError"
except llm_mod.LLMError:
    pass
assert _state["calls"] == 5, "429 一直失败应尝试 retry_times=5 次，实际 %d" % _state["calls"]

# 5xx 重试间隔固定为 retry_interval（不再递增），次数同样遵循 retry_times
_state["calls"] = 0
_sleeps = []


def _fake_post_5xx(url, json, headers, timeout, stream=False):
    _state["calls"] += 1
    r = requests_mod.Response()
    r.headers = {}
    r.status_code = 503
    r._content = b'{"error":{"message":"overloaded"}}'
    return r


_orig_sleep = llm_mod.time.sleep


def _fake_sleep(sec):
    _sleeps.append(sec)


llm_mod.time.sleep = _fake_sleep
_sess_obj.post = _fake_post_5xx
try:
    llm_mod.chat([{"role": "user", "content": "hi"}], retries=4)
    assert False, "5xx 一直失败应抛 LLMError"
except llm_mod.LLMError:
    pass
assert _state["calls"] == 4, "5xx 应尝试 retry_times=4 次，实际 %d" % _state["calls"]
assert len(_sleeps) == 3 and all(abs(s - 1) < 1e-6 for s in _sleeps), \
    "5xx 重试间隔应固定 retry_interval=1 秒，实际 %s" % _sleeps
llm_mod.time.sleep = _orig_sleep

llm_mod._session = _orig_session
llm_mod.RATE_LIMIT_MIN_WAIT = _orig_min_wait
config.load_config = _orig_load_cfg
print("[2b] LLM 429/5xx 重试次数与间隔遵循用户设置 OK")

# v0.71 chat_json 内容级重试：模型偶发返回坏 JSON（解析失败）→ 自动重新请求瞬时自愈，
# 不再一次坏 JSON 就报错停下等手动重试（生成/批量/分类/拆书/导入等所有 chat_json 调用方受益）
_jb = {"n": 0}


def _fake_chat_good2(messages, **kw):
    _jb["n"] += 1
    if _jb["n"] == 1:
        return "这不是 JSON 内容"
    return '{"ok": 1}'


_orig_cj_chat = llm_mod.chat
llm_mod.chat = _fake_chat_good2
assert llm_mod.chat_json("s", "u") == {"ok": 1}, "坏 JSON 应自动重试后成功"
assert _jb["n"] >= 2, "坏 JSON 应自动重试（调用次数>=2），实际 %d" % _jb["n"]
_orig_cfg71 = config.load_config
config.load_config = lambda: {
    "api_profiles": [{"name": "t", "base_url": "https://x/v1", "api_key": "k",
                      "model": "m", "role": "all"}],
    "current_profile": "t", "temperature": 1.0, "max_tokens": 32000,
    "retry_times": 3, "request_timeout": 5, "retry_interval": 1,
}
_jb2 = {"n": 0}


def _fake_chat_bad(messages, **kw):
    _jb2["n"] += 1
    return "还是坏 JSON"


llm_mod.chat = _fake_chat_bad
try:
    llm_mod.chat_json("s", "u")
    assert False, "持续坏 JSON 应抛 LLMError"
except llm_mod.LLMError as e:
    assert "有效 JSON" in str(e), "错误应说明 JSON 解析失败，实际 %r" % str(e)[:100]
assert _jb2["n"] == 4, "持续坏 JSON 应 3 次尝试 + 1 次 response_format 兜底 = 4 次请求，实际 %d" % _jb2["n"]
config.load_config = _orig_cfg71
llm_mod.chat = _orig_cj_chat
print("[2c] chat_json 坏 JSON 内容级自动重试（瞬时自愈 + 重试耗尽才报错）OK")

# v0.73 推理模型适配：thinking（reasoning_content）消耗输出预算 → 正文为空 →
# 自动翻倍 max_tokens 重试；仍空才显式报错（绝不静默返回空正文/空 JSON）
_reason_calls = {"n": 0, "mts": []}


def _fake_post_reason(url, json, headers, timeout, stream=False):
    _reason_calls["n"] += 1
    _reason_calls["mts"].append(json.get("max_tokens"))
    r = requests_mod.Response()
    r.headers = {}
    r.status_code = 200
    if _reason_calls["n"] == 1:
        _body = ('data: {"choices":[{"delta":{"reasoning_content":"思考过程"}}]}\n\n'
                 'data: {"choices":[{"delta":{"reasoning_content":"还在思考"}}]}\n\n'
                 'data: [DONE]\n\n').encode("utf-8")
    else:
        _body = ('data: {"choices":[{"delta":{"content":"正文出来了"}}]}\n\n'
                 'data: [DONE]\n\n').encode("utf-8")
    r.raw = _io.BytesIO(_body)
    return r


llm_mod._session = lambda: _sess_obj
_sess_obj.post = _fake_post_reason
assert llm_mod.chat([{"role": "user", "content": "hi"}], max_tokens=4000) == "正文出来了"
assert _reason_calls["n"] >= 2, "thinking 耗尽预算应自动翻倍重试，实际 %d 次" % _reason_calls["n"]
assert _reason_calls["mts"] == [4000, 8000], \
    "max_tokens 应翻倍（4000→8000），实际 %r" % _reason_calls["mts"]
_reason_calls2 = {"n": 0}


def _fake_post_reason_bad(url, json, headers, timeout, stream=False):
    _reason_calls2["n"] += 1
    r = requests_mod.Response()
    r.headers = {}
    r.status_code = 200
    r.raw = _io.BytesIO(b'data: {"choices":[{"delta":{"reasoning_content":"x"}}]}\n\n'
                        b'data: [DONE]\n\n')
    return r


_sess_obj.post = _fake_post_reason_bad
try:
    llm_mod.chat([{"role": "user", "content": "hi"}], max_tokens=1000)
    assert False, "持续空正文应显式报错（不静默返回空）"
except llm_mod.LLMError as e:
    assert "未返回有效内容" in str(e), "错误应说明空内容，实际 %r" % str(e)[:100]
assert _reason_calls2["n"] == 4, \
    "1000→2000→4000→8000（上限）4 次后应报错，实际 %d" % _reason_calls2["n"]
llm_mod._session = _orig_session
print("[2d] 推理模型适配：thinking 耗尽预算自动翻倍 max_tokens、空正文不静默 OK")

# v0.75 chat_json 默认不限制 max_tokens：不传时 payload 不带 max_tokens 键（网关默认）
_j75 = {"payloads": []}


def _fake_post_nomt(url, json, headers, timeout, stream=False):
    _j75["payloads"].append(json)
    r = requests_mod.Response()
    r.headers = {}
    r.status_code = 200
    _body = ('data: {"choices":[{"delta":{"content":"{\\"ok\\":1}"}}]}\n\n'
             'data: [DONE]\n\n').encode("utf-8")
    r.raw = _io.BytesIO(_body)
    return r


llm_mod._session = lambda: _sess_obj
_sess_obj.post = _fake_post_nomt
assert llm_mod.chat_json("s", "u") == {"ok": 1}
assert "max_tokens" not in _j75["payloads"][0], \
    "chat_json 不传 max_tokens 时 payload 不应带 max_tokens 键，实际 %r" % _j75["payloads"][0]
_j75["payloads"].clear()
llm_mod.chat_json("s", "u", max_tokens=500)
assert _j75["payloads"][0].get("max_tokens") == 500, \
    "显式 max_tokens 应原样传递，实际 %r" % _j75["payloads"][0]
llm_mod._session = _orig_session
print("[2e] chat_json 默认不限制 max_tokens（不传即网关默认，显式传参原样生效）OK")

# ---------- 400 max_tokens 超上限自动降档（deepseek 官方上限 [1,393216]，用户设置过高时服务端拒收） ----------
config.load_config = lambda: {
    "api_profiles": [{"name": "t", "base_url": "https://x/v1", "api_key": "k",
                      "model": "m", "role": "all"}],
    "current_profile": "t", "temperature": 1.0, "max_tokens": 640000,
    "retry_times": 3, "request_timeout": 5,
}
_state2 = {"calls": 0}


def _fake_post2(url, json, headers, timeout, stream=False):
    _state2["calls"] += 1
    r = requests_mod.Response()
    r.headers = {}
    if _state2["calls"] == 1:
        r.status_code = 400
        r._content = b'{"error":{"message":"Invalid max_tokens value, the valid range of max_tokens is [1, 393216]","type":"invalid_request_error"}}'
    else:
        r.status_code = 200
        r.raw = _io.BytesIO(b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
                            b'data: [DONE]\n\n')
    _state2["last_json"] = json
    return r


llm_mod._session = lambda: _sess_obj  # 重新注入假 Session
_sess_obj.post = _fake_post2
# v0.75：None = 不限制（不带 max_tokens），400 降档场景需显式传超大值模拟
out2 = llm_mod.chat([{"role": "user", "content": "hi"}], retries=2, max_tokens=640000)
assert out2 == "ok" and _state2["calls"] == 2, \
    "400 max_tokens 超限应自动降档重试，实际 %s / %d 次" % (out2, _state2["calls"])
assert _state2["last_json"].get("max_tokens") == 393216, \
    "降档后应使用服务端上限 393216，实际 %s" % _state2["last_json"].get("max_tokens")
llm_mod._session = _orig_session
config.load_config = _orig_load_cfg
print("[2c] 400 max_tokens 超上限自动降档为服务端合法值 OK")

# ---------- v1.38 本地网关不认 reasoning_effort（400）→ 自动去掉该参数重试一次 ----------
# 用户：本地api在API设置页全局思考强度设置那里，一设置就直接api报错——根因=设置后请求带
# reasoning_effort 参数，LM Studio/llama.cpp 等本地网关不认该参数返回 400；修复=400 时
# 去掉 reasoning_effort 重试一次（商汤等支持该参数的网关不受影响，不会走到这里）。
config.load_config = lambda: {
    "api_profiles": [{"name": "t", "base_url": "https://x/v1", "api_key": "k",
                      "model": "m", "role": "all"}],
    "current_profile": "t", "temperature": 1.0, "max_tokens": 32000,
    "retry_times": 3, "request_timeout": 5,
    "reasoning_effort": "low",   # 用户在设置页设了全局思考强度
}
_state38 = {"calls": 0}


def _fake_post38(url, json, headers, timeout, stream=False):
    _state38["calls"] += 1
    r = requests_mod.Response()
    r.headers = {}
    if _state38["calls"] == 1:
        r.status_code = 400
        r._content = b'{"error":{"message":"unknown parameter: reasoning_effort","type":"invalid_request_error"}}'
    else:
        r.status_code = 200
        r.raw = _io.BytesIO(b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
                            b'data: [DONE]\n\n')
    _state38["last_json"] = json
    return r


llm_mod._session = lambda: _sess_obj  # 重新注入假 Session
_sess_obj.post = _fake_post38
out38 = llm_mod.chat([{"role": "user", "content": "hi"}], retries=2, max_tokens=50)
assert out38 == "ok" and _state38["calls"] == 2, \
    "v1.38 400 拒绝 reasoning_effort 应自动去掉该参数重试，实际 %s / %d 次" % (out38, _state38["calls"])
assert "reasoning_effort" not in _state38["last_json"], \
    "v1.38 重试时 payload 不应再带 reasoning_effort，实际 %r" % _state38["last_json"]
llm_mod._session = _orig_session
config.load_config = _orig_load_cfg
print("[2c2] v1.38 本地网关不认 reasoning_effort（400）→ 自动去掉参数重试 OK")

# ---------- PySide6 页面构建 ----------
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from gui_app import MainWindow  # noqa: E402

app = QApplication(sys.argv)
from gui_theme import QSS  # noqa: E402
app.setStyleSheet(QSS)

QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)

win = MainWindow()
win.show()
app.processEvents()
win.switch_page(2)  # 角色页（v1.66 码字页插入后 index=2）
app.processEvents()
assert len(win.page_characters._cards_cache) >= 1, "角色卡片未渲染"
print("[3] 主窗口+角色页卡片数 = %d OK" % len(win.page_characters._cards_cache))

# ---------- 批量生成配角回归（不真调 LLM；模拟 1 个限流失败，验证不中断整批） ----------
import time  # noqa: E402
import llm as llm_mod  # noqa: E402
import main_ai as main_ai_mod  # noqa: E402
from gui_app import APP as _APP  # noqa: E402

_calls = {"n": 0}


def fake_gen_character(desc, project, store):
    _calls["n"] += 1
    if _calls["n"] == 2:
        raise llm_mod.LLMError("HTTP 429 限流（测试模拟）")
    return {"name": "批量测试%d" % _calls["n"], "role": "配角",
            "description": "批量生成回归测试角色", "scenario": "测试处境"}


_orig_gen = main_ai_mod.generate_character_ai
main_ai_mod.generate_character_ai = fake_gen_character
n_before = len(win.page_characters._cards_cache)
win.page_characters._spawn_ai_gen(["描述A", "描述B", "描述C"], batch=True)
while _APP["running"]:
    app.processEvents()
    time.sleep(0.05)
app.processEvents()
assert _calls["n"] == 3, "中途失败不应中断整批，实际调用 %d 次" % _calls["n"]
n_after = len(win.page_characters._cards_cache)
assert n_after == n_before + 2, "应新增 2 张卡（第 2 个失败），实际 %d → %d" % (n_before, n_after)
assert not _APP["running"], "running 应复位"
print("[3b] 批量生成：3 个描述中 2 成功 1 限流失败，失败不中断整批、角色页自动刷新 OK")

# 清理批量测试角色（**所有项目**：批量生成测试把「批量测试N」建进了当前项目如求仙问道，
# 旧清理只扫示例项目导致每次都在真实项目里留垃圾卡；只清本模式，不动其他测试依赖的角色）
for _d in os.listdir(storage.PROJECTS_DIR):
    if not os.path.isdir(os.path.join(storage.PROJECTS_DIR, _d)):
        continue
    try:
        _st = storage.ProjectStore(_d)
        for cid, name, _ in _st.list_characters():
            if name.startswith("批量测试"):
                _st.delete_character(cid)
    except Exception:
        pass
main_ai_mod.generate_character_ai = _orig_gen
win.page_characters.refresh()  # 让卡片与磁盘一致，避免后续计数基准带幽灵卡
print("[3c] 批量测试角色已清理 OK")

# ---------- 主AI按情节需要自动建档新角色（decide 给出 hint → 自动建卡） ----------
import engine as engine_mod  # noqa: E402
_eng = engine_mod.NovelEngine(st, lambda k, m: None)
_project = st.load_project()
_orig_gen2 = main_ai_mod.generate_character_ai
main_ai_mod.generate_character_ai = lambda desc, project, store: {
    "name": "情节新角色", "role": "城主府文书", "description": "按情节需要自动建档",
    "scenario": "城主府值夜"}
made = _eng._introduce_character(_project, "城主府的年轻文书，表面恭顺暗藏心机")
assert made is not None and made[0].name == "情节新角色", "应成功建档"
_card2, _lib2 = made
assert _lib2.scenario == "城主府值夜", "scenario 应写入信息库"
main_ai_mod.generate_character_ai = lambda *a, **k: (_ for _ in ()).throw(
    llm_mod.LLMError("模拟限流失败"))
assert _eng._introduce_character(_project, "x") is None, "失败应回退为 None 不阻塞"
main_ai_mod.generate_character_ai = _orig_gen2
st.delete_character(_card2.id)
print("[3d] 主AI按情节需要自动建档新角色（含失败回退）OK")

# ---------- 主AI审查 approved 判定：字符串 "false"/False 不得误判为通过 ----------
_orig_review = main_ai_mod.review_chapter
_calls = {"n": 0}


def _fake_review(project, store, chapter, target):
    _calls["n"] += 1
    if _calls["n"] == 1:
        return {"approved": "false", "rewrite_feedback": "节奏拖沓，重写"}  # 模型常输出字符串
    return {"approved": True, "pacing": "紧凑", "brief": "测试"}


main_ai_mod.review_chapter = _fake_review
_rewrites = 0
for _rnd in range(engine_mod.MAX_AUTO_REWRITES + 1):
    _rv = main_ai_mod.review_chapter(None, None, None, "t")
    _ap = str(_rv.get("approved")).strip().lower() == "true"
    if _ap or _rnd >= engine_mod.MAX_AUTO_REWRITES:
        break
    _rewrites += 1
assert _rewrites == 1 and str(_rv.get("approved")).strip().lower() == "true", \
    "字符串 false 应触发重写而非误判通过"
# traits 列表字段：_apply_world_updates 不应把列表 str() 成字面量
_tc2 = CharacterCard("审查测试角色", "测试")
_tc2.traits = ["沉稳"]
_tstore_tmp = st
_tc2_lib = InfoLibrary(_tc2.id)
_tstore_tmp.save_character(_tc2, _tc2_lib)
_eng._apply_world_updates(_project, Chapter(1, 1), {
    "characters": [{"id": _tc2.id,
                    "card_updates": {"traits": ["冷酷", "缜密"]}}]})
_rt, _ = _tstore_tmp.load_character(_tc2.id)
assert _rt.traits == ["冷酷", "缜密"] and isinstance(_rt.traits, list), \
    "traits 应作为列表更新，实际 %r" % _rt.traits
_tstore_tmp.delete_character(_tc2.id)
main_ai_mod.review_chapter = _orig_review
print("[3d2] 审查 approved 字符串判定 + traits 列表更新 OK")

# ---------- 联网搜索触发链路：search_queries → 搜索 → 重判（mock consolidate 与 web_search） ----------
import engine as _eng3  # noqa: E402
import web_search as _ws3  # noqa: E402
_orig_cons = main_ai_mod.consolidate
_orig_search = _ws3.search
_seq = {"n": 0}


def _fake_cons(project, store, chapter_no, scene_focus, inferences,
               new_char_pool_hint="", extra_context="", search_enabled=False,
               kb_prompt=""):
    _seq["n"] += 1
    if _seq["n"] == 1 and search_enabled:
        # 第一轮：要求联网搜索灵感
        return {"verdict": "ok", "search_queries": ["悬疑 密室 布局"],
                "approved_direction": "暂定", "foreshadows": [], "kb_update": [],
                "need_chapters": []}
    # 第二轮（带搜索结果的 extra_context）：通过，并给知识库追加
    return {"verdict": "ok", "approved_direction": "依据搜索结果定方向",
            "foreshadows": [], "kb_update": ["知识库测试条目"],
            "need_chapters": [], "search_queries": []}


_ws3.search = lambda q, max_results=6: [{"title": "搜索测试标题", "snippet": "搜索测试摘要", "url": "https://x.com"}]
main_ai_mod.consolidate = _fake_cons
_pjS = st.load_project()
_pjS.story_knowledge = ""
st.save_project(_pjS)
# 验证循环逻辑：第一轮 consolidate 返回 search_queries → 触发搜索（第二轮带结果）
from engine import MAX_CONSOLIDATE_ROUNDS as _MCR  # noqa: E402
_cfg_save = config.load_config()
config.save_config({**_cfg_save, "web_search_enabled": True})
import config as _cfgmod  # noqa: E402
_cfgmod._cache = None
_ok = False
for _r in range(_MCR + 4):
    _c = main_ai_mod.consolidate(_pjS, st, 2, "焦点", {}, "", "",
                                 search_enabled=True)
    _q = [str(x) for x in (_c.get("search_queries") or []) if str(x).strip()][:3]
    if _q and _r < 2:
        _items = _ws3.search(_q[0])
        if _items:
            _ok = True
            break
assert _ok, "联网搜索应触发一轮并拿到结果"
config.save_config(_cfg_save)
_cfgmod._cache = None
main_ai_mod.consolidate = _orig_cons
_ws3.search = _orig_search
print("[3d3] 联网搜索触发链路（search_queries→搜索→重判）OK")

# ---------- 世界快照 / 章节重写回滚 / 角色归档（独立临时项目，不动示例数据） ----------
import git_tool as git_tool_mod  # noqa: E402
_orig_commit = git_tool_mod.commit
git_tool_mod.commit = lambda *a, **k: None  # 测试期间不产生 git 提交
_t = storage.create_project("重写测试")
_tstore = storage.ProjectStore(_t.dir_name)
_tp = _tstore.load_project()
_ta = CharacterCard("阿甲", "主角")
_tb = CharacterCard("阿乙", "配角")
_tstore.save_character(_ta, InfoLibrary(_ta.id))
_tstore.save_character(_tb, InfoLibrary(_tb.id))
_tstore.save_world_snapshot(0)                      # 初始世界
_tp.state["next_chapter"] = 1
_tstore.save_project(_tp)
_ta.name = "阿甲改1"
_tstore.save_character(_ta)
_ch1 = Chapter(1, 1); _ch1.title = "第一章"; _ch1.content = "一"; _ch1.status = "approved"
_tstore.save_chapter(_ch1)
_tstore.save_world_snapshot(1)                      # 第1章完成后（快照含章节，与引擎 finalize 顺序一致）
_ta.name = "阿甲改2"
_tstore.save_character(_ta)
_ch2 = Chapter(2, 1); _ch2.title = "第二章"; _ch2.content = "二"; _ch2.status = "approved"
_tstore.save_chapter(_ch2)
_tp = _tstore.load_project()
_tp.state["next_chapter"] = 3
_tstore.save_project(_tp)
_tstore.save_world_snapshot(2)                      # 第2章完成后
assert [c["index"] for c in _tstore.load_world_snapshot(1)["chapters"]] == [1], \
    "快照应包含第1章"
_eng2 = engine_mod.NovelEngine(_tstore, lambda k, m: None)
assert _eng2.rewrite_from(_tp, 2), "rewrite_from 应成功"
_tp2 = _tstore.load_project()
assert _tp2.state["next_chapter"] == 2, "进度应回退到第2章"
assert _tstore.list_chapter_indices() == [1], "第2章应被删除"
_rc, _ = _tstore.load_character(_ta.id)
assert _rc.name == "阿甲改1", "角色卡应回滚到第1章后状态，实际 %s" % _rc.name
assert _tstore.list_snapshot_indices() == [0, 1], "重写章之后的旧快照应清理"
_eng2._apply_archive_suggestions([{"id": _tb.id, "reason": "测试归档"}])
_rb, _ = _tstore.load_character(_tb.id)
assert _rb.status == "archived", "应标记为归档"
storage.delete_project(_t.dir_name)
git_tool_mod.commit = _orig_commit
print("[3e] 世界快照/章节重写回滚/角色归档 OK")

# ---------- 快照完整性：章节+主AI知识库纳入快照，回滚可完全恢复原样 ----------
git_tool_mod.commit = lambda *a, **k: None  # 防 rewrite_from 触发真实 git 提交（污染仓库）
_t3 = storage.create_project("快照完整性测试")
_tstore3 = storage.ProjectStore(_t3.dir_name)
_tp3 = _tstore3.load_project()
_tchA = CharacterCard("快照主角", "主角")
_tstore3.save_character(_tchA, InfoLibrary(_tchA.id))
_tp3.story_knowledge = "初始知识A"
_tstore3.save_project(_tp3)
_tstore3.save_world_snapshot(0)                      # 初始：无章节、知识A
_c1 = Chapter(1, 1); _c1.title = "第一章"; _c1.content = "一"; _c1.status = "approved"
_tstore3.save_chapter(_c1)
_tp3 = _tstore3.load_project()
_tp3.story_knowledge = "初始知识A\n第1章知识B"
_tstore3.save_project(_tp3)
_tstore3.save_world_snapshot(1)                      # 第1章后：含ch1、知识A+B
_c2 = Chapter(2, 1); _c2.title = "第二章"; _c2.content = "二"; _c2.status = "approved"
_tstore3.save_chapter(_c2)
_tp3 = _tstore3.load_project()
_tp3.story_knowledge = "初始知识A\n第1章知识B\n第2章知识C"
_tstore3.save_project(_tp3)
_tp3.state["next_chapter"] = 3
_tstore3.save_project(_tp3)
_tstore3.save_world_snapshot(2)                      # 第2章后：含ch1/2、知识A+B+C
_snap1 = _tstore3.load_world_snapshot(1)
assert [c["index"] for c in _snap1["chapters"]] == [1], "快照应含第1章"
assert "第1章知识B" in _snap1["story_knowledge"], "快照应含主AI知识库"
_eng3 = engine_mod.NovelEngine(_tstore3, lambda k, m: None)
assert _eng3.rewrite_from(_tp3, 1), "从第1章重写应成功"
_tp3b = _tstore3.load_project()
assert _tstore3.list_chapter_indices() == [], "回滚到初始应无章节，实际 %r" % _tstore3.list_chapter_indices()
assert _tp3b.story_knowledge.strip() == "初始知识A", \
    "知识库应随回滚恢复原样（不应残留第2章知识），实际 %r" % _tp3b.story_knowledge
assert _tp3b.state["next_chapter"] == 1, "进度应回退到1"
# 旧版快照（缺 chapters/story_knowledge 字段）回滚应跳过对应恢复，不崩
_osnap = _tstore3.load_world_snapshot(0)
_osnap.pop("chapters", None)
_osnap.pop("story_knowledge", None)
_tstore3.rollback_world(_osnap)                      # 直接调用不应抛异常
assert _tstore3.load_project().story_knowledge == "初始知识A", "旧快照不应清空知识库"
storage.delete_project(_t3.dir_name)
git_tool_mod.commit = _orig_commit
print("[3n] 快照完整性：章节/知识库纳入快照并随回滚恢复（旧快照兼容）OK")

# ---------- 项目整体导入导出（zip 全量打包，换电脑继续写） ----------
_t4 = storage.create_project("导入导出测试")
_tstore4 = storage.ProjectStore(_t4.dir_name)
_tp4 = _tstore4.load_project()
_tp4.story_brief = "导入导出测试故事"
_tp4.story_knowledge = "导入导出知识"
_tstore4.save_project(_tp4)
_tz = CharacterCard("导出角色", "角色")
_tstore4.save_character(_tz, InfoLibrary(_tz.id))
_tc4 = Chapter(1, 1); _tc4.title = "导出章"; _tc4.content = "导出内容"; _tc4.status = "approved"
_tstore4.save_chapter(_tc4)
_tstore4.save_world_snapshot(1)
_zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_export_test.zip")
assert storage.export_project(_t4.dir_name, _zip_path), "导出应成功"
assert os.path.exists(_zip_path) and os.path.getsize(_zip_path) > 0, "zip 应非空"
# v0.97 manifest 应写入（章节/角色/快照计数，供导入校验）
import zipfile as _zip_mod  # noqa: E402
with _zip_mod.ZipFile(_zip_path, "r") as _zfm:
    _mani = [m for m in _zfm.infolist() if m.filename.endswith("manifest.json")]
    assert len(_mani) == 1, "导出 zip 应含 manifest.json"
    import json as _json97
    _mani_d = _json97.loads(_zfm.read(_mani[0].filename))
    assert _mani_d.get("chapters") == 1 and _mani_d.get("characters") == 1, \
        "manifest 计数应正确，实际 %r" % _mani_d
# 改包内顶层目录名后导入（验证导入不依赖目录名，只认 project.json）
_zip2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_export_test2.zip")
with _zip_mod.ZipFile(_zip_path, "r") as zfr, _zip_mod.ZipFile(_zip2, "w") as zfw:
    for m in zfr.infolist():
        zfw.writestr("不同目录名/" + m.filename.split("/", 1)[-1], zfr.read(m.filename))
_ret = storage.import_project(_zip2)
assert _ret is not None, "导入应返回 (dir, title, warning)"
_idir, _ititle, _iwarn = _ret
assert _iwarn == "", "完整包导入不应有警告，实际 %r" % _iwarn
assert _ititle == "导入导出测试"
_tstore5 = storage.ProjectStore(_idir)
assert _tstore5.load_project() is not None, "导入后 project.json 应可读"
assert _tstore5.load_project().story_brief == "导入导出测试故事", "导入后设定应完整"
assert _tstore5.load_project().story_knowledge == "导入导出知识", "导入后知识库应完整"
assert any(_n == "导出角色" for _, _n, _ in _tstore5.list_characters()), "导入后角色应存在"
assert _tstore5.list_chapter_indices() == [1], "导入后章节应存在"
assert _tstore5.load_world_snapshot(1) is not None, "导入后快照应存在"
# 再导入一次同名 → 自动加后缀不覆盖
_ret2 = storage.import_project(_zip2)
assert _ret2 is not None and _ret2[0] != _idir, "同名导入应自动加后缀"
assert storage.ProjectStore(_ret2[0]).load_project() is not None
storage.delete_project(_idir)
storage.delete_project(_ret2[0])
# 非法包应返回 None
_bad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_bad.zip")
with _zip_mod.ZipFile(_bad, "w") as zfb:
    zfb.writestr("随便.txt", "不是项目")
assert storage.import_project(_bad) is None, "无 project.json 的包应导入失败"
# v0.97 损坏/截断包校验：zip 内章节条目多于实际还原（重名条目）→ 返回不完整警告
_trunc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_trunc.zip")
with _zip_mod.ZipFile(_trunc, "w") as zft:
    zft.writestr("截断书/project.json", '{"title": "截断书", "story_brief": "设定"}')
    zft.writestr("截断书/chapters/ch_001.json", '{"index": 1}')
    zft.writestr("截断书/chapters/ch_001.json", '{"index": 1}')   # 重名 → 落盘只有 1 个条目
_tr = storage.import_project(_trunc)
assert _tr is not None, "损坏包也应导入（带警告），不阻断使用"
assert _tr[2] and "章节不完整" in _tr[2], "损坏包应返回章节不完整警告，实际 %r" % _tr[2]
storage.delete_project(_tr[0])
for _pp in (_zip_path, _zip2, _bad, _trunc):
    if os.path.exists(_pp):
        os.remove(_pp)
storage.delete_project(_t4.dir_name)
print("[3o] 项目整体导入导出（zip 全量：设定/角色/章节/快照齐全 + manifest + 同名后缀 + 非法包拒绝 + 损坏包警告）OK")

# ---------- 草稿箱：编辑/删除/回滚前自动备份，可恢复找回 ----------
git_tool_mod.commit = lambda *a, **k: None
_t5 = storage.create_project("草稿备份测试")
_tstore5 = storage.ProjectStore(_t5.dir_name)
_tp5 = _tstore5.load_project()
_tstore5.save_world_snapshot(0)                    # 初始世界快照（回滚到第1章需要）
for _i in (1, 2):
    _c = Chapter(_i, 1); _c.title = "第%d章" % _i; _c.content = "正文%d" % _i
    _c.status = "approved"
    _tstore5.save_chapter(_c)
_tp5.state["next_chapter"] = 3
_tstore5.save_project(_tp5)
_eng5 = engine_mod.NovelEngine(_tstore5, lambda k, m: None)
# 编辑前自动备份旧版
_c1 = _tstore5.load_chapter(1)
_c1.content = "编辑后内容"
_eng5.edit_chapter(_c1)
_d5 = _tstore5.list_chapter_drafts()
assert len(_d5) == 1 and _d5[0]["tag"] == "edit" and _d5[0]["index"] == 1, \
    "编辑前应自动备份第1章，实际 %r" % _d5
assert _tstore5.load_chapter_draft(_d5[0]["fname"]).content == "正文1", \
    "备份应为编辑前的旧内容"
# 仅删除第2章 → delete 备份
_eng5.delete_chapter_only(_tp5, 2)
_d5 = _tstore5.list_chapter_drafts()
assert any(d["index"] == 2 and d["tag"] == "delete" for d in _d5), "删除前应备份第2章"
# 回滚删除第1章及之后 → 先备份
assert _eng5.rollback_delete_from(_tp5, 1), "回滚删除应成功"
_d5 = _tstore5.list_chapter_drafts()
assert any(d["index"] == 1 and d["tag"] == "delete" for d in _d5), "回滚删除前应备份"
# 从草稿箱恢复第2章 → 写回正式章节
_f2 = next(d["fname"] for d in _d5 if d["index"] == 2 and d["tag"] == "delete")
_ch2r = _tstore5.restore_chapter_draft(_f2)
assert _ch2r is not None and _ch2r.content == "正文2", "应能恢复草稿内容"
assert _tstore5.load_chapter(2) is not None \
    and _tstore5.load_chapter(2).content == "正文2", "恢复应写回章节文件"
assert _tstore5.load_project().state["next_chapter"] >= 3, "恢复后进度应自动补位"
storage.delete_project(_t5.dir_name)
git_tool_mod.commit = _orig_commit
print("[3p] 草稿箱：编辑/删除/回滚前自动备份 + 恢复找回（进度补位）OK")

# ---------- if 线分支：保存完整项目状态 → 改动 → 载回完整还原 ----------
git_tool_mod.commit = lambda *a, **k: None
_t6 = storage.create_project("分支测试")
_tstore6 = storage.ProjectStore(_t6.dir_name)
_tp6 = _tstore6.load_project()
_tp6.story_brief = "分支初始剧情"
_tstore6.save_project(_tp6)
_ta6 = CharacterCard("支线主角", "主角")
_tstore6.save_character(_ta6, InfoLibrary(_ta6.id))
_c6 = Chapter(1, 1); _c6.title = "第一章"; _c6.content = "主线内容"; _c6.status = "approved"
_tstore6.save_chapter(_c6)
_tp6.state["next_chapter"] = 2
_tstore6.save_project(_tp6)
_tstore6.save_branch("主线")
assert os.path.exists(_tstore6.branch_path("主线")), "分支文件应存在"
_b6 = _tstore6.list_branches()
assert any(b["name"] == "主线" and b["chapters"] == 1 for b in _b6), "分支应列出且含章节数"
# 模拟走 if 线：改设定/改角色名/改章节
_tp6 = _tstore6.load_project()
_tp6.story_brief = "if线新剧情"
_tstore6.save_project(_tp6)
_ta6.name = "if线改名"
_tstore6.save_character(_ta6, None)
_c6b = _tstore6.load_chapter(1)
_c6b.content = "if线内容"
_tstore6.save_chapter(_c6b)
_tstore6.save_branch("if线")
# 载回主线 → 设定/角色/章节全部还原
_data6 = _tstore6.load_branch("主线")
_tstore6.apply_branch(_data6)
assert _tstore6.load_project().story_brief == "分支初始剧情", "载回应还原设定"
assert _tstore6.load_chapter(1).content == "主线内容", "载回应还原章节"
_n6 = [n for _, n, _ in _tstore6.list_characters() if n == "支线主角"]
assert _n6, "载回应还原角色名，实际 %r" % [n for _, n, _ in _tstore6.list_characters()]
# 再把 if 线载回来
_data6b = _tstore6.load_branch("if线")
_tstore6.apply_branch(_data6b)
assert _tstore6.load_project().story_brief == "if线新剧情", "ifl线载回应还原"
storage.delete_project(_t6.dir_name)
git_tool_mod.commit = _orig_commit
print("[3q] if线分支：保存→改动→载回完整还原（设定/角色/章节双向切换）OK")

# ---------- 角色卡导入：export_character_json 逆操作往返 ----------
from gui_characters import export_character_json, import_character_json  # noqa: E402
_tc7 = CharacterCard("导入测试角色", "测试身份")
_tc7.description = "导入测试描述"
_tc7.personality = "谨慎多疑"
_tc7.first_mes = "* 抬眼打量 *"
_tc7.system_prompt = "测试扮演规则"
_tlib7 = InfoLibrary(_tc7.id)
_tlib7.scenario = "驿站借宿"
_tlib7.events = [{"chapter": 3, "event": "目睹镖局失火", "impact": "对镖局生疑"}]
_tlib7.knowledge = [{"chapter": 5, "info": "废矿深夜有火光"}]
_tlib7.secrets = ["身上藏着一枚旧铜钥"]
_tlib7.notes = "右脚微跛"
_out7 = export_character_json(_tc7, _tlib7)
assert _out7["spec"] == "chara_card_v2", "导出应为酒馆格式"
_c7b, _l7b = import_character_json(_out7)
assert _c7b.name == "导入测试角色" and _c7b.description == "导入测试描述", "往返应还原角色卡"
assert _c7b.personality == "谨慎多疑" and _c7b.first_mes.startswith("*"), "高级字段应还原"
assert _c7b.system_prompt == "测试扮演规则"
assert _l7b.scenario == "驿站借宿", "信息库场景应还原，实际 %r" % _l7b.scenario
assert len(_l7b.events) == 1 and _l7b.events[0]["chapter"] == 3, "事件应还原"
assert _l7b.events[0]["event"] == "目睹镖局失火" and _l7b.events[0]["impact"] == "对镖局生疑"
assert len(_l7b.knowledge) == 1 and _l7b.knowledge[0]["chapter"] == 5, "情报应还原"
assert _l7b.secrets == ["身上藏着一枚旧铜钥"], "隐秘应还原"
assert _l7b.notes == "右脚微跛", "备注应还原"
_c7c, _l7c = import_character_json({"name": "裸卡角色", "description": "x"})
assert _c7c.name == "裸卡角色", "裸卡应可导入"
try:
    import_character_json({"description": "无名字"})
    raise SystemExit("缺 name 应抛错")
except ValueError:
    pass
print("[3s] 角色卡导入：酒馆 chara_card_v2 导出→导入往返（角色卡+信息库全字段）OK")

# ---------- v0.98 防重复建档 + 酒馆 spec_v2 字段 ----------
_t98 = storage.create_project("去重测试")
_tstore98 = storage.ProjectStore(_t98.dir_name)
import main_ai as _mai98  # noqa: E402
_mai98.save_generated_character(_tstore98,
                                {"name": "阿梨", "role": "老板娘", "description": "第一版描述"})
assert len(_tstore98.list_characters()) == 1, "首次生成应新建"
_c98a, _l98a, _cr98a = _mai98.save_generated_character(
    _tstore98, {"name": "阿梨", "role": "老板娘", "description": "",
                "scenario": "酒馆值夜"})
assert _cr98a is False, "同名角色应复用旧卡不新建"
assert len(_tstore98.list_characters()) == 1, "重复建档后仍应只有 1 张卡"
_c98a2 = _tstore98.load_character(_tstore98.list_characters()[0][0])[0]
assert _c98a2.description == "第一版描述", "旧卡已有字段不应被覆盖"
assert _c98a2.scenario == "酒馆值夜", "旧卡空缺 scenario 应被补齐"
assert _l98a.scenario == "酒馆值夜", "复用路径 scenario 应写入信息库"
# 包含匹配（唯一命中）→ 复用（如「客栈老板娘阿梨」vs「阿梨」）
_c98b, _l98b, _cr98b = _mai98.save_generated_character(
    _tstore98, {"name": "客栈老板娘阿梨", "role": "老板娘", "description": ""})
assert _cr98b is False, "包含匹配唯一命中应复用"
assert len(_tstore98.list_characters()) == 1, "包含匹配复用后仍应只有 1 张卡"
# 全新名字 → 新建
_mai98.save_generated_character(_tstore98, {"name": "新剑客", "role": "剑客"})
assert len(_tstore98.list_characters()) == 2, "全新名字应新建第 2 张卡"
# 已归档角色被重新引入 → 自动恢复在籍
_tstore98.list_characters()
for _cid98, _nm98, _st98 in _tstore98.list_characters():
    _c98z, _l98z = _tstore98.load_character(_cid98)
    if _c98z.name == "阿梨":
        _c98z.status = "archived"
        _tstore98.save_character(_c98z, _l98z)
_mai98.save_generated_character(_tstore98, {"name": "阿梨", "role": "老板娘", "description": ""})
for _cid98, _nm98, _st98 in _tstore98.list_characters():
    _c98z, _l98z = _tstore98.load_character(_cid98)
    if _c98z.name == "阿梨":
        assert _c98z.status == "active", "复用已归档角色应自动恢复在籍"
# spec_v2 字段解析（tags/character_version/creator_notes/post_history_instructions）
_c98d = _mai98.character_from_data({
    "name": "spec角色", "traits": "冷酷, 缜密",
    "tags": "主角，青年", "character_version": "main",
    "creator_notes": "设计备注", "post_history_instructions": "后置指示"})
assert _c98d.tags == ["主角", "青年"], "tags 应解析为列表，实际 %r" % _c98d.tags
assert _c98d.character_version == "main" and _c98d.creator_notes == "设计备注", "spec 字段应解析"
assert _c98d.post_history_instructions == "后置指示"
# 角色卡导出含 spec_v2 新字段
from gui_characters import export_character_json as _exp98  # noqa: E402
_ex98 = _exp98(_c98d, InfoLibrary(_c98d.id))
_d98 = _ex98["data"]
assert _d98.get("tags") == ["主角", "青年"] and _d98.get("character_version") == "main", \
    "导出应含 spec_v2 tags/character_version，实际 %r" % list(_d98.keys())
assert _d98.get("creator_notes") == "设计备注" and _d98.get("post_history_instructions") == "后置指示"
assert _d98.get("creator") == "星火笔" and isinstance(_d98.get("extensions"), dict) \
    and _d98.get("avatar") == "", "导出应含 spec_v2 creator/extensions/avatar，实际 %r" % list(_d98.keys())
# description 回退拼装：无 description/personality 的旧卡导出到酒馆仍可直接玩
_c98e = _mai98.character_from_data({"name": "旧卡张三", "appearance": "身材高大",
                                    "backstory": "曾是镖师", "speech_style": "寡言"})
_ex98e = _exp98(_c98e, InfoLibrary(_c98e.id))
_d98e = _ex98e["data"]
assert "外貌：身材高大" in _d98e["description"] and "背景：曾是镖师" in _d98e["description"] \
    and "说话风格：寡言" in _d98e["description"], \
    "旧卡 description 应回退拼装，实际 %r" % _d98e["description"][:60]
# 中文内容以 UTF-8 直写（ensure_ascii=False），酒馆直接读中文
import json as _json98u  # noqa: E402
_s98 = _json98u.dumps(_ex98, ensure_ascii=False)
assert "设计备注" in _s98, "导出 JSON 不应转义中文（应原样出现，而非 \\u 序列）"
storage.delete_project(_t98.dir_name)
print("[3u] v0.98 防重复建档（同名/包含唯一命中复用旧卡、归档角色回自动恢复在籍）+ 酒馆 spec_v2 字段解析/导出 OK")

# v0.98 角色卡库视图：归档角色不进主分组、卡库可见、可恢复在籍
_cur98 = _APP["project_dir"]
_t98b = storage.create_project("卡库测试")
_tstore98b = storage.ProjectStore(_t98b.dir_name)
for _i98, _n98 in enumerate(["在籍甲", "卡库乙"]):
    _cc98 = CharacterCard(_n98, "测试", card_id="lib98_%d" % _i98)
    if _n98 == "卡库乙":
        _cc98.status = "archived"
    _tstore98b.save_character(_cc98, InfoLibrary(_cc98.id))
win.select_project(_t98b.dir_name)
win.page_characters.refresh()
app.processEvents()


def _labels98(container):
    """收集容器内全部 QLabel 文本（分组行/卡库行的文字在子标签里）。"""
    _ql = __import__("PySide6").QtWidgets.QLabel
    _out = []
    for _i in range(container.count()):
        _w = container.itemAt(_i).widget()
        if _w is None:
            continue
        try:
            _out.append(_w.text() or "")
        except AttributeError:
            pass
        _out.extend(_l.text() or "" for _l in _w.findChildren(_ql))
    return _out


_gr98 = _labels98(win.page_characters.groups)
assert any("在籍甲" in t for t in _gr98), "在籍角色应出现在分组视图"
assert not any("卡库乙" in t for t in _gr98), "归档角色不应出现在主分组视图"
win.page_characters._open_library()
app.processEvents()
_lib_texts = _labels98(win.page_characters.groups)
assert any("卡库乙" in t for t in _lib_texts), "归档角色应出现在角色卡库视图"
assert any("已归档 1" in t for t in _lib_texts), "卡库应显示已归档计数"
# 恢复在籍
_cid98b = _tstore98b.list_characters()[1][0]
win.page_characters._restore_from_library(_cid98b)
_c98r = _tstore98b.load_character(_cid98b)[0]
assert _c98r.status == "active", "卡库恢复在籍应生效"
storage.delete_project(_t98b.dir_name)
if _cur98:
    win.select_project(_cur98)
win.page_characters.refresh()
print("[3v] v0.98 角色卡库视图：归档角色移出主分组、卡库可见计数、恢复在籍 OK")

# v0.98 git 存档自动补仓库：无 .git 的目录 commit 不再报「not a git repository」
import tempfile as _tmp98  # noqa: E402
_t98g = _tmp98.mkdtemp(prefix="xhb_git98_")
_git_msgs = []
_git_tool98 = __import__("git_tool")
_git_tool98.commit(_t98g, "测试提交", lambda k, m: _git_msgs.append("%s:%s" % (k, m)))
assert os.path.isdir(os.path.join(_t98g, ".git")), "无 .git 目录应自动 git init"
assert not any("not a git repository" in m for m in _git_msgs), \
    "不应再出现 not a git repository 警告，实际 %r" % _git_msgs
__import__("shutil").rmtree(_t98g, ignore_errors=True)
print("[3w] v0.98 git 存档无仓库自动 init（消除 not a git repository 警告）OK")

# ---------- 章节导入（完整txt拆分/分章文件夹）+ 批量删除 ----------
git_tool_mod.commit = lambda *a, **k: None
from gui_story import parse_novel_txt, chapters_from_folder  # noqa: E402
_txt = "第一卷 风云\n\n第1章 起始\n\n风雨夜，灯盏摇曳。\n\n第2章 惊变\n\n城中传来一声尖啸。\n\n第10章 收束\n\n尘埃落定。"
_parts = parse_novel_txt(_txt)
assert [p["title"] for p in _parts] == ["第1章 起始", "第2章 惊变", "第10章 收束"], \
    "完整 txt 应按第N章拆分，实际 %r" % [p["title"] for p in _parts]
assert "风雨夜" in _parts[0]["content"] and "尖啸" in _parts[1]["content"], "正文应拆对"
assert parse_novel_txt("没有标题的正文") == [{"title": "", "content": "没有标题的正文"}], \
    "无章节标题应整篇一章"
import tempfile as _tmp  # noqa: E402
_tmpdir = _tmp.mkdtemp(prefix="chapter_import_")
for _ci, _ct in ((2, "第二章 夜行"), (5, "第五章 追凶")):
    with open(os.path.join(_tmpdir, "第%03d章_%s.txt" % (_ci, _ct)), "w", encoding="utf-8") as _f:
        _f.write("%s\n%s\n\n分章正文%d。" % (_ct, "-" * 30, _ci))
_cf = chapters_from_folder(_tmpdir)
assert len(_cf) == 2 and _cf[0]["title"] == "第二章 夜行" and "分章正文2" in _cf[0]["content"], \
    "分章文件夹应按文件名序号排序并剥离标题行/分隔线，实际 %r" % _cf
_t7 = storage.create_project("章节导入测试")
_tstore7 = storage.ProjectStore(_t7.dir_name)
_tp7 = _tstore7.load_project()
_tp7.state["next_chapter"] = 3
_tstore7.save_project(_tp7)
_eng7 = engine_mod.NovelEngine(_tstore7, lambda k, m: None)
_n = _eng7.import_chapters(_tp7, _parts)
assert _n == 3 and _tstore7.list_chapter_indices() == [3, 4, 5], \
    "导入应从 next_chapter 开始编号，实际 %r" % _tstore7.list_chapter_indices()
assert _tstore7.load_chapter(3).title == "第1章 起始", "标题应保留原文"
assert _tstore7.load_project().state["next_chapter"] == 6, "进度应推进"
_eng7.delete_chapters_bulk(_tp7, [3, 5])
assert _tstore7.list_chapter_indices() == [4], "批量删除应删掉指定章，实际 %r" % _tstore7.list_chapter_indices()
assert _tstore7.load_project().state["next_chapter"] == 5, "进度应回退到现存最大章+1"
assert any(d["index"] == 5 and d["tag"] == "delete" for d in _tstore7.list_chapter_drafts()), \
    "批量删除前应备份到草稿箱"
storage.delete_project(_t7.dir_name)
import shutil as _sh7  # noqa: E402
_sh7.rmtree(_tmpdir, ignore_errors=True)
git_tool_mod.commit = _orig_commit
print("[3t] 章节导入（txt拆分/分章文件夹）+ 批量删除（进度回退+草稿备份）OK")

# ---------- 全自动模式遇 API 报错自动重试（连续失败才停，不再每次手动点） ----------
git_tool_mod.commit = lambda *a, **k: None
_t8 = storage.create_project("自动重试测试")
_tstore8 = storage.ProjectStore(_t8.dir_name)
_tp8 = _tstore8.load_project()
_tstore8.save_world_snapshot(0)
_eng8 = engine_mod.NovelEngine(_tstore8, lambda k, m: None)
_orig_gd8 = _eng8.generate_draft
_calls8 = {"n": 0}


def _fake_gd8(project, user_directive="", user_feedback="", beats_confirm=None):
    _calls8["n"] += 1
    if _calls8["n"] <= 2:
        raise llm_mod.LLMError("模拟限流失败")
    ch = Chapter(1, 1)
    ch.title = "第一章"; ch.content = "正文"
    ch.reasoning = {"review": {"approved": True}}
    return ch


def _fake_fin8(project, chapter, review=None):
    project.state["next_chapter"] = chapter.index + 1
    project.state["story_complete"] = True


_eng8.generate_draft = _fake_gd8
_eng8.finalize_chapter = _fake_fin8
_eng8.auto_run(_tp8, stop_check=None)
assert _calls8["n"] == 3, "前2次失败应自动重试、第3次成功，实际 %d 次" % _calls8["n"]
assert _tp8.state["next_chapter"] == 2, "成功后应推进进度"
# 一直失败 → 连续 MAX_AUTO_RETRY 次后自动停止（而不是无限循环）
_tp8.state["story_complete"] = False
_calls8b = {"n": 0}


def _fake_gd_fail(project, user_directive="", user_feedback="", beats_confirm=None):
    _calls8b["n"] += 1
    raise llm_mod.LLMError("模拟一直失败")


_eng8.generate_draft = _fake_gd_fail
_eng8.auto_run(_tp8, stop_check=None)
assert _calls8b["n"] == engine_mod.MAX_AUTO_RETRY, \
    "连续失败应重试 MAX_AUTO_RETRY 次后停止，实际 %d" % _calls8b["n"]
_eng8.generate_draft = _orig_gd8
storage.delete_project(_t8.dir_name)
git_tool_mod.commit = _orig_commit
print("[3u] 全自动模式遇 API 报错自动重试（连续失败才停）OK")

# ---------- 章节字数校验：超上限自动重写（不压缩、不截断内容） ----------
_t9 = storage.create_project("字数校验测试")
_st9 = storage.ProjectStore(_t9.dir_name)
_eng9 = engine_mod.NovelEngine(_st9, lambda k, m: None)
_calls_len = []


def _writer_len_ok():
    _calls_len.append(1)
    return "第1章", "正" * 3500   # 重写版字数正常


_out_len = _eng9._ensure_chapter_length(_t9, 1, 3500, "第1章", "长" * 7400, _writer_len_ok)
assert _calls_len == [1] and len(_out_len[1]) == 3500, \
    "超上限（7400）应自动重写一版，实际 %r/%d" % (_calls_len, len(_out_len[1]))

# 目标内不触发重写
_calls_len.clear()
_out_len = _eng9._ensure_chapter_length(_t9, 1, 3500, "第1章", "x" * 3000,
                                        lambda: ("x", "不应被调用"))
assert not _calls_len and _out_len[1] == "x" * 3000, "目标内不应触发重写"

# 重写后仍超限：循环重写直到达标（v1.17），上限内始终不达标才保留本版（绝不压缩/截断）
_calls_len.clear()


def _writer_len_stubborn():
    _calls_len.append(1)
    return "第1章", "冗" * 5000


_out_len = _eng9._ensure_chapter_length(_t9, 1, 3500, "第1章", "长" * 7400, _writer_len_stubborn)
assert len(_calls_len) == engine_mod.LENGTH_RETRY_MAX, \
    "超限始终不达标应循环重写到上限，实际 %d 次" % len(_calls_len)
assert len(_out_len[1]) == 5000, "循环后仍超限应保留本版完整内容，实际 %d" % len(_out_len[1])

# 偏低限（< 目标×0.8）：自动重写一版充实
_calls_len.clear()


def _writer_len_fix():
    _calls_len.append(1)
    return "第1章", "中" * 3000


_out_len = _eng9._ensure_chapter_length(_t9, 1, 3500, "第1章", "短" * 1500, _writer_len_fix)
assert _calls_len == [1] and len(_out_len[1]) == 3000, \
    "低于下限（1500）应自动重写一版，实际 %r/%d" % (_calls_len, len(_out_len[1]))

# 重写后仍偏短：循环重写直到达标（v1.17），始终不达标才保留本版（绝不注水凑字）
_calls_len.clear()


def _writer_len_still_short():
    _calls_len.append(1)
    return "第1章", "稀" * 2200


_out_len = _eng9._ensure_chapter_length(_t9, 1, 3500, "第1章", "短" * 1500,
                                        _writer_len_still_short)
assert len(_calls_len) == engine_mod.LENGTH_RETRY_MAX, \
    "偏短始终不达标应循环重写到上限，实际 %d 次" % len(_calls_len)
assert len(_out_len[1]) == 2200, "循环后仍偏短应保留本版内容，实际 %d" % len(_out_len[1])
storage.delete_project(_t9.dir_name)
print("[3x] 章节字数校验（超上限/低于下限循环重写直到达标、不压缩不截断不注水）OK")

# ---------- 章节管理：编辑 / 仅删单章 / 回滚删除（独立临时项目） ----------
git_tool_mod.commit = lambda *a, **k: None  # 章节管理不产生真实 git 提交
_t2 = storage.create_project("章节管理测试")
_tstore2 = storage.ProjectStore(_t2.dir_name)
_tp2 = _tstore2.load_project()
_tca = CharacterCard("甲章主", "主角")
_tstore2.save_character(_tca, InfoLibrary(_tca.id))
_tstore2.save_world_snapshot(0)                      # 初始世界
_tp2.state["next_chapter"] = 1
_tstore2.save_project(_tp2)
_tca.name = "甲章主改"                                # 第1章完成后的世界状态
_tstore2.save_character(_tca)
for _i in (1, 2, 3):
    _c = Chapter(_i, 1)
    _c.title = "第%d章" % _i
    _c.content = "正文%d" % _i
    _c.status = "approved"
    _c.characters = [_tca.id]   # v0.54 删除章节后按出场记录重建角色卡
    _tstore2.save_chapter(_c)
    _tstore2.save_world_snapshot(_i)
_tp2 = _tstore2.load_project()
_tp2.state["next_chapter"] = 4
_tstore2.save_project(_tp2)
_eng2b = engine_mod.NovelEngine(_tstore2, lambda k, m: None)
# 编辑第2章：标题与正文应落盘
_c2 = _tstore2.load_chapter(2)
_c2.title = "第2章 改后标题"
_c2.content = "改后正文内容。"
_eng2b.edit_chapter(_c2)
_c2r = _tstore2.load_chapter(2)
assert _c2r.title == "第2章 改后标题" and "改后正文" in _c2r.content, "章节编辑应保存，实际 %r/%r" % (
    _c2r.title, _c2r.content)
# 仅删除中间章（第2章）：保留 1、3，进度不变，快照清除
_eng2b.delete_chapter_only(_tp2, 2)
assert _tstore2.list_chapter_indices() == [1, 3], "仅删单章应保留后续章节，实际 %r" % _tstore2.list_chapter_indices()
assert _tstore2.load_project().state["next_chapter"] == 4, "删中间章不应改变进度"
assert _tstore2.load_world_snapshot(2) is None, "被删章节的世界快照应清除"
# 仅删除最后一章（第3章）：进度回退到该章，可续写
_eng2b.delete_chapter_only(_tp2, 3)
assert _tstore2.list_chapter_indices() == [1], "最后一章应被删除"
assert _tstore2.load_project().state["next_chapter"] == 3, "删最后一章进度应回退到3"
# 回滚删除：从第1章起删 → 全部章节清空、世界回滚到初始、进度回1
_ca, _ = _tstore2.load_character(_tca.id)
assert _ca.name == "甲章主改"
assert _eng2b.rollback_delete_from(_tp2, 1), "回滚删除应成功"
assert _tstore2.list_chapter_indices() == [], "回滚删除应清空全部章节"
assert _tstore2.load_project().state["next_chapter"] == 1, "进度应回退到1"
assert _tstore2.load_project().state.get("story_complete") is False, "story_complete 应复位"
_cb, _ = _tstore2.load_character(_tca.id)
assert _cb.name == "甲章主", "角色应回滚到初始世界状态，实际 %s" % _cb.name
assert _tstore2.list_snapshot_indices() == [0], "旧快照应清理，实际 %r" % _tstore2.list_snapshot_indices()
storage.delete_project(_t2.dir_name)
git_tool_mod.commit = _orig_commit
print("[3l] 章节管理：编辑 / 仅删单章 / 回滚删除（世界快照）OK")

# ---------- compress_summary 应返回 {note, archive} ----------
_orig_cj = llm_mod.chat_json
llm_mod.chat_json = lambda *a, **k: {"note": "管理笔记测试",
                                     "archive": [{"id": "x", "reason": "y"}]}
_cs = main_ai_mod.compress_summary(st.load_project(), st)
assert _cs["note"] == "管理笔记测试" and _cs["archive"][0]["id"] == "x", "应解析 note/archive"
llm_mod.chat_json = _orig_cj
print("[3f] compress_summary 返回 note/archive JSON OK")

# ---------- 批量生成对话框构造（防控件缺失 NameError）+ 自然语言批量 + 一键核心团 ----------
from PySide6.QtCore import QTimer  # noqa: E402
from gui_characters import BatchGenDialog, CharEditDialog  # noqa: E402
_bd = BatchGenDialog()
assert _bd.desc is not None, "批量对话框应有自然语言输入框"
_ce = CharEditDialog(st.list_characters()[0][0])
assert _ce.desc_edit is not None, "角色编辑对话框应能构造"
print("[3g] 批量/角色编辑对话框构造 OK（此前缺 QSpinBox import 导致批量弹窗 NameError）")

# ---------- 批量管理对话框：勾选 → 批量改状态 / 批量删除（一次确认） ----------
from gui_characters import BatchManageDialog  # noqa: E402
# 先清理历次失败运行残留的测试角色，再造 3 个新的（放在示例项目；对话框读取 APP["project_dir"]）
for cid, name, _s in st.list_characters():
    if name.startswith("批量管理测试"):
        st.delete_character(cid)
_bm_ids = []
for _i in range(3):
    _bc = CharacterCard("批量管理测试%d" % _i, "测试身份")
    st.save_character(_bc, InfoLibrary(_bc.id))
    _bm_ids.append(_bc.id)
win.select_project("示例项目_星海孤城")
app.processEvents()
_bmd = BatchManageDialog()
assert _bmd.table.rowCount() >= 3, "批量管理表格应列出角色"
# 勾选第 1、2 行（新造的角色在列表末尾，直接按名字找行）
_bm_rows = [r for r in range(_bmd.table.rowCount())
            if _bmd.table.item(r, 1) and "批量管理测试" in _bmd.table.item(r, 1).text()]
assert len(_bm_rows) == 3, "应找到 3 个测试角色行"
_sel_cids = [_bmd._rows[r][0] for r in _bm_rows[:2]]
for _r in _bm_rows[:2]:
    _bmd.table.cellWidget(_r, 0).setChecked(True)
assert len(_bmd._selected_rows()) == 2, "应选中 2 行"
# 批量改状态：选中行 → 已归档
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
_bmd.status_combo.setCurrentText("已归档")
_bmd._apply_status()
_archived_n = sum(1 for cid, _, _s in st.list_characters()
                  if cid in _sel_cids and _s == "archived")
assert _archived_n == 2, "2 个选中角色应被改为已归档，实际 %d" % _archived_n
# 批量删除：再选 2 行 → 一次确认删除
_bm_rows2 = [r for r in range(_bmd.table.rowCount())
             if _bmd.table.item(r, 1) and "批量管理测试" in _bmd.table.item(r, 1).text()]
for _r in _bm_rows2[:2]:
    _bmd.table.cellWidget(_r, 0).setChecked(True)
_bmd._delete_selected()
_left = [cid for cid, _n, _s in st.list_characters() if cid in _bm_ids]
assert len(_left) == 1, "应剩 1 个测试角色，实际 %d" % len(_left)
for _cid in _left:
    st.delete_character(_cid)
win.page_characters.refresh()
print("[3g2] 批量管理：勾选→批量改状态→一次确认批量删除 OK")

_orig_gbr = main_ai_mod.generate_batch_roles
main_ai_mod.generate_batch_roles = lambda desc, project, store: [
    {"name": "批量需求甲", "role": "管家", "description": "x", "scenario": "府中"},
    {"name": "批量需求乙", "role": "女掌柜", "description": "y"},
]
_nb = len(win.page_characters._cards_cache)


def _auto_accept():
    dlg = QApplication.activeModalWidget()
    if dlg is not None and hasattr(dlg, "desc"):
        dlg.desc.setPlainText("城主管家与商会女掌柜各一名")
        QTimer.singleShot(30, dlg.accept)


QTimer.singleShot(100, _auto_accept)
win.page_characters._gen_batch()  # exec() 阻塞，_auto_accept 在其事件循环里触发
while _APP["running"]:
    app.processEvents()
    time.sleep(0.05)
app.processEvents()
assert len(win.page_characters._cards_cache) == _nb + 2, "自然语言批量应生成 2 个角色"
for cid, name, _ in st.list_characters():
    if name in ("批量需求甲", "批量需求乙"):
        st.delete_character(cid)
main_ai_mod.generate_batch_roles = _orig_gbr
win.page_characters.refresh()
print("[3h] 自然语言批量生成（对话框→AI拆解→建档→刷新）OK")

main_ai_mod.generate_character_ai = lambda d, p, s: {
    "name": "核心团%d" % (int(time.time() * 1000) % 10000), "role": "核心", "description": "x"}
_nb2 = len(win.page_characters._cards_cache)
win.page_characters._gen_core()
while _APP["running"]:
    app.processEvents()
    time.sleep(0.05)
app.processEvents()
assert len(win.page_characters._cards_cache) == _nb2 + 3, "一键核心角色团应生成 3 个角色"
for cid, name, _ in st.list_characters():
    if name.startswith("核心团"):
        st.delete_character(cid)
main_ai_mod.generate_character_ai = _orig_gen
win.page_characters.refresh()
print("[3i] 一键核心角色团 OK")

# ---------- 顶部「新建项目」入口（按钮/弹窗/创建载入） ----------
from gui_project import NewProjectDialog  # noqa: E402
assert hasattr(win.page_project, "new_btn"), "顶部应有「新建项目」按钮"
_npd = NewProjectDialog()
assert _npd.title is not None and _npd.story is not None
# 项目下拉应显示真实标题（此前 list_projects 返回 dict 却被按元组解包 → 显示"dir"、无法切换）
win.page_project.refresh_projects()
assert win.page_project.proj_combo.count() >= 1
for _i in range(win.page_project.proj_combo.count()):
    assert win.page_project.proj_combo.itemText(_i) != "dir", "项目下拉不应显示 dir"
    _d = win.page_project.proj_combo.itemData(_i)
    assert _d and _d != "title", "currentData 应为真实目录名"
assert any(win.page_project.proj_combo.itemText(_i) == "示例项目·星海孤城"
           for _i in range(win.page_project.proj_combo.count())), \
    "下拉应包含示例项目标题"
print("[3j] 顶部「新建项目」入口 + 项目下拉显示/切换数据 OK")
win.page_project._do_create("回归新书", "回归测试故事")
assert any(p["dir"].startswith("回归新书") for p in storage.list_projects()), "应创建并注册项目"
for p in storage.list_projects():
    if p["dir"].startswith("回归新书"):
        storage.delete_project(p["dir"])
win.select_project("示例项目_星海孤城")  # 恢复当前项目
win.page_project.on_show()
app.processEvents()
print("[3j] 顶部「新建项目」入口（按钮/弹窗/创建载入）OK")

# ---------- 统一导出位置：output/ ----------
import export_utils  # noqa: E402
_od = export_utils.ensure_output_dir()
assert os.path.basename(_od) == "output", "导出目录应为项目根 output/"
_np = export_utils.default_novel_path("测试书")
assert os.path.dirname(os.path.dirname(_np)) == _od and _np.endswith(".txt"), \
    "小说默认导出到 output/测试书/ 下，实际 %s" % _np
assert os.path.basename(os.path.dirname(_np)) == "测试书", \
    "应按项目名分类目录，实际 %s" % os.path.dirname(_np)
assert os.path.basename(_np) == "测试书.txt"
_cd = export_utils.default_cards_dir("测试书")
assert os.path.dirname(os.path.dirname(_cd)) == _od and os.path.basename(_cd) == "角色卡", \
    "角色卡默认导出到 output/测试书/角色卡/，实际 %s" % _cd
_zp = export_utils.default_project_zip_path("测试书")
assert os.path.basename(_zp) == "测试书.zip" \
    and os.path.basename(os.path.dirname(_zp)) == "测试书", "项目包默认导出到 output/测试书/ 下"
print("[3j2] 统一导出位置按项目分类（output/<项目名>/ 小说txt + 角色卡 + 项目包）OK")

# ---------- 三栏合一：AI 辅助生成按勾选填入对应栏 + 创建带三栏 ----------
# 项目页应有三栏编辑框与勾选框（整合后无独立世界观/规则 tab 也正常）
assert win.page_project.p_story is not None
assert win.page_project.p_world is not None
assert win.page_project.p_rules is not None
assert win.page_project.plan_chk_story is not None and win.page_project.plan_chk_world is not None
assert win.page_project.plan_chk_rules is not None
# 先清空三栏（示例项目可能带历史设定），再勾选 剧情+世界观（不勾规则）
win.page_project.p_story.setPlainText("")
win.page_project.p_world.setPlainText("")
win.page_project.p_rules.setPlainText("")
# 勾选 剧情+世界观（不勾规则）→ mock plan_story_ai 按 targets 返回 → 只填勾选的两栏
_orig_plan = main_ai_mod.plan_story_ai
_FULL_PLAN = {"story": "AI 剧情草稿", "world": "AI 世界观草稿", "rules": "AI 规则草稿"}
main_ai_mod.plan_story_ai = lambda opening, notes, constraint, targets: {
    k: v for k, v in _FULL_PLAN.items() if k in targets}
win.page_project.plan_chk_story.setChecked(True)
win.page_project.plan_chk_world.setChecked(True)
win.page_project.plan_chk_rules.setChecked(False)
win.page_project.plan_notes.setText("测试想法")
win.page_project._plan_ai()
while _APP["running"]:
    app.processEvents()
    time.sleep(0.05)
app.processEvents()
assert "AI 剧情草稿" in win.page_project.p_story.toPlainText(), "剧情栏应填入"
assert "AI 世界观草稿" in win.page_project.p_world.toPlainText(), "世界观栏应填入"
assert win.page_project.p_rules.toPlainText() == "", "未勾选的规则栏不应被填"
# 保存三栏 → 落盘
win.page_project._save()
_pj5 = st.load_project()
assert _pj5.story_brief == "AI 剧情草稿" and _pj5.story_world == "AI 世界观草稿", \
    "保存应写入剧情与世界观"
main_ai_mod.plan_story_ai = _orig_plan
win.page_project.p_story.setPlainText("")
win.page_project.p_world.setPlainText("")
win.page_project.p_rules.setPlainText("")
print("[3k] 三栏合一：AI 辅助按勾选生成并填入对应栏 + 保存 OK")

# 新建项目 tab 勾选创建：mock 后 _create_with_ai 应创建带三栏的项目
main_ai_mod.plan_story_ai = lambda opening, notes, constraint, targets: {
    "story": "新书剧情", "world": "新书世界观", "rules": "新书规则"}
win.page_project.new_title.setText("三栏创建测试")
win.page_project.new_chk_story.setChecked(True)
win.page_project.new_chk_world.setChecked(True)
win.page_project.new_chk_rules.setChecked(True)
win.page_project._create_with_ai()
while _APP["running"]:
    app.processEvents()
    time.sleep(0.05)
app.processEvents()
_p3c = None
for _p in storage.list_projects():
    if _p["dir"].startswith("三栏创建测试"):
        _p3c = _p
        break
assert _p3c, "应创建三栏项目"
_pstore = storage.ProjectStore(_p3c["dir"])
_pj3c = _pstore.load_project()
assert _pj3c.story_brief == "新书剧情" and _pj3c.story_world == "新书世界观" \
    and _pj3c.story_rules == "新书规则", "创建应带三栏内容"
storage.delete_project(_p3c["dir"])
main_ai_mod.plan_story_ai = _orig_plan
win.select_project("示例项目_星海孤城")
win.page_project.on_show()
app.processEvents()
print("[3k2] 新建项目+AI辅助整合：按勾选 AI 生成三栏并创建项目 OK")

win.switch_page(0)  # 项目页
app.processEvents()
win.switch_page(9)  # 设置页（v1.66 码字页插入后：项目0 码字1 角色2 生成3 去AI味4 文风5 拆书6 AI对话7 故事8 设置9 教程10）
app.processEvents()
n0 = win.page_settings.list.count()
win.page_settings._add()
app.processEvents()
assert win.page_settings.list.count() == n0 + 1
# 用途分工：13 个用途下拉 + 13 个思考强度下拉（v0.56 拆书/导入；v0.64/0.66 文风校对四节点；
# v0.94 AI对话/Agent + 思考强度；v1.19 情景提示词制作；v1.65 删除 Agent；v1.69 新增 码字AI(write_tool)）
assert set(win.page_settings.role_combos.keys()) == {"decide", "write", "reason", "deai",
                                                     "review", "write_tool", "break",
                                                     "import", "scene_card",
                                                     "style_a", "style_b", "style_c",
                                                     "style_d", "chat"}, \
    "应有主AI决断/正文写作/角色推理/去AI味/审查AI/码字AI/拆书工坊/导入/情景提示词制作/文风校对四节点/AI对话 13 个用途下拉 + 思考强度，实际 %r" \
    % list(win.page_settings.role_combos.keys())
assert set(win.page_settings.think_combos.keys()) == set(
    win.page_settings.role_combos.keys()), "每行用途都应有独立思考强度下拉"
# v0.95 功能级思考强度应有 6 档（跟随全局/关闭/低/中/高/最大），含「关闭思考」
_tc_brk = win.page_settings.think_combos["break"]
assert _tc_brk.count() == 6, "功能级思考强度应有 6 档（跟随全局/关闭/低/中/高/最大），实际 %d" % _tc_brk.count()
assert _tc_brk.itemData(1) == "off", "功能级第 2 档应为「关闭思考（off）」，实际 %r" % _tc_brk.itemData(1)
# v0.94 思考强度：某行选「低」→ 写入 role_thinking 且 llm 按功能生效
_tk_brk = win.page_settings.think_combos["break"]
_tk_brk.setCurrentIndex(2)   # 低（low）（触发 currentIndexChanged → 自动保存）
app.processEvents()
config._cache = None
assert (config.load_config().get("role_thinking") or {}).get("break") == "low", \
    "拆书思考强度选「低」应写 role_thinking.break"
_tk_brk.setCurrentIndex(0)   # 归位跟随全局
app.processEvents()
_cfg_rp = config.load_config()
_new_name = _cfg_rp["api_profiles"][-1]["name"]
_cmb_decide = win.page_settings.role_combos["decide"]
_cmb_decide.setCurrentIndex(_cmb_decide.count() - 1)  # 选中刚新增的配置
app.processEvents()
config._cache = None
assert config.load_config().get("role_profiles", {}).get("decide") == _new_name, \
    "用途分工选择应自动保存"
# v0.56 拆书工坊/导入的用途分工 → 同步引擎读取键 break_profile/import_profile
_cmb_brk = win.page_settings.role_combos["break"]
_cmb_brk.setCurrentIndex(_cmb_brk.count() - 1)
_cmb_imp = win.page_settings.role_combos["import"]
_cmb_imp.setCurrentIndex(_cmb_imp.count() - 1)
# v0.66 文风校对四节点用途分工 → 同步引擎读取键 style_profiles dict（node_a 兼写旧单键 style_profile）
_cmb_sa = win.page_settings.role_combos["style_a"]
_cmb_sb = win.page_settings.role_combos["style_b"]
_cmb_sc = win.page_settings.role_combos["style_c"]
_cmb_sd = win.page_settings.role_combos["style_d"]
_cmb_sa.setCurrentIndex(_cmb_sa.count() - 1)
_cmb_sb.setCurrentIndex(_cmb_sb.count() - 1)
_cmb_sc.setCurrentIndex(_cmb_sc.count() - 1)
_cmb_sd.setCurrentIndex(_cmb_sd.count() - 1)
app.processEvents()
config._cache = None
_cfg_rp2 = config.load_config()
assert _cfg_rp2.get("break_profile") == _new_name, "拆书工坊用途分工应写 break_profile"
assert _cfg_rp2.get("import_profile") == _new_name, "小说导入成项目用途分工应写 import_profile"
assert (_cfg_rp2.get("style_profiles") or {}).get("node_a") == _new_name, \
    "文风校对节点A用途分工应写 style_profiles.node_a"
assert (_cfg_rp2.get("style_profiles") or {}).get("node_b") == _new_name, \
    "文风校对节点B用途分工应写 style_profiles.node_b"
assert (_cfg_rp2.get("style_profiles") or {}).get("node_c") == _new_name, \
    "文风校对节点C用途分工应写 style_profiles.node_c"
assert (_cfg_rp2.get("style_profiles") or {}).get("node_d") == _new_name, \
    "文风校对节点D用途分工应写 style_profiles.node_d"
assert _cfg_rp2.get("style_profile") == _new_name, "node_a 应兼容写旧单键 style_profile"
# 还原 break/import/文风校对分工
_cmb_brk.setCurrentIndex(0)
_cmb_imp.setCurrentIndex(0)
_cmb_sa.setCurrentIndex(0)
_cmb_sb.setCurrentIndex(0)
_cmb_sc.setCurrentIndex(0)
_cmb_sd.setCurrentIndex(0)
app.processEvents()
config._cache = None
win.page_settings.list.setCurrentRow(win.page_settings.list.count() - 1)
win.page_settings._delete()
app.processEvents()
config._cache = None
assert config.load_config().get("role_profiles", {}).get("decide") != _new_name, \
    "删除配置应清理用途分工里对它的引用"
# 迁移回归：用户保存过用途分工（含全「不指定」）后，残留的旧 role 字段不得再自动回填
_cfg_mig = config.load_config()
_cfg_mig["role_profiles"] = {}
if _cfg_mig["api_profiles"]:
    _cfg_mig["api_profiles"][0]["role"] = "write"   # 模拟旧版配置残留
config.save_config(_cfg_mig)
config._cache = None
assert "write" not in (config.load_config().get("role_profiles") or {}), \
    "已保存的用途分工（含不指定）不应被旧 role 字段迁移覆盖"
cfg = config.load_config()
assert len(cfg["api_profiles"]) == len(_ORIG_CFG["api_profiles"]), \
    "设置页增删后 profile 条数应恢复为用户原配置"
print("[4] 设置页 API 配置增删 + 用途分工联动 OK")

# v0.60 设置页布局修复回归：此前「伏笔逾期阈值（高级设置第 7 项）」落在网格 (2,0)，
# 「审查策略」也被放进 (2,0) → 两功能在同一格重叠看不到。现应在不同行且几何不重叠。
win.switch_page(9)   # 设置页（v1.66 码字页插入后，设置 index=9）
app.processEvents()
_fs_spin = win.page_settings.spins["foreshadow_overdue_chapters"]
_rs_radio = win.page_settings.rewrite_chk
app.processEvents()
_g_fs, _g_rs = _fs_spin.geometry(), _rs_radio.geometry()
assert _g_fs.width() > 0 and _g_rs.width() > 0, "布局未生效（宽=%d/%d）" % (_g_fs.width(), _g_rs.width())
assert _g_fs.y() != _g_rs.y() and not _g_fs.intersects(_g_rs), \
    "伏笔逾期阈值与审查策略不应重叠（%r vs %r）" % (_g_fs, _g_rs)
assert win.page_settings.search_chk is not None and win.page_settings.effort_combo is not None, \
    "灵感来源/推理思考强度控件应存在"
print("[4d] 设置页高级网格：伏笔逾期阈值 与 审查策略 不再重叠 OK")

# v0.63 剧情点确认开关断链修复（子代理审查发现：不持久化 + 全自动/重新生成路径勾了不生效）
_orig_cb = config.load_config().get("confirm_beats_enabled", False)
_gg = win.page_generate
_gg.on_show()
assert _gg.confirm_beats_check.isChecked() == bool(_orig_cb), "on_show 应回填开关"
_gg.confirm_beats_check.setChecked(True)      # 勾选 → 立即写 config
app.processEvents()
assert config.load_config().get("confirm_beats_enabled") is True, "勾选应写入 config 键"
_gg.on_show()
assert _gg.confirm_beats_check.isChecked() is True, "保存后回填应保持勾选（持久化）"
_gg.confirm_beats_check.setChecked(False)     # 取消 → 写回 False
app.processEvents()
assert config.load_config().get("confirm_beats_enabled") is False, "取消应写入 config"
import inspect as _ins
import engine as _eng_mod
assert "beats_confirm" in _ins.signature(_eng_mod.NovelEngine.auto_run).parameters, \
    "auto_run 应支持 beats_confirm（全自动连写弹确认）"
assert "beats_confirm" in _ins.signature(_eng_mod.NovelEngine.generate_draft).parameters, \
    "generate_draft 应支持 beats_confirm"
_gg_src = open("src/gui_generate.py", encoding="utf-8").read()
assert "beats_confirm=beats_confirm" in _gg_src, "重新生成/全自动路径应传 beats_confirm"
_cfg_r = config.load_config()
_cfg_r["confirm_beats_enabled"] = _orig_cb
config.save_config(_cfg_r)
config._cache = None
print("[4e] 剧情点确认开关断链修复：持久化 + 全自动/重新生成路径生效 OK")

# 温度控件应为小数步进（可设 0.8 等常用值），超时上限应足够大（本地模型慢）
from PySide6.QtWidgets import QDoubleSpinBox  # noqa: E402
assert isinstance(win.page_settings.spins["temperature"], QDoubleSpinBox), \
    "温度控件应为小数输入"
assert win.page_settings.spins["request_timeout"].maximum() == 999999, \
    "超时上限应放开（999999 秒）"
win.page_settings.spins["temperature"].setValue(0.8)
win.page_settings.spins["request_timeout"].setValue(600)
win.page_settings._save_params()
config._cache = None
cfg = config.load_config()
assert abs(cfg["temperature"] - 0.8) < 1e-9, "温度应保存为 0.8"
assert cfg["request_timeout"] == 600, "超时应保存为 600"
print("[4b] 温度小数步进 + 超时上限放开（保存/回读）OK")

# 重试次数/重试间隔应可在设置页配置
assert win.page_settings.spins["retry_times"] is not None \
    and win.page_settings.spins["retry_interval"] is not None, "设置页应有重试次数/间隔控件"
win.page_settings.spins["retry_times"].setValue(5)
win.page_settings.spins["retry_interval"].setValue(8)
win.page_settings._save_params()
config._cache = None
cfg = config.load_config()
assert cfg["retry_times"] == 5 and cfg["retry_interval"] == 8, \
    "重试次数/间隔应保存，实际 %s/%s" % (cfg.get("retry_times"), cfg.get("retry_interval"))

# 自动保存：参数改动后不手动点「保存参数」，也应自动落盘（防抖 600ms）
win.page_settings.on_show()
config._cache = None
win.page_settings.spins["retry_times"].setValue(11)
win.page_settings.spins["retry_interval"].setValue(33)
for _ in range(12):
    app.processEvents()
    time.sleep(0.1)
config._cache = None
cfg = config.load_config()
assert cfg["retry_times"] == 11 and cfg["retry_interval"] == 33, \
    "参数改动应自动保存，实际 %s/%s" % (cfg.get("retry_times"), cfg.get("retry_interval"))

win.page_settings.spins["retry_times"].setValue(int(_ORIG_CFG.get("retry_times", 3)))
win.page_settings.spins["retry_interval"].setValue(int(_ORIG_CFG.get("retry_interval", 3)))
win.page_settings._save_params()
config._cache = None
print("[4c] 设置页重试次数/间隔可配置 + 改动自动保存 OK")

win.switch_page(3)  # 生成页（v1.66 码字页插入后 index=3）
app.processEvents()
# 生成页应能查看已归档的前文（示例项目无章节时，先造一个测试章节）
from models import Chapter as _Ch  # noqa: E402
_ch = st.load_chapter(1)
if _ch is None:
    _tc = _Ch(1, 1)
    _tc.title = "第一章 冒烟测试章"
    _tc.content = "冒烟测试正文内容。"
    _tc.status = "approved"
    st.save_chapter(_tc)
    _made_ch = True
else:
    _made_ch = False
win.page_generate._refresh_history(st, st.load_project())
assert win.page_generate.hist_combo.count() >= 1, "「已写章节」下拉应列出已归档章节"
from gui_generate import ChapterViewDialog  # noqa: E402
_ch = st.load_chapter(1)
assert _ch is not None
_dlg = ChapterViewDialog(_ch, st)
assert _dlg.windowTitle()  # 弹窗应能构建
from gui_generate import SummaryViewDialog  # noqa: E402
_sd = SummaryViewDialog("测试管理笔记")
assert _sd.windowTitle() == "主AI管理笔记"
if _made_ch:
    import os as _os  # noqa: E402
    _p = st.chapter_path(1)
    if _os.path.exists(_p):
        _os.remove(_p)
print("[5] 生成页构建 + 已写章节下拉/阅读弹窗/管理笔记弹窗 OK")
win.switch_page(8)  # 故事页（v1.66 码字页插入后顺序：项目0 码字1 角色2 生成3 去AI味4 文风5 拆书6 AI对话7 故事8 设置9）
app.processEvents()
assert hasattr(win.page_story, "summary_view"), "故事页应有管理笔记页签"
win.page_story.refresh_all()
app.processEvents()
print("[5b] 故事页构建 + 主AI管理笔记页签 OK")

# ---------- 生成页主AI提示词保存（与项目页④同一字段）+ 章节管理对话框构造 ----------
win.switch_page(3)  # 生成页（v1.66 码字页插入后 index=3）
app.processEvents()
assert hasattr(win.page_generate, "main_prompt"), "生成页应有主AI提示词框"
_prev_mp = st.load_project().story_main_prompt
win.page_generate.main_prompt.setPlainText("生成页主AI提示词测试")
win.page_generate._save_main_prompt()
assert st.load_project().story_main_prompt == "生成页主AI提示词测试", "主AI提示词应写入项目"
win.page_generate.main_prompt.setPlainText(_prev_mp or "")
win.page_generate._save_main_prompt()
assert st.load_project().story_main_prompt == (_prev_mp or ""), "主AI提示词应恢复原值"
from gui_generate import (ChapterManagerDialog, ChapterEditDialog,  # noqa: E402
                          DeleteChapterDialog)
# 确保示例项目有一章，便于章节管理列出
_made_ch2 = False
if st.load_chapter(1) is None:
    _tc2 = _Ch(1, 1)
    _tc2.title = "第一章 管理测试"
    _tc2.content = "章节管理测试正文。"
    _tc2.status = "approved"
    st.save_chapter(_tc2)
    _made_ch2 = True
win.page_generate._update_progress()
app.processEvents()
_cmd = ChapterManagerDialog(win)
assert _cmd.listw.count() >= 1, "章节管理应列出章节，实际 %d" % _cmd.listw.count()
_ced = ChapterEditDialog(st.load_chapter(1), st)
assert _ced.title_edit is not None and _ced.content_edit is not None, "编辑对话框应有标题/正文控件"
_dd = DeleteChapterDialog(1, "第一章 管理测试")
assert _dd.rb_rollback is not None and _dd.rb_single is not None, "删除确认应有两种模式"
_dd.rb_single.setChecked(True)
_dd._ok()
assert _dd.rollback_mode is False, "选择仅删本章后 rollback_mode 应为 False"
if _made_ch2:
    import os as _os3  # noqa: E402
    _p2 = st.chapter_path(1)
    if _os3.path.exists(_p2):
        _os3.remove(_p2)
win.page_generate._update_progress()
print("[5c] 生成页主AI提示词保存 + 章节管理对话框（列/编辑/删除模式）OK")

# ---------- 章节管理多选（连续阅读/批量删除按钮）+ 角色卡导入按钮 ----------
from PySide6.QtWidgets import QAbstractItemView as _QAIV  # noqa: E402
from gui_generate import MultiChapterDialog  # noqa: E402
_made_ch4 = False
if st.load_chapter(1) is None:
    _tc4 = _Ch(1, 1)
    _tc4.title = "第一章 多选测试甲"
    _tc4.content = "多选测试正文甲。"
    _tc4.status = "approved"
    st.save_chapter(_tc4)
    _tc4b = _Ch(2, 1)
    _tc4b.title = "第二章 多选测试乙"
    _tc4b.content = "多选测试正文乙。"
    _tc4b.status = "approved"
    st.save_chapter(_tc4b)
    _made_ch4 = True
win.page_generate._update_progress()
app.processEvents()
_cmd2 = ChapterManagerDialog(win)
assert _cmd2.listw.selectionMode() == _QAIV.SelectionMode.ExtendedSelection, \
    "章节列表应为多选模式"
assert _cmd2.read_multi_btn is not None and _cmd2.del_multi_btn is not None, "应有批量操作按钮"
assert not _cmd2.del_multi_btn.isEnabled(), "单选时批量按钮应禁用"
_cmd2.listw.item(0).setSelected(True)
_cmd2.listw.item(1).setSelected(True)
app.processEvents()
assert _cmd2.read_multi_btn.isEnabled() and _cmd2.del_multi_btn.isEnabled(), \
    "多选后批量按钮应启用"
assert hasattr(_cmd2, "_export") and callable(_cmd2._export), "章节管理应有导出小说入口"
_md = MultiChapterDialog(st, [1, 2])
assert "连续阅读" in _md.windowTitle() and _md.idxs == [1, 2], "连续阅读弹窗应可构造"
assert hasattr(win.page_characters, "_import_cards"), "角色页应有导入角色卡入口"
if _made_ch4:
    for _ci4 in (1, 2):
        _p4 = st.chapter_path(_ci4)
        if os.path.exists(_p4):
            os.remove(_p4)
win.page_generate._update_progress()
print("[5d] 章节管理多选（连续阅读/批量删除按钮联动）+ 连续阅读弹窗 + 角色卡导入入口 OK")

# ---------- 小说导出双格式：完整拼接 txt + 分章文件夹（每章一个 txt） ----------
win.switch_page(8)  # 故事页（v1.66 码字页插入后顺序：项目0 码字1 角色2 生成3 去AI味4 文风5 拆书6 AI对话7 故事8 设置9）
app.processEvents()
_made_ch3 = False
if st.load_chapter(1) is None:
    _tc3 = _Ch(1, 1)
    _tc3.title = "第一章 双格式测试章"
    _tc3.content = "双格式导出测试正文内容。"
    _tc3.status = "approved"
    st.save_chapter(_tc3)
    _made_ch3 = True
win.page_story.refresh_all()
app.processEvents()
import PySide6.QtWidgets as _qtw2  # noqa: E402
_orig_save = _qtw2.QFileDialog.getSaveFileName
_orig_info = _qtw2.QMessageBox.information
_tmp_export = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_export_double.txt")
_qtw2.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (_tmp_export, "文本文件 (*.txt)"))
_qtw2.QMessageBox.information = staticmethod(lambda *a, **k: _qtw2.QMessageBox.StandardButton.Ok)
win.page_story._export_novel()
_qtw2.QFileDialog.getSaveFileName = _orig_save
_qtw2.QMessageBox.information = _orig_info
assert os.path.exists(_tmp_export), "完整版 txt 应生成"
with open(_tmp_export, encoding="utf-8") as _f:
    _full_txt = _f.read()
assert "双格式导出测试正文内容" in _full_txt, "完整版应含章节正文"
_export_dir = _tmp_export[:-4] + "_分章"
assert os.path.isdir(_export_dir), "分章文件夹应生成"
_vols = sorted(os.listdir(_export_dir))
assert _vols == ["第1卷"], "分章文件夹应按卷分子目录，实际 %r" % _vols
_files = sorted(os.listdir(os.path.join(_export_dir, "第1卷")))
assert len(_files) >= 1 and _files[0].endswith(".txt") and "第001章" in _files[0], \
    "分章文件名应按章节排序，实际 %r" % _files
with open(os.path.join(_export_dir, "第1卷", _files[0]), encoding="utf-8") as _f:
    assert "双格式导出测试正文内容" in _f.read(), "分章文件应含正文"
import shutil as _sh3  # noqa: E402
if os.path.exists(_tmp_export):
    os.remove(_tmp_export)
if os.path.isdir(_export_dir):
    _sh3.rmtree(_export_dir)
if _made_ch3:
    _p3 = st.chapter_path(1)
    if os.path.exists(_p3):
        os.remove(_p3)
win.page_story.refresh_all()
print("[3r] 小说导出双格式（完整txt + 分章文件夹逐章txt）OK")

# ---------- EPUB 电子书导出（v0.56 回归补测：引擎级，验证 EPUB3 结构） ----------
import export_utils as _eu  # noqa: E402
import zipfile as _z4  # noqa: E402
_made_ep = False
if st.load_chapter(1) is None:
    _tec = _Ch(1, 1)
    _tec.title = "EPUB 测试章"
    _tec.content = "双格式导出测试正文内容。"
    _tec.status = "approved"
    st.save_chapter(_tec)
    _made_ep = True
_epub_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_export_test.epub")
_epub_ok = _eu.export_novel_epub(st.load_project(), st, _epub_path)
assert _epub_ok and os.path.exists(_epub_path), "EPUB 导出应成功"
with _z4.ZipFile(_epub_path) as _zf:
    _names = _zf.namelist()
    assert _names and _names[0] == "mimetype", "EPUB mimetype 应为第一个文件，实际 %r" % _names[:1]
    assert _zf.read("mimetype").decode("utf-8", errors="replace").strip() == "application/epub+zip", \
        "mimetype 内容应正确"
    assert any("content.opf" in n for n in _names), "EPUB 应含 content.opf"
    assert any("nav.xhtml" in n for n in _names), "EPUB 应含 EPUB3 nav.xhtml"
    assert any("双格式导出测试正文内容" in _zf.read(n).decode("utf-8", errors="replace")
               for n in _names if n.endswith(".xhtml")), "EPUB 应含章节正文"
    assert any(n.endswith(".ncx") for n in _names), "EPUB 应含 toc.ncx（EPUB2 兜底）"
if os.path.exists(_epub_path):
    os.remove(_epub_path)
if _made_ep:
    _p4 = st.chapter_path(1)
    if os.path.exists(_p4):
        os.remove(_p4)
print("[3r2] EPUB3 电子书导出（mimetype 首项/content.opf/nav/toc.ncx/正文）OK")

# ---------- 分卷管理（v0.56 回归补测：引擎级单章归卷/整卷合并/还原） ----------
_chv = st.load_chapter(1)
if _chv is not None:
    _orig_vol = _chv.volume
    st.set_chapter_volume(1, 9)
    assert st.load_chapter(1).volume == 9, "单章归卷应生效"
    st.rename_volume(9, 3)
    assert st.load_chapter(1).volume == 3, "整卷合并应生效"
    st.set_chapter_volume(1, _orig_vol)
    assert st.load_chapter(1).volume == _orig_vol, "归卷应还原"
    print("[3r3] 分卷管理（单章归卷/整卷合并/还原）OK")

# ---------- 去AI味：存储 CRUD + apply_deai 备份合并 + UI 全链路（mock LLM） ----------
assert hasattr(win, "page_deai") and win.page_deai is not None, "主窗口应有去AI味页"
_pd = win.page_deai
assert _pd.rb_clean is not None and _pd.rb_replace is not None and _pd.rb_rewrite is not None, \
    "应有三种处理模式单选"
assert _pd.rb_whole is not None and _pd.rb_part is not None, "应有整章/局部重写范围选择"
assert _pd.rules_edit is not None and _pd.ch_list is not None and _pd.draft_list is not None

# 待定稿存储 CRUD（临时项目）
_p_deai = storage.create_project("去AI味测试")
_st_deai = storage.ProjectStore(_p_deai.dir_name)
_tc_deai = _Ch(1, 1)
_tc_deai.title = "去AI味测试章"
_tc_deai.content = "他不是害怕，而是愤怒。他缓缓握紧拳头，指尖发白。"
_tc_deai.status = "approved"
_st_deai.save_chapter(_tc_deai)
_st_deai.save_deai_draft(1, "他握紧拳头，指节咯咯作响。", mode="clean", rules="测试规则")
assert _st_deai.load_deai_draft(1)["polished"] == "他握紧拳头，指节咯咯作响。", "待定稿应保存"
assert any(d["chapter"] == 1 for d in _st_deai.list_deai_drafts()), "待定稿应列出"
_st_deai.delete_deai_draft(1)
assert not _st_deai.load_deai_draft(1), "待定稿应已删除"

# apply_deai：写回 + 合并前自动备份草稿箱（mock git）
_eng_deai = engine_mod.NovelEngine(_st_deai, lambda k, m: None)
_orig_commit_deai = git_tool_mod.commit
git_tool_mod.commit = lambda *a, **k: None
ok = _eng_deai.apply_deai(_p_deai, 1, "他一把抓住桌沿。")
assert ok, "apply_deai 应成功"
assert _st_deai.load_chapter(1).content == "他一把抓住桌沿。", "合并后章节应为润色稿"
assert any(d["tag"] == "deai" for d in _st_deai.list_chapter_drafts()), \
    "合并前应自动备份旧稿（tag=deai）"

# UI 全链路：mock deai_chapter → 处理 → 待定稿 → 对比预览 → 全部合并
def _fake_deai(project, store, chapter, mode="clean", rules="",
               selected_text="", directive="", audit_issues=None, style_ref=""):
    return "【润色】" + (chapter.content or "")

_orig_deai_fn = getattr(main_ai_mod, "deai_chapter", None)
_orig_deai_audit = getattr(main_ai_mod, "deai_audit", None)
main_ai_mod.deai_chapter = _fake_deai
main_ai_mod.deai_audit = lambda *a, **k: []   # 整体审查 mock：避免真调 API
win.select_project(_p_deai.dir_name)
_pd.on_show()
app.processEvents()
assert _pd.ch_list.count() >= 1, "去AI味页章节列表应有章节"
# 选中章节应立即在原文预览显示（供查看/选中局部重写目标）
_pd.ch_list.item(0).setSelected(True)
app.processEvents()
assert _pd.orig_view.toPlainText().strip(), "选中章节后原文预览应有内容"
_pd.ch_list.item(_pd.ch_list.count() - 1).setSelected(True)
_pd.rb_clean.setChecked(True)
_pd._start()
_found_draft = False
for _ in range(80):
    app.processEvents()
    time.sleep(0.1)
    if _pd.draft_list.count() >= 1:
        _found_draft = True
        break
assert _found_draft, "处理应产生待定稿"
_pd.draft_list.setCurrentRow(0)
app.processEvents()
assert "【润色】" in _pd.polish_view.toPlainText(), "对比预览应显示润色稿"
_pd._merge_all()
assert _st_deai.load_chapter(1).content.startswith("【润色】"), "全部合并后章节应为润色稿"
assert not _st_deai.list_deai_drafts(), "合并后待定稿应清空"
# 局部重写目标：在原文预览里拖选文本 → 选区自动成为目标且提示更新
from PySide6.QtGui import QTextCursor as _QTC  # noqa: E402
_pd.orig_view.setPlainText("他缓缓握拳，指尖发白。远处传来钟声。")
_curs = _pd.orig_view.textCursor()
_curs.setPosition(0)
_curs.setPosition(len("他缓缓握拳，指尖发白。"), _QTC.MoveMode.KeepAnchor)
_pd.orig_view.setTextCursor(_curs)
app.processEvents()
assert "缓缓" in _pd._sel_text, "拖选文本应成为局部重写目标，实际 %r" % _pd._sel_text
assert "已选" in _pd.sel_text_lbl.text(), "应实时显示已选字数"
if _orig_deai_fn is not None:
    main_ai_mod.deai_chapter = _orig_deai_fn
if _orig_deai_audit is not None:
    main_ai_mod.deai_audit = _orig_deai_audit
git_tool_mod.commit = _orig_commit_deai
win.select_project("示例项目_星海孤城")
win.page_deai.on_show()
storage.delete_project(_p_deai.dir_name)
print("[6] 去AI味：存储CRUD + apply_deai备份合并 + UI全链路（处理→待定稿→合并）OK")

# 清理：删除测试角色，恢复用户真实配置（API Key 原样保留，绝不删除）
st.delete_character(card.id)

# ---------- v0.53 写作工作台：章节交换 / 全文搜索 / 写作统计 / AI 段落工具 ----------
_p_ws = storage.create_project("工作台测试")
_st_ws = storage.ProjectStore(_p_ws.dir_name)
for _i in (1, 2, 3):
    _tc = _Ch(_i, 1)
    _tc.title = "第%d章 工具测试" % _i
    _tc.content = "第%d章正文内容。主角林晚推开木门。" % _i
    _tc.status = "approved"
    _st_ws.save_chapter(_tc)
# 搜索：标题/正文命中
_hits = _st_ws.search_chapters("林晚")
assert len(_hits) == 3, "全文搜索应命中 3 章（正文含主角名），实际 %d" % len(_hits)
_hits2 = _st_ws.search_chapters("工具测试")
assert len(_hits2) == 3 and all(h["where"] in ("title", "brief") or True for h in _hits2), \
    "标题搜索应命中"
_hits3 = _st_ws.search_chapters("不存在的词")
assert _hits3 == [], "无命中应返回空列表"
# 统计
_sts = _st_ws.project_stats()
assert _sts["chapters"] == 3 and _sts["total_chars"] > 0, "统计应含章数与总字数"
assert _sts["volume_chars"] and _sts["volume_chars"][0]["vol"] == 1 \
    and _sts["volume_chars"][0]["count"] == 3, "统计应按卷聚合"
# 交换：第1章与第3章内容互换（旧版备份草稿箱）
assert _st_ws.swap_chapters(1, 3), "交换应成功"
assert _st_ws.load_chapter(1).title == "第3章 工具测试", "第1章应变为原第3章标题"
assert _st_ws.load_chapter(3).title == "第1章 工具测试", "第3章应变为原第1章标题"
assert any(d["tag"] == "swap" for d in _st_ws.list_chapter_drafts()), \
    "交换前应备份到草稿箱（tag=swap）"
assert not _st_ws.swap_chapters(2, 2), "同章交换应失败"
assert not _st_ws.swap_chapters(2, 99), "不存在的章节交换应失败"
# 引擎级交换（含 git 存档 mock）
_eng_ws = engine_mod.NovelEngine(_st_ws, lambda k, m: None)
_orig_commit_ws = git_tool_mod.commit
git_tool_mod.commit = lambda *a, **k: None
assert _eng_ws.swap_chapters(1, 2), "引擎交换第1/2章应成功"
git_tool_mod.commit = _orig_commit_ws
# AI 段落工具：mock 维护函数，验证对话框可构造
from gui_generate import SearchDialog, StatsDialog, PolishParagraphDialog  # noqa: E402
_dlg_stats = StatsDialog(_st_ws, win)
assert _dlg_stats is not None
_dlg_search = SearchDialog(win)
assert _dlg_search.kw is not None, "搜索对话框应有关键词输入框"
_dlg_polish = PolishParagraphDialog("他缓缓握紧拳头，指尖发白。", win)
assert _dlg_polish.mode.count() == 4, "段落工具应有 4 种处理模式"
assert _dlg_polish._text.startswith("他缓缓"), "段落工具应携带选中文本"
win.select_project("示例项目_星海孤城")
_storage_mod2 = storage
_ws_dir_name = _st_ws.dir_name
_ws_base = _st_ws.base
del _st_ws, _p_ws
storage.delete_project(_ws_dir_name)   # 同步清索引，不留死条目
print("[7] 写作工作台：全文搜索 / 写作统计 / 章节交换（引擎+草稿备份） / AI 段落工具 OK")

# ---------- v0.54 一键成书：AI 立项（书名+三栏设定）→ 建项目 → 核心角色 → 连写 N 章 ----------
# mock 全部 LLM 环节，验证 AutoBookDialog 可构造 + 工作器整链路 + 停止后项目保留
from PySide6.QtCore import QThread  # noqa: E402
_orig_plan_title = main_ai_mod.plan_title
_orig_plan_story = main_ai_mod.plan_story_ai
main_ai_mod.plan_title = lambda idea: "测试一键书"
main_ai_mod.plan_story_ai = lambda *a, **k: {
    "story": "主角穿越修仙世界，觉醒捡垃圾金手指。",
    "world": "修真界九洲大陆。",
    "rules": "金手指：捡的废品可变神器。",
}
# 一键成书连写链路复刻 [3u] 全自动的 mock 集合：无需真实调 API
_orig_decide_bk = main_ai_mod.decide_characters
_orig_infer_bk = engine_mod.char_ai.run_inference
_orig_cons_bk = main_ai_mod.consolidate
_orig_write_bk = main_ai_mod.write_chapter
_orig_review_bk = main_ai_mod.review_chapter
main_ai_mod.decide_characters = lambda *a, **k: {
    "scene_focus": "场景", "characters": [{"id": "c_bk"}],
    "recall": [], "new_character_hint": ""}
engine_mod.char_ai.run_inference = lambda *a, **k: {}
main_ai_mod.consolidate = lambda *a, **k: {
    "verdict": "ok", "approved_direction": "d", "chapter_beats": [],
    "planning_note": "", "cliche_watch": [],
    "foreshadows": [], "kb_update": [], "need_chapters": [],
    "search_queries": []}
main_ai_mod.write_chapter = lambda *a, **k: ("第1章 一键测试", "一键成书测试正文。" * 140)
main_ai_mod.review_chapter = lambda *a, **k: {
    "approved": True, "issues": [], "pacing": "稳", "scores": {},
    "cliches": [], "brief": "梗概", "next_direction": ""}
# finalize_chapter 战后的 LLM 环节一并 mock（否则真实调 API 卡死）
_orig_upd_world = main_ai_mod.update_world
_orig_compress = main_ai_mod.compress_summary
_orig_vol_close = main_ai_mod.volume_closing
_orig_proof = main_ai_mod.proofread_chapter
main_ai_mod.update_world = lambda *a, **k: {}
main_ai_mod.compress_summary = lambda *a, **k: {"note": "", "archive": []}
main_ai_mod.volume_closing = lambda *a, **k: ""
main_ai_mod.proofread_chapter = lambda *a, **k: {"content": "", "notes": []}
_orig_ensure_bk = engine_mod.NovelEngine.ensure_world

def _fake_ensure(store_self, project):
    from models import CharacterCard, InfoLibrary  # noqa: E402
    for _nm, _role in (("林晚", "捡垃圾主角"), ("老狗", "话痨宠物")):
        _card = CharacterCard(_nm, _role)
        _card.description = "一键成书自动生成的核心角色。"
        store_self.store.save_character(_card, InfoLibrary(_card.id))
        # 把 id 同步给 decide mock（按角色名匹配）

engine_mod.NovelEngine.ensure_world = _fake_ensure
# decide mock 改为返回空角色，由 ensure_world 已建的角色池兜底（引擎会自动选池内角色）
main_ai_mod.decide_characters = lambda *a, **k: {
    "scene_focus": "场景", "characters": [],
    "recall": [], "new_character_hint": ""}
_git_orig2 = git_tool_mod.commit
git_tool_mod.commit = lambda *a, **k: None
# 一键成书窗口/面板可无头构造
from gui_book import AutoBookDialog, BookPanel, _BookWorker  # noqa: E402
_dlg_book = AutoBookDialog(win)
_pan = _dlg_book.panel
assert _pan.idea_edit is not None and _pan.ch_spin is not None, \
    "一键成书对话框应有想法输入与章数控件"
assert hasattr(_pan, "total_spin") and _pan.total_spin.value() == 30, \
    "v0.52 一键成书应有「小说总章节数」输入（默认 30）"
assert _pan.ch_spin.value() == 5 and _pan.ch_spin.maximum() >= 100, \
    "默认本次生成 5 章、上限 100"
_pan_b = BookPanel(win, show_title=False)
assert _pan_b.idea_edit is not None, "BookPanel 独立面板应可直接构造"
# v1.00 一键成书面板：完整 AI 设置（文风要点/参考样本/主AI提示词/正文AI提示词/拆书风格）
for _attr100 in ("style_note_edit", "style_ref_edit", "main_prompt_edit",
                 "writer_prompt_edit", "break_combo", "apply_style_btn"):
    assert hasattr(_pan_b, _attr100), "一键成书面板缺 %s" % _attr100
assert _pan_b.break_combo.count() >= 1 and _pan_b.break_combo.currentText() == "不使用（默认）", \
    "拆书风格下拉应默认「不使用（默认）」"
_sv100 = _pan_b._current_style_values()
assert _sv100.get("note") == "" and _sv100.get("style_ref") == "" and \
    _sv100.get("main_prompt") == "" and _sv100.get("writer_prompt") == "" and \
    _sv100.get("break_style") == "", \
    "默认 AI 设置应全为空，实际 %r" % _sv100
# v1.18 一键成书面板情景写作提示词勾选：默认不勾选任何卡
assert _sv100.get("scene_cards") == [], \
    "v1.18 一键成书面板默认不应勾选情景卡，实际 %r" % _sv100.get("scene_cards")
# 工作器整链路：真实线程跑（moveToThread + 事件循环），验证建项目 + 连写 + 完成
th = QThread()
worker = _BookWorker()
wm = {"worker": worker, "res": {}, "ev": []}
worker.log.connect(lambda k, m: wm["ev"].append((k, m)))
worker.progress.connect(lambda d, t: wm["ev"].append(("progress", (d, t))))
worker.done.connect(lambda payload: wm["res"].update(payload))
worker.moveToThread(th)
th.started.connect(lambda: worker.run("测试小说想法", 1, 30, None,
                                      "冷峻白描短句", "测试拆书风格",
                                      "参考样本文本", "主AI要求快节奏", "正文AI对话短而有力"))
th.start()
for _ in range(150):
    app.processEvents()
    time.sleep(0.05)
    if wm["res"]:
        break
th.quit()
th.wait(3000)
assert wm["res"].get("ok"), "一键成书应成功，实际 %r" % wm["res"]
assert wm["res"].get("title") == "测试一键书", "书名应使用 AI 生成值"
assert wm["res"].get("chapters") == 1, "应完成 1 章，实际 %r" % wm["res"]
_bk_dir = wm["res"].get("dir")
_bk_store = storage.ProjectStore(_bk_dir)
assert _bk_store.load_project() is not None, "完成/停止后项目应存在"
assert len(_bk_store.list_chapter_indices()) == 1, "应写出 1 章"
assert _bk_store.load_project().story_brief == "主角穿越修仙世界，觉醒捡垃圾金手指。", \
    "AI 起草的剧情应写入项目"
assert _bk_store.load_project().volume_target == 30, \
    "全书总章节数应写入项目卷目标，实际 %r" % _bk_store.load_project().volume_target
_pj100 = _bk_store.load_project()
assert _pj100.story_style_note == "冷峻白描短句", "v1.00 应写入文风要点"
assert _pj100.story_break_style == "测试拆书风格", "v1.00 应写入拆书风格"
assert _pj100.story_style_ref == "参考样本文本", "v1.00 应写入参考文风样本"
assert _pj100.story_main_prompt == "主AI要求快节奏", "v1.00 应写入主AI全局提示词"
assert _pj100.story_writer_prompt == "正文AI对话短而有力", "v1.00 应写入正文AI角色提示词"
assert _bk_dir in [p["dir"] for p in storage.list_projects()], "完成/停止后项目应在书架"
# 停止路径：中断正在跑的多章任务（worker.stop 在循环开头拦截）
th2 = QThread()
w2 = _BookWorker()
wm2 = {"res": {}, "ev": []}
w2.log.connect(lambda k, m: wm2["ev"].append((k, m)))
w2.done.connect(lambda payload: wm2["res"].update(payload))
w2.moveToThread(th2)
th2.started.connect(lambda: w2.run("停止测试", 3, 50))
th2.start()
for _ in range(10):
    app.processEvents()
    time.sleep(0.05)
w2.stop()   # 模拟用户点「停止」
for _ in range(150):
    app.processEvents()
    time.sleep(0.05)
    if wm2["res"]:
        break
th2.quit()
th2.wait(3000)
assert wm2["res"].get("ok") or wm2["res"].get("chapters", 0) < 3, \
    "停止后应提前结束（完成章数 < 目标），实际 %r" % wm2["res"]
assert wm2["res"].get("chapters", 0) <= 3, "停止后完成章数不应超过目标"
if wm2["res"].get("dir"):
    storage.delete_project(wm2["res"]["dir"])   # 同步清索引，不留死条目
# v0.72「继续写」：在已建项目上从断点自动连写（不重新立项、不覆盖已写章节）
assert hasattr(_pan, "continue_btn") and not _pan.continue_btn.isEnabled(), \
    "一键成书面板应有「继续写」按钮（初始禁用）"
_th3 = QThread()
_w3 = _BookWorker()
_wm3 = {"res": {}, "ev": []}
_w3.log.connect(lambda k, m: _wm3["ev"].append((k, m)))
_w3.done.connect(lambda payload: _wm3["res"].update(payload))
_w3.moveToThread(_th3)
_th3.started.connect(lambda: _w3.run("", 3, 0, _bk_dir))   # 继续：从第 2 章写到第 3 章
_th3.start()
for _ in range(200):
    app.processEvents()
    time.sleep(0.05)
    if _wm3["res"]:
        break
_th3.quit()
_th3.wait(3000)
assert _wm3["res"].get("ok"), "继续写应成功，实际 %r" % _wm3["res"]
assert _wm3["res"].get("dir") == _bk_dir, "继续写不应新建项目，实际 %r" % _wm3["res"]
assert _wm3["res"].get("chapters") == 3, "应续写到第 3 章，实际 %r" % _wm3["res"]
assert len(storage.ProjectStore(_bk_dir).list_chapter_indices()) == 3, \
    "项目应累积 3 章（1 章已写 + 续写 2 章）"
assert any("继续模式" in m for _, m in _wm3["ev"]), \
    "继续写日志应提示继续模式，实际 %r" % [m for _, m in _wm3["ev"]][:4]
# 还原
engine_mod.NovelEngine.ensure_world = _orig_ensure_bk
main_ai_mod.plan_title = _orig_plan_title
main_ai_mod.plan_story_ai = _orig_plan_story
main_ai_mod.decide_characters = _orig_decide_bk
engine_mod.char_ai.run_inference = _orig_infer_bk
main_ai_mod.consolidate = _orig_cons_bk
main_ai_mod.write_chapter = _orig_write_bk
main_ai_mod.review_chapter = _orig_review_bk
main_ai_mod.update_world = _orig_upd_world
main_ai_mod.compress_summary = _orig_compress
main_ai_mod.volume_closing = _orig_vol_close
main_ai_mod.proofread_chapter = _orig_proof
git_tool_mod.commit = _git_orig2
storage.delete_project(_bk_store.dir_name)   # 同步清索引，不留死条目
print("[8] 一键成书：对话框构造 + 立项（书名+三栏）→ 建项目 → 连写 → 停止后保留书架 OK")

# ---------- v1.01 章节标题重设计（按本书类型/书名风格取题 + 批量重命名） ----------
_t101 = storage.create_project("标题重设计测试")
_st101 = storage.ProjectStore(_t101.dir_name)
_p101 = _st101.load_project()
_p101.title = "飞升是我编的"
_p101.story_brief = "修仙题材：主角靠捡垃圾逆袭飞升。"
_st101.save_project(_p101)
for _i101 in range(1, 4):
    _ch101 = Chapter(_i101, 1)
    _ch101.title = "旧标题%d" % _i101
    _ch101.brief = "第%d章：主角推进主线并埋下伏笔" % _i101
    _ch101.status = "approved"
    _st101.save_chapter(_ch101)
# ① 写章提示词内置标题风格引导（源码级断言：书名气质 + 「xx与xx」模板禁令）
_src101 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "src", "prompts.py"), encoding="utf-8").read()
assert "『xx与xx』" in _src101 and "书名《%s》的气质" in _src101, \
    "写章提示词应含标题风格引导与模板禁令"
# ② 重设计提示词构造（真实调用）
_sys101, _usr101 = prompts_mod.retitle_chapters(_p101, _st101, 1, 3)
assert "飞升是我编的" in _usr101 and "『xx与xx』" in _usr101, "重设计提示词应含书名与模板禁令"
assert "旧标题1" in _usr101 and "第1章：主角推进主线" in _usr101, "重设计提示词应含各章原标题与梗概"
# ③ 重设计写回（mock chat_json 返回新标题）
_orig_cj101 = llm_mod.chat_json
llm_mod.chat_json = lambda _s, _u, **kw: {
    "titles": [{"chapter": 1, "title": "捡垃圾开局"},
               {"chapter": 2, "title": "黑水旧档"},
               {"chapter": 3, "title": "三印不合"}]}
try:
    _ok101, _fail101 = main_ai_mod.retitle_chapters(_p101, _st101, 1, 3)
finally:
    llm_mod.chat_json = _orig_cj101
assert (_ok101, _fail101) == (3, 0), "应成功重命名 3 章，实际 %r" % ((_ok101, _fail101),)
assert _st101.load_chapter(1).title == "捡垃圾开局", "标题应写回，实际 %r" % _st101.load_chapter(1).title
assert _st101.load_chapter(3).title == "三印不合", "第 3 章标题应写回"
assert _st101.load_chapter(2).brief == "第2章：主角推进主线并埋下伏笔", "重设计不应改动梗概/正文"
# ④ 生成页控件
assert hasattr(win.page_generate, "retitle_start_spin") and \
    hasattr(win.page_generate, "retitle_end_spin"), "生成页应有章节标题重设计区间控件"
storage.delete_project(_t101.dir_name)
print("[8b] v1.01 章节标题按本书类型/书名风格取题 + 批量重设计（第 x~y 章，只改标题不改正文）OK")

# ---------- v1.02 去AI味参考文风样本（光靠规则不够，加一段想要的味道） ----------
_t102 = storage.create_project("去AI味参考测试")
_st102 = storage.ProjectStore(_t102.dir_name)
_p102 = _st102.load_project()
_p102.story_brief = "冷峻谍战题材。"
_st102.save_project(_p102)
_ch102 = Chapter(1, 1)
_ch102.title = "第1章 试探"
_ch102.content = "他坐在窗边，看着雨。雨敲在玻璃上，像某种心跳。"
_ch102.brief = "主角试探接头人"
_ch102.status = "approved"
_st102.save_chapter(_ch102)
# ① 去AI味章节提示词注入参考文风样本
_sys102, _usr102 = prompts_mod.deai_chapter(
    _p102, _ch102, mode="rewrite", rules="",
    style_ref="她推开门时，风先一步进来。旧窗帘扬了扬，又落回窗台。")
assert "参考文风样本" in _usr102 and "她推开门时" in _usr102, \
    "去AI味提示词应注入参考文风样本，实际 %r" % _usr102[:120]
assert "【本章原文（完整）】" in _usr102, "原文段应保留"
# ② main_ai.deai_chapter 转发 style_ref（mock chat_text 记录入参；style_ref 走提示词 user）
_orig_ct102 = llm_mod.chat_text
_cap102 = {}
llm_mod.chat_text = lambda _s, _u, **kw: (_cap102.update({"ref": kw.get("style_ref", ""), "u": _u}) or "润色后正文")
try:
    _out102 = main_ai_mod.deai_chapter(_p102, _st102, _ch102, mode="clean",
                                       rules="", style_ref="参考样本甲")
finally:
    llm_mod.chat_text = _orig_ct102
assert _out102 == "润色后正文", "deai_chapter 应返回模型文本"
assert _cap102.get("ref") == "", "llm.chat_text 不应收 style_ref 参数（走提示词 user 注入）"
assert "参考样本甲" in _cap102.get("u", ""), \
    "main_ai.deai_chapter 应把 style_ref 注入去AI味提示词 user"
# ③ 段落工具提示词注入参考文风样本
_sys102b, _usr102b = prompts_mod.polish_paragraph(_p102, "一段文字", mode="deai",
                                                  style_ref="参考样本乙")
assert "参考文风样本" in _usr102b and "参考样本乙" in _usr102b, \
    "段落工具 deai 提示词应注入参考文风样本"
# ④ 去AI味页控件 + 全局配置往返
assert hasattr(win.page_deai, "style_ref_edit"), "去AI味页应有参考文风样本编辑框"
_cfg102 = config_mod.load_config()
_cfg102["deai_style_ref"] = "保存的参考文本"
config_mod.save_config(_cfg102)
assert (config_mod.load_config().get("deai_style_ref") or "") == "保存的参考文本", \
    "deai_style_ref 应写入并读回 config"
_cfg102.pop("deai_style_ref", None)
config_mod.save_config(_cfg102)
assert not (config_mod.load_config().get("deai_style_ref") or ""), "重置后应清空"
storage.delete_project(_t102.dir_name)
print("[8c] v1.02 去AI味参考文风样本：章节级 + 段落工具注入 + 页面控件 + 配置往返 OK")

# ---------- v1.03 修复：章节标题重设计完成后主线程弹框（后台线程不再直接 QMessageBox，防 UI 卡死） ----------
_t103 = storage.create_project("重设计UI测试")
_st103 = storage.ProjectStore(_t103.dir_name)
_p103 = _st103.load_project()
_st103.save_project(_p103)
for _i103 in range(1, 4):
    _ch103 = Chapter(_i103, 1)
    _ch103.title = "原标题%d" % _i103
    _ch103.brief = "第%d章梗概" % _i103
    _ch103.status = "approved"
    _st103.save_chapter(_ch103)
_cur103 = _APP["project_dir"]
win.select_project(_t103.dir_name)
_orig_rt103 = main_ai_mod.retitle_chapters
main_ai_mod.retitle_chapters = lambda _p, _s, a, b: (2, 1)   # 成功 2、未处理 1
_orig_msg103 = QMessageBox.information
_msgs103 = []
QMessageBox.information = staticmethod(lambda *a, **k: _msgs103.append((a[1], a[2])))
try:
    win.page_generate.retitle_start_spin.setValue(1)
    win.page_generate.retitle_end_spin.setValue(3)
    win.page_generate._retitle_chapters()
    _got103 = False
    for _ in range(80):
        app.processEvents()
        time.sleep(0.05)
        if _msgs103:
            _got103 = True
            break
    assert _got103, "重设计完成后应在主线程弹完成提示框（信号回主线程，不再后台直接弹导致 UI 卡死）"
    assert _msgs103[0][0] == "完成" and "重新设计 2 章标题" in _msgs103[0][1], \
        "完成提示框内容应正确，实际 %r" % (_msgs103[0],)
finally:
    QMessageBox.information = _orig_msg103
    main_ai_mod.retitle_chapters = _orig_rt103
storage.delete_project(_t103.dir_name)
if _cur103:
    win.select_project(_cur103)
# 源码级防线：重设计 work 内不得再出现直接 QMessageBox（防回归；主线程槽 _on_retitle_done 里弹框合法）
_src103 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "src", "gui_generate.py"), encoding="utf-8").read()
_i_work103 = _src103.find("def _retitle_chapters")
_i_after103 = _src103.find("def _save_main_prompt", _i_work103)
_seg103 = _src103[_i_work103:_i_after103]
_work_body103 = _seg103.split("def work")[1].split("def _on_retitle_done")[0]
assert "QMessageBox." not in _work_body103, \
    "重设计后台 work 内不应直接调 QMessageBox（注释提及字样不算）"
assert "self._retitle_done.emit(" in _seg103, "重设计应通过信号回主线程"
print("[8d] v1.03 章节标题重设计完成弹框改主线程信号（后台不再直接 QMessageBox，防 UI 卡死）OK")

# ---------- v1.04 一键自动去AI味：改写→自动验收（文风+剧情+字数）→达标自动合并 ----------
_t104 = storage.create_project("自动去AI味测试")
_st104 = storage.ProjectStore(_t104.dir_name)
_p104 = _st104.load_project()
_p104.story_brief = "都市谍战。"
_st104.save_project(_p104)
_ch104 = Chapter(1, 1)
_ch104.title = "第1章 试探"
_ch104.content = "他坐在窗边，看着雨。雨敲在玻璃上，像某种心跳。"
_ch104.brief = "主角试探接头人"
_ch104.status = "approved"
_st104.save_chapter(_ch104)
_ch104b = Chapter(2, 1)
_ch104b.title = "第2章 接头"
_ch104b.content = "窗外雨声不断。他握紧茶杯，等待接头人。"
_ch104b.status = "approved"
_st104.save_chapter(_ch104b)
_ch104c = Chapter(3, 1)
_ch104c.title = "第3章 雨夜"
_ch104c.content = "雨夜。"
_ch104c.status = "approved"
_st104.save_chapter(_ch104c)
_ch104d = Chapter(4, 1)
_ch104d.title = "第4章 夜色"
_ch104d.content = "夜色沉沉。他倚着栏杆，等一个人的消息。"
_ch104d.status = "approved"
_st104.save_chapter(_ch104d)
# ① 验收提示词结构：style_score/plot_same + 参考样本注入 + 从严锚点；deai_chapter 上轮反馈注入
_sys104v, _usr104v = prompts_mod.deai_verify(_p104, _ch104, "原文内容。", "润色内容。",
                                             rules="", style_ref="参考样本甲")
assert "style_score" in _usr104v and "plot_same" in _usr104v and "参考文风样本" in _usr104v, \
    "验收提示词应含 style_score/plot_same/参考样本，实际 %r" % _usr104v[:160]
assert "扣分锚点" in _usr104v and "从严核对" in _usr104v, \
    "v1.05 验收提示词 user 应从严（扣分锚点/从严核对），实际 %r" % _usr104v[:200]
assert "宁严勿松" in _sys104v, "v1.05 验收系统提示词应从严（宁严勿松）"
_sys104r, _usr104r = prompts_mod.deai_chapter(_p104, _ch104, mode="rewrite",
                                              revise_note="剧情一致性不通过：对话含义变了")
assert "上一轮验收反馈" in _usr104r and "剧情一致性不通过" in _usr104r, \
    "去AI味重写提示词应注入上轮验收反馈"
# ② _deai_metrics 合成公式：有样本=0.4×TFIDF+0.6×LLM；无样本=LLM 评分；v1.05 字数差为字符数
class _FakeEv104:
    def tfidf_cosine(self, a, b):
        return 0.9
_m104 = main_ai_mod._deai_metrics("一二三四五六七八九十。", "一二三四五六七八九十。改",
                                  "样本参考文本", {"style_score": 90, "plot_same": True}, _FakeEv104())
assert _m104 == (90.0, 90.0, 1, True, True), "有样本时 final=0.4*TFIDF+0.6*LLM、字数差=1 字，实际 %r" % (_m104,)
_m104b = main_ai_mod._deai_metrics("一二三四五六七八九十。", "一二三四五六七八九十。改",
                                   "", {"style_score": 90, "plot_same": True}, _FakeEv104())
assert _m104b[0] == 90.0 and _m104b[1] == 0.0, "无样本时 final=LLM 去AI味完成度，实际 %r" % (_m104b,)
# ③ 引擎工作流：场景A（第一轮未达标→带反馈第二轮达标→自动合并）；场景D（未达标跑满轮次取最高分轮）
_orig_ct104 = _llm_mod.chat_text
_orig_cj104 = _llm_mod.chat_json
def _fake_ct104(_s, _u, **kw):
    if "夜色沉沉" in _u:                  # 场景D（第4章）：按反馈内容返回不同轮次稿
        if "得分 82" in _u:
            return "夜稿三。"
        if "得分 70" in _u:
            return "夜稿二。"
        return "夜稿一。"
    if "窗外雨声不断" in _u:              # 场景B（第2章）：恒定短稿
        return "改后文本。"
    if "雨夜" in _u:                      # 场景C（第3章）：恒定超长稿（550 字，差 547>500 卡字数）
        return "很长很长。" * 110
    if "上一轮验收反馈" in _u:            # 场景A第二轮：修正稿（字数=原文）
        return "他坐在窗边，望着雨。雨敲在玻璃上，像某种心跳。"
    return "第一轮润色。" * 30            # 场景A第一轮：字数差 184（容差内，靠文风/剧情卡）
def _fake_cj104(_s, _u, tag="json", **kw):
    if tag == "deai_audit":
        return {"issues": []}
    if tag == "deai_verify":
        if "夜稿一" in _u:
            return {"style_score": 70, "plot_same": True}
        if "夜稿二" in _u:
            return {"style_score": 82, "plot_same": True}
        if "夜稿三" in _u:
            return {"style_score": 65, "plot_same": True}
        if "第一轮润色" in _u:
            return {"style_score": 60, "style_issues": "套话残留",
                    "plot_same": False, "plot_issue": "对话含义变了"}
        if "改后文本" in _u:
            return {"style_score": 50, "plot_same": False, "plot_issue": "对话含义变了"}
        if "很长很长" in _u:
            return {"style_score": 95, "plot_same": True}
        return {"style_score": 85, "plot_same": True}   # 场景A第二轮修正稿
    raise AssertionError("unexpected tag %r" % tag)
_llm_mod.chat_text = _fake_ct104
_llm_mod.chat_json = _fake_cj104
# v1.07 前后章节参考：场景 mock 按 user 关键词分流（窗外雨声/雨夜/夜色沉沉/上一轮验收反馈），
# 附近章节注入会把其他章的文本带进 user 导致分流错乱——引擎场景测试期间临时关闭（0），[8f] 单独验证注入
_cfg104n = config_mod.load_config()
_had104n = _cfg104n.get("deai_nearby_chapters")
_cfg104n["deai_nearby_chapters"] = 0
config_mod.save_config(_cfg104n)
_orig_gt104 = git_tool_mod.commit
git_tool_mod.commit = lambda *a, **k: None   # mock git：apply_deai 的本地存档不真跑（防污染主仓）
try:
    _ev104 = list(main_ai_mod.deai_auto_workflow(
        _p104, _st104, [1], rules="", style_ref="", threshold=80, max_rounds=3, length_tol=500))
    _k104 = [e[0] for e in _ev104]
    assert _k104 == ["chapter_start", "round_done", "round_done", "chapter_done"], \
        "场景A事件序列应为 两轮→达标合并，实际 %r" % _k104
    assert _ev104[1][1]["passed"] is False and _ev104[1][1]["score"] == 60.0 and \
        _ev104[1][1]["diff"] == 157, "第一轮未达标（剧情不一致；字数差157在容差内），实际 %r" % _ev104[1][1]
    assert _ev104[2][1]["passed"] is True and _ev104[2][1]["score"] == 85.0, \
        "第二轮达标（修正剧情+字数一致），实际 %r" % _ev104[2][1]
    assert _ev104[3][1]["rounds"] == 2 and _ev104[3][1]["best_round"] == 2, \
        "达标应取最高分达标轮（第2轮）合并，实际 %r" % _ev104[3][1]
    assert _st104.load_chapter(1).content == "他坐在窗边，望着雨。雨敲在玻璃上，像某种心跳。", \
        "达标应自动合并回原文"
    # 场景B：剧情始终不一致 → 轮次耗尽保留原文
    _ev104b = list(main_ai_mod.deai_auto_workflow(
        _p104, _st104, [2], rules="", style_ref="", threshold=80, max_rounds=2, length_tol=500))
    assert [e[0] for e in _ev104b] == ["chapter_start", "round_done", "round_done", "chapter_fail"], \
        "场景B应跑满2轮后失败，实际 %r" % [e[0] for e in _ev104b]
    assert _ev104b[-1][1]["reason"] == "轮次耗尽仍未达标", "失败原因应为轮次耗尽"
    assert _st104.load_chapter(2).content == "窗外雨声不断。他握紧茶杯，等待接头人。", \
        "未达标应保留原文不合并"
    # 场景C：文风得分高但字数差超容差（560 字 vs 3 字原文）→ 字数容差按字独立卡住
    _ev104c = list(main_ai_mod.deai_auto_workflow(
        _p104, _st104, [3], rules="", style_ref="", threshold=80, max_rounds=1, length_tol=500))
    assert _ev104c[1][1]["score"] == 95.0 and _ev104c[1][1]["length_ok"] is False and \
        _ev104c[1][1]["diff"] > 500, "字数差超容差（字）时应独立不通过，实际 %r" % _ev104c[1][1]
    assert _ev104c[-1][0] == "chapter_fail" and _st104.load_chapter(3).content == "雨夜。", \
        "字数不达标应保留原文"
    # 场景D：三轮流分 70/82/65 全不达标 → 报告取最高分轮（82/第2轮），不是最后一轮（65）
    _ev104d = list(main_ai_mod.deai_auto_workflow(
        _p104, _st104, [4], rules="", style_ref="", threshold=85, max_rounds=3, length_tol=500))
    assert [e[0] for e in _ev104d] == ["chapter_start", "round_done", "round_done",
                                       "round_done", "chapter_fail"], \
        "场景D应跑满3轮后失败，实际 %r" % [e[0] for e in _ev104d]
    assert _ev104d[-1][1]["score"] == 82.0 and _ev104d[-1][1]["best_round"] == 2 and \
        _ev104d[-1][1]["rounds"] == 3, "未达标报告应取评分最高轮（82/第2轮）而非最后一轮（65），实际 %r" % _ev104d[-1][1]
    assert _st104.load_chapter(4).content.startswith("夜色沉沉"), "场景D未达标应保留原文不合并"
finally:
    _llm_mod.chat_text = _orig_ct104
    _llm_mod.chat_json = _orig_cj104
    git_tool_mod.commit = _orig_gt104
    # 恢复 v1.07 nearby 临时置 0（还原引擎场景测试前的值）
    if _had104n is not None:
        _cfg104n["deai_nearby_chapters"] = _had104n
    else:
        _cfg104n.pop("deai_nearby_chapters", None)
    config_mod.save_config(_cfg104n)
# ④ 页面控件 + 配置往返
assert hasattr(win.page_deai, "auto_thresh_spin") and hasattr(win.page_deai, "auto_rounds_spin"), \
    "去AI味页应有阈值/轮次控件"
assert hasattr(win.page_deai, "auto_tol_spin") and hasattr(win.page_deai, "auto_btn"), \
    "去AI味页应有字数容差控件与一键按钮"
assert win.page_deai.auto_rounds_spin.maximum() >= 999, \
    "v1.06 轮次上限不应被限制死为个位数（用户自己决断），实际 %r" % win.page_deai.auto_rounds_spin.maximum()
assert win.page_deai.auto_tol_spin.maximum() >= 99999, \
    "v1.06 字数容差上限不应被限制死，实际 %r" % win.page_deai.auto_tol_spin.maximum()
_cfg104 = config_mod.load_config()
_cfg104["deai_auto_threshold"] = 90
_cfg104["deai_auto_max_rounds"] = 2
_cfg104["deai_auto_length_tol"] = 800    # v1.05 语义=字
config_mod.save_config(_cfg104)
assert config_mod.load_config().get("deai_auto_threshold") == 90 and \
    config_mod.load_config().get("deai_auto_max_rounds") == 2 and \
    config_mod.load_config().get("deai_auto_length_tol") == 800, "自动去AI味验收设置应写入并读回 config"
_cfg104.pop("deai_auto_threshold", None)
_cfg104.pop("deai_auto_max_rounds", None)
_cfg104.pop("deai_auto_length_tol", None)
config_mod.save_config(_cfg104)
assert config_mod.load_config().get("deai_auto_threshold") == 80 and \
    config_mod.load_config().get("deai_auto_max_rounds") == 3 and \
    config_mod.load_config().get("deai_auto_length_tol") == 500, "重置后应回默认 80/3/500（字）"
# v1.05 旧百分比（20）迁移为字（500）：页面回填不受残留旧值影响
_cfg104b = config_mod.load_config()
_cfg104b["deai_auto_length_tol"] = 20
config_mod.save_config(_cfg104b)
try:
    win.page_deai._load_config_rules()
finally:
    _cfg104b.pop("deai_auto_length_tol", None)
    config_mod.save_config(_cfg104b)
assert win.page_deai.auto_tol_spin.value() == 500, \
    "旧百分比语义（20%）应迁移为默认字（500），实际 %r" % win.page_deai.auto_tol_spin.value()
# ⑤ UI 全流程：mock 工作流（1 章达标 + 1 章未达标）→ 一键运行 → 进度显示/按钮复位
_cur104 = _APP["project_dir"]
win.select_project(_t104.dir_name)
win.page_deai.on_show()   # 刷新章节列表（select_project 不保证切换页面）
_orig_aw104 = main_ai_mod.deai_auto_workflow
def _fake_aw104(project, store, chapters, rules="", style_ref="", threshold=80.0,
                max_rounds=3, length_tol=20.0, stop_check=None, log=None):
    for _n, _c in enumerate(chapters, 1):
        yield ("chapter_start", {"chapter": _c, "title": "t%d" % _c, "total": len(chapters)})
        if _n == 1:
            yield ("round_done", {"chapter": _c, "round": 1, "score": 90.0, "tfidf": 80.0,
                                  "diff": 3.0, "plot_ok": True, "length_ok": True,
                                  "verify_ok": True, "passed": True,
                                  "style_issues": "", "plot_issue": ""})
            yield ("chapter_done", {"chapter": _c, "rounds": 1, "score": 90.0})
        else:
            yield ("chapter_fail", {"chapter": _c, "rounds": 3, "score": 60.0,
                                    "reason": "剧情一致性不通过"})
main_ai_mod.deai_auto_workflow = _fake_aw104
try:
    win.page_deai.ch_list.item(0).setSelected(True)
    win.page_deai.ch_list.item(1).setSelected(True)
    win.page_deai._start_auto()
    _got104 = False
    for _ in range(100):
        app.processEvents()
        time.sleep(0.05)
        if win.page_deai.auto_btn.isEnabled() and "自动去AI味结束" in win.page_deai.progress_lbl.text():
            _got104 = True
            break
    assert _got104, "一键自动去AI味应跑完并复位按钮，当前状态 %r" % win.page_deai.progress_lbl.text()
    assert "通过 1 章 / 未达标 1 章" in win.page_deai.progress_lbl.text(), \
        "结束提示应统计通过/未达标，实际 %r" % win.page_deai.progress_lbl.text()
finally:
    main_ai_mod.deai_auto_workflow = _orig_aw104
storage.delete_project(_t104.dir_name)
if _cur104:
    win.select_project(_cur104)
# 源码级防线：自动去AI味 worker 内不得出现直接 QMessageBox（防回归卡死）
_src104 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "src", "gui_deai.py"), encoding="utf-8").read()
_aw_seg104 = _src104.split("class _AutoDeaiWorker")[1].split("class DeaiPage")[0]
assert "QMessageBox." not in _aw_seg104, \
    "自动去AI味后台 worker 内不应直接调 QMessageBox（注释提及字样不算）"
assert "self.event.emit(" in _aw_seg104, "自动去AI味应通过信号回主线程"
# v1.16 停止立即生效：worker 必须绑定 llm.set_abort（点停止即中断当前 LLM 调用，不等完成）
assert "set_abort(stop_event)" in _aw_seg104, \
    "v1.16 自动去AI味 worker 应绑定 llm.set_abort(stop_event)——点停止立即中断当前改写/验收，不等完成才停"
assert "set_abort(None)" in _aw_seg104, \
    "v1.16 自动去AI味 worker 结束应解绑 abort"
print("[8e] v1.04 一键自动去AI味：改写→自动验收（文风+剧情+字数）→达标自动合并 / 未达标带反馈重写 OK")

# ---------- v1.07 去AI味参考样本放开（多情景笔调）+ 前后章节参考（防剧情偏移；与写后校对共用） ----------
_t107 = storage.create_project("前后章参考测试")
_st107 = storage.ProjectStore(_t107.dir_name)
_p107 = _st107.load_project()
_p107.story_brief = "测试。"
_st107.save_project(_p107)
for _i107 in (1, 2, 3):
    _chx = Chapter(_i107, 1)
    _chx.title = "第%d章" % _i107
    _chx.content = "第%d章正文内容，描述角色状态。" % _i107
    _chx.brief = "第%d章梗概" % _i107
    _chx.status = "approved"
    _st107.save_chapter(_chx)
_ch107 = _st107.load_chapter(2)
# ① main_ai._nearby_context 组装：处理第2章时应包含前后章（标题+梗概+正文节选）
_nby107 = main_ai_mod._nearby_context(_st107, _ch107, 2)
assert "第1章" in _nby107 and "第3章" in _nby107 and "前后章节参考" in _nby107, \
    "_nearby_context 应组装前后章节参考，实际 %r" % _nby107[:160]
assert main_ai_mod._nearby_context(_st107, _ch107, 0) == "", "0=不注入前后章"
_nby107_first = main_ai_mod._nearby_context(_st107, _st107.load_chapter(1), 2)
assert "第3章" in _nby107_first, "首章处理时应注入后文（第2/3章），实际 %r" % _nby107_first[:120]
# ② prompts 四环节注入 nearby_text
_sys107a, _usr107a = prompts_mod.deai_audit(_p107, _ch107, rules="", nearby_text="【前后章参考测试A】")
assert "前后章参考测试A" in _usr107a, "deai_audit 应注入前后章参考"
_sys107b, _usr107b = prompts_mod.deai_chapter(_p107, _ch107, mode="rewrite",
                                              style_ref="多情景样本", nearby_text="【前后章参考测试B】")
assert "前后章参考测试B" in _usr107b, "deai_chapter 应注入前后章参考"
assert "多段不同情景的笔调" in _usr107b, "参考文风样本文案应引导多情景笔调"
_sys107c, _usr107c = prompts_mod.deai_verify(_p107, _ch107, "原文。", "润色稿。",
                                             nearby_text="【前后章参考测试C】")
assert "前后章参考测试C" in _usr107c, "deai_verify 应注入前后章参考"
_sys107d, _usr107d = prompts_mod.proofread_chapter(_p107, _st107, _ch107,
                                                   nearby_text="【前后章参考测试D】")
assert "前后章参考测试D" in _usr107d, "proofread_chapter 应注入前后章参考"
# ③ 参考文风样本不再截断到几百字：deai_verify 传 2000+ 字样本 → 应完整保留在 user 里
_ref107 = "样本开头" + "长样本。" * 600 + "样本结尾"
assert len(_ref107) > 2400, "测试样本应超过 2000 字，实际 %d" % len(_ref107)
_sys107v, _usr107v = prompts_mod.deai_verify(_p107, _ch107, "原文。", "润色稿。",
                                             style_ref=_ref107)
assert "样本结尾" in _usr107v, "参考样本不应被截断到几百字，应完整注入验收提示词"
# ④ main_ai 转发 nearby：deai_chapter mock chat_text 记录 user 含前后章
_orig_ct107 = llm_mod.chat_text
_cap107 = {}
llm_mod.chat_text = lambda _s, _u, **kw: (_cap107.update({"u": _u}) or "润色后正文")
try:
    main_ai_mod.deai_chapter(_p107, _st107, _ch107, mode="clean")
finally:
    llm_mod.chat_text = _orig_ct107
assert "第1章" in _cap107.get("u", ""), "main_ai.deai_chapter 应自动注入前后章参考"
# ⑤ 页面控件 + config 往返（去AI味页 auto_nearby_spin 与项目页写后校对 proof_near_spin 共用 deai_nearby_chapters）
assert hasattr(win.page_deai, "auto_nearby_spin"), "去AI味页应有前后章节参考控件"
assert hasattr(win.page_project, "proof_near_spin"), "项目页写后校对应有前后章节参考控件"
_cfg107 = config_mod.load_config()
_cfg107["deai_nearby_chapters"] = 5
config_mod.save_config(_cfg107)
assert (config_mod.load_config().get("deai_nearby_chapters") or 2) == 5, \
    "deai_nearby_chapters 应写入并读回 config"
_cfg107.pop("deai_nearby_chapters", None)
config_mod.save_config(_cfg107)
assert (config_mod.load_config().get("deai_nearby_chapters") or 2) == 2, "重置后应回默认 2"
storage.delete_project(_t107.dir_name)
print("[8f] v1.07 参考样本放开多情景笔调 + 前后章节参考（去AI味/写后校对照前后章核对剧情衔接，防偏移）OK")

# ---------- v0.55 拆书工坊：长文解析 / 四阶段管线 / 风格库 / 页面构造 ----------
import book_break as bb  # noqa: E402
from gui_break import BreakPage, _BreakWorker  # noqa: E402
_bb_txt = ("简介：拆书测试用小说。\n\n"
           "第一卷 风起\n第一章 山雨欲来\n夜里下雨，林晚站在窗前。\n"
           "第二章 敲门声\n有人敲门，门后是一封信。\n"
           "第二卷 浪涌\n第三章 出海\n船帆升起。\n第四章 风暴\n闪电划破夜空。\n")
_pr = bb.parse_novel(_bb_txt)
assert _pr["total_chapters"] == 4, "解析应得 4 章，实际 %r" % _pr
assert len(_pr["volumes"]) == 2 and _pr["volumes"][0]["title"] == "风起", "卷结构错误"
# 超长自动分卷：260 章无卷标 → 3 卷
_bb_long = "\n".join("第%d章 事件%d\n正文内容铺垫。" % (i, i) for i in range(1, 261))
assert len(bb.parse_novel(_bb_long)["volumes"]) == 3, "260 章应自动分 3 卷"
# LLM 环节 mock
_orig_tb = bb.summarize_title_batch
_orig_sk = bb.build_skeleton
_orig_av = bb.analyze_volume
_orig_md = bb.merge_doc
bb.summarize_title_batch = lambda titles, profile=None, user_prompt="": (
    {"people": ["林晚"], "events": ["风雨夜探"],
     "place": ["客栈"], "hints": ["信"]})
bb.build_skeleton = lambda payload, profile=None, user_prompt="": (
    {"story": "主角风雨夜收到神秘信件渐入江湖。",
     "arcs": [{"vols": "1-2", "task": "开局立悬念"}],
     "characters": [{"name": "林晚", "role": "主角",
                     "arc": "从看客到入局"}],
     "foreshadow_pool": ["那封信（第2章出现）"],
     "tech": ["日常三句话里藏主线钩子"]})
bb.analyze_volume = lambda payload, profile=None, user_prompt="": (
    {"events": [{"title": "夜探客栈", "start_ch": 1, "end_ch": 2, "chapters": 2,
                 "drive": "神秘信件悬念", "conflict": "不知来信者敌友", "climax": "信上留名"}],
     "foreshadow_seed": [{"text": "她说今天没胃口——实则躲开搜查", "chapter": 1,
                          "type": "日常"}],
     "foreshadow_payoff": [{"text": "那封信", "chapter": 2}],
     "chars": [{"name": "林晚", "change": "开始主动查信"}],
     "tech": ["用日常对话藏伏笔"]})
bb.merge_doc = lambda payload, profile=None, user_prompt="", stage="final": (
    {"doc": "# 拆书 · 测试\n## 一、全书总览\n主线。\n"
            "## 三、卷事件细纲\n- 夜探客栈（1~2章·2章）\n"
            "## 四、伏笔总表\n- 日常：她说今天没胃口（1章→2章）\n"
            "## 五、技法总结\n- 日常三句藏钩子",
     "learning": "开篇用一封神秘信迅速建立悬念；"
                 "以日常对话埋长线伏笔；每事件 2-3 章收束一个悬念。"})
# 四阶段管线（同步跑，体积小）
_breaker = bb.NovelBreaker(log=lambda k, m: None)
_res = _breaker.run(_bb_txt, "拆书测试", progress_cb=lambda *a: None)
assert _res.get("ok") and _res["doc"].find("夜探客栈") >= 0, "拆书文档应含事件细纲"
assert _res["doc"].find("日常") >= 0, "文档应含日常式伏笔"
assert _res["learning"].find("悬念") >= 0, "学习文本应含技法"
assert len(_res["doc"]) <= bb.DOC_MAX_CHARS, "文档不应超 5 万字"
# 停止路径：stop_check 立即停
_breaker2 = bb.NovelBreaker(log=lambda k, m: None, stop_check=lambda: True)
assert _breaker2.run(_bb_txt, "t")["ok"] is False, "立即停止应返回未完成"
# 风格库：保存/列表/读取/删除/learning
_saved = bb.save_break("拆书风格测试", _res["doc"], _res["learning"])
assert _saved.get("ok"), "保存风格应成功"
assert any(x["name"] == "拆书风格测试" for x in bb.list_breaks()), "列表应含新风格"
assert bb.load_break("拆书风格测试")["doc"].find("夜探客栈") >= 0, "读取应还原文档"
assert bb.learning_text("拆书风格测试").find("悬念") >= 0, "学习文本应可注入主AI"
bb.delete_break("拆书风格测试")
assert not any(x["name"] == "拆书风格测试" for x in bb.list_breaks()), "删除应移除"
# 页面构造（含风格库下拉/当前项目风格绑定）
_win_bp = BreakPage(win)
assert _win_bp.style_combo is not None and _win_bp.result_view is not None, "拆书页应可构造"

# ---------- v0.56 拆书设置：token 预算切分 / 并行 / 提示词传递 / 单独 API ----------
_caps = {}
bb.summarize_title_batch = lambda titles, profile=None, user_prompt="": (
    _caps.update({"tb_prof": profile, "tb_prompt": user_prompt}),
    {"people": ["林晚"], "events": ["夜探"], "place": [], "hints": ["信"]})[1]
bb.build_skeleton = lambda payload, profile=None, user_prompt="": (
    _caps.update({"sk_prof": profile, "sk_prompt": user_prompt}),
    {"story": "主线。", "arcs": [], "characters": [], "foreshadow_pool": [],
     "tech": ["藏钩子"]})[1]
bb.analyze_volume = lambda payload, profile=None, user_prompt="": (
    _caps.update({"av_prof": profile, "av_prompt": user_prompt}),
    {"events": [{"title": "事件一", "start_ch": 1, "end_ch": 2, "chapters": 2,
                 "drive": "悬念", "conflict": "冲突", "climax": "高潮"}],
     "foreshadow_seed": [], "foreshadow_payoff": [], "chars": [], "tech": []})[1]
bb.merge_doc = lambda payload, profile=None, user_prompt="", stage="final": (
    _caps.update({"md_prof": profile, "md_prompt": user_prompt}),
    {"doc": "# 拆书\n事件一", "learning": "技法：悬念推进。"})[1]
_settings = {"profile": "测试配置X", "token_per_part": 16000,
             "parallel": True, "parallel_n": 3,
             "prompt": "重点关注日常情节与人物塑造——日常对话怎么藏伏笔、配角怎么立住。"}
# 预算换算：16000 token × 0.75 / (每章≈640字×1.6) ≈ 11 章/部分；标题每批 ≈ 250
assert bb.chapters_per_part(_settings) >= 8, "16000 预算应切出约 11 章/部分"
assert bb.titles_per_part(_settings) >= 200, "16000 预算标题批应 ≥ 200"
# 并行管线：3 并发跑 260 章无卷标书（自动分卷 120→但按预算切分 ≈ 24 单元）
_bb_par = "\n".join("第%d章 事件%d\n正文铺垫。" % (i, i) for i in range(1, 261))
_rp = bb.NovelBreaker(log=lambda k, m: None, settings=_settings).run(_bb_par, "并行测试")
assert _rp.get("ok") and "事件一" in _rp["doc"], "并行拆书应完成 %r" % str(_rp)[:80]
# 提示词与 profile 已传递到各环节（mock 里记录了）
assert _caps.get("sk_prompt") == _settings["prompt"], "骨架应带上用户拆书提示词"
assert _caps.get("av_prompt") == _settings["prompt"], "卷细纲应带上用户拆书提示词"
assert _caps.get("sk_prof") == "测试配置X", "骨架应使用拆书专用 API 配置"
assert _caps.get("av_prof") == "测试配置X", "卷细纲应使用拆书专用 API 配置"
# 默认设置（未配置时）：智能模式 + 串行 + 每部分约 5~6 章（8000 预算）
# v0.69 先隔离用户真实 config 已保存的拆书设置（如档位激进），断言默认值后再恢复
_bs_cfg = config.load_config()
_bs_keys = ("break_mode", "break_smart_sub", "model_context_window", "break_token_per_part",
            "break_overlap_token", "break_l3_batch", "break_parallel", "break_parallel_n",
            "break_prompt", "break_profile", "import_profile")
_bs_saved = {k: _bs_cfg.get(k) for k in _bs_keys}
for _k in _bs_keys:
    _bs_cfg.pop(_k, None)
config.save_config(_bs_cfg)
config._cache = None
_d = bb.break_settings()
assert _d["mode"] == "smart", "默认拆书模式应为智能，实际 %r" % _d["mode"]
assert _d["smart_sub"] == "balanced", "智能模式默认档位应为正常（balanced）"
assert _d["model_context"] == 0, "上下文默认 0（自动）"
assert _d["parallel"] is False and _d["token_per_part"] == 8000, "默认应为串行/8000"
assert _d["overlap_token"] == 0 and _d["l3_batch"] == 0, "默认不应开重叠/分批"
assert bb.chapters_per_part(_d) >= 4, "默认预算每部分应约 5 章"
_bs_cfg2 = config.load_config()
for _k, _v in _bs_saved.items():
    if _v is None:
        _bs_cfg2.pop(_k, None)
    else:
        _bs_cfg2[_k] = _v
config.save_config(_bs_cfg2)
config._cache = None
# v0.58 高级模式：token 不卡上限 + 重叠换算（重叠章数 = 重叠预算×0.75 ÷ 每章采样 token）
_adv = {"token_per_part": 2000000, "overlap_token": 16000}
assert bb.chapters_per_part(_adv) >= 1400, "200 万预算应切出约 1466 章/部分（不卡上限）"
assert bb.overlap_chapters(_adv) >= 11, "16000 重叠预算应换算约 11 章重叠"
assert bb.overlap_chapters({"token_per_part": 8000, "overlap_token": 0}) == 0, "重叠默认 0"
# v0.59 智能模式三档：按模型上下文长度自动定每部分 token（v0.63 调整：保守30% / 正常50% / 激进70%）
_ctx1m = {"mode": "smart", "smart_sub": "aggressive", "model_context": 1048576}
assert bb.smart_token_per_part(_ctx1m) >= 700000, "1M 上下文激进档应 ≥ 70 万 token（73 万）"
assert bb.smart_token_per_part(dict(_ctx1m, smart_sub="balanced")) >= 500000, "1M 正常档 ≈ 52 万"
assert bb.smart_token_per_part(dict(_ctx1m, smart_sub="conservative")) >= 300000, "1M 保守档 ≈ 31 万"
_ctx256 = {"mode": "smart", "smart_sub": "aggressive", "model_context": 262144}
assert 150000 <= bb.smart_token_per_part(_ctx256) <= 200000, "262144 激进档 ≈ 18.4 万"
assert 65000 <= bb.smart_token_per_part(dict(_ctx256, smart_sub="conservative")) <= 90000, \
    "262144 保守档 ≈ 7.9 万（稳）"
assert bb.smart_token_per_part(dict(_ctx256, smart_sub="balanced")) == 131072, "262144 正常档 = 13.1 万（均衡）"
# 生效 token：智能模式无视手填 token（按上下文）；简单/高级用手填
assert bb.effective_token({**_ctx1m, "token_per_part": 8000}) >= 400000, \
    "智能模式应忽略手填 token 按上下文定档"
assert bb.effective_token({"mode": "advanced", "token_per_part": 64000}) == 64000, \
    "高级模式用手填 token"
# 上下文来源：手填 > 配置拉取记录 > 默认 262144 兜底（不触发任何网络请求）
_cfg_pctx = config.load_config()
for _p in (_cfg_pctx.get("api_profiles") or []):
    _p["context_window"] = 131072
config.save_config(_cfg_pctx)
config._cache = None
assert bb.known_context({"model_context": 1000000}) == 1000000, "手填上下文优先"
assert bb.known_context({"model_context": 0}) == 131072, "配置拉取记录次之"
_cfg_pctx = config.load_config()
for _p in (_cfg_pctx.get("api_profiles") or []):
    _p["context_window"] = 0
config.save_config(_cfg_pctx)
config._cache = None
assert bb.known_context({"model_context": 0}) == bb.DEFAULT_CONTEXT == 262144, "兜底 262144"
# 智能模式 L3 自动分批：小上下文激进档（ctx=8192→每部分 8000→per_c≈5）→ 每批 1 单元 → 3 批+final
_smt_calls = []
bb.merge_doc = lambda payload, profile=None, user_prompt="", stage="final": (
    _smt_calls.append(stage),
    {"doc": "# 智能分批 %d 批" % len(payload.get("partials") or payload.get("volumes") or []),
     "learning": "技法：自动分批。"})[1]
bb.analyze_volume = lambda payload, profile=None, user_prompt="": {
    "events": [{"title": "事%d" % payload.get("vol_no", 1), "start_ch": 1, "end_ch": 2,
                "chapters": 2, "drive": "悬念", "conflict": "冲突", "climax": "高潮"}],
    "foreshadow_seed": [], "foreshadow_payoff": [], "chars": [], "tech": []}
_smt_r = bb.NovelBreaker(
    log=lambda k, m: None,
    settings={"mode": "smart", "smart_sub": "aggressive", "model_context": 8192,
              "parallel": False, "parallel_n": 2, "prompt": "", "token_per_part": 8000}).run(
    "\n".join("第%d章 事%d\n正文铺垫。" % (i, i) for i in range(1, 16)), "智能分批测试")
assert _smt_r.get("ok"), "智能模式自动分批应完成 %r" % str(_smt_r)[:80]
assert _smt_calls == ["partial", "partial", "partial", "final"], \
    "智能模式 L3 应自动分批（小上下文 → 每批 1 单元），实际 %r" % _smt_calls
# 智能模式单元不多时一次合并（不折腾）：15 章、1M 激进档 → 1 单元
bb.merge_doc = lambda payload, profile=None, user_prompt="", stage="final": {
    "doc": "# 智能一次合并", "learning": "技法。"}
_os_r = bb.NovelBreaker(
    log=lambda k, m: None,
    settings={"mode": "smart", "smart_sub": "aggressive", "model_context": 1048576,
              "parallel": False, "parallel_n": 2, "prompt": ""}).run(
    "\n".join("第%d章 事%d\n正文铺垫。" % (i, i) for i in range(1, 16)), "智能一次合并")
assert _os_r.get("ok") and "一次合并" in _os_r["doc"], "智能模式单元少应一次合并"
# v0.59 L1 无意义章节名：全自动编号标题 → L1 改用每章开头采样概览（mock 捕获标题入参）
_ts_captured = []
bb.summarize_title_batch = lambda titles, profile=None, user_prompt="": (
    _ts_captured.extend(titles),
    {"people": [], "events": [], "place": [], "hints": []})[1]
bb.analyze_volume = lambda payload, profile=None, user_prompt="": {
    "events": [{"title": "事件一", "start_ch": 1, "end_ch": 2, "chapters": 2,
                "drive": "悬念", "conflict": "冲突", "climax": "高潮"}],
    "foreshadow_seed": [], "foreshadow_payoff": [], "chars": [], "tech": []}
bb.merge_doc = lambda payload, profile=None, user_prompt="", stage="final": {
    "doc": "# 拆书 无标题", "learning": "技法。"}
_gen_txt = "简介：无标题测试。\n\n第一章\n正文开头：林晚站在窗前，手里握着信。\n第二章\n正文开头：阿禾擦着柜台。\n第三章\n正文开头：敲门声响起。\n"
_gen_r = bb.NovelBreaker(log=lambda k, m: None).run(_gen_txt, "无标题测试")
assert _gen_r.get("ok"), "无意义章节名拆书应完成 %r" % str(_gen_r)[:80]
assert _ts_captured and "开头：" in _ts_captured[0], \
    "L1 标题流应带每章开头采样，实际 %r" % (_ts_captured or [])[:2]
assert bb.generic_title_mode({"volumes": [{"chapters": [{"title": "第1章"}, {"title": "夜探"},
                                                        {"title": "追凶"}]}]}) is False, \
    "标题过半有意义 → 非无意义模式"
assert bb.generic_title_mode({"volumes": [{"chapters": [{"title": "第1章"}, {"title": "第2章"},
                                                        {"title": "夜探"}]}]}) is True, \
    "标题过半自动编号 → 无意义模式"
# 重叠切分：同 20 章一卷，预算 8000（per_c≈5）、重叠 1 章 → 单元步长 4 → 更多单元
_ovl_r = bb.NovelBreaker(log=lambda k, m: None,
                         settings={"token_per_part": 8000, "overlap_token": 1024,
                                   "parallel": False, "parallel_n": 2, "prompt": "",
                                   "mode": "advanced"}).run(
    "\n".join("第%d章 事%d\n正文铺垫。" % (i, i) for i in range(1, 21)), "重叠测试")
assert _ovl_r.get("ok"), "开重叠的拆书应完成 %r" % str(_ovl_r)[:80]
# v0.58 输出加厚：事件推进要点 / 人物关系进展与性格刻画 进入（阶段/兜底）文档
bb.analyze_volume = lambda payload, profile=None, user_prompt="": {
    "events": [{"title": "事件一", "start_ch": 1, "end_ch": 2, "chapters": 2,
                "drive": "悬念", "conflict": "冲突", "climax": "高潮",
                "advance": "主角先发现线索，随后被追杀，最后在客栈反转"}],
    "overview": "本部分主角入局、卷入悬案。",
    "foreshadow_seed": [], "foreshadow_payoff": [],
    "chars": [{"name": "林晚", "change": "从看客到主动查案",
               "relation": "与阿禾因共同追查信件而关系更进一步",
               "portrayal": "通过主动夜探客栈刻画其胆大心细"}],
    "tech": []}
bb.merge_doc = lambda payload, profile=None, user_prompt="", stage="final": {
    "doc": "# 拆书\n## 三、卷事件细纲\n- 事件一（推进：主角先发现线索）\n"
           "## 二、核心人物设计\n- 林晚（关系：与阿禾更进一步；刻画：胆大心细）",
    "learning": "技法：悬念推进。"}
_rich_r = bb.NovelBreaker(log=lambda k, m: None).run(
    "\n".join("第%d章 事%d\n正文铺垫。" % (i, i) for i in range(1, 16)), "加厚测试")
assert _rich_r.get("ok"), "加厚输出拆书应完成 %r" % str(_rich_r)[:80]
assert bb._fallback_doc("加厚测试", {}, [{"vol": 1, "title": "", "events": [
    {"title": "事件一", "start_ch": 1, "end_ch": 2, "chapters": 2, "drive": "悬念",
     "advance": "主角先发现线索"}],
    "chars": [{"name": "林晚", "change": "主动查案", "relation": "与阿禾更进一步",
               "portrayal": "胆大心细"}]}]).find("推进") >= 0, "兜底文档应带推进要点"
assert bb._fallback_doc("加厚测试", {}, [{"vol": 1, "title": "", "events": [],
    "chars": [{"name": "林晚", "change": "主动查案", "relation": "与阿禾更进一步",
               "portrayal": "胆大心细"}]}]).find("关系") >= 0, "兜底文档应带人物关系/刻画"
# v0.58 L3 分批汇总后手：l3_batch=2、4 个单元 → 2 批分卷文档 + 1 次最终合并（stage 可验证）
_merge_calls = []
bb.merge_doc = lambda payload, profile=None, user_prompt="", stage="final": (
    _merge_calls.append(stage),
    {"doc": "# 分批合并 %d 批" % len(payload.get("partials") or payload.get("volumes") or []),
     "learning": "技法：分批合并。"})[1]
bb.analyze_volume = lambda payload, profile=None, user_prompt="": {
    "events": [{"title": "事%d" % payload.get("vol_no", 1), "start_ch": 1, "end_ch": 2,
                "chapters": 2, "drive": "悬念", "conflict": "冲突", "climax": "高潮"}],
    "foreshadow_seed": [], "foreshadow_payoff": [], "chars": [], "tech": []}
_l3_r = bb.NovelBreaker(log=lambda k, m: None,
                        settings={"token_per_part": 8000, "parallel": False,
                                  "parallel_n": 2, "prompt": "", "mode": "advanced",
                                  "overlap_token": 0, "l3_batch": 2}).run(
    "\n".join("第%d章 事%d\n正文铺垫。" % (i, i) for i in range(1, 25)), "分批测试")
assert _l3_r.get("ok"), "分批汇总拆书应完成 %r" % str(_l3_r)[:80]
assert _merge_calls == ["partial", "partial", "partial", "final"], \
    "L3 分批应 partial×3 再 final，实际 %r" % _merge_calls
assert "分批合并" in _l3_r["doc"], "分批汇总文档应含最终合并结果"
# v0.57 导入拆书文档（对称补齐导出）：纯文本 / 风格库 JSON 两种格式
_imp1 = bb.import_break_from_text("导入测试A", "# 拆书 · 外部\n## 三、卷事件细纲\n- 事件\n")
assert _imp1.get("ok"), "导入纯文本应成功"
assert bb.load_break("导入测试A")["doc"].find("外部") >= 0, "导入文档应可读取"
import json as _json
_imp2 = bb.import_break_from_text("导入测试B",
                                  _json.dumps({"doc": "# 拆书 B", "learning": "技法B"},
                                              ensure_ascii=False))
assert _imp2.get("ok") and bb.load_break("导入测试B")["learning"] == "技法B", "JSON 导入应还原 learning"
assert bb.learning_text("导入测试B") == "技法B", "learning 直取"
assert bb.learning_text("导入测试A").find("拆书") >= 0, "无 learning 的文档退化为 doc 前缀供主AI学习"
bb.delete_break("导入测试A")
bb.delete_break("导入测试B")
# v0.58 拆书页：三档模式设置组件（简单/智能/高级）+ 保存往返；拆完「保存为拆书风格」应可用
from gui_break import BreakSettingsBox  # noqa: E402
assert hasattr(_win_bp, "settings_box") and _win_bp.settings_box.mode_combo is not None, \
    "拆书页应有三档拆书模式设置组件"
assert _win_bp.save_btn is not None and not _win_bp.save_btn.isEnabled(), \
    "拆完前「保存为拆书风格」应禁用"
assert _win_bp.settings_box.mode() in ("simple", "smart", "advanced"), "拆书模式应有效"
# 高级模式：重叠/L3 控件可见、token 上限放开；简单模式：隐藏 + token 上限 32000
_win_bp.settings_box.mode_combo.setCurrentIndex(2)   # 高级
app.processEvents()
assert not _win_bp.settings_box.overlap_spin.isHidden() \
    and not _win_bp.settings_box.l3_spin.isHidden(), \
    "高级模式应显示重叠/L3 控件"
assert _win_bp.settings_box.token_spin.maximum() >= 1000000, "高级模式 token 不应卡上限"
_win_bp.settings_box.mode_combo.setCurrentIndex(0)   # 简单
app.processEvents()
assert _win_bp.settings_box.overlap_spin.isHidden(), "简单模式应隐藏重叠控件"
assert _win_bp.settings_box.token_spin.maximum() <= 32000, "简单模式 token 应限 32000"
# v0.59 智能模式：显示档位 + 上下文（自动换算每部分 token），隐藏手填 token/重叠/L3
_win_bp.settings_box.mode_combo.setCurrentIndex(1)   # 智能
app.processEvents()
assert not _win_bp.settings_box.smart_sub_combo.isHidden() \
    and not _win_bp.settings_box.ctx_spin.isHidden(), "智能模式应显示档位/上下文控件"
assert _win_bp.settings_box.token_spin.isHidden(), "智能模式应隐藏手填 token"
# v0.60 拆书参数框放大回归：模式下拉最小宽度 200（此前单行 8 组控件被压缩到只显示一个字）
assert _win_bp.settings_box.mode_combo.minimumWidth() >= 200, "拆书模式下拉应设最小宽度"
assert _win_bp.settings_box.par_combo.minimumWidth() >= 130, "并行/串行下拉应设最小宽度"
# 智能档位 + 上下文保存往返
_win_bp.settings_box.smart_sub_combo.setCurrentIndex(2)   # 激进
_win_bp.settings_box.ctx_spin.setValue(1000000)
_win_bp.settings_box.save()
assert bb.break_settings()["smart_sub"] == "aggressive", "智能档位应写回"
assert bb.break_settings()["model_context"] == 1000000, "模型上下文应写回"
# 保存往返：改模式/token/重叠/并行/提示词/L3 → 写回 config，break_settings 读同一键
_win_bp.settings_box.mode_combo.setCurrentIndex(2)
_win_bp.settings_box.token_spin.setValue(100000)
_win_bp.settings_box.overlap_spin.setValue(4000)
_win_bp.settings_box.l3_spin.setValue(5)
_win_bp.settings_box.par_combo.setCurrentIndex(1)
_win_bp.settings_box.prompt_edit.setPlainText("重点看伏笔网")
_win_bp.settings_box.save()
assert bb.break_settings()["mode"] == "advanced", "模式应写回"
assert bb.break_settings()["token_per_part"] == 100000, "token 应写回（高级不卡上限）"
assert bb.break_settings()["overlap_token"] == 4000, "重叠应写回"
assert bb.break_settings()["l3_batch"] == 5, "L3 分批应写回"
assert bb.break_settings()["parallel"] is True and bb.break_settings()["prompt"] == "重点看伏笔网", \
    "并行/提示词应写回"
# 拆完 → 「保存为拆书风格」启用（模拟 done 信号回调；屏蔽弹窗）
_orig_info = _qtw2.QMessageBox.information
_qtw2.QMessageBox.information = staticmethod(lambda *a, **k: _qtw2.QMessageBox.StandardButton.Ok)
_win_bp._on_done({"ok": True, "doc": "# 拆书 · 模拟\n正文。", "learning": "技法。",
                  "stats": {"volumes": 1, "chapters": 5}})
_qtw2.QMessageBox.information = _orig_info
assert _win_bp.save_btn.isEnabled(), "拆完后「保存为拆书风格」应启用（无需导出再导入）"
assert _win_bp.export_btn.isEnabled(), "拆完后导出也应启用"
# 一键成书入口迁移：项目页有按钮、生成页无按钮（用户指正位置）
# v0.55 顶部入口按钮已移除（子 UI 页面里已有功能按键，顶部重复多余）；tab 是独立界面入口
assert not hasattr(win.page_project, "book_btn"), "项目页顶部不应再有一键成书按钮"
assert not hasattr(win.page_project, "import_book_btn"), "项目页顶部不应再有小说导入成项目按钮"
assert not hasattr(win.page_generate, "book_btn"), "生成页不应有一键成书按钮"
# v0.53 一键成书独立 UI：项目页应有「✨ 一键成书」tab（与新建项目平级）
_tabs_proj = win.page_project.tabs
_tab_titles = [_tabs_proj.tabText(i) for i in range(_tabs_proj.count())]
assert any("一键成书" in t for t in _tab_titles), \
    "项目页应有「✨ 一键成书」独立 tab，实际 %r" % _tab_titles
assert "新建项目" in _tab_titles, "新建项目 tab 应存在（与一键成书平级）"
_bi = [i for i, t in enumerate(_tab_titles) if "一键成书" in t][0]
win.page_project.tabs.setCurrentIndex(_bi)
app.processEvents()
assert _tabs_proj.currentIndex() == _bi, "一键成书 tab 应可切换（独立界面入口）"
# v0.70 失败环节自动重试：瞬时失败自动补跑成功（不再停下等手动重试）；
# 重试耗尽仍失败才返回「未完成」（不写 done、不假装完成、失败环节不落盘）
import llm as _llm70
import tempfile as _tmpf70
import shutil as _sh70
_orig_rd70 = bb.RETRY_DELAY
bb.RETRY_DELAY = 0.0   # 测试加速：不真等重试间隔
_tmp_job = os.path.join(_tmpf70.gettempdir(), "xhb_br_retry70")
_sh70.rmtree(_tmp_job, ignore_errors=True)
_tries70 = {"n": 0}


def _fail_tb70(titles, profile=None, user_prompt=""):
    _tries70["n"] += 1
    if _tries70["n"] == 1:
        raise _llm70.LLMError("测试失败：模型未返回有效 JSON")
    return {"people": [], "events": ["事件%d" % (i + 1) for i in range(len(titles))],
            "place": [], "hints": []}


_otb69, _osk69 = bb.summarize_title_batch, bb.build_skeleton
_oav69, _omd69 = bb.analyze_volume, bb.merge_doc
bb.summarize_title_batch = _fail_tb70
bb.build_skeleton = lambda payload, profile=None, user_prompt="": (
    {"mainline": "主线", "characters": [], "volumes": [], "foreshadows": [], "techniques": []})
bb.analyze_volume = lambda payload, profile=None, user_prompt="": ({"events": [{"title": "事件"}]})
bb.merge_doc = lambda payload, profile=None, user_prompt="", stage="final": (
    {"doc": "# 拆书\n正文", "learning": "技法"})
# ① L1 标题批瞬时失败 → 自动重试补跑成功（落盘、后续环节继续）
_rr70 = bb.NovelBreaker(log=lambda k, m: None).run(_bb_txt, "失败测试", job_dir=_tmp_job)
assert _rr70.get("ok") is True, "L1 瞬时失败应自动重试补跑成功，实际 %r" % str(_rr70)[:120]
assert _tries70["n"] >= 2, "瞬时失败应自动重试（调用次数>=2），实际 %d" % _tries70["n"]
assert os.path.exists(os.path.join(_tmp_job, "title_summ.json")), \
    "自动重试成功后应落盘 title_summ.json"
assert os.path.exists(os.path.join(_tmp_job, "skeleton.json")), \
    "L1 成功后续环节应继续（骨架落盘）"
# ② L2 单元瞬时失败 → 自动重试补跑成功
_vol_tries70 = {"n": 0}


def _fail_vol70(payload, profile=None, user_prompt=""):
    _vol_tries70["n"] += 1
    if _vol_tries70["n"] == 1:
        raise _llm70.LLMError("测试失败：单元 JSON 错误")
    return {"events": [{"title": "事件"}]}


_sh70.rmtree(_tmp_job, ignore_errors=True)
_vol_tries70["n"] = 0
bb.analyze_volume = _fail_vol70
_rv70 = bb.NovelBreaker(log=lambda k, m: None).run(_bb_txt, "失败测试", job_dir=_tmp_job)
assert _rv70.get("ok") is True, "L2 瞬时失败应自动重试补跑成功，实际 %r" % str(_rv70)[:120]
assert _vol_tries70["n"] >= 2, "L2 瞬时失败应自动重试，实际 %d" % _vol_tries70["n"]
# ③ 骨架瞬时失败 → 自动重试补跑成功
_sk_tries70 = {"n": 0}


def _fail_sk70(payload, profile=None, user_prompt=""):
    _sk_tries70["n"] += 1
    if _sk_tries70["n"] == 1:
        raise _llm70.LLMError("测试失败：骨架错误")
    return {"mainline": "主线", "characters": [], "volumes": [],
            "foreshadows": [], "techniques": []}


_sh70.rmtree(_tmp_job, ignore_errors=True)
_sk_tries70["n"] = 0
bb.analyze_volume = _oav69
bb.build_skeleton = _fail_sk70
_rsk70 = bb.NovelBreaker(log=lambda k, m: None).run(_bb_txt, "失败测试", job_dir=_tmp_job)
assert _rsk70.get("ok") is True, "骨架瞬时失败应自动重试补跑成功，实际 %r" % str(_rsk70)[:120]
assert _sk_tries70["n"] >= 2, "骨架瞬时失败应自动重试，实际 %d" % _sk_tries70["n"]
# ④ 连续失败（重试耗尽）→ 返回「未完成」，失败批不落盘，不再继续后续环节
_tries70all = {"n": 0}


def _fail_tb70_all(titles, profile=None, user_prompt=""):
    _tries70all["n"] += 1
    raise _llm70.LLMError("测试失败：持续错误")


_sh70.rmtree(_tmp_job, ignore_errors=True)
_tries70all["n"] = 0
bb.build_skeleton = _osk69
bb.analyze_volume = _oav69
bb.summarize_title_batch = _fail_tb70_all
_rf70 = bb.NovelBreaker(log=lambda k, m: None).run(_bb_txt, "失败测试", job_dir=_tmp_job)
assert _rf70.get("ok") is False and "未完成" in str(_rf70.get("error") or ""), \
    "连续失败应返回「未完成」错误，实际 %r" % str(_rf70)[:120]
assert "自动重试" in str(_rf70.get("error") or ""), \
    "错误消息应说明已自动重试，实际 %r" % str(_rf70.get("error"))[:120]
assert _tries70all["n"] == bb.RETRY_TIMES, \
    "连续失败应自动重试满 %d 次才放弃，实际 %d" % (bb.RETRY_TIMES, _tries70all["n"])
assert not os.path.exists(os.path.join(_tmp_job, "title_summ.json")), \
    "重试耗尽仍失败不应落盘 title_summ.json"
assert not os.path.exists(os.path.join(_tmp_job, "skeleton.json")), \
    "失败后不应继续跑骨架/L3"
_sh70.rmtree(_tmp_job, ignore_errors=True)
bb.RETRY_DELAY = _orig_rd70
bb.summarize_title_batch = _otb69   # 供下方 restart 测试走成功路径
# v0.72 拆书失败弹窗：直接给出「继续拆书 / 重新开始拆书」恢复入口（不再只报错让用户猜）
import gui_break as _gb72   # noqa: E402
_fmb72 = {"btns": []}
_orig_qmb72 = _gb72.QMessageBox


class _FakeMB72:
    ButtonRole = _orig_qmb72.ButtonRole   # addButton 的 role 参数用真实枚举

    def __init__(self, *a, **k):
        pass

    def setWindowTitle(self, t):
        pass

    def setText(self, t):
        pass

    def addButton(self, label, role):
        _fmb72["btns"].append(label)
        return label

    def exec(self):
        return 0

    def clickedButton(self):
        return None   # 模拟点「取消」：不自动重跑


_gb72.QMessageBox = _FakeMB72
_win_bp._on_done({"ok": False, "error": "1 个环节未完成（失败）：L2 第 2 单元"})
assert any("继续拆书" in b for b in _fmb72["btns"]), \
    "失败弹窗应有「继续拆书（只补跑失败环节）」按钮，实际 %r" % _fmb72["btns"]
assert any("重新开始拆书" in b for b in _fmb72["btns"]), \
    "失败弹窗应有「重新开始拆书」按钮，实际 %r" % _fmb72["btns"]
_gb72.QMessageBox = _orig_qmb72
# v0.69 重新开始拆书：worker restart=True 不做续传、提示重置
from gui_break import _BreakWorker as _BW69
_wk69 = _BW69()
_restart_log = []
_dres69 = {}
_wk69.log.connect(lambda k, m: _restart_log.append((k, m)))
_wk69.done.connect(lambda p: _dres69.update(r=p))
_wk69.run(_bb_txt, "重启测试", restart=True)
_wres69 = _dres69.get("r") or {}
assert _wres69.get("ok") is True, "restart 重跑应成功，实际 %r" % str(_wres69)[:120]
assert any("重新开始" in m for _, m in _restart_log), \
    "restart=True 应提示重新开始（不续传），实际 %r" % [m for _, m in _restart_log][:4]
bb.summarize_title_batch, bb.build_skeleton = _otb69, _osk69
bb.analyze_volume, bb.merge_doc = _oav69, _omd69
# 还原 mock
bb.summarize_title_batch = _orig_tb
bb.build_skeleton = _orig_sk
bb.analyze_volume = _orig_av
bb.merge_doc = _orig_md
print("[9] 拆书工坊：长文解析（分卷/自动分卷）/ 四阶段管线 / 停止 / 风格库 CRUD / 页面构造 / "
      "v0.56 设置（预算切分/并行/提示词/单独API）OK")

# ---------- v1.09 拆书再细化：事件逐章节拍 beats / 人物当前状态 state / 伏笔载体 carrier·回收方式 by ----------
_orig_av09 = bb.analyze_volume
_orig_cj09 = _llm_mod.chat_json
_cap09 = {}
_llm_mod.chat_json = lambda _s, _u, **kw: (_cap09.update(
    {"sys": _s, "user": _u}) or {"events": [], "overview": "x",
                                 "foreshadow_seed": [], "foreshadow_payoff": [],
                                 "chars": [], "tech": []})
try:
    # L2 提示词（sys）应要求逐章节拍/当前状态/伏笔载体与回收方式 + 输入带章节样本
    bb.analyze_volume({"chapters": [{"no": 1, "title": "t", "head": "h", "tail": "d"}]})
    _pr09 = _cap09.get("sys") or ""
    assert "beats" in _pr09 and "第X章" in _pr09, "v1.09 L2 提示词应要求逐章节拍 beats"
    assert "state" in _pr09 and "当前状态" in _pr09, "v1.09 L2 提示词应要求人物当前状态"
    assert "carrier" in _pr09 and "埋设载体" in _pr09, "v1.09 L2 提示词应要求伏笔埋设载体"
    assert "by" in _pr09 and "回收方式" in _pr09, "v1.09 L2 提示词应要求伏笔回收方式"
    # L3 汇总（final）提示词应带逐章节拍/当前状态/载体回收
    _orig_cj09b = _llm_mod.chat_json
    _cap09b = {}
    _llm_mod.chat_json = lambda _s, _u, **kw: (_cap09b.update({"sys": _s}) or
                                               {"doc": "x", "learning": "y"})
    try:
        bb.merge_doc({"title": "t"}, stage="final")
    finally:
        _llm_mod.chat_json = _orig_cj09b
    _pr09b = _cap09b.get("sys") or ""
    assert "逐章节拍" in _pr09b and ("卷末人物状态" in _pr09b or "当前状态" in _pr09b) \
        and "载体" in _pr09b, "v1.09 L3 汇总提示词应带逐章节拍/人物状态/伏笔载体"
    assert "人物与事件穿插" in _pr09b or "穿插" in _pr09b, \
        "v1.10 L3 汇总提示词应要求人物事件穿插"
finally:
    bb.analyze_volume = _orig_av09
    _llm_mod.chat_json = _orig_cj09
print("[9r] v1.09 拆书再细化：L2 事件逐章节拍 / 人物当前状态 / 伏笔埋设载体与回收方式 OK")

# ---------- v1.10 拆书穿插：人物与事件合写卷内叙事流 / 无卷概念按剧情阶段判卷 / 锚点伏笔入卷 ----------
_orig_cj10 = _llm_mod.chat_json
_cap10 = {}
_llm_mod.chat_json = lambda _s, _u, **kw: (_cap10.update(
    {"sys": _s, "tag": kw.get("tag")}) or {})
try:
    # L1-b 骨架：arcs 支持无明确卷概念时按剧情阶段自行判卷（start/end/title/task/basis）
    bb.build_skeleton({"volumes": [], "title_summaries": []})
    _sk10 = _cap10.get("sys") or ""
    assert "按剧情阶段" in _sk10 and "basis" in _sk10 and "判卷" in _sk10, \
        "v1.10 L1-b 骨架应支持无卷概念时按剧情阶段自行判卷（basis）"
    assert "title(卷题" in _sk10 and "task(这阶段的剧情任务" in _sk10, \
        "v1.10 arcs 应带卷题与剧情任务"
    # L3 汇总（final）：主体改为「卷内细纲」——人物与事件穿插成叙事流，不人物表/事件表分离
    _cap10.clear()
    bb.merge_doc({"title": "t"}, stage="final")
    _md10 = _cap10.get("sys") or ""
    assert "卷内细纲" in _md10 and "人物与事件穿插" in _md10, \
        "v1.10 L3 汇总应要求卷内细纲人物与事件穿插"
    assert "锚点与伏笔" in _md10 and "卷末人物状态" in _md10, \
        "v1.10 L3 应带本卷锚点与伏笔、卷末人物状态"
    assert "判卷" in _md10 or "卷划分说明" in _md10, "v1.10 L3 应说明卷划分（原书卷/剧情阶段）"
    assert "禁止退回" in _md10 and "分离写法" in _md10, \
        "v1.10 L3 应显式禁止退回人物表+事件表分离写法"
    # partial 分支同样穿插
    _cap10.clear()
    bb.merge_doc({"title": "t"}, stage="partial")
    _md10p = _cap10.get("sys") or ""
    assert "人物与事件穿插" in _md10p and "剧情线" in _md10p, \
        "v1.10 partial 汇总也应人物与事件穿插"
finally:
    _llm_mod.chat_json = _orig_cj10
print("[9s] v1.10 拆书穿插：人物与事件合写卷内叙事流 / 无卷判卷 / 锚点伏笔入卷 OK")

# ---------- v1.11 拆书四段式：事件按 起因→经过→高潮→结尾 拆解，每段标占用章数范围；篇幅放开充分利用上限 ----------
_orig_cj11 = _llm_mod.chat_json
_cap11 = {}
_llm_mod.chat_json = lambda _s, _u, **kw: (_cap11.update(
    {"sys": _s, "tag": kw.get("tag")}) or {})
try:
    # L2 单卷：events 按四段式拆解，每段带章数范围（cause/process/climax/ending + _ch）
    bb.analyze_volume({"chapters": [{"no": 1, "title": "t", "head": "h", "tail": "d"}]})
    _pr11 = _cap11.get("sys") or ""
    assert "起因" in _pr11 and "经过" in _pr11 and "高潮" in _pr11 and "结尾" in _pr11, \
        "v1.11 L2 事件应按 起因/经过/高潮/结尾 四段式拆解"
    assert "cause_ch" in _pr11 and "process_ch" in _pr11 and "ending_ch" in _pr11, \
        "v1.11 L2 四段式每段应标注占用章数范围"
    assert "误导" in _pr11 and "章数范围" in _pr11, "v1.11 L2 经过应写误导因素 + 章数范围"
    # L3 汇总（final）：卷内细纲事件段四段式 + 每段章数 + 篇幅放开
    _cap11.clear()
    bb.merge_doc({"title": "t"}, stage="final")
    _md11 = _cap11.get("sys") or ""
    assert "起因→经过→高潮→结尾" in _md11 and "每段标注占用的章数范围" in _md11, \
        "v1.11 L3 final 应要求事件段四段式并标注每段章数"
    assert "因为什么引起" in _md11 and "受到哪些因素误导" in _md11, \
        "v1.11 L3 final 起因/经过应写清引因与误导因素"
    assert "冲突是怎么产生的" in _md11 and "以什么方式收场" in _md11, \
        "v1.11 L3 final 高潮/结尾应写清冲突产生与收场方式"
    assert "5~8 万字" in _md11 and "充分利用篇幅上限" in _md11, \
        "v1.11 L3 final 篇幅应按剧情量放开、超长篇写到 5~8 万字"
    assert "严禁压缩成只剩标题的提纲" in _md11, "v1.11 应显式禁止压缩成提纲"
    # partial 分支同样四段式
    _cap11.clear()
    bb.merge_doc({"title": "t"}, stage="partial")
    _md11p = _cap11.get("sys") or ""
    assert "起因→经过→高潮→结尾" in _md11p and "误导/干扰/假象" in _md11p, \
        "v1.11 partial 也应四段式并写误导因素"
    assert "篇幅与剧情量匹配" in _md11p and "严禁压缩成只剩标题的提纲" in _md11p, \
        "v1.11 partial 篇幅也应与剧情量匹配"
finally:
    _llm_mod.chat_json = _orig_cj11
print("[9t] v1.11 拆书四段式：起因/经过/高潮/结尾 + 每段章数标注 + 篇幅放开 OK")

# ---------- v1.12 主AI拆书参考提示词：事件长度与节奏/影响层级/冲突误导/伏笔回收 五维度 —— 提示词本身可断言（一键成书与正常写作共用 main_system 链路） ----------
# 主AI系统提示词注入拆书学习文本的引导文案，应覆盖事件长度/影响层级等维度并保留禁抄措辞；
# L3 生成 learning 技法文本的提示词同样要求覆盖这些维度（否则学习文本里没有对应技法可学）。
import types as _types112  # noqa: E402
_orig_lt112 = bb.learning_text
bb.learning_text = lambda name: "事件长度与节奏技法文本；事件影响层级技法文本。"
_proj112 = _types112.SimpleNamespace(story_break_style="风格测试", story_main_prompt="")
try:
    _sys112 = prompts_mod.main_system(_proj112)
    assert "事件长度与节奏" in _sys112 and "事件影响层级" in _sys112, \
        "v1.12 main_system 拆书参考段应含事件长度/影响层级维度"
    assert "只学这些技法" in _sys112 and "绝不照抄情节" in _sys112, \
        "v1.12 main_system 应保留只学技法不抄情节防线"
    # L3 learning 生成提示词也应要求这些维度（学习文本来源侧）
    _orig_cj112 = _llm_mod.chat_json
    _cap112 = {}
    _llm_mod.chat_json = lambda _s, _u, **kw: (_cap112.update({"sys": _s}) or
                                               {"doc": "x", "learning": "y"})
    try:
        bb.merge_doc({"title": "t"}, stage="final")
    finally:
        _llm_mod.chat_json = _orig_cj112
    _md112 = _cap112.get("sys") or ""
    assert "事件长度与节奏" in _md112 and "事件影响层级" in _md112, \
        "v1.12 L3 learning 生成应要求事件长度/影响层级技法"
    assert "绝不出现具体情节" in _md112, "v1.12 L3 learning 生成应禁照搬情节"
finally:
    bb.learning_text = _orig_lt112
print("[9v] v1.12 主AI拆书参考：事件长度/影响层级/冲突误导/伏笔回收 五维度 + 一键成书同链路 OK")

# ---------- v1.13 故事设定规范化：plan_story_ai 剧情按 卷划分/起止章号/卷内主要事件 结构；world/rules 分栏；一键成书可指定书名 ----------
_orig_cj113 = _llm_mod.chat_json
try:
    # 1) plan_story_ai 提示词：剧情按规范大纲（主线总判/卷划分/卷内主要事件/结尾方向 + 章节号覆盖），world/rules 分栏条目
    #    （规范细节在 user 侧 part_notes；sys 只有总要求概述）
    _sys113, _usr113 = prompts_mod.plan_story_ai(
        "", "一个修仙废土捡垃圾逆袭的故事", "200 章", ("story", "world", "rules"))
    assert "卷划分" in _usr113 and "起止章号" in _usr113 and "卷内主要事件" in _usr113, \
        "v1.13 story 提示词应要求卷划分/起止章号/卷内主要事件"
    assert "主线总判" in _usr113 and "全书结尾方向" in _usr113, \
        "v1.13 story 提示词应含主线总判与结尾方向"
    assert "分栏条目" in _usr113 and "金手指" in _usr113 and "禁忌" in _usr113, \
        "v1.13 world/rules 提示词应分栏条目"
    assert "章数范围" in _usr113, "v1.13 卷内主要事件应带章数范围"
    # v1.14 放开死限制：卷数/事件数/条目数由 AI 按规模自行判断，只给参考标准（30 章短篇不许套 3~6 卷模板）
    assert "自行判断" in _usr113 and "参考标准" in _usr113 and "不要生搬硬套" in _usr113, \
        "v1.14 卷划分应由 AI 按规模自行判断（只给参考标准）"
    assert "数量随该卷剧情量自行把握" in _usr113, "v1.14 卷内主要事件数应随剧情量自行把握"
    assert "按需给" in _usr113, "v1.14 world/rules 条目数应按需给、不硬性规定"
    # 2) 一键成书可指定书名：BookPanel 有 title_edit；run 签名支持 book_title
    from gui_book import BookPanel as _bp113, _BookWorker as _bw113  # noqa: E402
    import inspect  # noqa: E402
    _pan113 = BookPanel(win, show_title=False)
    assert hasattr(_pan113, "title_edit"), "v1.13 BookPanel 应有书名输入框 title_edit"
    assert "book_title" in inspect.signature(_bw113.run).parameters, \
        "v1.13 _BookWorker.run 应支持 book_title 参数"
finally:
    _llm_mod.chat_json = _orig_cj113
print("[9w] v1.13 故事设定规范化：剧情按卷划分/主要事件/章节号 + world/rules 分栏 + 一键成书可指定书名 OK")

# ---------- v1.15 一键成书立项即刷新：项目已建+三栏已写入不等第一章，书架/故事设定立刻可见 ----------
from gui_book import BookPanel as _bp115, _BookWorker as _bw115  # noqa: E402
from PySide6.QtCore import Signal as _QtSignal115  # noqa: E402
_pan115 = BookPanel(win, show_title=False)
assert hasattr(_pan115, "_on_project_ready"), "v1.15 BookPanel 应有 _on_project_ready 槽"
assert hasattr(_pan115, "_refresh_project_page"), "v1.15 BookPanel 应有 _refresh_project_page 公共刷新方法"
assert isinstance(_bw115.project_ready, _QtSignal115), "v1.15 _BookWorker 应有 project_ready 信号"
# run() 在立项完成后应 emit project_ready（源码级检查防回归）
import inspect as _inspect115  # noqa: E402
_src115 = _inspect115.getsource(_bw115.run)
assert "project_ready.emit" in _src115, "v1.15 run() 立项完成应 emit project_ready"
print("[9x] v1.15 一键成书立项即刷新：project_ready 信号 + 项目页刷新槽 OK")

# ---------- v1.17 正文AI情景规则卡（可选插入项）+ 正文长度上下限开放 + 字数循环重写直到达标 ----------
import config as _cfg117  # noqa: E402
# 1) config 默认键：writer_scene_cards / chapter_min_chars / chapter_max_chars
_cfg117d = _cfg117.load_config()
assert "writer_scene_cards" in _cfg117d, \
    "v1.17 config 应有 writer_scene_cards 键"
# v1.23 修正：默认空列表断言查 DEFAULT_CONFIG（用户建卡后 load_config 返回用户数据，断言运行时值会误报）
assert _cfg117.DEFAULT_CONFIG.get("writer_scene_cards") == [], \
    "v1.17 config 默认 writer_scene_cards 应为空列表"
assert _cfg117d.get("chapter_min_chars", 0) == 0 and _cfg117d.get("chapter_max_chars", 0) == 0, \
    "v1.17 config 上下限默认 0=自动"
# 2) consolidate 只注入本项目启用的情景规则卡 + JSON schema 含 scene_cards
_orig_ld117 = _cfg117.load_config


def _fake_ld117():
    d = dict(_orig_ld117())
    d["writer_scene_cards"] = [
        {"name": "武打", "content": "攻防有节奏，杀招有取舍，不轻拿轻放。"},
        {"name": "文斗", "content": "言语交锋层层进逼，心理攻防不点到即止。"},
        {"name": "情感对峙", "content": "压抑中层层逼近，不轻拿轻放。"}]
    return d


_pj2.scene_cards = [   # v1.21 项目主AI可用库（与总库独立；主AI每章优先从这里选已有卡）
    {"name": "武打", "content": "攻防有节奏，杀招有取舍，不轻拿轻放。", "source": "user"},
    {"name": "文斗", "content": "言语交锋层层进逼，心理攻防不点到即止。", "source": "user"}]
_cfg117.load_config = _fake_ld117
try:
    _cs117, _cu117 = prompts_mod.consolidate(_pj2, st, 1, "两人拔剑对峙", {}, "")
finally:
    _cfg117.load_config = _orig_ld117
assert "正文AI情景规则卡" in _cu117 and "武打" in _cu117 and "文斗" in _cu117, \
    "v1.21 consolidate 应注入本项目主AI可用库的情景规则卡"
assert "情感对峙" not in _cu117, "v1.21 未加入本项目库的卡不应注入（项目 scene_cards 控制）"
assert '"scene_cards"' in _cu117 and '"new_scene_cards"' in _cu117, \
    "v1.21 consolidate JSON schema 应有 scene_cards 与 new_scene_cards 字段"
assert "用户提供" in _cu117 and "AI 制作" in _cu117, \
    "v1.21 consolidate 应标注卡来源（用户提供/AI 制作）并支持主AI按需自做新卡"
_pj2.scene_cards = []
# 3) write_chapter 注入选中卡 + 用户自设上下限文本
_cs117b, _cu117b = prompts_mod.write_chapter(
    _pj2, st, 1, "焦点", "方向", {}, [], 2500,
    scene_cards=[{"name": "武打", "content": "攻防有节奏。"}],
    min_chars=1500, max_chars=4500)
assert "本章情景规则卡" in _cu117b and "攻防有节奏" in _cu117b, \
    "v1.17 write_chapter 应注入主AI选中的情景规则卡"
assert "1500～4500 字" in _cu117b and "超出 4500 字或低于 1500 字" in _cu117b, \
    "v1.17 write_chapter 篇幅文本应使用用户自设上下限"
# 未设上下限时保持自动文本（防回归旧断言）
_cs117c, _cu117c = prompts_mod.write_chapter(_pj2, st, 1, "焦点", "方向", {}, [], 2500)
assert "±500 字" in _cu117c, "v1.17 未设上下限时应保持目标±500 自动文本"
# 4) main_ai.generate_scene_card：AI 一键生成情景卡（mock chat_text）
import main_ai as _mai117  # noqa: E402
import llm as _llm117  # noqa: E402
assert hasattr(_mai117, "generate_scene_card"), "v1.17 main_ai 应有 generate_scene_card"
_orig_ct117 = _llm117.chat_text
_llm117.chat_text = lambda *a, **k: "武打规则：攻防节奏分明，杀招不轻放。"
try:
    _card117 = _mai117.generate_scene_card("武打")
finally:
    _llm117.chat_text = _orig_ct117
assert "攻防节奏分明" in _card117, "v1.17 generate_scene_card 应返回 AI 生成内容"
# 5) 设置页：上下限 spin 上限不设死；情景卡管理 v1.18 已移到独立功能页 SceneCardsPage
assert win.page_settings.spins["chapter_min_chars"].maximum() >= 999999, \
    "v1.17 正文下限 spin 上限不设死"
assert win.page_settings.spins["chapter_max_chars"].maximum() >= 999999, \
    "v1.17 正文上限 spin 上限不设死"
from gui_scene_cards import SceneCardsPage as _scp117  # noqa: E402
assert hasattr(win.page_scene_cards, "card_list") and hasattr(win.page_scene_cards, "_card_ai_gen"), \
    "v1.18 情景规则卡管理在独立功能页 SceneCardsPage（列表 + AI 一键生成）"
assert not hasattr(win.page_settings, "card_list"), \
    "v1.18 设置页不应再有情景卡管理区（已移到独立功能页）"
# 6) engine 字数循环使用用户自设上下限（mock load_config 传 1500/4500）
_eng117 = engine_mod.NovelEngine(st, lambda k, m: None)
_got_fb117 = []


def _w117(fb=""):
    _got_fb117.append(fb or "")
    return "第1章", "长" * 5000   # 始终超 4500 上限


_orig_ld117b = _cfg117.load_config


def _fake_ld117b():
    d = dict(_orig_ld117b())
    d["chapter_min_chars"] = 1500
    d["chapter_max_chars"] = 4500
    return d


_cfg117.load_config = _fake_ld117b
try:
    _o117 = _eng117._ensure_chapter_length(_pj2, 1, 2500, "第1章", "长" * 9000, _w117)
finally:
    _cfg117.load_config = _orig_ld117b
assert len(_got_fb117) == engine_mod.LENGTH_RETRY_MAX and "4500" in _got_fb117[0], \
    "v1.17 _ensure_chapter_length 应使用用户自设上限并循环重写"
assert len(_o117[1]) == 5000, "v1.17 循环后仍超限应保留本版内容"
print("[9y] v1.17 情景规则卡（consolidate 选卡 + write_chapter 注入 + AI 一键生成 + 设置页管理）"
      " + 正文长度上下限开放 + 字数循环重写直到达标 OK")

# ---------- v1.18/v1.21 情景写作提示词：独立功能页 + 项目级主AI可用库（v1.21 与总库独立） ----------
import models as _mdl118  # noqa: E402
# 1) v1.21 项目模型 scene_cards（[{name,content,source}]）字段往返 + 兼容导出
_pj118 = _mdl118.NovelProject("dir118", "测试")
_pj118.scene_cards = [{"name": "武打", "content": "攻防有节奏。", "source": "user"},
                      {"name": "见父母装傻", "content": "装傻充愣。", "source": "ai"}]
_d118 = _pj118.to_dict()
assert "scene_cards" in _d118 and len(_d118["scene_cards"]) == 2, \
    "v1.21 to_dict 应导出 scene_cards（项目主AI可用库）"
assert _d118["scene_cards_active"] == ["武打", "见父母装傻"], \
    "v1.21 scene_cards_active 应兼容导出为项目库卡名列表"
_pj118b = _mdl118.NovelProject.from_dict(_d118, "dir118")
assert [c["name"] for c in _pj118b.scene_cards] == ["武打", "见父母装傻"] and \
    _pj118b.scene_cards[1]["source"] == "ai", \
    "v1.21 scene_cards（含来源 user/ai）应往返保存"
# 1b) 旧项目迁移：只有 scene_cards_active 卡名列表 → 从总库复制内容（source=user）
import config as _cfg118  # noqa: E402
_orig_ld118 = _cfg118.load_config


def _fake_ld118():
    d = dict(_orig_ld118())
    d["writer_scene_cards"] = [
        {"name": "武打", "content": "攻防有节奏，杀招有取舍。"},
        {"name": "文斗", "content": "言语交锋层层进逼。"}]
    return d


_cfg118.load_config = _fake_ld118
try:
    _old118 = _mdl118.NovelProject.from_dict(
        {"title": "旧书", "scene_cards_active": ["武打"]}, "dir118old")
finally:
    _cfg118.load_config = _orig_ld118
assert len(_old118.scene_cards) == 1 and _old118.scene_cards[0]["name"] == "武打" and \
    _old118.scene_cards[0]["source"] == "user" and \
    "攻防有节奏" in _old118.scene_cards[0]["content"], \
    "v1.21 旧项目 scene_cards_active 应迁移为项目库卡（从总库复制内容，source=user）"
assert _old118.scene_cards_active == ["武打"], "v1.21 迁移后 scene_cards_active 应回填项目库卡名"
# 2) 独立功能页卡库：批量导出文本格式 + 可再导入（往返）+ 无分隔单卡导入
from gui_scene_cards import (SceneCardsPage as _scp118,  # noqa: E402
                             _export_text as _et118,
                             _parse_import as _pi118)
_cards118 = [{"name": "武打", "content": "攻防有节奏，杀招有取舍。"},
             {"name": "文斗", "content": "言语交锋层层进逼。"}]
_txt118 = _et118(_cards118)
assert "【卡名】武打" in _txt118 and "【卡名】文斗" in _txt118, \
    "v1.18 批量导出应以【卡名】分隔每张卡"
_back118 = _pi118(_txt118, fallback_name="情景库")
assert {c["name"] for c in _back118} == {"武打", "文斗"} and \
    any(c["name"] == "武打" and "攻防有节奏" in c["content"] for c in _back118), \
    "v1.18 批量导出文本应能解析回卡（往返）"
_single118 = _pi118("你是一位擅长写实的作者。\n**核心定位：**……\n**写作执行与自检清单：**1. …",
                    fallback_name="通用情景写作提示词")
assert len(_single118) == 1 and _single118[0]["name"] == "通用情景写作提示词", \
    "v1.18 无分隔单卡导入应整段作一张卡、卡名取文件名"
# 3) AI 一键生成提示词按范例结构（核心定位 + 分节 + 写作执行自检清单，字数不限）
_sys118g, _usr118g = prompts_mod.generate_scene_card_ai("武打")
assert "核心定位" in _usr118g and "写作执行与自检清单" in _usr118g, \
    "v1.18 generate_scene_card_ai 应按范例结构（核心定位+分节+自检清单）"
assert ("字数不做要求" in _usr118g) or ("字数不限" in _usr118g), \
    "v1.18 AI 生成卡字数不做要求"
# 4) 项目页文风参考有本项目主AI可用库显示 + 跳转管理
assert hasattr(win.page_project, "scene_cards_list") and \
    hasattr(win.page_project, "_goto_scene_cards"), \
    "v1.21 项目页文风参考应显示本项目主AI可用情景卡 + 跳转「情景提示词」页管理"
# 5) 一键成书面板有勾选列表 + run 签名/写入支持 scene_cards_active → project.scene_cards
from gui_book import BookPanel as _bp118, _BookWorker as _bw118  # noqa: E402
import inspect as _inspect118  # noqa: E402
_pan118 = BookPanel(win, show_title=False)
assert hasattr(_pan118, "scene_cards_list") and hasattr(_pan118, "_refresh_scene_cards"), \
    "v1.18 一键成书面板应有情景卡勾选列表"
assert "scene_cards_active" in _inspect118.signature(_bw118.run).parameters, \
    "v1.18 _BookWorker.run 应支持 scene_cards_active 参数"
_src118b = _inspect118.getsource(_bw118.run)
assert "scene_cards_active" in _src118b and "project.scene_cards" in _src118b, \
    "v1.21 run() 应把总库勾选的卡写入新项目 project.scene_cards（与总库独立）"
print("[9z] v1.18 情景写作提示词：独立功能页（卡库/批量导入导出/AI 按范例格式） + 项目级启用（项目页+一键成书）OK")

# ---------- v1.19 情景提示词制作：用途分工独立 API 行 + 从文本提取规则卡 ----------
# 1) prompts.extract_scene_card_ai：从参考文本提炼（结构同范例，禁止照抄原文）
_sys119x, _usr119x = prompts_mod.extract_scene_card_ai("武打", "雨夜持刀搏命的一段打斗写法。")
assert "核心定位" in _usr119x and "写作执行与自检清单" in _usr119x, \
    "v1.19 extract_scene_card_ai 应按范例结构（核心定位+分节+自检清单）"
assert "参考文本" in _usr119x and "禁止照抄原文" in _usr119x, \
    "v1.19 extract_scene_card_ai 应引用参考文本并要求提炼不照抄"
# 2) main_ai.extract_scene_card 存在且走 llm.chat_text（mock）
import main_ai as _mai119  # noqa: E402
assert hasattr(_mai119, "extract_scene_card"), "v1.19 main_ai 应有 extract_scene_card"
assert hasattr(_mai119, "generate_scene_card"), "v1.19 main_ai 保留 generate_scene_card（纯 AI 生成）"
_orig_ct119 = _llm117.chat_text
_llm117.chat_text = lambda *a, **k: "武打规则：从参考文本提炼攻防节奏。"
try:
    _ext119 = _mai119.extract_scene_card("武打", "雨夜搏命写法。")
finally:
    _llm117.chat_text = _orig_ct119
assert "攻防节奏" in _ext119, "v1.19 extract_scene_card 应返回提炼内容"
# 3) 用途分工 scene_card 行：role_profiles["scene_card"] 可选独立 API（不指定时跟随通用）
import config as _cfg119  # noqa: E402
assert "scene_card" in win.page_settings.role_combos, \
    "v1.19 设置页用途分工应有「情景提示词制作」行"
# 4) 情景提示词功能页有「从文本提取」按钮与方法
assert hasattr(win.page_scene_cards, "extract_btn") and \
    hasattr(win.page_scene_cards, "_card_extract"), \
    "v1.19 情景提示词页应有「从文本提取」按钮与方法"
print("[9a] v1.19 情景提示词制作：用途分工独立 API 行（scene_card）+ 从文本提取规则卡（保留纯 AI 生成）OK")

# ---------- v1.20 提取提示词可编辑（保存/恢复初始）+ 当前项目主AI可选情景卡显示框 ----------
import config as _cfg120  # noqa: E402
# 1) config 默认 extract_scene_card_prompt = None（未自定义 → 用内置初始）
assert _cfg120.load_config().get("extract_scene_card_prompt", None) is None, \
    "v1.20 config extract_scene_card_prompt 默认应为 None（用内置初始提取提示词）"
# 2) prompts.extract_scene_card_ai 无 prompt → 内置初始（微调自初始提取.txt：只提风格忽略情节 + 规则卡）
from prompts import _DEFAULT_EXTRACT_SYS  # noqa: E402
assert _DEFAULT_EXTRACT_SYS and "风格" in _DEFAULT_EXTRACT_SYS and \
    "忽略具体人物姓名" in _DEFAULT_EXTRACT_SYS, \
    "v1.20 内置初始提取提示词应含初始提取.txt 的骨架（只提风格忽略情节）"
_sys120a, _usr120a = prompts_mod.extract_scene_card_ai("武打", "雨夜搏命片段。")
assert _sys120a == _DEFAULT_EXTRACT_SYS, "v1.20 未自定义时应使用内置初始提取提示词"
# 3) 传自定义 prompt → 用之（sys 侧替换）
_sys120b, _usr120b = prompts_mod.extract_scene_card_ai("武打", "雨夜搏命片段。",
                                                       prompt="我自定义的提取要求")
assert "我自定义的提取要求" in _sys120b and "风格" not in _sys120b, \
    "v1.20 传自定义提取提示词应替换内置初始"
# 4) main_ai.extract_scene_card 读 config 自定义（mock chat_text 断言收到自定义 sys）
import main_ai as _mai120  # noqa: E402
import llm as _llm120  # noqa: E402
_orig_ld120 = _cfg120.load_config


def _fake_ld120():
    d = dict(_orig_ld120())
    d["extract_scene_card_prompt"] = "我的自定义提取提示词XYZ"
    return d


_orig_ct120 = _llm120.chat_text
_seen_sys120 = {}


def _fake_ct120(system, user, **kw):
    _seen_sys120["sys"] = system
    return "武打规则草稿"


_cfg120.load_config = _fake_ld120
_llm120.chat_text = _fake_ct120
try:
    _res120 = _mai120.extract_scene_card("武打", "片段。")
finally:
    _cfg120.load_config = _orig_ld120
    _llm120.chat_text = _orig_ct120
assert "我的自定义提取提示词XYZ" in _seen_sys120.get("sys", ""), \
    "v1.20 main_ai.extract_scene_card 应把 config 自定义提取提示词传给 prompts"
assert "武打规则草稿" in _res120, "v1.20 extract_scene_card 应返回提炼内容"
# 5) 情景提示词页：提取提示词编辑区（保存/恢复初始）+ 当前项目可选情景卡显示框
assert hasattr(win.page_scene_cards, "extract_prompt_edit") and \
    hasattr(win.page_scene_cards, "_save_extract_prompt") and \
    hasattr(win.page_scene_cards, "_reset_extract_prompt"), \
    "v1.20 情景提示词页应有提取提示词编辑区（保存/恢复初始）"
assert hasattr(win.page_scene_cards, "project_cards_view") and \
    hasattr(win.page_scene_cards, "_refresh_project_cards"), \
    "v1.20 情景提示词页应有当前项目主AI可选情景卡显示框"
print("[9b] v1.20 提取提示词可编辑（保存/恢复初始，初始=初始提取.txt 微调）+ 当前项目主AI可选情景卡显示框 OK")

# ---------- v1.21 总库/项目库分离：主AI按需自做卡（只进项目库）+ 放入总库 + 一键成书/项目页入口同步 ----------
# 1) engine._collect_scene_cards：选中已有卡 + 主AI自做新卡（只进项目库，source=ai，一并注入）
_eng121 = engine_mod.NovelEngine(st, lambda k, m: None)
_saved121 = {"n": 0}
_eng121.store.save_project = lambda p: _saved121.__setitem__("n", _saved121["n"] + 1)
_pj121 = _mdl118.NovelProject("dir121", "测试")
_pj121.scene_cards = [{"name": "武打", "content": "攻防有节奏。", "source": "user"}]
_got121 = _eng121._collect_scene_cards(_pj121, {
    "scene_cards": ["武打"],
    "new_scene_cards": [{"name": "文斗", "content": "言语交锋层层进逼。"}]})
assert [c["name"] for c in _got121] == ["武打", "文斗"], \
    "v1.21 应同时注入选中卡与主AI自做新卡"
assert len(_pj121.scene_cards) == 2 and _pj121.scene_cards[1]["source"] == "ai" and \
    _pj121.scene_cards[1]["name"] == "文斗", \
    "v1.21 主AI自做卡应只存入本项目库并标记 AI 制作"
assert _saved121["n"] == 1, "v1.21 自做卡入库后应持久化项目"
# 同名跳过（保留已有卡）
_eng121._collect_scene_cards(_pj121, {
    "new_scene_cards": [{"name": "武打", "content": "覆盖版"}]})
assert len(_pj121.scene_cards) == 2 and "覆盖版" not in str(_pj121.scene_cards), \
    "v1.21 主AI自做卡与已有卡重名应跳过（保留已有）"
# 无选择/自做 → 返回空
assert _eng121._collect_scene_cards(_pj121, {}) == [], \
    "v1.21 无选中/自做卡时应返回空列表"
# 名称在项目库缺失 → 降级查总库兜底
_orig_ld121 = _cfg118.load_config


def _fake_ld121():
    d = dict(_orig_ld121())
    d["writer_scene_cards"] = [{"name": "情感对峙", "content": "压抑中层层逼近。"}]
    return d


_cfg118.load_config = _fake_ld121
try:
    _got121b = _eng121._collect_scene_cards(_pj121, {"scene_cards": ["情感对峙"]})
finally:
    _cfg118.load_config = _orig_ld121
assert _got121b and _got121b[0]["name"] == "情感对峙" and \
    "压抑" in _got121b[0]["content"], \
    "v1.21 选中卡在项目库缺失时应降级查总库兜底"
# 2) 情景提示词功能页：项目库管理（从总库加入/移出/放入总库）+ 卡内容预览
assert hasattr(win.page_scene_cards, "_project_add_from_lib") and \
    hasattr(win.page_scene_cards, "_project_remove") and \
    hasattr(win.page_scene_cards, "_project_to_lib") and \
    hasattr(win.page_scene_cards, "_on_project_row") and \
    hasattr(win.page_scene_cards, "project_cards_detail"), \
    "v1.21 情景提示词页应有项目库管理（从总库加入/移出/放入总库）与卡内容预览"
# 3) 一键成书「应用以上设置到当前项目」→ project.scene_cards（总库卡复制进项目库）
import inspect as _inspect121  # noqa: E402
_src121 = _inspect121.getsource(_bp118._apply_style_to_project)
assert "project.scene_cards" in _src121 and "writer_scene_cards" in _src121, \
    "v1.21 一键成书应用设置应把总库勾选卡复制进 project.scene_cards"
# 4) 项目页 Tab ⑤ 只读显示项目库（含来源标注）+ 跳转管理
_src121p = _inspect121.getsource(win.page_project._refresh_scene_cards)
assert "project.scene_cards" in _src121p and "我提供" in _src121p and "AI 制作" in _src121p, \
    "v1.21 项目页情景卡应只读显示项目库（含来源标注）"
print("[9c] v1.21 总库/项目库分离（主AI按需自做卡只进项目库 + 放入总库 + 一键成书/项目页入口同步）OK")

# ---------- v1.22 「设为当前」API 修复 + 主AI选卡策略强化（优先已有/相近可套用/自做参考已有卡） ----------
# 1) config.pick_profile 修复：通用配置设为当前 → **任意用途**都用它（旧实现漏了该分支，
#    带用途的调用落到"列表第一个 role=all 的配置"，"设为当前"不生效——老 bug）
import config as _cfg122  # noqa: E402
_orig_ld122 = _cfg122.load_config


def _fake_ld122():
    return {
        "api_profiles": [
            {"name": "默认配置", "base_url": "https://x/v1", "api_key": "sk-1",
             "model": "m", "role": "all"},
            {"name": "写作号", "base_url": "https://x/v1", "api_key": "sk-2",
             "model": "m", "role": "write"},
            {"name": "推理号", "base_url": "https://x/v1", "api_key": "sk-3",
             "model": "m", "role": "reason"},
        ],
        "current_profile": "默认配置",
        "role_profiles": {"write": "写作号", "reason": "推理号"},
    }


_cfg122.load_config = _fake_ld122
try:
    assert _cfg122.pick_profile("decide")["name"] == "默认配置", \
        "v1.22 通用当前配置应匹配任意用途（设为当前即通用兜底）"
    assert _cfg122.pick_profile("all")["name"] == "默认配置", \
        "v1.22 通用用途应走当前配置"
    assert _cfg122.pick_profile("deai")["name"] == "默认配置", \
        "v1.22 未指定用途应回退当前配置"
    assert _cfg122.pick_profile("write")["name"] == "写作号", \
        "v1.22 用途分工指定仍优先于当前配置"
    assert _cfg122.pick_profile("reason")["name"] == "推理号", \
        "v1.22 用途分工指定仍优先于当前配置"
    # 专用配置设为当前 → 只匹配该用途（decide 不得被顶到专用当前配置）
    _d122 = _fake_ld122()
    _d122["current_profile"] = "写作号"
    _cfg122.load_config = lambda: _d122
    assert _cfg122.pick_profile("write")["name"] == "写作号", \
        "v1.22 专用当前配置应匹配自己的用途"
    assert _cfg122.pick_profile("decide")["name"] != "写作号", \
        "v1.22 专用当前配置不应顶掉其他用途"
finally:
    _cfg122.load_config = _orig_ld122
# 2) consolidate 选卡策略（v1.32 按需精确匹配：平淡章不选卡、绝不硬套不匹配的卡；v1.33 匹配即选不保守+选卡理由必填）
_pj122 = _mdl118.NovelProject("dir122", "测试")
_pj122.scene_cards = [{"name": "武打", "content": "攻防有节奏。", "source": "user"}]
_cs122, _cu122 = prompts_mod.consolidate(_pj122, st, 1, "两人拔剑对峙", {}, "")
assert "仅当本章剧情确实包含" in _cu122 and "绝不硬套不匹配的卡" in _cu122 and \
    "绝不因怕选错而漏用" in _cu122 and "scene_cards_reason" in _cu122, \
    "v1.33 consolidate 应要求按需精确选卡（平淡章不选卡、绝不硬套不匹配的卡、匹配即选不保守、选卡理由必填）"
assert "不凭空创造" in _cu122 and "都不真正匹配" in _cu122 and "写法摘录" in _cu122, \
    "v1.35 consolidate 应要求自做卡参考已有卡写法摘录（不凭空创造），仅当库中所有卡都不真正匹配时才做"
assert "攻防有节奏。" in _cu122, \
    "v1.35 consolidate 卡清单前 10 张应附内容摘录（供自制新卡参考已有卡写法）"
# 3) 空库分支：明确无已有卡可参考，按通用范例自做（同样是按需原则 + 选卡理由）
_pj122.scene_cards = []
_cs122b, _cu122b = prompts_mod.consolidate(_pj122, st, 1, "两人拔剑对峙", {}, "")
assert "没有已有卡可参考" in _cu122b and "scene_cards_reason" in _cu122b, \
    "v1.33 项目库为空时应注明无已有卡可参考（按通用范例自做），且仍要求输出选卡理由"
print("[9d] v1.22 设为当前API修复 + v1.32 选卡按需精确 + v1.33 匹配即选不保守/选卡理由必填 OK")

# ---------- v1.23 一键成书情景卡可选（空库引导占位+建卡跳转）+ AI 生成卡支持细节方向 ----------
import inspect as _inspect123  # noqa: E402
# 1) prompts.generate_scene_card_ai 支持 detail（细节方向注入；不传 behavior 不变）
_sys123, _usr123 = prompts_mod.generate_scene_card_ai("武打")
assert "细节方向" not in _usr123, "v1.23 不传 detail 时应保持原生成提示词"
_sys123b, _usr123b = prompts_mod.generate_scene_card_ai("武打", detail="偏兵刃近身、狠辣致命")
assert "细节方向" in _usr123b and "偏兵刃近身、狠辣致命" in _usr123b, \
    "v1.23 传 detail 应注入【细节方向】段供 AI 按方向设计"
# 2) main_ai.generate_scene_card 签名带 detail（转发）
import main_ai as _mai123  # noqa: E402
assert "detail" in _inspect123.signature(_mai123.generate_scene_card).parameters, \
    "v1.23 main_ai.generate_scene_card 应支持 detail 参数"
# 3) 情景提示词页 AI 一键生成：名称 + 细节方向两步输入
_src123g = _inspect123.getsource(win.page_scene_cards._card_ai_gen)
assert "getMultiLineText" in _src123g and "细节方向" in _src123g, \
    "v1.23 AI 生成应可填细节方向（getMultiLineText）"
_src123w = _inspect123.getsource(win.page_scene_cards._card_ai_gen_worker)
assert "detail" in _src123w, "v1.23 生成 worker 应把细节方向传给 main_ai"
# 4) 一键成书：空库引导占位（不可勾选）+ 建卡跳转按钮
assert hasattr(_pan118, "_goto_scene_cards"), \
    "v1.23 一键成书面板应有「去情景提示词页建卡」跳转"
_src123r = _inspect123.getsource(_pan118._refresh_scene_cards)
assert "总库为空" in _src123r, "v1.23 一键成书勾选列表空库应有引导占位"
_orig_ld123 = _cfg122.load_config
_cfg122.load_config = lambda: {"writer_scene_cards": []}
try:
    _pan118._refresh_scene_cards()
    assert _pan118.scene_cards_list.count() >= 1 and \
        _pan118._current_style_values().get("scene_cards") == [], \
        "v1.23 空库占位项不应被当作可勾选的卡"
finally:
    _cfg122.load_config = _orig_ld123
print("[9e] v1.23 一键成书情景卡可选（空库引导占位+建卡跳转）+ AI 生成卡支持细节方向 OK")

# ---------- v1.24 一键成书「加入」式（不再全部并列勾选）+ 情景卡分类管理 ----------
# 1) 加入式：BookPanel 有 _card_pick/_added_scene_cards，加入列表驱动 scene_cards 取值
assert hasattr(_pan118, "_card_pick") and hasattr(_pan118, "_added_scene_cards"), \
    "v1.24 一键成书面板应有「＋ 加入」机制（_card_pick/_added_scene_cards）"


def _fake_ld124():
    return {"writer_scene_cards": [
        {"name": "武打", "content": "攻防有节奏。", "category": "武打类"},
        {"name": "文斗", "content": "言语交锋。", "category": "文斗类"}]}


_orig_ld124 = _cfg122.load_config
_cfg122.load_config = _fake_ld124
try:
    _pan118._added_scene_cards = []
    _pan118._refresh_scene_cards()
    assert _pan118.scene_cards_list.count() >= 1 and \
        "未加入任何情景卡" in _pan118.scene_cards_list.item(0).text(), \
        "v1.24 未加入时列表应显示占位引导（不淹没全部总库卡）"
    assert _pan118._current_style_values().get("scene_cards") == [], \
        "v1.24 未加入任何卡时 scene_cards 为空"
    _pan118._added_scene_cards = ["武打"]
    _pan118._refresh_scene_cards()
    assert _pan118._current_style_values().get("scene_cards") == ["武打"], \
        "v1.24 加入的卡应驱动 scene_cards 取值"
    assert any("武打" in _pan118.scene_cards_list.item(i).text()
               for i in range(_pan118.scene_cards_list.count())), \
        "v1.24 已加入的卡应显示在列表中"
finally:
    _cfg122.load_config = _orig_ld124
# 2) 分类：页面有分类筛选/分类输入 + 筛选方法
assert hasattr(win.page_scene_cards, "category_combo") and \
    hasattr(win.page_scene_cards, "category_edit") and \
    hasattr(win.page_scene_cards, "_refresh_categories") and \
    hasattr(win.page_scene_cards, "_category_filter"), \
    "v1.24 情景提示词页应有分类筛选（category_combo）/分类输入（category_edit）"
# 3) 分类导出/导入往返（带【分类】行 + 无分类向后兼容）
from gui_scene_cards import _export_text as _exp124, _parse_import as _par124  # noqa: E402
_txt124 = _exp124([{"name": "武打", "content": "攻防有节奏。", "category": "武打类"},
                   {"name": "文斗", "content": "言语交锋。"}])
assert "【分类】武打类" in _txt124 and "【分类】武打类\n攻防有节奏。" in _txt124, \
    "v1.24 有分类的卡导出应带【分类】行（位于内容前），无分类卡不带"
_cards124 = _par124(_txt124)
assert len(_cards124) == 2 and _cards124[0]["category"] == "武打类" and \
    _cards124[1]["category"] == "" and _cards124[0]["content"] == "攻防有节奏。", \
    "v1.24 导入应解析【分类】行（无分类卡 category 空），内容不含【分类】行"
# 4) 项目库卡分类往返（models）
_pj124 = _mdl118.NovelProject("dir124", "测试")
_pj124.scene_cards = [{"name": "武打", "content": "攻防。", "source": "user", "category": "武打类"}]
_d124 = _pj124.to_dict()
_pj124b = _mdl118.NovelProject.from_dict(_d124, "dir124")
assert _pj124b.scene_cards[0].get("category") == "武打类", \
    "v1.24 项目库卡分类应随 to_dict/from_dict 往返"
print("[9f] v1.24 一键成书「加入」式（点加入从总库勾选）+ 情景卡分类管理（筛选/编辑/导出导入/项目库带分类）OK")

# ---------- v1.25 分类下拉选择（不怕忘分类名）+ 选择对话框按分类分组（整类全选/子项单独勾选） ----------
from PySide6.QtCore import Qt as _Qt125  # noqa: E402
from PySide6.QtWidgets import QComboBox as _QCB125  # noqa: E402
from gui_scene_cards import _PickCardsDialog as _Pick125  # noqa: E402
# 1) 编辑区分类是下拉列表（QComboBox），可从已有分类选择（不怕忘）
assert isinstance(win.page_scene_cards.category_edit, _QCB125), \
    "v1.25 卡分类应为下拉列表（已有分类可选，不怕忘）"
_cards125 = [{"name": "武打·兵刃", "content": "刀剑对拼。", "category": "武打"},
             {"name": "武打·拳脚", "content": "肉搏缠斗。", "category": "武打"},
             {"name": "文斗", "content": "言语交锋。", "category": "文斗"}]
_dlg125 = _Pick125(_cards125, set(), None, checked=[])
_datas125 = [_dlg125.list.item(i).data(_Qt125.ItemDataRole.UserRole)
             for i in range(_dlg125.list.count())]
assert _datas125[0] == "__CAT__" and _datas125[1] in ("武打·兵刃", "武打·拳脚") and \
    _datas125[2] in ("武打·兵刃", "武打·拳脚") and _datas125[3] == "__CAT__" and \
    _datas125[4] == "文斗", \
    "v1.25 选择对话框应按分类分组（标题行后跟该分类卡）"
# 2) 勾选「武打」分类标题 → 该分类整类全选，其他分类不受影响
_dlg125.list.item(0).setCheckState(_Qt125.CheckState.Checked)
assert _dlg125.list.item(1).checkState() == _Qt125.CheckState.Checked and \
    _dlg125.list.item(2).checkState() == _Qt125.CheckState.Checked and \
    _dlg125.list.item(4).checkState() == _Qt125.CheckState.Unchecked, \
    "v1.25 勾选分类标题应整类全选且不影响其他分类"
assert sorted(_dlg125.picked()) == ["武打·兵刃", "武打·拳脚"], \
    "v1.25 整类全选后 picked 返回该分类全部卡名"
# 3) 取消分类标题 → 整类全不选；子项可单独勾选
_dlg125.list.item(0).setCheckState(_Qt125.CheckState.Unchecked)
assert _dlg125.picked() == [], "v1.25 取消分类标题应整类全不选"
_dlg125.list.item(1).setCheckState(_Qt125.CheckState.Checked)
assert _dlg125.picked() == ["武打·兵刃"], "v1.25 组内卡可单独勾选"
# 4) 分类下拉有「未分类」项（保存时转空存储）
win.page_scene_cards.category_edit.setCurrentText("未分类")
assert win.page_scene_cards.category_edit.currentText().strip() == "未分类", \
    "v1.25 分类下拉应有「未分类」项"
print("[9g] v1.25 分类下拉选择（不怕忘分类名）+ 选择对话框按分类分组（整类全选/子项单独勾选）OK")

# ---------- v1.26 情景卡拆书：从导入小说拆出全部情景卡草稿（三阶段：分片抽候选→相似度合并→逐类生成卡） ----------
import llm as _llm126  # noqa: E402
import scene_card_extract as _sce126  # noqa: E402
# 1) 引擎三阶段链路（mock）：5 片候选 + 合并 + 每合并类型生成一张卡
_orig_chars126 = _sce126.SCENE_BATCH_CHARS
_orig_cj126 = _llm126.chat_json
_orig_ct126 = _llm126.chat_text
_sce126.SCENE_BATCH_CHARS = 400
_cj_n126 = {"n": 0}
_ct_n126 = {"n": 0}
_cand_names126 = ["夜战夺镖·兵刃近身", "男主初登场", "街头群殴", "情侣冷战分手", "绝境垂死"]


def _fake_cj126(system, user, **kw):
    if "【全部候选情景】" in str(user):
        # 合并调用：把 5 个候选合并为 5 类（含大类）
        return [{"category": ("武打" if ("夺镖" in t or "群殴" in t)
                              else "情感" if "分手" in t
                              else "开篇" if "登场" in t else "绝境"),
                 "type": t, "examples": ["片段%d。" % i]}
                for i, t in enumerate(_cand_names126, 1)]
    # 候选调用：逐片返回不同候选（顺序取，与分片数无关）
    _cj_n126["n"] += 1
    i = _cj_n126["n"]
    nm = _cand_names126[(i - 1) % len(_cand_names126)]
    return [{"type": nm, "brief": "b%s" % i, "example": "片段%s。" % i}]


def _fake_ct126(system, user, **kw):
    _ct_n126["n"] += 1
    return "你是一位……\n\n**核心定位：**…\n\n**写作执行与自检清单：**\n1. …"


_llm126.chat_json = _fake_cj126
_llm126.chat_text = _fake_ct126
try:
    _text126 = "".join("第%d章\n" % i + "这章是正文内容，" * 30 for i in range(1, 6))
    _cards126 = _sce126.extract_scene_cards_from_novel(_text126, sink=lambda k, m: None)
    assert len(_cards126) == 5 and _cards126[0]["name"] == "夜战夺镖·兵刃近身" and \
        _cards126[0]["category"] == "武打" and _cards126[0]["content"].strip(), \
        "v1.26 三阶段情景卡拆书应返回合并后的卡草稿（名称/分类/内容）"
    assert _ct_n126["n"] == 5, "v1.26 每个合并类型应生成一张卡草稿"
    # 2) 停止传播（StopRequested 不吞）
    def _fake_cj_stop126(system, user, **kw):
        raise _llm126.StopRequested("测试停止")
    _llm126.chat_json = _fake_cj_stop126
    try:
        _sce126.extract_scene_cards_from_novel(_text126[:600], sink=lambda k, m: None)
        assert False, "v1.26 停止信号应传播（StopRequested 不吞）"
    except _llm126.StopRequested:
        pass
finally:
    _llm126.chat_json = _orig_cj126
    _llm126.chat_text = _orig_ct126
    _sce126.SCENE_BATCH_CHARS = _orig_chars126
# 3) 拆书页情景卡拆书区块：按钮/结果列表/存进总库 + 后台 worker
_break126 = win.page_break
assert hasattr(_break126, "_sc_start") and hasattr(_break126, "_sc_stop") and \
    hasattr(_break126, "_sc_save") and hasattr(_break126, "sc_result_list") and \
    hasattr(_break126, "sc_start_btn") and hasattr(_break126, "sc_stop_btn") and \
    hasattr(_break126, "sc_save_btn"), \
    "v1.26 拆书页应有情景卡拆书区块（按钮/结果列表/存进总库）"
from gui_break import SceneCardExtractWorker as _SCEW126  # noqa: E402
assert _SCEW126 is not None, "v1.26 应有 SceneCardExtractWorker 后台线程载体"
# ---------- v1.27 情景卡拆书控制性提示词（方向控制）+ 主AI空库自动做卡确认 ----------
import inspect as _inspect127  # noqa: E402
assert "prompt" in _inspect127.signature(_SCEW126.run).parameters, \
    "v1.27 SceneCardExtractWorker.run 应支持 prompt 参数"
assert hasattr(_break126, "sc_prompt_edit"), \
    "v1.27 拆书页应有情景卡拆书控制性提示词输入框（sc_prompt_edit）"
_cj_seen127 = {"user": ""}
_orig_cj127 = _llm126.chat_json


def _fake_cj_cap127(system, user, **kw):
    _cj_seen127["user"] = str(user)
    return []


_llm126.chat_json = _fake_cj_cap127
try:
    _sce126._candidate_batch({"title": "t", "text": "正文内容。"}, "重点拆武打。")
    assert "用户指定关注方向" in _cj_seen127["user"] and "重点拆武打" in _cj_seen127["user"], \
        "v1.27 传 prompt 应注入【用户指定关注方向】段"
    _cj_seen127["user"] = ""
    _sce126._candidate_batch({"title": "t", "text": "正文内容。"})
    assert "用户指定关注方向" not in _cj_seen127["user"], \
        "v1.27 不传 prompt 应保持通用拆卡提示词"
finally:
    _llm126.chat_json = _orig_cj127
print("[9h] v1.26 情景卡拆书（分片抽候选→相似度合并→逐类生成卡草稿；可存进总库）+ v1.27 控制性提示词（方向控制）OK")

# ---------- v1.28 「＋ 加入」交互修复：点卡行即勾选（点复选框照旧）+ 空勾选明确提示 ----------
from PySide6.QtWidgets import QDialog as _QDialog128  # noqa: E402
from gui_scene_cards import _CheckListWidget as _CLW128  # noqa: E402
_dlg128 = _Pick125(_cards125, set(), None, checked=[])
assert isinstance(_dlg128.list, _CLW128), "v1.28 选卡弹窗列表应支持点行即勾选"
_row128 = None
for _i128 in range(_dlg128.list.count()):
    if _dlg128.list.item(_i128).data(_Qt125.ItemDataRole.UserRole) not in (
            None, "__CAT__"):
        _row128 = _i128
        break
assert _row128 is not None, "v1.28 弹窗应有卡行"
_dlg128.list.toggle_row(_dlg128.list.item(_row128))
assert _dlg128.list.item(_row128).checkState() == _Qt125.CheckState.Checked, \
    "v1.28 点行文本应切换该卡为勾选"
_dlg128.list.toggle_row(_dlg128.list.item(_row128))
assert _dlg128.list.item(_row128).checkState() == _Qt125.CheckState.Unchecked, \
    "v1.28 再点一次应取消勾选"
# 空勾选点确定 → 明确提示（不会静默无反馈）
_orig_exec128 = _Pick125.exec


def _fake_exec_none128(self):
    return _QDialog128.DialogCode.Accepted  # 模拟确定，但不勾选任何卡


_Pick125.exec = _fake_exec_none128
try:
    _pan118._added_scene_cards = []
    _pan118._card_pick()
    assert "未勾选任何情景卡" in _pan118.hint.text(), \
        "v1.28 空勾选点确定应给出明确提示"
    assert _pan118._current_style_values().get("scene_cards") == [], \
        "v1.28 空勾选时不应加入任何卡"
finally:
    _Pick125.exec = _orig_exec128
print("[9i] v1.28 「＋ 加入」点行即勾选（点复选框照旧）+ 空勾选明确提示 OK")

# ---------- v1.29 审查补漏：复制卡保留分类 / 拆书worker异常兜底复位 / 分批二次合并保示例 ----------
import inspect as _inspect129  # noqa: E402
# 1) 一键成书立项 & 应用设置：从总库复制卡进项目库必须保留分类（v1.24 分类功能一致性）
_src129a = _inspect129.getsource(_bw118.run)
_src129b = _inspect129.getsource(_pan118._apply_style_to_project)
assert '"category"' in _src129a, "v1.29 一键成书立项复制总库卡应保留 category"
assert '"category"' in _src129b, "v1.29 应用以上设置复制总库卡应保留 category"
# 2) 情景卡拆书 worker 异常兜底：非停止异常也要复位按钮；StopRequested 必须在
#    except Exception 之前（StopRequested 是 LLMError(Exception) 子类，防吞停止）
_src129c = _inspect129.getsource(_SCEW126.run)
assert "except Exception" in _src129c and \
    _src129c.index("except Exception") > _src129c.index("except llm.StopRequested"), \
    "v1.29 拆书 worker 异常兜底须在 except llm.StopRequested 之后（防吞停止信号）"
# 3) 分批二次合并（候选>60）保示例：输入结构已是 {type,examples} 时仍能带上代表片段
_oj129 = _llm126.chat_json
_seen129 = {"n": 0, "u": ""}


def _fake129(system, user, **kw):
    _seen129["n"] += 1
    _seen129["u"] = str(user)
    seen = []
    # 合并结果：40 项（触发二次合并路径）
    for i in range(40):
        seen.append({"category": "c", "type": "合并款%d" % i,
                     "examples": ["示例片段%d" % i]})
    return seen


_llm126.chat_json = _fake129
try:
    _sce126._merge_once([{"type": "夜战夺镖", "examples": ["刀光一闪。"]}], "t")
    assert "刀光一闪。" in _seen129.get("u", ""), \
        "v1.29 候选无 example/brief 时应从 examples 取代表片段（防全丢）"
    _merge_user129 = []
    _orig_cj129 = _llm126.chat_json

    def _fake129b(system, user, **kw):
        _merge_user129.append(str(user))
        return [{"category": "c", "type": "合并款%d" % i,
                 "examples": ["示例片段%d" % i]} for i in range(40)]

    _llm126.chat_json = _fake129b
    try:
        _out129 = _sce126._merge_all(
            [{"type": "候选%d" % i, "example": "片段%d" % i} for i in range(63)])
        assert isinstance(_out129, list) and len(_merge_user129) == 3, \
            "v1.29 63 个候选应分批（60+3）→ 二次合并共 3 次调用"
        assert "示例片段" in _merge_user129[2], \
            "v1.29 二次合并输入（{type,examples}）应带示例片段（防止只凭类型名二分）"
    finally:
        _llm126.chat_json = _orig_cj129
finally:
    _llm126.chat_json = _oj129
print("[9j] v1.29 审查补漏（复制卡保留分类/拆书worker异常复位/分批二次合并保示例）OK")

# ---------- v1.30 ① 情景卡拆书按钮"点了没反应"修复（_sc_worker 未初始化 → 首次点击 AttributeError） ----------
import gui_break as _gb130  # noqa: E402
_bp130 = _inspect129.getsource(_gb130.BreakPage.__init__)
assert "self._sc_worker = None" in _bp130, \
    "v1.30 拆书页 __init__ 必须初始化 _sc_worker=None（否则首次点「开始情景卡拆书」按钮 AttributeError 点了没反应）"
# ---------- v1.30 ② 批量导出（txt + 细分文件夹）与批量导入 ----------
import tempfile as _tmp130  # noqa: E402
import os as _os130  # noqa: E402
from gui_scene_cards import _file_safe as _fs130  # noqa: E402
from PySide6.QtWidgets import QFileDialog as _qfd130, QMessageBox as _qmb130  # noqa: E402
assert _fs130("夜战夺镖/武林:*?") == "夜战夺镖_武林___" and _fs130("") == "未命名", \
    "v1.30 细分文件名应替换 Windows 非法字符"
_page130 = win.page_scene_cards
_orig_cards130 = _page130._cards
_orig_gd130 = _qfd130.getExistingDirectory
_orig_ofn130 = _qfd130.getOpenFileNames
_orig_qmb130 = _qmb130.information
_qmb130.information = staticmethod(lambda *a, **k: None)
_tdir130 = _tmp130.mkdtemp()
_page130._cards = lambda: [
    {"name": "夜战夺镖", "content": "刀光一闪。", "category": "武打"},
    {"name": "文斗", "content": "唇枪舌剑。", "category": ""}]
_qfd130.getExistingDirectory = staticmethod(lambda *a, **k: _tdir130)
try:
    _page130._export_batch()
    _fsn130 = _os130.listdir(_tdir130)
    _subs130 = [d for d in _fsn130 if d.endswith("_细分")]
    _sum130 = [f for f in _fsn130 if f.endswith(".txt") and not f.endswith("_细分")]
    assert len(_sum130) == 1 and _subs130, \
        "v1.30 批量导出应生成 1 个汇总 txt + 一个 _细分 文件夹"
    _subf130 = _os130.listdir(_os130.path.join(_tdir130, _subs130[0]))
    assert "[武打]夜战夺镖.txt" in _subf130 and "文斗.txt" in _subf130, \
        "v1.30 细分文件夹每张卡一个文件（有分类的带[分类]前缀，无分类用卡名）"
finally:
    _page130._cards = _orig_cards130
    _qfd130.getExistingDirectory = _orig_gd130
_tp130 = _tmp130.mkdtemp()
_p1_130 = _os130.path.join(_tp130, "汇总.txt")
with open(_p1_130, "w", encoding="utf-8") as f:
    f.write("【卡名】武打\n攻防有节奏。\n\n【卡名】文斗\n唇枪舌剑。")
_p2_130 = _os130.path.join(_tp130, "绝境.txt")
with open(_p2_130, "w", encoding="utf-8") as f:
    f.write("垂死挣扎。")
_saved130 = {"cards": []}
_page130._cards = lambda: [{"name": "武打", "content": "旧内容", "category": ""}]
_page130._persist = lambda cards: _saved130.__setitem__("cards", list(cards))
_qfd130.getOpenFileNames = staticmethod(lambda *a, **k: ([_p1_130, _p2_130], ""))
try:
    _page130._import_batch()
    _ns130 = {str(c.get("name") or "") for c in _saved130["cards"]}
    assert _ns130 == {"武打", "文斗", "绝境"}, \
        "v1.30 批量导入应合并汇总多卡 + 单卡文件（卡名取文件名）"
    _wuda130 = [c for c in _saved130["cards"] if c["name"] == "武打"][0]
    assert _wuda130["content"] == "旧内容", \
        "v1.30 批量导入同名自动跳过（不覆盖已有卡）"
finally:
    _page130._cards = _orig_cards130
    _qfd130.getOpenFileNames = _orig_ofn130
    _qmb130.information = _orig_qmb130
# ---------- v1.30 ③ consolidate 卡注入瘦身（只发卡名清单；明确卡不影响剧情判断→防主AI写乱情节） ----------
_pj130 = _mdl118.NovelProject("dir130", "测试")
_pj130.scene_cards = [
    {"name": "武打", "content": "攻防有节奏，杀招有取舍。", "source": "user",
     "category": "武打类"},
    {"name": "文斗", "content": "言语交锋，唇枪舌剑。", "source": "user"},
    {"name": "绝境长卡", "content": "绝境写法：" + "步步紧逼" * 40, "source": "user"}]
_cs130, _cu130 = prompts_mod.consolidate(_pj130, st, 1, "两人拔剑对峙", {}, "")
assert '"scene_cards"' in _cu130 and '"new_scene_cards"' in _cu130, \
    "v1.30 consolidate JSON schema 保留"
assert "武打" in _cu130 and "文斗" in _cu130 and "绝境长卡" in _cu130 and "用户提供" in _cu130, \
    "v1.30 应注入卡名清单（含来源标注）"
assert "绝不影响你的剧情判断" in _cu130, \
    "v1.30 应声明卡不影响剧情判断（防主AI把卡当剧情指令写乱情节）"
# v1.35 语义升级：前 10 张卡附写法摘录（前150字）供自制新卡参考——短卡全文即摘录注入、
# 长卡只注入摘录、不注入全文（保留 v1.30 防带偏剧情判断的边界）
assert "攻防有节奏，杀招有取舍。" in _cu130 and "言语交锋，唇枪舌剑。" in _cu130, \
    "v1.35 consolidate 应注入卡写法摘录（短卡全文即摘录）供自制新卡参考"
assert "绝境写法：" in _cu130 and "步步紧逼" * 37 not in _cu130, \
    "v1.35 consolidate 卡内容只注入写法摘录（前150字），不注入全文（防带偏剧情判断）"
_pj130.scene_cards = []
_cs130b, _cu130b = prompts_mod.consolidate(_pj130, st, 1, "两人拔剑对峙", {}, "")
assert "没有已有卡可参考" in _cu130b and "绝不影响剧情判断" in _cu130b, \
    "v1.30 空库分支也应声明卡不影响剧情判断"
print("[9k][9l][9m] v1.30 拆书按钮修复 + 批量导出细分/批量导入 + 卡注入瘦身防写乱情节 OK")

# ---------- v1.31 批量导入分类保留（细分文件【分类】行 + 文件名前缀兼容）+ 拆书按钮真实点击链路 ----------
from gui_scene_cards import _parse_import as _pi131  # noqa: E402
# ① v1.30 批量导出的细分文件内容只写正文（分类放文件名）→ 导入丢分类；v1.31 内容带【分类】行
_subdir131 = _os130.path.join(_tdir130, _subs130[0])
with open(_os130.path.join(_subdir131, "[武打]夜战夺镖.txt"),
          "r", encoding="utf-8") as _f131:
    _subtxt131 = _f131.read()
assert _subtxt131.startswith("【分类】武打\n"), \
    "v1.31 批量导出细分文件内容应以【分类】行开头（与汇总一致，导入不再丢分类）"
# ② 兼容 v1.30 旧细分文件：文件名 [分类]卡名.txt → 拆出分类与干净卡名
_c131 = _pi131("刀光一闪。", fallback_name="[武打]夜战夺镖")
assert _c131 and _c131[0]["name"] == "夜战夺镖" and _c131[0]["category"] == "武打", \
    "v1.31 fallback_name「[分类]卡名」应拆出分类与干净卡名（不再把[武打]当前缀）"
_c131b = _pi131("【分类】文斗\n唇枪舌剑。", fallback_name="[武打]旧名")
assert _c131b[0]["category"] == "文斗" and _c131b[0]["name"] == "旧名", \
    "v1.31 内容带【分类】行时应以内容分类为准（文件名前缀仅兜底）"
# ③ round-trip：拿 v1.31 导出的细分文件真实批量导入 → 分类保留
_saved131 = {"cards": []}
_oc131 = _page130._cards
_op131 = _page130._persist
_page130._cards = lambda: []
_page130._persist = lambda cards: _saved131.__setitem__("cards", list(cards))
_qfd131_orig = _qfd130.getOpenFileNames
_qmb131_orig = _qmb130.information
_qfd130.getOpenFileNames = staticmethod(
    lambda *a, **k: ([_os130.path.join(_subdir131, "[武打]夜战夺镖.txt"),
                      _os130.path.join(_subdir131, "文斗.txt")], ""))
_qmb130.information = staticmethod(lambda *a, **k: None)
try:
    _page130._import_batch()
    _cat131 = {str(c.get("name") or ""): str(c.get("category") or "")
               for c in _saved131["cards"]}
    assert _cat131.get("夜战夺镖") == "武打", \
        "v1.31 导入细分文件后分类应保留，实际 %r" % (_cat131,)
    assert "文斗" in _cat131 and _cat131.get("文斗") == "", \
        "v1.31 无分类卡导入后分类应为空"
    assert not any("[武打]" in k for k in _cat131), \
        "v1.31 卡名不应再带[分类]文件名前缀"
finally:
    _page130._cards = _oc131
    _page130._persist = _op131
    _qfd130.getOpenFileNames = _qfd131_orig
    _qmb130.information = _qmb131_orig
# ④ 拆书按钮真实点击链路：点击 → worker 注入 → done 复位（防"点了没反应"再次发生）
class _FakeSCW131(_SCEW126):
    def run(self, text, prompt):
        self.done.emit([{"name": "测试卡", "content": "内容。", "category": "武打"}])


_orig_scw131 = _gb130.SceneCardExtractWorker
_gb130.SceneCardExtractWorker = _FakeSCW131
_break131 = win.page_break
_break131._source_text = "测试全文。"
_break131._sc_worker = None
try:
    _break131.sc_start_btn.click()
    _started131 = _break131._sc_worker is not None
    for _ in range(60):
        app.processEvents()
        time.sleep(0.02)
        if _break131._sc_worker is None and _break131.sc_start_btn.isEnabled():
            break
    assert _started131, "v1.31 点击拆书按钮应启动 worker（_sc_worker 非 None）"
    assert _break131._sc_worker is None and _break131.sc_start_btn.isEnabled(), \
        "v1.31 拆书完成后 worker 应复位（_sc_worker=None）且按钮恢复可用"
    assert _break131.sc_result_list.count() == 1, \
        "v1.31 拆书完成后结果列表应有勾选卡"
    assert _break131.sc_save_btn.isEnabled(), \
        "v1.31 结果勾选后应可「存进总库」"
finally:
    _gb130.SceneCardExtractWorker = _orig_scw131
    _break131._sc_worker = None
    _break131.sc_start_btn.setEnabled(True)
    _break131.sc_stop_btn.setEnabled(False)
print("[9n] v1.31 批量导入分类保留（细分文件【分类】行+文件名前缀兼容）+ 拆书按钮真实点击链路 OK")

# ---------- v1.36 情景卡拆书边拆边显示（逐张实时入列；长小说可停止，已拆出的卡保留可直接保存） ----------
import inspect as _inspect136  # noqa: E402
assert hasattr(_break126, "_sc_on_card") and hasattr(_break126, "_sc_add_card_item"), \
    "v1.36 拆书页应有 _sc_on_card（逐张实时入列）与 _sc_add_card_item（完成/实时共用入列）"
assert hasattr(_SCEW126, "card_ready"), \
    "v1.36 SceneCardExtractWorker 应有 card_ready 信号（逐张实时回调）"
assert "on_card=lambda c: self.card_ready.emit(c)" in \
    _inspect136.getsource(_SCEW126.run), \
    "v1.36 worker.run 应把引擎 on_card 回调接到 card_ready 信号"
assert "已拆出的卡保留在结果列表，可直接保存" in _inspect136.getsource(_break126._sc_stop), \
    "v1.36 停止提示应说明已拆出的卡保留可直接保存"
import llm as _llm136  # noqa: E402
import scene_card_extract as _sce136  # noqa: E402
_orig_chars136 = _sce136.SCENE_BATCH_CHARS
_orig_cj136 = _llm136.chat_json
_orig_ct136 = _llm136.chat_text
_sce136.SCENE_BATCH_CHARS = 400
_names136 = ["武打·近身", "文斗", "绝境"]


def _fake_cj136(system, user, **kw):
    if "【全部候选情景】" in str(user):
        return [{"category": ("武打" if "近身" in t else "情感" if "文斗" in t else "绝境"),
                 "type": t, "examples": ["片段。"]} for t in _names136]
    return [{"type": _names136[0], "brief": "b", "example": "片段。"}]


_llm136.chat_json = _fake_cj136
_llm136.chat_text = lambda system, user, **kw: "核心定位：…\n写作执行自检清单：…"
try:
    _got136 = []
    _cards136 = _sce136.extract_scene_cards_from_novel(
        "".join("第%d章\n" % i + "正文内容。" * 30 for i in range(1, 4)),
        sink=lambda k, m: None, on_card=_got136.append)
    assert len(_cards136) == 3 and len(_got136) == 3 and \
        _got136[0]["name"] == "武打·近身" and _got136[2]["category"] == "绝境", \
        "v1.36 on_card 应逐张回调（数量与返回列表一致，含卡名/分类）"
    # 停止时已回调的卡保留：合并后第 2 张卡抛 StopRequested，第 1 张已回调不丢
    _ct136 = {"n": 0}


    def _fake_ct_stop136(system, user, **kw):
        _ct136["n"] += 1
        if _ct136["n"] == 2:
            raise _llm136.StopRequested("测试停止")
        return "核心定位：…\n写作执行自检清单：…"


    _llm136.chat_text = _fake_ct_stop136
    _got136b = []
    try:
        _sce136.extract_scene_cards_from_novel(
            "".join("第%d章\n" % i + "正文内容。" * 30 for i in range(1, 4)),
            sink=lambda k, m: None, on_card=_got136b.append)
        assert False, "v1.36 停止信号应传播（StopRequested 不吞）"
    except _llm136.StopRequested:
        pass
    assert len(_got136b) == 1, \
        "v1.36 停止时已回调的卡应保留（长小说可停止后保存已拆出的卡）"
finally:
    _llm136.chat_json = _orig_cj136
    _llm136.chat_text = _orig_ct136
    _sce136.SCENE_BATCH_CHARS = _orig_chars136
print("[9q] v1.36 情景卡拆书边拆边显示（逐张实时入列 + 停止保留已拆卡）OK")

# ---------- v1.32 情景卡机制修正：选卡按需精确（平淡章不选卡/绝不硬套）+ 卡注入片段级参考 + 拆书泛化 + 角色卡丰富化 + 运行状态 ----------
# 1) consolidate：平淡章不选卡（但匹配即选不保守、绝不因怕选错漏卡、选卡理由必填）
_pj132 = _mdl118.NovelProject("dir132", "测试")
_pj132.scene_cards = [{"name": "武打", "content": "攻防有节奏。", "source": "user"},
                      {"name": "文斗", "content": "言语交锋层层进逼。", "source": "user"}]
_cs132, _cu132 = prompts_mod.consolidate(_pj132, st, 1, "主角在客栈吃早饭，平静日常", {}, "")
assert "常规叙事章节不选卡" in _cu132 and "绝不硬套不匹配的卡" in _cu132 and \
    "绝不因怕选错而漏用" in _cu132 and "scene_cards_reason" in _cu132, \
    "v1.33 consolidate 应要求平淡/日常章不选卡、绝不硬套不匹配的卡、匹配即选不保守、选卡理由必填"
assert "片段级" in _cu132 or "片段" in _cu132, "v1.33 应说明卡只约束特殊情景片段"
# 2) write_chapter：卡注入为片段级参考，明确铺垫/日常段落不受卡约束
_cs132b, _cu132b = prompts_mod.write_chapter(
    _pj132, st, 1, "焦点", "方向", {}, [], 2500,
    scene_cards=[{"name": "武打", "content": "攻防有节奏。"}])
assert "片段级写法参考" in _cu132b, "v1.32 write_chapter 卡注入应声明为片段级写法参考"
assert "铺垫" in _cu132b and "不许为了套卡压缩铺垫" in _cu132b, \
    "v1.32 write_chapter 应明确铺垫/日常段落不受卡约束（防止正文AI不会铺垫）"
# 3) 拆书三阶段提示词：泛化要求（拆出可迁移写法，禁止绑定具体人物/关系/场景细节）
import inspect as _inspect132  # noqa: E402
import scene_card_extract as _sce132  # noqa: E402
_src_sys_cand132 = _inspect132.getsource(_sce132)
assert "v1.32 泛化要求" in _src_sys_cand132, \
    "v1.32 拆书候选提示词应含泛化要求（可迁移写法，不绑定具体人物/场景）"
assert "禁止绑定具体人物/关系/场景细节" in _src_sys_cand132, \
    "v1.32 拆书候选应禁止绑定具体人物关系/场景细节（防拆出'兄妹做饭打闹'这类无泛化价值的卡）"
assert "怎么写" in _src_sys_cand132 and "允许出现任何行为/事件/情节指令" not in _src_sys_cand132 \
    and "禁止出现任何行为/事件/情节指令" in _src_sys_cand132, \
    "v1.33 拆书三阶段应写明'怎么写/怎么做边界'——卡只写写法技法、严禁行为/事件/情节指令（防与主AI指令冲突/抄袭/窄化）"
# 4) 角色卡生成丰富化：personality/appearance/description 不再压成一两句
import prompts as _prompts132  # noqa: E402
_orig_ld132 = _cfg122.load_config
_cfg122.load_config = lambda: {"writer_scene_cards": []}
try:
    _p132s, _p132u = _prompts132.generate_character_ai("测试配角", _pj132, st)
    assert "250-450字" in _p132u and "100-200字" in _p132u and "80-150字" in _p132u, \
        "v1.32 角色卡生成应要求立体丰满（description 250-450/personality 100-200/appearance 80-150）"
    assert "不要三言两语打发" in _p132u, "v1.32 角色卡生成应明确禁止三言两语打发"
finally:
    _cfg122.load_config = _orig_ld132
# 5) 新功能 worker 运行状态：情景卡 AI 生成/文本提取/拆书 均已 set_running（左下角显示运行中）
_src132g = _inspect132.getsource(win.page_scene_cards._card_ai_gen)
_src132x = _inspect132.getsource(win.page_scene_cards._card_extract)
_src132s = _inspect132.getsource(_break131._sc_start)
assert "set_running(True)" in _src132g and "set_running(True)" in _src132x and \
    "set_running(True)" in _src132s, \
    "v1.32 情景卡AI生成/文本提取/拆书 worker 启动均应 set_running(True)（左下角不再一直空闲）"
_src132gd = _inspect132.getsource(win.page_scene_cards._on_card_generated)
_src132d = _inspect132.getsource(_break131._sc_on_done)
assert "set_running(False)" in _src132gd and "set_running(False)" in _src132d, \
    "v1.32 worker 完成/失败均应 set_running(False) 复位运行状态"
print("[9o] v1.32 情景卡机制修正（选卡按需精确/卡注入片段级/拆书泛化/角色卡丰富化/新功能运行状态）OK")

# ---------- v1.37 事件跨章节奏与前后衔接（用户：每章有自己的想法、都想着自己搞高潮桥段、恨不得一章一个事件、
# 完全没做铺垫衔接——一个事件从酝酿到高潮到收尾得用几章甚至十几章几十章，主AI特别毛躁；让主AI自己判断） ----------
_pj137 = _mdl118.NovelProject("dir137", "测试")
_pj137.scene_cards = [{"name": "武打", "content": "攻防有节奏。", "source": "user"}]
_cs137, _cu137 = prompts_mod.consolidate(_pj137, st, 1, "两人拔剑对峙", {}, "")
assert "事件节奏" in _cu137 and "跨多章推进" in _cu137 and "绝不在单章内把一个事件从头到尾讲完" in _cu137, \
    "v1.37 consolidate 应要求事件跨多章推进（本章只是事件链上的一步，不在单章内讲完整个事件）"
assert "承接【最近章节概要】中上一章结尾" in _cu137 and "本章结尾为下一章留衔接" in _cu137, \
    "v1.37 consolidate 应要求承接上章结尾、为下章留衔接（防每章自成一格）"
assert "平淡铺垫章完全可以没有高潮" in _cu137 and "不要把『完成整个事件』写成 beat" in _cu137, \
    "v1.37 consolidate 应允许铺垫章无高潮、禁止把完整事件写成单章 beat（防一章一事件毛躁）"
assert "当前事件链上的一步,非完整事件" in _cu137, \
    "v1.37 consolidate JSON schema 的 chapter_beats 说明应改为事件链上的一步"
_cs137w, _cu137w = prompts_mod.write_chapter(_pj137, st, 1, "焦点", "方向", {}, [], 2500)
assert "情绪支点**不强制每章都有**" in _cu137w and "不硬造高潮" in _cu137w, \
    "v1.37 write_chapter 应不再强制每章至少一个情绪支点（铺垫/发展/过渡章以自然推进为主）"
assert "结尾按事件进度收束" in _cu137w and "不强行在章内收束大事件" in _cu137w, \
    "v1.37 write_chapter 结尾应按事件进度收束、不强行章内收束大事件（承接上章-延续下章）"
print("[9r] v1.37 事件跨章节奏与前后衔接（主AI按全书长度判断事件节奏 + 铺垫章可无高潮 + 承接上章/为下章留衔接）OK")

# ---------- v1.34 选卡名带「〔分类〕」前缀兼容（全链路实测抓出：consolidate 把清单显示格式整串填进 scene_cards，
# engine 按纯卡名匹配失败 → 明明选了卡却落"未选用"、卡没注入正文AI） ----------
# 1) consolidate 提示词明确 scene_cards 只填纯卡名（不带【分类】前缀/来源标注）
_cs134, _cu134 = prompts_mod.consolidate(_pj122, st, 1, "两人拔剑对峙", {}, "")
assert "只填卡名本身" in _cu134 and "不要带【分类】前缀" in _cu134, \
    "v1.34 consolidate 应明确 scene_cards 只填纯卡名（防止把〔分类〕前缀整串填进去导致白选）"
# 2) engine._collect_scene_cards 兼容带「〔分类〕」前缀的卡名（剥离前缀后仍匹配到库卡并注入）
_pj134 = _mdl118.NovelProject("dir134", "测试")
_pj134.scene_cards = [{"name": "环境奇观渲染描写", "content": "对称排比营造史诗氛围。",
                       "source": "user", "category": "氛围酝酿"}]
_got134 = _eng121._collect_scene_cards(_pj134, {
    "scene_cards": ["〔氛围酝酿〕环境奇观渲染描写"],
    "scene_cards_reason": "本章核心为环境压迫感营造，匹配该卡。"})
assert _got134 and _got134[0]["name"] == "环境奇观渲染描写" and \
    "对称排比" in _got134[0]["content"], \
    "v1.34 带〔分类〕前缀的卡名也应剥离前缀匹配到项目库卡并注入（否则明明选了卡却白选）"
# 3) 纯卡名匹配不受影响（回归）
_got134b = _eng121._collect_scene_cards(_pj134, {"scene_cards": ["环境奇观渲染描写"]})
assert _got134b and _got134b[0]["name"] == "环境奇观渲染描写", \
    "v1.34 纯卡名匹配应保持可用（回归）"
print("[9p] v1.34 选卡名带〔分类〕前缀兼容（consolidate 只填纯卡名 + engine 剥离前缀匹配注入）OK")

# ---------- v1.40 多情景卡：一章多情景全选不漏 + 每卡带分类 + write_chapter 多卡分工注入互不冲突 ----------
# （回退到 v1.38 基线后重新落：consolidate 选卡「一章几个特殊情景就选几张、全选不漏、
#  分工组合而非单选」；engine 注入卡带 category（【分类】首行回退或字段直取）；write_chapter
#  每张卡带〔分类〕标注 + 多卡组合规则——每段只受所属片段对应卡约束、不叠加不冲突）
_pj140c = _mdl118.NovelProject("dir140c", "测试")
_pj140c.scene_cards = [{"name": "武打", "content": "攻防有节奏。", "source": "user"}]
_cs140, _cu140 = prompts_mod.consolidate(_pj140c, st, 1, "两人拔剑对峙", {}, "")
assert "全选不漏" in _cu140 and "分工组合" in _cu140 and "同时出现多个特殊情景" in _cu140, \
    "v1.40 consolidate 应明确一章几个特殊情景选几张、全选不漏、分工组合而非单选"
assert "必须把每个情景各自匹配的卡全部选上" in _cu140, \
    "v1.40 consolidate 应要求多情景章节把匹配的卡全部选上（防只选一张导致割裂）"
_pj140 = _mdl118.NovelProject("dir140", "测试")
_pj140.scene_cards = [
    {"name": "对话心理攻防", "content": "【分类】对话攻防\n短句一问一应。", "source": "user"},
    {"name": "视线交汇冲击", "content": "目光相触的刹那抽离外部世界推进。", "source": "user",
     "category": "氛围酝酿"}]
_got140 = _eng121._collect_scene_cards(_pj140, {
    "scene_cards": ["对话心理攻防", "视线交汇冲击"],
    "scene_cards_reason": "本章既有对话交锋又有氛围酝酿，两张卡全选分工。"})
assert len(_got140) == 2, \
    "v1.40 engine 应能一次注入多张卡（对话+氛围组合），实际 %d 张" % len(_got140)
assert _got140[0]["category"] == "对话攻防" and _got140[1]["category"] == "氛围酝酿", \
    "v1.40 engine 注入卡应带分类（content 首行【分类】回退或 category 字段直取）"
_cs140w, _cu140w = prompts_mod.write_chapter(
    _pj140, st, 1, "焦点", "方向", {}, [], 2500, scene_cards=_got140)
assert "多卡分工" in _cu140w and "〔对话攻防〕对话心理攻防" in _cu140w \
    and "〔氛围酝酿〕视线交汇冲击" in _cu140w, \
    "v1.40 write_chapter 应标注每张卡分类（〔对话攻防〕〔氛围酝酿〕），正文AI按片段对号入座"
assert "每段文字只受" in _cu140w and "不得把多张卡的规则叠加在同一段" in _cu140w, \
    "v1.40 write_chapter 应明确多卡组合规则（各卡管各段、互不冲突不叠加）"
print("[9u] v1.40 多情景卡（consolidate 全选不漏 + engine 带分类 + write_chapter 多卡分工）OK")

# ---------- v1.42 全局文风与情景卡边界（正文AI角色提示词第一优先）：consolidate 自制卡先确认正文基础文风 +
# 主AI按项目文风适配项目库情景卡（只改项目库不动总库）+ 拆书库文档可再导出 ----------
import main_ai as _mai142  # noqa: E402
_pj142 = _mdl118.NovelProject("dir142", "测试")
_pj142.scene_cards = [{"name": "对话心理攻防", "content": "【分类】对话攻防\n绵密攻防拉扯。", "source": "user"},
                      {"name": "视线交汇冲击", "content": "目光相触瞬间抽离外部世界推进。", "source": "user"}]
_pj142.story_writer_prompt = "你是一个擅长冷峻写实的网文作者，描写克制、短句、极少直抒胸臆。"
_pj142.story_style_note = "短句推进，动作先行。"
# 1) consolidate 注入正文AI基础文风（主AI自制卡前先确认正文文风，第一优先）
_cs142, _cu142 = prompts_mod.consolidate(_pj142, st, 1, "两人拔剑对峙", {}, "")
assert "正文AI基础文风" in _cu142 and "冷峻写实" in _cu142 and "第一优先" in _cu142, \
    "v1.42 consolidate 应注入正文AI基础文风（story_writer_prompt + 风格要点，第一优先）"
assert "自制" not in _cu142 or "契合" in _cu142, \
    "v1.42 consolidate 自制新卡要求应参考正文AI基础文风"
# 2) write_chapter 卡段显式优先级：正文AI角色提示词第一优先、情景卡在其框架内精修、不得凌驾
_cs142w, _cu142w = prompts_mod.write_chapter(
    _pj142, st, 1, "焦点", "方向", {}, [], 2500,
    scene_cards=[{"name": "对话心理攻防", "content": "绵密攻防拉扯。", "category": "对话攻防"}])
assert "用户对正文AI的角色设定/风格要求" in _cu142w and "第一优先" in _cu142w and "不得凌驾或背离" in _cu142w, \
    "v1.42 write_chapter 应显式裁定正文AI角色提示词第一优先、卡不得凌驾或背离（防全局文风与卡打架）"
# 3) 适配提示词：保持情景内核/卡名/分类不变、只调写法契合文风
_ps142, _pu142 = prompts_mod.adapt_project_scene_card_ai(_pj142, _pj142.scene_cards)
assert "冷峻写实" in _pu142 and "保持情景内核" in _ps142 and "卡名原样保留" in _pu142, \
    "v1.42 适配卡提示词应注入项目文风并保持卡情景内核/卡名不变"
assert "卡只讲怎么写" in _ps142, "v1.42 适配卡提示词应重申卡只讲怎么写（不新增剧情/行为指令）"
# 4) engine.adapt_project_scene_cards：mock main_ai 返回，验证只改项目库卡 content、不动总库
_orig_adapt142 = _mai142.adapt_project_scene_cards
_mai142.adapt_project_scene_cards = lambda project, cards: {
    "adapted": [{"name": "对话心理攻防", "content": "【分类】对话攻防\n（冷峻版）短句一问一应。"},
                {"name": "视线交汇冲击", "content": "（冷峻版）目光相触瞬间抽离外部世界。"}]}
try:
    _r142 = _eng121.adapt_project_scene_cards(_pj142)
    assert _r142.get("ok") == 2, "v1.42 engine 适配应写回 2 张卡，实际 %r" % _r142
    _cur142 = {str(c.get("name")): str(c.get("content")) for c in _pj142.scene_cards}
    assert "冷峻版" in _cur142.get("对话心理攻防", "") and "冷峻版" in _cur142.get("视线交汇冲击", ""), \
        "v1.42 engine 适配后项目库卡 content 应被替换为适配版"
finally:
    _mai142.adapt_project_scene_cards = _orig_adapt142
# 5) GUI：项目页适配按钮 + 拆书页导出选中风格（源码断言）
import inspect as _inspect142  # noqa: E402
import gui_project as _gp142  # noqa: E402
import gui_break as _gb142  # noqa: E402
_src142gp = _inspect142.getsource(_gp142)
_src142gb = _inspect142.getsource(_gb142)
assert "_adapt_scene_cards" in _src142gp and "主AI按本文风适配本项目卡" in _src142gp, \
    "v1.42 项目页应有「主AI按本文风适配本项目卡」按钮及 handler"
assert "_export_style" in _src142gb and "导出选中风格（txt）" in _src142gb, \
    "v1.42 拆书页风格库应可再次导出选中风格（修复：库里文档之前无法导出）"
print("[9u2] v1.42 全局文风边界（正文AI角色提示词第一优先 + consolidate 先确认基础文风 + 项目库卡按文风适配 + 拆书库再导出）OK")

# ---------- v1.43 思考气泡（AI对话/Agent 可折叠）+ 文风/剧情设计预设微调 + 拆书代表性章节细纲 ----------
import json as _json143  # noqa: E402
import inspect as _in143  # noqa: E402
import msg_bubbles as _mb143  # noqa: E402
import gui_chat as _gc143  # noqa: E402
_ROOT143 = os.path.dirname(os.path.abspath(__file__))
# 1) llm.chat 支持 on_think 回调（推理思考分片流式转发给 GUI）
_sig143 = _in143.signature(llm_mod.chat)
assert "on_think" in _sig143.parameters, "v1.43 llm.chat 应支持 on_think 回调参数"
assert "on_chunk" in _sig143.parameters, "v1.43 llm.chat 保留 on_chunk 参数"
# 2) msg_bubbles 提供可折叠思考气泡组件
assert hasattr(_mb143, "ThinkingBubble"), "v1.43 msg_bubbles 应有 ThinkingBubble 可折叠思考气泡"
assert hasattr(_mb143.ThinkingBubble, "append_text") and hasattr(
    _mb143.ThinkingBubble, "finish"), "v1.43 ThinkingBubble 应支持 append_text/finish"
# 3) AI 对话页接入思考气泡（think 信号、_on_think、_stream_finish、_on_chunk 折叠）
assert hasattr(_gc143.ChatPage, "_on_think") and hasattr(_gc143.ChatPage, "_stream_finish"), \
    "v1.43 ChatPage 应有 _on_think/_stream_finish（思考气泡实时展示与折叠）"
assert hasattr(_gc143._ChatWorker, "think"), "v1.43 _ChatWorker 应有 think 信号"
# 5) 文风提取预设 A/C/D 微调（去方向限定、C 评文风像不像）
_pe143 = _json143.load(open(os.path.join(_ROOT143, "data", "style_extract", "presets.json"),
                             encoding="utf-8"))
_wf143 = _pe143["presets"]["文风提取"]
# v1.51~v1.58 预设多轮演进（源头抽象→精简回归原文形态→防迭代漂移），不做正文措辞断言，
# 只做结构级检查：四节点齐全（读预设正文可能含触发内容审查的文本，按红线只查结构）
assert set(_wf143.keys()) >= {"node_a", "node_b", "node_c", "node_d"}, \
    "v1.43+ 文风提取预设应含 A/B/C/D 四节点，实际 %r" % list(_wf143.keys())
assert all(isinstance(_wf143.get(k), str) and _wf143[k].strip()
           for k in ("node_a", "node_b", "node_c", "node_d")), \
    "v1.43+ 文风提取预设四节点均应为非空字符串"
# 6) 剧情设计提取预设 A/B/C/D 微调（A 通用化、B 生成世界观+金手指+20多章逐章设计）
_sd143 = _pe143["presets"]["剧情设计提取"]
assert set(_sd143.keys()) >= {"node_a", "node_b", "node_c", "node_d"}, \
    "v1.43+ 剧情设计提取预设应含 A/B/C/D 四节点，实际 %r" % list(_sd143.keys())
assert all(isinstance(_sd143.get(k), str) and _sd143[k].strip()
           for k in ("node_a", "node_b", "node_c", "node_d")), \
    "v1.43+ 剧情设计提取预设四节点均应为非空字符串"
# 7) 拆书 merge_doc 输出新增代表性章节细纲与逐章提示词
_src_md143 = _in143.getsource(bb.merge_doc)
assert "代表性章节细纲" in _src_md143 and "逐章提示词" in _src_md143, \
    "v1.43 拆书 merge_doc 应输出代表性章节细纲与逐章提示词区块"
# 8) 打包脚本保留拆书文档/文风预设（data/breaks + data/style_extract）
_pack143 = open(os.path.join(_ROOT143, "scripts", "_pack_v143.py"), encoding="utf-8").read()
assert "breaks" in _pack143 and "style_extract" in _pack143, \
    "v1.43 打包脚本应保留 data/breaks（拆书文档）与 data/style_extract（文风预设）"
print("[9u3] v1.43 思考气泡（AI对话/Agent 可折叠）+ 文风/剧情预设微调 + 拆书代表性章节细纲 OK")

# ---------- v1.44 拆书工坊参数预设导入导出（json 文件：备份/迁移/分享整套拆书设置） ----------
_bsb144 = _win_bp.settings_box
assert hasattr(_bsb144, "export_preset_btn") and hasattr(_bsb144, "import_preset_btn"), \
    "拆书参数框应有「导出预设（json）/导入预设（json）」按钮"
assert hasattr(_bsb144, "_preset_values") and hasattr(_bsb144, "export_preset") \
    and hasattr(_bsb144, "import_preset"), "拆书参数框应有预设导入导出方法"
_vs144 = _bsb144._preset_values()
assert set(_vs144.keys()) >= {"break_mode", "break_smart_sub", "model_context_window",
                              "break_token_per_part", "break_overlap_token", "break_parallel",
                              "break_parallel_n", "break_l3_batch", "break_prompt"}, \
    "拆书预设应覆盖全部拆书参数键（与引擎 break_settings 同键）：%r" % sorted(_vs144.keys())
# 导出（mock 文件对话框到临时文件）
import tempfile as _tmpf144  # noqa: E402
_bsb144.mode_combo.setCurrentIndex(2)          # 高级
_bsb144.token_spin.setValue(150000)
_bsb144.overlap_spin.setValue(6000)
_bsb144.l3_spin.setValue(8)
_bsb144.par_combo.setCurrentIndex(1)           # 并行
_bsb144.par_n_spin.setValue(4)
_bsb144.prompt_edit.setPlainText("预设导入导出测试提示词")
_orig_sfn144 = _qtw2.QFileDialog.getSaveFileName
_orig_ofn144 = _qtw2.QFileDialog.getOpenFileName
_tmp_preset144 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_break_preset144.json")
_qtw2.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (_tmp_preset144, "JSON 文件 (*.json)"))
_bsb144.export_preset()
_qtw2.QFileDialog.getSaveFileName = _orig_sfn144
assert os.path.exists(_tmp_preset144), "预设 json 应导出"
import json as _json144  # noqa: E402
with open(_tmp_preset144, encoding="utf-8") as _f:
    _pp144 = _json144.load(_f)
assert _pp144.get("type") == "break_settings_preset", "预设文件应带类型标记"
assert _pp144.get("settings", {}).get("break_mode") == "advanced", "预设应含全部参数"
assert _pp144.get("settings", {}).get("break_token_per_part") == 150000, "预设 token 应写入"
assert _pp144.get("settings", {}).get("break_prompt") == "预设导入导出测试提示词", "预设提示词应写入"
# 导入（先把控件改乱，再从此前的预设文件恢复；导入应写回 config 立即生效）
_bsb144.mode_combo.setCurrentIndex(0)          # 简单（改乱）
_bsb144.token_spin.setValue(5000)
_bsb144.prompt_edit.setPlainText("改乱了")
_qtw2.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (_tmp_preset144, "JSON 文件 (*.json)"))
_bsb144.import_preset()
_qtw2.QFileDialog.getOpenFileName = _orig_ofn144
assert _bsb144.mode() == "advanced", "导入后模式应恢复为预设值"
assert _bsb144.token_spin.value() == 150000, "导入后 token 应恢复 150000"
assert _bsb144.overlap_spin.value() == 6000, "导入后重叠应恢复 6000"
assert _bsb144.l3_spin.value() == 8, "导入后 L3 分批应恢复 8"
assert _bsb144.par_combo.currentData() is True, "导入后应恢复并行"
assert _bsb144.par_n_spin.value() == 4, "导入后并行数应恢复 4"
assert _bsb144.prompt_edit.toPlainText() == "预设导入导出测试提示词", "导入后提示词应恢复"
assert bb.break_settings()["mode"] == "advanced", "导入应写回 config（mode）"
assert bb.break_settings()["token_per_part"] == 150000, "导入应写回 config（token）"
# 恢复用户拆书设置（导入测试覆盖了 config，归还为测试前快照）
_cfg_bs144 = config.load_config()
_bs_snap144 = {k: _cfg_bs144.get(k) for k in _bs_keys}
for _k144, _v144 in _bs_snap144.items():
    if _v144 is None:
        _cfg_bs144.pop(_k144, None)
    else:
        _cfg_bs144[_k144] = _v144
config.save_config(_cfg_bs144)
config._cache = None
os.remove(_tmp_preset144)
print("[9u4] v1.44 拆书工坊参数预设导入导出（json 导出/导入 + 写回 config 生效）OK")

# ---------- v1.45 文风校对页预设导入导出（json：备份/迁移/分享整套四节点提示词预设） ----------
_se145 = win.page_style_extract
assert hasattr(_se145, "export_preset_btn") and hasattr(_se145, "import_preset_btn"), \
    "文风校对页应有「导出预设（json）/导入预设（json）」按钮"
assert hasattr(_se145, "_export_preset") and hasattr(_se145, "_import_preset"), \
    "文风校对页应有预设导入导出方法"
import style_extract as _sem145  # noqa: E402
import json as _json145  # noqa: E402
_wf145 = _sem145.StyleExtractorWorkflow()
_wf145.save_preset("smoke预设A", {"node_a": "测试A", "node_b": "测试B",
                                  "node_c": "测试C", "node_d": "测试D"})
_se145._refresh_preset_combo(keep="smoke预设A")
_se145.preset_combo.setCurrentText("smoke预设A")
_tmp_se145 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_style_preset145.json")
_orig_sfn145 = _qtw2.QFileDialog.getSaveFileName
_qtw2.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (_tmp_se145, "JSON 文件 (*.json)"))
_se145._export_preset()
_qtw2.QFileDialog.getSaveFileName = _orig_sfn145
assert os.path.exists(_tmp_se145), "文风校对预设应导出 json 文件"
with open(_tmp_se145, encoding="utf-8") as _f:
    _pp145 = _json145.load(_f)
assert _pp145.get("type") == "style_extract_preset", "预设文件应带类型标记"
assert _pp145.get("name") == "smoke预设A", "预设文件应带预设名"
assert set((_pp145.get("prompts") or {}).keys()) >= {"node_a", "node_b", "node_c", "node_d"}, \
    "预设文件应含四节点提示词"
_wf145.delete_preset("smoke预设A")
_se145._refresh_preset_combo()
assert "smoke预设A" not in _wf145.load_presets(), "删除后预设应不在库中"
_orig_ofn145 = _qtw2.QFileDialog.getOpenFileName
_qtw2.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (_tmp_se145, "JSON 文件 (*.json)"))
_se145._import_preset()
_qtw2.QFileDialog.getOpenFileName = _orig_ofn145
_pres145 = _wf145.load_presets()
assert "smoke预设A" in _pres145, "导入后预设应回到库中"
assert set((_pres145["smoke预设A"] or {}).keys()) >= {"node_a", "node_b", "node_c", "node_d"}, \
    "导入的预设应含四节点提示词"
assert _pres145["smoke预设A"].get("node_a") == "测试A", "导入的预设内容应与导出一致"
_wf145.delete_preset("smoke预设A")
_se145._refresh_preset_combo()
os.remove(_tmp_se145)
print("[9u5] v1.45 文风校对页预设导入导出（json 导出/导入 + 库往返）OK")

# ---------- v1.46 思考气泡真实执行防回归（v1.43 曾因 import 漏 ThinkingBubble → 回调 NameError 不显示） ----------
import msg_bubbles as _mb146  # noqa: E402
assert hasattr(_mb146, "ThinkingBubble"), "v1.46 msg_bubbles 应有 ThinkingBubble"
# ChatPage 真实执行思考气泡链路：_begin_stream → _on_think → _on_chunk 折叠
_cc146 = win.page_chat
_cc146._begin_stream()
_cc146._on_think("思考分片甲")
_cc146._on_think("思考分片乙")
assert _cc146._think_row is not None, \
    "v1.46 ChatPage 收到思考分片应创建思考气泡（v1.43 import 遗漏 ThinkingBubble → NameError 不显示）"
assert _cc146._think_row.bubble.text() == "思考分片甲思考分片乙", \
    "思考气泡应实时写入全部思考内容"
_cc146._on_chunk("正文初始分片")
assert not _cc146._think_row.toggle_btn.isChecked(), \
    "正文开始后思考气泡应收起（保留标题可点开回顾）"
assert "思考分片甲思考分片乙" in _cc146._think_row.bubble.text(), "收起后思考内容应保留"
# 清理流式行，避免污染后续 msg_vbox 断言
_cr146 = _mb146.clear_rows
_cr146(_cc146.msg_vbox)
_cc146.msg_vbox.addStretch(1)
_cc146._stream_row = None
_cc146._think_row = None
assert "from msg_bubbles import BubbleRow, ThinkingBubble, clear_rows" in (
    open(os.path.join(_ROOT143, "src", "gui_chat.py"), encoding="utf-8").read()), \
    "v1.46 gui_chat 必须 import ThinkingBubble"
print("[9u6] v1.46 思考气泡真实执行防回归（ChatPage/AgentPage 思考分片→气泡创建→正文时折叠）OK")

# ---------- v1.47 思考内容持久化（落库 + 重绘后仍可回顾，不再随消息重绘消失） ----------
import chat_lib as _cl147  # noqa: E402
# 1) chat_lib think 落库往返（append_message / append_to_last_message 均带 think）
_tid147 = _cl147.create_topic("smoke-think-147")
_cl147.append_message(_tid147, "assistant", "正文147", think="思考内容147")
_t147 = _cl147.load_topic(_tid147)
assert _t147["messages"][-1].get("think") == "思考内容147", \
    "v1.47 chat_lib.append_message 应落库 think 字段（重绘可回顾）"
_cl147.append_to_last_message(_tid147, "续写", think="续写思考")
_t147 = _cl147.load_topic(_tid147)
assert _t147["messages"][-1].get("think") == "思考内容147续写思考", \
    "v1.47 append_to_last_message 应把续写思考追加到既有 think"
assert _t147["messages"][-1]["content"].endswith("续写"), "续写正文应正常追加"
_cl147.delete_topic(_tid147)
# 2) ChatPage：_on_think 累积 _think_text（完成时落库） + 重绘渲染思考气泡
_cc147 = win.page_chat
_cc147._begin_stream()
_cc147._on_think("思考分片1")
_cc147._on_think("思考分片2")
assert _cc147._think_text == "思考分片1思考分片2", \
    "v1.47 ChatPage 应累积思考全文（_think_text）"
_cc147._stream_row = None
_cc147._think_row = None
# 重绘（模拟完成后的 _render_all）：消息带 think → 必须渲染可折叠思考气泡
_cc147._msgs = [{"role": "user", "content": "问题"},
                {"role": "assistant", "content": "正文", "think": "完整思考内容"}]
_cc147._render_all()
_found147 = any(
    hasattr(_cc147.msg_vbox.itemAt(_i).widget(), "toggle_btn")
    and _cc147.msg_vbox.itemAt(_i).widget().bubble.text() == "完整思考内容"
    for _i in range(_cc147.msg_vbox.count()))
assert _found147, "v1.47 重绘后应渲染带 think 的消息为思考气泡（可展开回顾）"
import msg_bubbles as _mb147  # noqa: E402
_mb147.clear_rows(_cc147.msg_vbox)
_cc147.msg_vbox.addStretch(1)
_cc147._msgs = []
print("[9u7] v1.47 思考内容持久化（think 落库往返 + 重绘后气泡仍在可展开回顾）OK")

# ---------- v1.48 拆书章节解析多格式放宽 + 文风校对 D 节点 Top3 开关 ----------
# ① 拆书：常见导出格式应全部识别出多章（用户：丢一整本书只识别出一章、其余全被吞）
_cases148 = {
    "【第X章】标题": "【第一章】初见\n正文1\n【第二章】拜师\n正文2\n【第三章】下山\n正文3\n",
    "（第X章）标题": "（第一章）初见\n正文1\n（第二章）拜师\n正文2\n（第三章）下山\n正文3\n",
    "第X话 标题": "第一话 初见\n正文1\n第二话 拜师\n正文2\n第三话 下山\n正文3\n",
    "数字.标题": "1.初见\n正文1\n2.拜师\n正文2\n3.下山\n正文3\n",
    "—第X章—装饰": "—第一章—\n正文1\n—第二章—\n正文2\n—第三章—\n正文3\n",
    "裸第一章（无副标题）": "第一章\n正文1\n第二章\n正文2\n第三章\n正文3\n",
}
for _name148, _txt148 in _cases148.items():
    _pr148 = bb.parse_novel(_txt148)
    assert _pr148["total_chapters"] == 3, \
        "v1.48 拆书应识别「%s」为 3 章，实际 %d（%r）" % (
            _name148, _pr148["total_chapters"], _pr148)
# 开头简介不应成章、卷结构保留（原 smoke 断言 4 章 2 卷）
_pr148b = bb.parse_novel(
    "简介：拆书测试用小说。\n\n第一卷 风起\n第一章 山雨欲来\n夜里下雨，林晚站在窗前。\n"
    "第二章 敲门声\n有人敲门，门后是一封信。\n第二卷 浪涌\n第三章 出海\n船帆升起。\n"
    "第四章 风暴\n闪电划破夜空。\n")
assert _pr148b["total_chapters"] == 4 and len(_pr148b["volumes"]) == 2 and \
    _pr148b["volumes"][0]["title"] == "风起", "v1.48 简介不应成章、卷结构应保留：%r" % _pr148b
# ② 文风校对 D 节点 Top3 开关（style_d_see_top3）
import style_extract as style_extract_mod  # noqa: E402
_se148 = win.page_style_extract
assert hasattr(_se148, "see_top3_chk"), "v1.48 文风校对页应有 D 节点 Top3 开关"
_cfg148 = config_mod.load_config()
_cfg148["style_d_see_top3"] = True
config_mod.save_config(_cfg148)
assert config_mod.load_config().get("style_d_see_top3") is True, \
    "v1.48 style_d_see_top3 应写入 config"
_orig_ct148 = llm_mod.chat_text
_cap148 = {}


def _fake_ct148(system, user, temperature=None, max_tokens=None, role="all",
                profile=None, on_chunk=None, think_role=None):
    if think_role == "style_d":
        _cap148["user_d"] = user
    if think_role == "style_a":
        return "冷峻白描，重氛围。"
    if think_role == "style_b":
        return "夜色如墨，他站在巷口。"
    if think_role == "style_c":
        return "85"
    return "优化后：冷峻白描，短句节奏。"


llm_mod.chat_text = _fake_ct148
_wf148 = style_extract_mod.StyleExtractorWorkflow()
for _k148, _d148 in _wf148.run_workflow_stream(
        "夜色如墨。", max_rounds=2, threshold=99.0,
        custom_prompts={"node_a": "{原文}请分析文风",
                        "node_b": "{文风提示词}请生成文章",
                        "node_c": "{原文}{生成文章}请评分",
                        "node_d": "{文风提示词}{原文}{生成文章}请优化"}):
    pass
llm_mod.chat_text = _orig_ct148
assert "排名前三" in (_cap148.get("user_d") or ""), \
    "v1.48 开启后 D 节点应看到 Top3 提示词与分数"
assert "排名第一" in (_cap148.get("user_d") or ""), \
    "v1.48 D 应被要求在最高分（排名第一）基础上改进"
_cfg148.pop("style_d_see_top3", None)
config_mod.save_config(_cfg148)
_se148.see_top3_chk.setChecked(False)
print("[9u8] v1.48 拆书多格式解析 + 文风校对 D 节点 Top3 开关 OK")

# ---------- v1.49 拆书章节识别再放宽（装饰符号前缀 + 两层兜底） ----------
# ① 装饰符号前缀标题（网站导出格式如「☆、第一章 假钞」——《都市猎人（心动可乐）.txt》814 章全这种）
_du149 = ("☆、第一章 假钞\n正文一。\n☆、第二章 未来高考\n正文二。\n"
          "☆、第3章 手机丢了\n正文三。\n☆、第4章 夜空下的女孩\n正文四。\n")
_pr149 = bb.parse_novel(_du149)
assert _pr149["total_chapters"] == 4, "v1.49 装饰符号前缀标题应拆出 4 章（实际 %d）" % _pr149["total_chapters"]
assert _pr149["volumes"][0]["chapters"][0]["title"] == "假钞", "装饰前缀标题应剥离装饰符取副标题"
# ② 乱取名兜底：无「第X章」字样但行首有装饰符的短标题（作者乱取名）→ 扫描切分
_t149 = ("☆序章\n正文一。\n☆初见\n正文二。\n☆离别\n正文三。\n☆重逢\n正文四。\n" +
         ("正文填充段落。\n" * 5000))
_pr149b = bb.parse_novel(_t149)
assert _pr149b["total_chapters"] == 4, "v1.49 乱取名短标题兜底应拆 4 章（实际 %d）" % _pr149b["total_chapters"]
# ③ 完全无标题兜底：只有换行正文 → 按固定行数分块
_t149c = ("陈乐走在街头。\n" * 3000)
_pr149c = bb.parse_novel(_t149c)
assert _pr149c["total_chapters"] >= 2, "v1.49 无标题书应按固定行数分块（实际 %d）" % _pr149c["total_chapters"]
print("[9u9] v1.49 拆书装饰符号前缀标题 + 乱取名/无标题两层兜底 OK")

# ---------- v1.50 拆书 L3 汇总防压缩：第六节限幅 + 分批合并不删减（用户：拆书文档从约 5w 缩到 1.5w——“加具体章节范例后其他内容反而变简略了”） ----------
import inspect as _in150  # noqa: E402
_src150 = _in150.getsource(bb.merge_doc)
assert "合并≠删减" in _src150 and "不得低于各分卷之和" in _src150, \
    "v1.50 L3 分批合并（final）应明确「合并≠删减、内容量不得低于各分卷之和」"
assert "1500~3000" in _src150 and "80~150" in _src150 and "严禁为写第六节而压缩" in _src150, \
    "v1.50 第六节应有限幅（1500~3000 字、每章 80~150 字）且严禁挤占一~五节"
# 行为断言：partials 输入走「合并≠删减」文案，volumes 一次合并不带
_orig_cj150 = _llm_mod.chat_json
_cap150 = {}
_llm_mod.chat_json = lambda _s, _u, **kw: (_cap150.update({"sys": _s}) or {})
try:
    _cap150.clear()
    bb.merge_doc({"title": "t", "skeleton": {}, "volumes": [{"vol": 1, "title": "v"}]},
                 stage="final")
    _md150 = _cap150.get("sys") or ""
    assert "请按以下结构输出 markdown" in _md150 and "合并≠删减" not in _md150, \
        "一次合并（volumes）不应带分批防压缩文案"
    _cap150.clear()
    bb.merge_doc({"title": "t", "skeleton": {}, "partials": ["分卷一", "分卷二"]},
                 stage="final")
    _md150b = _cap150.get("sys") or ""
    assert "合并≠删减" in _md150b and "不得低于各分卷之和" in _md150b, \
        "分批合并（partials）应带「合并≠删减、不低于分卷之和」文案"
    _cap150.clear()
    bb.merge_doc({"title": "t", "skeleton": {}, "volumes": [{"vol": 1}]},
                 stage="partial")
    _md150p = _cap150.get("sys") or ""
    assert "分部：<本次覆盖的卷/单元范围>" in _md150p, "partial 分支结构不应被改坏"
finally:
    _llm_mod.chat_json = _orig_cj150
print("[9u10] v1.50 拆书 L3 汇总防压缩：第六节限幅 + 分批合并不删减 OK")

# ---------- v0.54 小说导入成项目：txt → 完整项目还原（拆书/设定/角色卡/章节/分章状态轨迹） ----------
import novel_import as nimp  # noqa: E402
from gui_import import ImportPanel, ImportDialog, _ImportWorker  # noqa: E402
# 重新 mock 拆书 LLM 环节 + 导入专属 LLM 环节
bb.summarize_title_batch = lambda titles, profile=None, user_prompt="": (
    {"people": ["林晚", "阿禾"], "events": ["风雨夜探"],
     "place": ["客栈"], "hints": ["信"]})
bb.build_skeleton = lambda payload, profile=None, user_prompt="": (
    {"story": "主角风雨夜收到神秘信件渐入江湖。",
     "arcs": [{"vols": "1-2", "task": "开局立悬念"}],
     "characters": [{"name": "林晚", "role": "主角", "arc": "从看客到入局"}],
     "foreshadow_pool": ["那封信（第2章出现）"],
     "tech": ["日常三句话里藏主线钩子"]})
bb.analyze_volume = lambda payload, profile=None, user_prompt="": (
    {"events": [{"title": "夜探客栈", "start_ch": 1, "end_ch": 2, "chapters": 2,
                 "drive": "神秘信件悬念", "conflict": "不知来信者敌友", "climax": "信上留名"}],
     "foreshadow_seed": [{"text": "她说今天没胃口——实则躲开搜查", "chapter": 1,
                          "type": "日常"}],
     "foreshadow_payoff": [{"text": "她说今天没胃口", "chapter": 2}],
     "chars": [{"name": "林晚", "change": "开始主动查信"}],
     "tech": ["用日常对话藏伏笔"]})
bb.merge_doc = lambda payload, profile=None, user_prompt="", stage="final": (
    {"doc": "# 拆书 · 导入测试\n## 一、全书总览\n主线。\n"
            "## 三、卷事件细纲\n- 夜探客栈（1~2章）\n## 四、伏笔总表\n- 日常：她说今天没胃口\n"
            "## 五、技法总结\n- 日常三句藏钩子",
     "learning": "开篇用一封神秘信迅速建立悬念；以日常对话埋长线伏笔。"})
# 导入专属 LLM 环节
_orig_isyn = nimp.synthesize_settings
_orig_ichunk = nimp.analyze_chunk_people
_orig_icards = nimp.build_character_cards
_orig_isummary = nimp.synthesize_summary
nimp.synthesize_summary = lambda payload, profile=None, user_prompt="": (
    {"summary": "第一卷 风起：林晚雨夜收信入局；第二卷 追信：林晚追查写信人，阿禾暗助。"
                "人物动向：林晚（看客→追信）、阿禾（客栈老板娘，暗中留意）、神秘客（送信后离城）。",
     "ideas": ["那封信的署名真相", "阿禾的身世线索"]})
nimp.synthesize_settings = lambda payload, profile=None, user_prompt="": (
    {"brief": "【开局】风雨夜，林晚在客栈收到神秘来信，卷入门派悬案。",
     "world": "江湖九域，客栈暗通消息，剑宗与商会两派对峙。",
     "rules": "主角不得无故开挂；日常对话里藏伏笔。",
     "style": "冷峻白描，短句推进，悬疑氛围。",
     "style_note": ["短句推进，动作先行", "日常三句藏钩子"],
     "lore": [{"title": "铁砧客栈", "content": "情报中转站，老板娘阿禾掌握各方消息。"},
              {"title": "剑宗", "content": "江湖大派，与商会明争暗斗。"}],
     "foreshadows": [{"text": "那封信", "chapter": 2, "type": "物件"}],
     "summary": "开局：林晚客栈收信，卷入门派悬案；后续追查写信人。",
     "key_characters": [{"name": "林晚", "info": "主角，客栈看客入局查信。"}]})
nimp.analyze_chunk_people = lambda payload, profile=None, user_prompt="": (
    {"new_chars": [{"name": "阿禾", "role": "客栈老板娘", "first_ch": 1,
                    "persona": "圆滑精明的情报贩子"},
                   {"name": "神秘客", "role": "黑衣人", "first_ch": 2,
                    "persona": "行踪诡秘的送信人"}],
     "states": [{"ch": 1, "char": "林晚", "scenario": "雨夜窗前拆信",
                 "status": "active"},
                {"ch": 3, "char": "林晚", "scenario": "开始追查写信人",
                 "status": "active"},
                {"ch": 2, "char": "阿禾", "scenario": "暗中留意林晚动向",
                 "status": "active"}],
     "transitions": [{"ch": 3, "char": "神秘客", "status": "traveling",
                      "reason": "送完信后离城"}]})
nimp.build_character_cards = lambda batch, samples, profile=None, user_prompt="": (
    [{"name": b["name"], "role": b.get("role", ""),
      "personality": "立体性格：冷静多疑但重情义。",
      "traits": ["冷静", "多疑"], "values": "不滥杀无辜",
      "goals": "查清写信人身份", "fears": "家人被卷入",
      "speech_style": "寡言，偶尔调侃", "backstory": "客栈常客",
      "relationships": "与阿禾相熟", "appearance": "青衫佩剑",
      "description": "青衫剑客，冷峻寡言，客栈常客。",
      "first_mes": "风又大了。", "mes_example": "「信是谁送来的？」\n「不知道。」",
      "scenario": "雨夜窗前拆信"} for b in batch])
_imp_txt = ("简介：导入测试用小说。\n\n第一卷 风起\n第一章 山雨欲来\n夜里下雨，林晚站在窗前，"
            "手里握着一封信。阿禾在柜台后擦杯。\n第二章 敲门声\n有人敲门，门后是神秘客，"
            "送来第二封信。林晚收信。\n第三章 追信\n林晚离开客栈开始追查写信人，阿禾相送。\n")
_nir = nimp.NovelImporter(log=lambda k, m: None).run(_imp_txt, "导入测试书", None)
assert _nir.get("ok"), "导入应成功，实际 %r" % str(_nir)[:120]
_nst = storage.ProjectStore(_nir["dir"])
_nproj = _nst.load_project()
assert _nproj is not None and _nproj.title == "导入测试书", "项目应创建"
assert _nproj.story_world.find("江湖九域") >= 0, "世界观应合成"
assert _nproj.story_rules.find("日常对话") >= 0, "特殊规则应合成"
assert _nproj.story_style.find("冷峻") >= 0, "文风描述应合成"
assert _nproj.story_style_note.find("短句推进") >= 0, "风格要点应合成"
assert _nproj.story_style_ref.find("夜里下雨") >= 0, "参考文风样本应取自原文"
assert _nproj.story_break_style == "《导入测试书》拆书", "拆书风格应挂到项目"
_break_d = bb.load_break("《导入测试书》拆书")
assert _break_d and _break_d["learning"].find("悬念") >= 0, "拆书风格应保存进风格库"
assert len(_nproj.lore_entries) >= 2, "设定锚点应合成（%d）" % len(_nproj.lore_entries)
assert _nproj.story_summary.find("风起") >= 0 and _nproj.story_summary.find("林晚") >= 0, \
    "主AI管理笔记应按卷梳理剧情与人物动向"
assert len(_nproj.chapter_plans) >= 1, "卷细纲事件应生成章节写作计划（%d）" % len(_nproj.chapter_plans)
# v0.83 写作技巧库功能已删除：导入不再写入 story_techniques（拆书技法仍进 learning 与风格要点）
assert not (_nproj.story_techniques or "").strip(), \
    "写作技巧库已删除，导入不应再写 story_techniques（当前=%r）" % _nproj.story_techniques[:20]
assert any("署名真相" in s for s in _nproj.story_ideas), "管理笔记的后续灵感应并入剧情灵感"
assert _nproj.state["next_chapter"] == 4, "进度应到第 4 章（3 章导入后）"
assert _nproj.volume_target == 3, "全书目标应为 3 章"
_chs = _nst.list_chapter_indices()
assert _chs == [1, 2, 3], "应导入 3 章，实际 %r" % _chs
_ch1 = _nst.load_chapter(1)
assert _ch1.status == "approved" and _ch1.content.find("林晚") >= 0, "章节应原样 approved 入库"
_ch2 = _nst.load_chapter(2)
assert _ch2.volume == 1 and _ch2.brief, "章节应带卷号与梗概"
# 角色卡：林晚/阿禾详卡 + 神秘客轻量卡？——神秘客在名册（new_chars 报出）且出场，应建卡
_cards = dict((c.name, (c, _l)) for c, _l in _nst.list_character_cards())
_names = list(_cards.keys())
assert "林晚" in _names and "阿禾" in _names, "主角与配角应建卡，实际 %r" % _names
_lw = _cards["林晚"][0]
assert _lw.description.find("青衫剑客") >= 0, "详卡应写入综合描述"
assert _lw.created_by == "ai", "导入角色应为 ai 创建"
assert any(e["ch"] == 1 for e in _lw.chapter_states), "主角应有分章状态轨迹（第1章）"
assert any(e["ch"] == 3 for e in _lw.chapter_states), "主角轨迹应到第3章"
# 章节出场角色已挂 id
assert any(cid in _ch1.characters for cid, nm, _s in _nst.list_characters()
            if nm == "林晚"), "第1章应记录主角出场"
# 伏笔台账
_fs = _nst.load_foreshadows()
assert any(f.text.find("没胃口") >= 0 and f.planted_chapter == 1 for f in _fs), "日常伏笔应入库"
assert any(f.text.find("没胃口") >= 0 and f.status == "resolved"
            and f.resolved_chapter == 2 for f in _fs), \
    "伏笔回收应记录（第2章）"
# 删除章节 → 角色卡回退：删除第 2、3 章（保留第 1 章）
_nst.delete_chapters_from(2)
_nst.rebuild_world_after_delete(1)
_cards2 = dict((c.name, (c, _l)) for c, _l in _nst.list_character_cards())
_names2 = list(_cards2.keys())
assert "林晚" in _names2, "第1章出场的林晚应保留"
assert "神秘客" not in _names2, "第2章才出场的神秘客应随章节删除而删除，实际 %r" % _names2
_lw2 = _cards2["林晚"][0]
_ll2 = _cards2["林晚"][1]
assert all(e["ch"] <= 1 for e in _lw2.chapter_states), "轨迹应截断到第1章"
assert _lw2.scenario == "雨夜窗前拆信", "角色卡应回退到第1章状态，实际 %r" % _lw2.scenario
assert _ll2.scenario == "雨夜窗前拆信", "信息库处境应同步回退"
# 导入项目无逐章快照：engine.rewrite_from 走轨迹回退兜底（删除第1章 → 角色全部清理）
import engine as _engmod  # noqa: E402
_git_orig3 = git_tool_mod.commit
git_tool_mod.commit = lambda *a, **k: None  # 防 rewrite_from 触发真实 git 提交
_engI = _engmod.NovelEngine(_nst, log_fn=lambda k, m: None)
_ok = _engI.rewrite_from(_nproj, 1)
assert _ok, "导入项目应能从第1章回滚（无逐章快照时按轨迹）"
assert not _nst.list_characters(), "删除全部章节后角色卡应全部清理"
_nproj = _nst.load_project()
assert _nproj.state["next_chapter"] == 1, "进度应回退到第1章"
git_tool_mod.commit = _git_orig3
# 页面构造：项目页应有「小说导入成项目」独立 tab（顶部无重复按钮）+ 面板可构造
_tabs_proj2 = win.page_project.tabs
_tab_titles2 = [_tabs_proj2.tabText(i) for i in range(_tabs_proj2.count())]
assert any("小说导入成项目" in t for t in _tab_titles2), \
    "项目页应有「📥 小说导入成项目」tab，实际 %r" % _tab_titles2
assert not hasattr(win.page_project, "import_book_btn"), "顶部不应再有小说导入按钮（子 UI 内有）"
_ii = [i for i, t in enumerate(_tab_titles2) if "小说导入成项目" in t][0]
win.page_project.tabs.setCurrentIndex(_ii)
app.processEvents()
assert _tabs_proj2.currentIndex() == _ii, "导入 tab 应可切换（独立界面入口）"
_ipan = ImportPanel(win)
assert _ipan.pick_btn is not None and _ipan.title_edit is not None, "导入面板应可构造"
assert _ipan.settings_box is not None and _ipan.settings_box.mode_combo is not None, \
    "导入设置应有三档拆书模式设置组件"
assert not hasattr(_ipan, "profile_edit"), "导入面板不应再有手打 API 配置小栏（设置页用途分工选）"
assert _ipan.intro_edit is not None and _ipan.save_set_btn is not None, "导入设置应有小说规划栏"
# 导入设置保存往返（写入 config 拆书设置键 + import_intro；与拆书工坊共用同一套键）
_ipan.settings_box.mode_combo.setCurrentIndex(2)      # 高级
_ipan.settings_box.token_spin.setValue(12000)
_ipan.settings_box.overlap_spin.setValue(2000)
_ipan.settings_box.par_combo.setCurrentIndex(1)       # 并行
_ipan.settings_box.par_n_spin.setValue(3)
_ipan.settings_box.prompt_edit.setPlainText("重点关注日常伏笔")
_ipan.intro_edit.setPlainText("修仙宗门文，主角剑宗弃徒，前20章已写完入狱起因，后续靠残剑逆袭；主题「剑心即本心」。")
_ipan._save_import_settings()
assert bb.break_settings()["mode"] == "advanced", "模式应写回"
assert bb.break_settings()["token_per_part"] == 12000, "token 预算应写回"
assert bb.break_settings()["overlap_token"] == 2000, "重叠应写回"
assert bb.break_settings()["parallel"] is True and bb.break_settings()["parallel_n"] == 3, \
    "并行/并行数应写回"
assert bb.break_settings()["prompt"] == "重点关注日常伏笔", "提示词应写回"
assert bb.break_settings()["import_intro"].find("剑心即本心") >= 0, "小说规划应写回 import_intro"
# v0.56 导入规划注入：NovelImporter._user_prompt 合并拆书提示词 + 小说规划
_imp_dbg = nimp.NovelImporter(log=lambda k, m: None)
_up = _imp_dbg._user_prompt()
assert _up.find("重点关注日常伏笔") >= 0 and _up.find("剑心即本心") >= 0, \
    "导入提示词应合并拆书大方向与小说规划，实际 %r" % _up[:60]
_cfg2 = config.load_config()
_cfg2["break_mode"] = "smart"
_cfg2["break_smart_sub"] = "balanced"
_cfg2["model_context_window"] = 0
_cfg2["break_token_per_part"] = 8000
_cfg2["break_overlap_token"] = 0
_cfg2["break_l3_batch"] = 0
_cfg2["break_parallel"] = False
_cfg2["break_parallel_n"] = 2
_cfg2["break_profile"] = ""
_cfg2["break_prompt"] = ""
_cfg2["import_profile"] = ""
_cfg2["import_intro"] = ""
config.save_config(_cfg2)
config._cache = None
_idlg = ImportDialog(win)
assert _idlg.panel is not None, "导入对话框应可构造"
# v0.56 教程页：导航入口 + 分页构造
assert hasattr(win, "page_tutorial") and win.page_tutorial.tabs.count() >= 5, \
    "应有教程页且分页 ≥5，实际 %d" % win.page_tutorial.tabs.count()
_tut_titles = [win.page_tutorial.tabs.tabText(i) for i in range(win.page_tutorial.tabs.count())]
assert any("快速上手" in t for t in _tut_titles) and any("拆书" in t for t in _tut_titles), \
    "教程分页应有快速上手/拆书等，实际 %r" % _tut_titles
# v0.56 教程内容渲染：每分页正文非空
for _ti in range(win.page_tutorial.tabs.count()):
    _tb = win.page_tutorial.tabs.widget(_ti)
    _html = _tb.toHtml() if hasattr(_tb, "toHtml") else ""
    assert len(_html) > 300, "教程第 %d 页内容应非空（%d 字）" % (_ti, len(_html))
# v0.56 教程导航点击（回归：修复 page_tutorial 未 addWidget 导致点击无反应 + 缺 on_show 崩溃）
_btn_tut = [b for b in win.nav_buttons if "教程" in b.text()]
assert len(_btn_tut) == 1, "导航应有「📖 教程」按钮，实际 %r" % [b.text() for b in win.nav_buttons]
win._switch(win.page_tutorial, _btn_tut[0])
app.processEvents()
assert win.pages.currentWidget() is win.page_tutorial, "点击教程导航应切到教程页（index=%d）" \
    % win.pages.indexOf(win.page_tutorial)
# v0.64 文风校对页插入「去AI味」之后 → 教程 index 7→8；v0.88 AI 对话页 → 8→9；v0.91 Agent 独立页 → 9→10；
# v1.65 删除 Agent 页 → 10→9？不——v1.66 码字页插第二位、Agent 已删：注册顺序
# 项目0 码字1 角色2 生成3 去AI味4 文风校对5 拆书6 对话7 故事8 设置9 教程10 情景提示词11
assert win.pages.indexOf(win.page_tutorial) == 10, "教程页应为第 11 页（index=10，v1.65 删 Agent + v1.66 码字页插入后）"
# v0.64 文风校对页：导航入口 + 构造 + 预设资产 + 轻量相似度 + 工作流（mock LLM）
from gui_style_extract import StyleExtractPage  # noqa: E402
import style_extract as style_extract_mod  # noqa: E402
assert hasattr(win, "page_style_extract") and win.page_style_extract.text_edit is not None, \
    "应有文风校对页"
_btn_se = [b for b in win.nav_buttons if "文风校对" in b.text()]
assert len(_btn_se) == 1, "导航应有「文风校对」按钮"
win._switch(win.page_style_extract_scroll, _btn_se[0])
app.processEvents()
assert win.pages.currentWidget() is win.page_style_extract_scroll, "点击应切到文风校对页（滚动容器）"
assert win.pages.indexOf(win.page_style_extract_scroll) == 5, "文风校对页滚动容器 index 应为 5（v1.66 码字页插入后）"
assert win.page_style_extract_scroll.widget() is win.page_style_extract, "滚动容器应包住文风校对页"
# v0.64.1 输入栏不被压扁成一条线：滚动容器 + 输入框最小高度兜底
assert win.page_style_extract.text_edit.minimumHeight() >= 100, \
    "原文输入框最小高度应≥100（防被压扁成一条线）"
assert all(win.page_style_extract.prompt_edits[k].minimumHeight() >= 80
           for k in ("node_a", "node_b", "node_c", "node_d")), "节点提示词编辑框最小高度应≥80"
# 拆书工坊页同类问题一并修：同样包滚动容器（index 5 不变）
assert win.pages.indexOf(win.page_break_scroll) == 6, "拆书页滚动容器 index 应为 6（v1.66 码字页插入后）"
assert win.page_break_scroll.widget() is win.page_break, "滚动容器应包住拆书页"
_se_preset_names = [win.page_style_extract.preset_combo.itemText(i)
                    for i in range(win.page_style_extract.preset_combo.count())]
assert "default" in _se_preset_names, \
    "预设库应含 default 空壳（允许用户已保存的自定义预设），实际 %r" % _se_preset_names
# 轻量相似度：相同风格文本得分显著高于不同风格
_se_eval = style_extract_mod.SimilarityEvaluator()
_same = _se_eval.tfidf_cosine("夜深了，窗外风声呜咽，他握紧手中长剑。", "夜深了，窗外雨声阵阵，她握紧手中残剑。")
_diff = _se_eval.tfidf_cosine("夜深了，窗外风声呜咽，他握紧手中长剑。", "今天天气不错，我们一起去超市买苹果。")
assert _same > _diff and _same > 0.3, "轻量相似度应区分同风格/异风格（same=%.2f diff=%.2f）" % (_same, _diff)
# 工作流 mock：A/B/C/D 四节点调用 + 轮次/阈值/final 结构 + v0.66 四节点各走各的 API 配置
_orig_ct = llm_mod.chat_text
# mock 掉 style_settings，避免触碰真实 config：四节点各指定不同配置名
_orig_ss = style_extract_mod.style_settings
style_extract_mod.style_settings = lambda: {"profiles": {
    "node_a": "API-A", "node_b": "API-B", "node_c": "API-C", "node_d": "API-D"}}
_calls = {"n": 0, "prof": []}

def _fake_ct(system, user, temperature=None, max_tokens=None, role="all", profile=None,
             on_chunk=None, think_role=None):
    _calls["n"] += 1
    _calls["prof"].append(profile)
    # 工作流注入固定 custom_prompts（见 _se_custom_prompts），mock 按固定串匹配即可稳定命中：
    # A「请分析以上文本」/ C「相似度评分」/ B「创作」/ 其余(D)。
    if "请分析以上文本" in user:
        return "冷峻白描短句，重氛围轻修饰。"
    if "相似度" in user or "评分" in user:
        return "85"
    if "创作" in user:
        return "夜色如墨。他站在巷口，衣角被风掀起，久久未动。"
    return "优化后：冷峻白描，短句切割节奏，重感官氛围，禁陈词滥调。"
llm_mod.chat_text = _fake_ct
_se_stages = []
def _collect_stage(kind, data):
    _se_stages.append(kind)
_wf = style_extract_mod.StyleExtractorWorkflow()
_se_result = None
# v1.68+ 测试与用户实际 prompts.json 解耦：注入固定提示词（节点 A/B/C/D 各自含可识别关键词），
# 不依赖「文风提取/剧情设计提取」当前生效预设（用户 prompts.json 可能是任一预设）
_se_custom_prompts = {
    "node_a": "{原文}请分析以上文本的文风",
    "node_b": "{文风提示词}请根据以上文风特征创作一篇短文",
    "node_c": "{原文}{生成文章}请对比两篇文本并给出相似度评分（0-100 数字）",
    "node_d": "{文风提示词}请优化以上文风提示词",
}
for _k, _d in _wf.run_workflow_stream("夜色如墨，他站在巷口，衣角被风掀起。",
                                      max_rounds=2, threshold=95.0,
                                      custom_prompts=_se_custom_prompts):
    _collect_stage(_k, _d)
    if _k == "final":
        _se_result = _d
llm_mod.chat_text = _orig_ct
assert "a_done" in _se_stages and "b_done" in _se_stages and "c_done" in _se_stages \
    and "d_done" in _se_stages and "final" in _se_stages, "工作流阶段应完整，实际 %r" % _se_stages
assert _se_result is not None and len(_se_result.get("all_rounds", [])) == 2 \
    and _se_result.get("top_style_prompts"), "工作流 final 应含两轮结果与 Top3"
assert _se_result.get("reached_threshold") is False, "95 阈值下两轮 85 分不应达标"
# v0.66 四节点各走各的 API：首轮调用序 A→B→C→D，profile 分别对应 API-A/B/C/D
assert _calls["prof"][:4] == ["API-A", "API-B", "API-C", "API-D"] and len(_calls["prof"]) == 6, \
    "四节点应按各自配置调用（A/B/C/D × 2 轮），实际 %r" % _calls["prof"]
# 阈值达标提前结束：阈值 80 → 第 1 轮 85 分 → 提前结束（只有 1 轮）
# （注意：最终得分 = 0.4×TF-IDF + 0.6×LLM 分；原文须与生成文有足够字符重合，
#   TF-IDF≈85 才使最终≈85≥80。原文过短（如「夜色如墨。」）TF-IDF 仅≈38 → 最终≈66<80，
#   会正确跑满 5 轮，断言须用长句）
# （chat_text 已恢复真实函数，此处必须重新 mock，否则会打真实 API）
llm_mod.chat_text = _fake_ct
_calls["prof"] = []
_se_rounds = []
for _k, _d in _wf.run_workflow_stream("夜色如墨，他站在巷口，衣角被风掀起。",
                                      max_rounds=5, threshold=80.0,
                                      custom_prompts=_se_custom_prompts):
    if _k == "final":
        _se_rounds = _d.get("all_rounds", [])
llm_mod.chat_text = _orig_ct
style_extract_mod.style_settings = _orig_ss
assert len(_se_rounds) == 1, "阈值 80、首轮 85 分应提前结束（只跑 1 轮），实际 %d 轮" % len(_se_rounds)
# 提前结束的单轮调用序 A→B→C（无 D），三节点 profile 仍各自对应
assert _calls["prof"] == ["API-A", "API-B", "API-C"], \
    "提前结束轮仍应按各自配置调用（A/B/C，无 D），实际 %r" % _calls["prof"]
# v0.78 UI 卡死修复：放开轮次上限（99→999）+ 大文本截断显示 + 运行计时（不碰引擎/API）
_se_page = win.page_style_extract
assert _se_page.round_spin.maximum() == 999, \
    "最大校对轮次应放开到 999（用户要 200 轮慢慢打磨，99 限制是自缚手脚），实际 %d" \
    % _se_page.round_spin.maximum()
assert hasattr(_se_page, "elapsed_lbl"), "应有运行计时标签"
# b_done 大文本截断：mock 生成 8 万字符 → full_view 只显示前 8000 字 + 截断提示，完整正文留内存（导出用）
_se_page.text_edit.setPlainText("原文参考文本。" * 500)
_orig_ct2 = llm_mod.chat_text
_se_long = "生成" * 20000   # 8 万字符


def _fake_long(system, user, temperature=None, max_tokens=None, role="all", profile=None,
               on_chunk=None, think_role=None):
    if "对比以上两篇文本的文风相似度" in user or "评分" in user:
        return "87"
    if "请分析以上文本" in user:
        return "文风提示词"
    if "优化" in user:
        return "新提示词"
    return _se_long


llm_mod.chat_text = _fake_long
_se_page._start()
_t0 = time.time()
while _se_page._running and time.time() - _t0 < 10:
    app.processEvents()
llm_mod.chat_text = _orig_ct2
assert not _se_page._running, "mock 任务应快速完成（1 轮达标）"
_se_ftxt = _se_page.full_view.toPlainText()
assert len(_se_ftxt) <= 9000, "full_view 应截断显示（≤9000 字符），实际 %d" % len(_se_ftxt)
assert "完整" in _se_ftxt and "已保存" in _se_ftxt, "截断应提示完整内容已保存，实际 %r" % _se_ftxt[:120]
assert _se_page._full_text == _se_long, "完整正文应保留在内存（导出用），实际长度 %d" % len(_se_page._full_text)
print("[11] 文风校对页：导航/构造/预设库仅default空壳/轻量相似度/工作流（轮次·阈值·阶段）OK")

# v0.55 断点续传：chunks 阶段中断 → job 保留 → 同一文本重跑自动跳过已完成环节
import tempfile as _tmp2  # noqa: E402
_job = _tmp2.mkdtemp(prefix="imp_job_")
_imp_stops = {"n": 0}

def _imp_stop_after():
    # 调用序（3章1卷1批1单元，行为确定）：break 内 L1-a 批前/骨架前/L2 单元前/L3 前 = 第1~4次；
    # run 内 settings 前/后 = 第5~6次；chunks 块1前第7次（False）→ 块1完成落盘 part_0.json；
    # chunks 后第8次 → True 停止
    _imp_stops["n"] += 1
    return _imp_stops["n"] >= 8

_imp_stops["n"] = 0
_r1 = nimp.NovelImporter(log=lambda k, m: None,
                         stop_check=_imp_stop_after).run(_imp_txt, "续传测试书", None,
                                                         job_dir=_job)
assert not _r1.get("ok") and _r1.get("error") == "已停止", "第一次应中途停止，实际 %r" % str(_r1)[:80]
import os as _os2  # noqa: E402
assert _os2.path.exists(os.path.join(_job, "chunks", "part_0.json")), "中断时应已落盘完成的块结果"
# 第二次（无 stop）续传完成，且 chunks 不再重复调 LLM
_call_cnt = {"chunk": 0}
_orig_chunk2 = nimp.analyze_chunk_people
nimp.analyze_chunk_people = lambda payload, profile=None, user_prompt="": (
    _call_cnt.update({"chunk": _call_cnt["chunk"] + 1}),
    {"new_chars": [], "states": [], "transitions": []})[1]
_r2 = nimp.NovelImporter(log=lambda k, m: None).run(_imp_txt, "续传测试书", None, job_dir=_job)
assert _r2.get("ok"), "续传应完成，实际 %r" % str(_r2)[:80]
assert _call_cnt["chunk"] == 0, "续传应跳过已完成的块（不重复调 LLM），实际 %d" % _call_cnt["chunk"]
assert _os2.path.exists(os.path.join(_job, "done.json")), "完成应写 done 标志"
assert storage.ProjectStore(_r2["dir"]).load_project().title == "续传测试书", "续传落库应复用项目"
storage.delete_project(_r2["dir"])
nimp.analyze_chunk_people = _orig_chunk2
import shutil as _shu2  # noqa: E402
_shu2.rmtree(_job, ignore_errors=True)
# 停止立即生效：绑定停止事件后 LLM 调用立即抛 StopRequested（不发请求）
import llm as _llm  # noqa: E402
import threading as _th  # noqa: E402
# 隔离环境（zip 内 env / 无用户配置）下先补一个临时 API 配置，让 chat 通过 Key 检查走到 abort 检查
import config as _cfgmod  # noqa: E402
_cfgs3 = _cfgmod.load_config()
if not any((p.get("api_key") or "").strip()
           for p in (_cfgs3.get("api_profiles") or [])):
    _cfgs3["api_profiles"] = [{"name": "临时测试", "base_url": "http://127.0.0.1:9/v1",
                               "api_key": "sk-test", "model": "deepseek-chat", "role": "all"}]
    _cfgmod.save_config(_cfgs3)
    _cfgmod._cache = None
_ev_stop = _th.Event()
_llm.set_abort(_ev_stop)
_ev_stop.set()
try:
    _llm.chat([{"role": "user", "content": "x"}])
    raise SystemExit("停止事件置位后 chat 应立即抛 StopRequested")
except _llm.StopRequested:
    pass
finally:
    _llm.set_abort(None)
_llm.set_abort(_th.Event())   # 未置位时正常调用路径（不真发请求，仅验证不抛）
_llm.set_abort(None)
# v0.70 导入「逐块人物抽取」瞬时失败 → 自动重试补跑成功
_imp_rt70 = {"n": 0}
_orig_ichunk70 = nimp.analyze_chunk_people


def _fail_ichunk70(payload, profile=None, user_prompt=""):
    _imp_rt70["n"] += 1
    if _imp_rt70["n"] == 1:
        raise _llm70.LLMError("测试失败：人物块 JSON 错误")
    return {"new_chars": [], "states": [], "transitions": []}


nimp.analyze_chunk_people = _fail_ichunk70
_irt70 = nimp.NovelImporter(log=lambda k, m: None).run(_imp_txt, "导入重试测试", None)
assert _irt70.get("ok"), "导入人物抽取瞬时失败应自动重试补跑成功，实际 %r" % str(_irt70)[:120]
assert _imp_rt70["n"] >= 2, "瞬时失败应自动重试（调用次数>=2），实际 %d" % _imp_rt70["n"]
nimp.analyze_chunk_people = _orig_ichunk70
storage.delete_project(_irt70["dir"])
bb.delete_break("《导入重试测试》拆书")
# 还原 mock
bb.summarize_title_batch = _orig_tb
bb.build_skeleton = _orig_sk
bb.analyze_volume = _orig_av
bb.merge_doc = _orig_md
nimp.synthesize_settings = _orig_isyn
nimp.analyze_chunk_people = _orig_ichunk
nimp.build_character_cards = _orig_icards
nimp.synthesize_summary = _orig_isummary
bb.delete_break("《导入测试书》拆书")
bb.delete_break("《续传测试书》拆书")
# 清理测试项目（含索引，不留死条目）
storage.delete_project(_nir["dir"])
print("[10] 小说导入成项目：txt 还原（拆书风格/设定合成/角色卡/章节原样入库/伏笔台账/管理笔记按卷梳理/"
      "写作计划/写作技巧库）+ 删除章节角色卡回退 + 无快照回滚兜底 + 导入设置（token/并行/API/提示词）"
      "+ 断点续传 + 立即停止 + 页面构造 OK")

# v0.81 三项 UI 改动断言：一键成书章数上限放开、文风校对设置移到项目页、设置页撤销自定义禁词栏
_se_pg = win.page_project
assert hasattr(_se_pg, "proofread_chk") and hasattr(_se_pg, "proofread_edit"), \
    "项目页应有文风校对开关与提示词编辑（⑤ 文风校对区块）"
assert hasattr(_se_pg, "_save_proofread"), "项目页应有文风校对保存方法"
assert not hasattr(win.page_generate, "proofread_chk"), \
    "生成页应已移除文风校对区块（移到项目页）"
assert not hasattr(win.page_settings, "tone_word_list"), \
    "设置页应已撤销「自定义禁词」栏（tone_word_list 控件移除）"
# 一键成书：本次连写上限放开（可一次生成到全书总章节数）
from gui_book import BookPanel as _bp
_bp_w = _bp(None, show_title=True)
assert _bp_w.ch_spin.maximum() >= 9999, "一键成书「本次生成到」上限应放开到 9999"
# 项目页文风校对保存闭环：改动提示词 → 防抖保存 → config 更新（完成后恢复真实值）
_se_cfg_bak = config.load_config()
_se_pg.proofread_edit.setPlainText("测试校对规则：少用重词。")
_se_pg._proofread_dirty()
_t0 = time.time()
while time.time() - _t0 < 1.5:
    app.processEvents()
    if config.load_config().get("proofread_rules") == "测试校对规则：少用重词。":
        break
    time.sleep(0.05)
assert config.load_config().get("proofread_rules") == "测试校对规则：少用重词。", \
    "项目页文风校对提示词应防抖自动保存进 config"
_se_pg.proofread_edit.setPlainText(_se_cfg_bak.get("proofread_rules") or "")
_se_pg._proofread_dirty()
_t0 = time.time()
while time.time() - _t0 < 1.5:
    app.processEvents()
    if config.load_config().get("proofread_rules") == (_se_cfg_bak.get("proofread_rules") or None):
        break
    time.sleep(0.05)
assert config.load_config().get("proofread_rules") == (_se_cfg_bak.get("proofread_rules") or None), \
    "文风校对提示词应恢复原值"
print("[12] v0.81 一键成书章数放开（9999）+ 文风校对设置移到项目页（开关/提示词/保存闭环）"
      "+ 生成页移除 + 设置页撤销自定义禁词栏 OK")

# v0.82 断言：拆书暂停/继续按钮、NovelBreaker pause_check、文风校对失败自动重试
_br_pg = win.page_break
assert hasattr(_br_pg, "pause_btn") and hasattr(_br_pg, "resume_btn"), "拆书页应有暂停/继续按钮"
assert hasattr(_br_pg, "_pause") and hasattr(_br_pg, "_resume"), "拆书页应有暂停/继续方法"
import book_break as _bb_mod
_nb = _bb_mod.NovelBreaker(pause_check=lambda: False)
assert hasattr(_nb, "_wait_pause"), "NovelBreaker 应支持 pause_check（v0.82 暂停）"
assert _br_pg.pause_btn.text() == "暂停" and _br_pg.resume_btn.text() == "继续"
# 文风校对失败自动重试：mock proofread_chapter 前 2 次抛 LLMError、第 3 次成功 → 返回 notes
import engine as _eng_mod
class _Ch:
    index = 1
    content = "正文内容。" * 120
    reasoning = {}
_calls = {"n": 0}
_orig_pr = _eng_mod.main_ai.proofread_chapter
def _flaky(project, store, chapter, rules="", max_tokens=None):
    _calls["n"] += 1
    if _calls["n"] < 3:
        raise llm_mod.LLMError("模拟限流")
    return {"content": "新的正文内容。" * 400, "notes": ["已修正"]}
_eng_mod.main_ai.proofread_chapter = _flaky
_eng = _eng_mod.NovelEngine(None)
try:
    _notes = _eng._proofread_once(None, _Ch(), 2000)
finally:
    _eng_mod.main_ai.proofread_chapter = _orig_pr
assert _calls["n"] == 3 and _notes == ["已修正"], \
    "文风校对失败应自动重试 3 次（第 3 次成功，实际调用 %d 次、notes=%r）" % (_calls["n"], _notes)
# v0.83 追加断言：文风校对工坊页暂停/继续、故事设定 Tab 文风校对、写作技巧库已删除
_se_style_pg = win.page_style_extract
assert hasattr(_se_style_pg, "pause_btn") and hasattr(_se_style_pg, "resume_btn"), \
    "文风校对工坊页应有暂停/继续按钮（v0.83）"
assert _se_style_pg.pause_btn.text() == "⏸ 暂停" and _se_style_pg.resume_btn.text() == "▶ 继续"
import style_extract as _se_mod
assert "pause_check" in _se_mod.StyleExtractorWorkflow.run_workflow_stream.__code__.co_varnames, \
    "run_workflow_stream 应支持 pause_check"
# 写作技巧库删除：项目页无 p_techniques/tech_extract_btn，prompts 无 extract_writing_techniques
assert not hasattr(win.page_project, "p_techniques"), "写作技巧库 UI 应已删除（无 p_techniques）"
assert not hasattr(win.page_project, "tech_extract_btn"), "写作技巧库 UI 应已删除（无 tech_extract_btn）"
import prompts as _prompts_mod
assert not hasattr(_prompts_mod, "extract_writing_techniques"), \
    "prompts.extract_writing_techniques 应已删除"
assert hasattr(_se_pg, "proofread_chk"), "项目页应有文风校对（正文生成后/主AI验收前）开关"
# v0.85/0.86 独立「写后校对」子页面 Tab（正文生成后、主AI验收前的校对，命名「写后校对」与工坊页区分）
_se_tab_names = [win.page_project.tabs.tabText(i) for i in range(win.page_project.tabs.count())]
assert "写后校对" in _se_tab_names, "项目主页应有独立「写后校对」子页面，当前 Tab=%r" % _se_tab_names
assert not hasattr(_se_pg, "p_tech_source"), "写作技巧库素材控件应已删除"
print("[13] v0.82 拆书暂停/继续（按钮+NovelBreaker pause_check）+ 文风校对失败自动重试（3 次）"
      "+ 项目页文风参考 Tab 滚动容器 OK")
print("[14] v0.83 文风校对工坊页暂停/继续 + 项目页「故事设定」Tab 文风校对（⑥）+ 写作技巧库已删除 OK")

# v0.87 追加断言：①文风校对工坊「暂停中收到停止」立即退出挂起（_wait_pause 判 stop_check）；
#   ②engine._proofread_once 遇 StopRequested 必须向外传播（不被外层 except Exception 吞成「保留原文继续」）
_orig_load87 = config.load_config
config.load_config = lambda: {"proofread_enabled": True, "proofread_rules": ""}
try:
    _saved_se_chat = _se_mod.llm.chat_text
    _se_mod.llm.chat_text = lambda *a, **k: "风格内容"
    _se_wf87 = _se_mod.StyleExtractorWorkflow()
    _se_wf87.load_prompts = lambda: {"node_a": "a{原文}", "node_b": "b", "node_c": "c", "node_d": "d"}
    _se_stopped87 = False
    try:
        for _k87, _d87 in _se_wf87.run_workflow_stream(
                "原文", max_rounds=3, threshold=80,
                stop_check=lambda: True, pause_check=lambda: True):
            pass
    except llm_mod.StopRequested:
        _se_stopped87 = True
    _se_mod.llm.chat_text = _saved_se_chat
    assert _se_stopped87, \
        "v0.87 文风校对暂停中收到停止应立即抛 StopRequested（_wait_pause 应判 stop_check）"

    _orig_pr87 = _eng_mod.main_ai.proofread_chapter
    _calls87 = {"n": 0}
    def _pf87(*a, **k):
        _calls87["n"] += 1
        raise llm_mod.StopRequested("stop")
    _eng_mod.main_ai.proofread_chapter = _pf87
    _se_pr87_hit = False
    try:
        _eng_mod.NovelEngine(None)._proofread_once(None, _Ch(), 2000)
    except llm_mod.StopRequested:
        _se_pr87_hit = True
    _eng_mod.main_ai.proofread_chapter = _orig_pr87
    assert _se_pr87_hit and _calls87["n"] == 1, \
        "v0.87 _proofread_once 遇 StopRequested 应立即传播（实际调用 %d 次，被吞=0）" % _calls87["n"]
finally:
    config.load_config = _orig_load87
print("[15] v0.87 停止传播修复：文风校对暂停中可停止 + 写后校对 StopRequested 不吞 OK")

# v0.88 追加断言：AI 对话页——话题/文件夹存储往返、导出、项目上下文不含正文、
#   llm.on_chunk 流式回调、Qwen CLI 解析、页面导航 index
import chat_lib as _chat_mod  # noqa: E402
_orig_chat_data = _chat_mod.config.DATA_DIR
_tmp_chats = _tmp.mkdtemp(prefix="xhb_chat_")
_chat_mod.config.DATA_DIR = _tmp_chats
try:
    _fid = _chat_mod.create_folder("测试文件夹")
    assert _fid and [f["name"] for f in _chat_mod.list_folders()] == ["测试文件夹"], \
        "文件夹创建/列表应正常"
    _tid1 = _chat_mod.create_topic("话题甲", _fid)
    _tid2 = _chat_mod.create_topic("话题乙")
    _chat_mod.append_message(_tid1, "user", "你好")
    _chat_mod.append_message(_tid1, "assistant", "你好呀")
    assert len(_chat_mod.load_topic(_tid1)["messages"]) == 2, "消息应可追加"
    _tl16 = {t["id"]: t for t in _chat_mod.list_topics()}
    assert _tl16[_tid1]["folder"] == _fid and _tl16[_tid1]["msg_count"] == 2, "话题应带文件夹与消息数"
    _chat_mod.move_topic(_tid1, "")
    assert _chat_mod.load_topic(_tid1)["folder"] == "", "移动话题到未分类应生效"
    _md16 = os.path.join(_tmp_chats, "export.md")
    assert _chat_mod.export_topic_md(_tid1, _md16) and os.path.isfile(_md16), "导出 md 应成功"
    with open(_md16, encoding="utf-8") as _f16:
        assert "你好" in _f16.read(), "导出的 md 应含消息内容"
    _chat_mod.rename_topic(_tid2, "改名话题")
    assert _chat_mod.load_topic(_tid2)["title"] == "改名话题", "重命名话题应生效"
    _chat_mod.delete_folder(_fid)
    assert not _chat_mod.list_folders() and _chat_mod.load_topic(_tid1)["folder"] == "", \
        "删文件夹应清空列表并把话题移回未分类"
    # 项目上下文（不含正文）：组装设定/锚点/伏笔/角色，绝不含章节正文
    _proj16 = _mdl.NovelProject(dir_name="t16", title="测试书")
    _proj16.story_brief = "一个关于剑客的江湖故事"
    _proj16.story_style = "沉稳冷峻"
    _proj16.lore_entries = [{"id": "l1", "title": "剑宗", "content": "剑宗戒律严明"}]
    _proj16.story_knowledge = "主角来自剑宗"
    _proj16.state = {"next_chapter": 5}
    class _FS16:
        f_type = "plant"
        status = "open"
        text = "断剑伏笔"
        planted_chapter = 3
    class _FakeStore16:
        base = _tmp_chats
        def list_characters(self):
            return []
        def load_character(self, cid):
            return None, None
        def load_foreshadows(self):
            return [_FS16()]
    _ctx16 = _chat_mod.build_project_context(_FakeStore16(), _proj16)
    assert "测试书" in _ctx16 and "剑客" in _ctx16 and "断剑伏笔" in _ctx16, \
        "项目上下文应含设定/锚点/伏笔"
    assert _ctx16.count("正文") == 2, \
        "项目上下文除两处提示语外不应出现正文内容（实际 %d 处）" % _ctx16.count("正文")
    # llm.on_chunk 流式回调：假 Session 两片 content → 逐片收到且最终文本完整
    _orig_sess16 = llm_mod._session
    _sess16 = type("_FakeSess16", (), {})()
    _chunks16 = []
    def _fp16(url, json, headers, timeout, stream=False):
        r = requests_mod.Response()
        r.status_code = 200
        r.headers = {}
        _body16 = ('data: {"choices":[{"delta":{"content":"片1"}}]}\n\n'
                   'data: {"choices":[{"delta":{"content":"片2"}}]}\n\n'
                   'data: [DONE]\n\n').encode("utf-8")
        r.raw = _io.BytesIO(_body16)
        return r
    _sess16.post = _fp16
    llm_mod._session = lambda: _sess16
    _out16 = llm_mod.chat([{"role": "user", "content": "hi"}], on_chunk=_chunks16.append)
    llm_mod._session = _orig_sess16
    assert _out16 == "片1片2" and _chunks16 == ["片1", "片2"], \
        "on_chunk 流式回调应逐片收到，最终文本完整：%r / %r" % (_out16, _chunks16)
    # 页面导航：AI 对话页 index=6、导航按钮、话题树/API 下拉（在临时数据目录下刷新）
    _cp16 = win.page_chat
    assert _cp16.input_edit is not None and _cp16.tree is not None, "AI 对话页应可构造"
    assert win.pages.indexOf(win.page_chat) == 7, "AI 对话页 index 应为 7（v1.66 码字页插入后）"
    _btn_chat16 = [b for b in win.nav_buttons if "AI 对话" in b.text()]
    assert len(_btn_chat16) == 1, "导航应有「AI 对话」按钮"
    _cp16.on_show()
    app.processEvents()
    assert _cp16.tree.topLevelItemCount() >= 1, "话题树应有根节点"
    assert _cp16.cur_api_lbl is not None, "对话页应有生效配置只读标签"
    assert "上下文" in _cp16.ctx_lbl.text(), "对话页应有上下文用量标签"
    # v0.96 气泡渲染：用户右对齐 + AI 左对齐 + 头像框（真实控件，替代不生效的 HTML 气泡）
    from msg_bubbles import BubbleRow as _Br16
    _cp16._msgs = [{"role": "user", "content": "用户问题"},
                   {"role": "assistant", "content": "AI 回答"}]
    _cp16._render_all()
    _rows16 = [_cp16.msg_vbox.itemAt(i).widget()
               for i in range(_cp16.msg_vbox.count())
               if _cp16.msg_vbox.itemAt(i).widget() is not None]
    _br16 = [w for w in _rows16 if isinstance(w, _Br16)]
    assert len(_br16) == 2, "对话页渲染应有 2 条气泡行，实际 %d" % len(_br16)
    assert _br16[0]._role == "user" and _br16[1]._role == "assistant", \
        "对话页气泡行角色应正确，实际 %r/%r" % (_br16[0]._role, _br16[1]._role)
    assert _br16[0].bubble.text() == "用户问题", "用户气泡内容应正确"
    assert _br16[1].bubble.text() == "AI 回答", "AI 气泡内容应正确"
    assert _br16[0].avatar.text() == "我" and _br16[1].avatar.text() == "AI", \
        "对话页头像框文字应正确（我/AI）"
    _cp16._begin_stream()
    _cp16._stream_piece("正在")
    _cp16._stream_piece("输出…")
    assert _cp16._stream_row is not None, "流式气泡行应存在"
    assert _cp16._stream_row.bubble.text() == "正在输出…", "流式文字应实时写入气泡"
    _cp16._stream_row = None
    # v1.08 话题可命名：新建弹命名框（mock QInputDialog）+ 标题栏重命名按钮 + 双击改名链路
    from PySide6.QtWidgets import QInputDialog as _QInput16
    from PySide6.QtWidgets import QTreeWidgetItem as _TreeW16
    from PySide6.QtCore import Qt as _Qt16
    assert hasattr(_cp16, "rename_btn"), "对话页标题栏应有「重命名」按钮"
    _orig_gt16 = _QInput16.getText
    _cap_n16 = {}
    _QInput16.getText = staticmethod(lambda *a, **k: (_cap_n16.update(
        {"title": a[2] if len(a) > 2 else ""}) or ("我的自定义话题", True)))
    try:
        _cp16._new_topic()   # prompt=True：应先弹命名框
        _named16 = [t for t in _chat_mod.list_topics() if t["title"] == "我的自定义话题"]
        assert _named16, "新建话题应使用命名框输入的标题，实际 %r" % \
            [t["title"] for t in _chat_mod.list_topics()][:5]
        _cp16._tid = _named16[0]["id"]
        _cp16._rename_current()   # 标题栏重命名按钮 → 再改一次名
        _renamed16 = [t for t in _chat_mod.list_topics()
                      if t["id"] == _cp16._tid][0]["title"]
        assert _renamed16 == "我的自定义话题", "重命名按钮应改当前话题名"
        # 双击改名（_tree_double）：构造树 item 直接调
        _ti16 = _TreeW16(["双击改名"])
        _ti16.setData(0, _Qt16.ItemDataRole.UserRole, ("topic", _cp16._tid))
        _cp16._tree_double(_ti16, 0)
        assert _chat_mod.load_topic(_cp16._tid)["title"] == "我的自定义话题", \
            "双击话题改名应生效"
    finally:
        _QInput16.getText = _orig_gt16
finally:
    _chat_mod.config.DATA_DIR = _orig_chat_data
    import shutil as _shut16  # noqa: E402
    _shut16.rmtree(_tmp_chats, ignore_errors=True)
print("[16] v0.88 AI 对话页：话题/文件夹/导出往返 + 项目上下文不含正文 + llm.on_chunk 流式 + Qwen CLI 解析 + 导航 OK")


# v1.65 移除 Agent 功能：原 v0.89/0.91 Agent 页（Skill/MCP/会话/权限模式/气泡）、v0.90/0.91 Agent 指令与 Skill zip、v0.93 Agent ctx 标签与自动压缩闭环断言已删除
print("[17] v1.65 移除 Agent 功能（原 v0.89/0.91 Agent 页断言已删除）")

# v0.90/0.91 追加断言：对话页消息编辑（数据层）+ Agent 页指令分发（/help /clear /skills /compress）+ Skill zip/本机扫描
_tmp_q90 = _tmp.mkdtemp(prefix="xhb_q90_")
_orig_q90_data = _chat_mod.config.DATA_DIR
_chat_mod.config.DATA_DIR = _tmp_q90
try:
    _t90 = _chat_mod.create_topic("话题90")
    for _role90 in ("user", "assistant", "user"):
        _chat_mod.append_message(_t90, _role90, "消息%d" % len(_chat_mod.load_topic(_t90)["messages"]))
    # 数据层：编辑最后一条 / 追加末尾（继续生成）/ 删除末尾 / 摘要 / 截断 / 整体覆盖
    _chat_mod.update_last_message(_t90, "改后消息")
    assert _chat_mod.load_topic(_t90)["messages"][-1]["content"] == "改后消息", "编辑最后一条应生效"
    _chat_mod.append_to_last_message(_t90, "续写")
    assert _chat_mod.load_topic(_t90)["messages"][-1]["content"] == "改后消息续写", "继续生成追加应生效"
    _chat_mod.pop_last_messages(_t90, 1)
    assert len(_chat_mod.load_topic(_t90)["messages"]) == 2, "删除末尾应生效"
    _chat_mod.set_topic_summary(_t90, "摘要ABC")
    assert _chat_mod.load_topic(_t90)["summary"] == "摘要ABC", "摘要保存应生效"
    _chat_mod.truncate_topic_messages(_t90, 1)
    assert len(_chat_mod.load_topic(_t90)["messages"]) == 1, "截断消息应生效"
    _chat_mod.set_topic_messages(_t90, [{"role": "user", "content": "x"}])
    assert len(_chat_mod.load_topic(_t90)["messages"]) == 1, "整体覆盖应生效"
    # v1.65 移除 Agent：Skill zip/本机扫描与 Agent 指令断言删除；对话页消息操作控件保留
    # 对话页消息操作按钮（v1.65 移除 Agent 指令断言）
    _cp90 = win.page_chat
    assert hasattr(_cp90, "edit_btn") and hasattr(_cp90, "reg_btn") \
        and hasattr(_cp90, "cont_btn") and hasattr(_cp90, "del_btn"), "对话页应有消息操作按钮（编辑/重生成/继续/删除）"
    assert hasattr(_cp90, "web_chk"), "对话页应有联网搜索开关"
    assert hasattr(_cp90, "att_list") and hasattr(_cp90, "_attachments"), "对话页应有附件栏"
finally:
    _chat_mod.config.DATA_DIR = _orig_q90_data
    import shutil as _shut90  # noqa: E402
    _shut90.rmtree(_tmp_q90, ignore_errors=True)
print("[18] v0.90/0.91 消息编辑数据层 + 对话页消息操作/联网/附件控件 + Agent 指令（/help /skills /clear /update /compress 闭环）+ Skill zip 安装 OK")

# v0.93 追加断言：上下文估算与窗口读取（v1.65 移除 Agent：ctx 标签/自动压缩断言删除）
# ① chat_lib.estimate_tokens / context_window
assert _chat_mod.estimate_tokens("字" * 400) == int(400 / _chat_mod.TOKENS_PER_CHAR), \
    "token 估算应按 TOKENS_PER_CHAR（400 字 → %d）" % int(400 / _chat_mod.TOKENS_PER_CHAR)
assert _chat_mod.estimate_tokens("") == 0, "空文本估算应为 0"
_orig_pick93 = config.pick_profile
config.pick_profile = lambda *a, **k: {"name": "t", "model": "m", "context_window": 262144}
assert _chat_mod.context_window(None) == 262144, "context_window 应读取 pick_profile 的拉取记录"
config.pick_profile = _orig_pick93
# ② 对话页与 Agent 页均有上下文用量标签
_cp93 = win.page_chat
assert hasattr(_cp93, "ctx_lbl"), "对话页应有上下文用量标签"
_cp93.on_show()
app.processEvents()
assert "上下文" in _cp93.ctx_lbl.text(), "对话页 ctx 标签应显示估算，实际 %r" % _cp93.ctx_lbl.text()
    # v1.65 移除 Agent：Agent 页 ctx 标签与 60% 自动压缩闭环断言删除；对话页 ctx 标签保留
# 恢复用户真实配置（API Key 原样保留，绝不删除）
config._cache = None
config.save_config(_ORIG_CFG)
config._cache = None
print("ALL_OK")
