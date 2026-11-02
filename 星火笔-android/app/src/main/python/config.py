# -*- coding: utf-8 -*-
"""应用级配置：多 API 配置（profiles）、推理与生成参数。存储于 data/config.json（已 gitignore）。

config.json 结构：
{
  "api_profiles": [
    {"name":"主号","base_url":"https://api.deepseek.com/v1","api_key":"...",
     "model":"deepseek-chat","role":"all"}   # role: all | decide | reason | write
  ],
  "current_profile": "主号",                 # 当前启用的配置名
  "temperature": 1.0, "max_tokens": 32000, ...
}
"""
import json
import os
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_ROOT, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

DEFAULT_CONFIG = {
    "api_profiles": [
        {"name": "默认配置", "base_url": "https://api.deepseek.com/v1",
         "api_key": "", "model": "deepseek-chat", "role": "all"},
    ],
    "current_profile": "默认配置",
    "role_profiles": None,      # 用途分工：{"decide": 配置名, "reason": 配置名, "write": 配置名}；None=未设置过（首次从旧 role 字段迁移）
    "role_thinking": None,      # v0.94 各功能思考强度：{"decide": "low", "chat": "", ...}；空/缺失 = 跟随全局 reasoning_effort
    "temperature": 1.0,
    "max_tokens": 32000,
    "chapter_target_chars": 2500,
    # v1.17 正文长度上下限（0=自动：下限=目标×0.8、上限=目标×1.15；用户可在设置页自设）
    "chapter_min_chars": 0,
    "chapter_max_chars": 0,
    # v1.17 正文AI情景规则卡（可选插入项：按正文类型标注，主AI每章按本章内容自动选用注入正文AI）
    "writer_scene_cards": [],
    # v1.20 从文本提取情景规则卡的提取提示词（None=内置初始，取自「初始提取.txt」微调；情景提示词页可编辑保存/恢复初始）
    "extract_scene_card_prompt": None,
    "reasoning_mode": "sequential",   # sequential | parallel
    "max_workers": 5,
    "request_timeout": 300,
    "retry_times": 3,           # 请求失败自动重试次数（0 = 不重试；429 限流同样计入）
    "retry_interval": 3,        # 重试间隔（秒）：每次失败后等待的基础时长（固定间隔）
    "rate_limit_min_wait": 5,   # 429 限流最小等待（秒）：限流窗口按分钟计，实际等待取 max(此项, retry_interval)
    "auto_rewrite": True,
    "deai_rules": None,       # 去AI味规则文本（None=使用内置默认规则；在「去AI味」页可编辑）
    "deai_style_ref": "",     # 去AI味参考文风样本（v1.02：一段想要的味道，AI 去AI味时模仿其语感句式，不抄内容；留空=只按规则改）
    # v1.04 一键自动去AI味（结合文风校对的「评分→优化→达标自动通过」验收循环）：
    # deai_auto_threshold=文风契合度阈值（0-100，达标自动合并回原文）；deai_auto_max_rounds=每章最大优化轮次；
    # deai_auto_length_tol=字数容差（字，v1.05 起与正文写作的 ±500 字标准一致；超出即不通过，保证篇幅不崩）
    "deai_auto_threshold": 80,
    "deai_auto_max_rounds": 3,
    "deai_auto_length_tol": 500,
    # v1.07 去AI味/写后校对照前后章节参考（前后各 N 章，0=不看）：
    # 处理本章时注入附近章节（标题+梗概+正文节选），让 AI 核对剧情衔接（人物状态/地点/时间线/
    # 伏笔不与前后文冲突），防去AI味/校把剧情改偏移；去AI味页与项目页写后校对设置共用此键。
    "deai_nearby_chapters": 2,
    "compress_interval": 5,   # 主AI每多少章压缩一次管理笔记（上下文瘦身；短篇可设小）
    "foreshadow_overdue_chapters": 15,  # 伏笔埋设后超过该章数未回收 → 标记逾期并强提醒（伏笔看板/提示词）
    "web_search_enabled": False,   # 主AI联网搜索灵感（默认关，用户决定）
    "writer_recent_chapters": 3,   # 正文AI写作时可读最近 N 章正文（含剧情压缩卷）
    # 推理思考强度（参考 deepseek-harness 的 reasoning_effort；None=不传、跟随 API 默认）：
    # "off" 关思考 / "low" / "high" / "max" 分级。推理模型（如商汤 deepseek-v4-flash）不控制
    # 思考时每个请求先想很久 → 拖慢全流程；JSON 环节（决断/推理/校验）通常不需要深度思考，设
    # low 或 off 可显著提速；正文写作保留默认或 high 保质量。网关不认该参数时会忽略或报错，可关。
    "reasoning_effort": None,
    # 写后校对（正文AI完稿后、主AI审查前，只改文本不改剧情）：
    # proofread_enabled=False 可关闭该环节；proofread_rules=None=使用内置默认校对规则，
    # 在设置页可自由编辑（留空恢复内置默认）。
    "proofread_enabled": True,
    "proofread_rules": None,
    # v0.63 生成前剧情点确认关卡（生成页开关；持久化，全自动连写/凭意见重新生成同样生效）
    "confirm_beats_enabled": False,
    # v1.68 码字 AI 任务上下文开关（续写/段落工具共用，省 token 可关）：
    # tool_ctx_style=应用正文AI提示词与文风要求（story_writer_prompt + 参考文风样本 + 风格要点）；
    # tool_ctx_notes=读取主AI笔记（管理笔记/重要角色档案/灵感/知识库）；
    # tool_ctx_rp=对涉及人物读取推理（角色卡，按人设推理其行为/语言/情绪并落实）。
    # 默认全开（保证"有灵魂"）；需要省 token 时按任务关掉对应项。
    "tool_ctx_style": True,
    "tool_ctx_notes": True,
    "tool_ctx_rp": True,
}

_lock = threading.Lock()
_cache = None


def load_config():
    """读取配置；旧版本单 API 字段自动迁移为 profiles。"""
    global _cache
    with _lock:
        if _cache is not None:
            # 返回深拷贝：调用方（如设置页）可能直接改 dict，避免与后台生成线程
            # 并发读同一对象（list 迭代中增删会抛 RuntimeError）
            return json.loads(json.dumps(_cache))
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    cfg.update(saved)
        except Exception:
            pass
        _migrate(cfg)
        _ensure_minimal(cfg)
        _cache = cfg
        return json.loads(json.dumps(cfg))


def _migrate(cfg):
    """旧版本（无 api_profiles）迁移：把顶层 base_url/api_key/model 并入一个 profile。"""
    if not cfg.get("api_profiles") and (cfg.get("api_key") or cfg.get("base_url")):
        cfg["api_profiles"] = [{
            "name": "默认配置",
            "base_url": cfg.get("base_url", "https://api.deepseek.com/v1"),
            "api_key": cfg.get("api_key", ""),
            "model": cfg.get("model", "deepseek-chat"),
            "role": "all",
        }]
        cfg["current_profile"] = "默认配置"
    for k in ("api_key", "base_url", "model"):
        cfg.pop(k, None)


def _ensure_minimal(cfg):
    profs = cfg.get("api_profiles") or []
    if not profs:
        cfg["api_profiles"] = [dict(DEFAULT_CONFIG["api_profiles"][0])]
    cur = cfg.get("current_profile")
    names = [p.get("name", "") for p in cfg["api_profiles"]]
    if not cur or cur not in names:
        cfg["current_profile"] = names[0]
    # 用途分工（v2.28 起在设置页三用途下拉里显式选配置）：
    # 仅当 config.json 从未保存过 role_profiles（None）时，才从旧版 profile 自带
    # role=decide/reason/write 字段迁移一次；用户保存过的分工（含「不指定」）绝不再覆盖。
    rp = cfg.get("role_profiles")
    if rp is None:
        rp = {}
        for p in cfg["api_profiles"]:
            r = p.get("role")
            if r in ("decide", "reason", "write") and p.get("name"):
                rp.setdefault(r, p["name"])
        cfg["role_profiles"] = rp
    elif not isinstance(rp, dict):
        cfg["role_profiles"] = {}


def save_config(cfg):
    global _cache
    with _lock:
        _cache = None
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------- API profiles 便捷操作 ----------
def profiles():
    cfg = load_config()
    return list(cfg.get("api_profiles", []))


def current_profile():
    cfg = load_config()
    cur = cfg.get("current_profile")
    for p in cfg.get("api_profiles", []):
        if p.get("name") == cur:
            return p
    if cfg.get("api_profiles"):
        return cfg["api_profiles"][0]
    return None


def pick_profile(role="all"):
    """按用途选择 API 配置：先用「用途分工」映射（设置页各用途下拉显式指定的配置），
    其次「设为当前」配置（用途兼容时），再次通用（role=all）配置。

    role: all（通用） | decide（主AI决断与校验） | reason（角色推理） | write（正文写作）
    | deai（去AI味） | review（审查AI：正文与主AI验收之间的审查；未单独指定时跟随主AI决断配置）
    """
    cfg = load_config()
    profs = cfg.get("api_profiles", []) or []
    cur_name = cfg.get("current_profile")
    cur = next((p for p in profs if p.get("name") == cur_name), None)

    def usable(p):
        return bool((p.get("api_key") or "").strip())

    keyed = [p for p in profs if usable(p)]
    name_to = {p.get("name"): p for p in keyed}

    # 1) 用途分工：用户在「主AI决断/正文写作/角色推理/去AI味/审查」下拉里显式指定的配置
    if role and role != "all":
        rp = cfg.get("role_profiles") or {}
        pname = rp.get(role)
        # v2.45：审查用途默认跟随主AI决断配置（未单独指定时），保持既有「审查=主AI」行为；
        # 用户在用途分工里显式给「审查AI」选了配置后即独立。
        if not pname and role == "review":
            pname = rp.get("decide")
        if pname and pname in name_to:
            return name_to[pname]
    # 2) 「设为当前」配置（v1.22 修复老 bug）：通用配置（role=all/空）可用于**任意用途**——
    #    用户「设为当前」的意图就是让当前配置做通用兜底；专用配置只用于匹配的用途。
    #    （旧实现漏了「当前是通用配置应匹配任意用途」，导致带用途的调用落到分支3
    #    返回列表里第一个 role=all 的配置而不是当前配置——"设为当前没用"老 bug。）
    if cur and usable(cur):
        cur_role = cur.get("role")
        if cur_role in ("all", None, ""):
            return cur
        if cur_role == role:
            return cur
    # 3) 退回任意通用（role=all）配置
    for p in keyed:
        if p.get("role") in ("all", None, ""):
            return p
    return cur or (profs[0] if profs else None)