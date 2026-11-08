# -*- coding: utf-8 -*-
"""AI 对话库（v0.88）：话题/文件夹存储、导出、项目上下文构建（不含正文）。

存储布局（data/chats/）：
  meta.json            {"folders": [{"id","name"}]}
  topics/<id>.json     {"id","title","folder","messages":[{role,content,ts}],"updated"}


"""
import json
import os
import shutil
import time
import uuid

import config
import llm

MAX_HISTORY = 24      # 发给模型的最近消息条数（服务端无状态，防上下文膨胀）
MAX_CONTEXT_CHARS = 3000   # 项目上下文各字段截断上限
TOKENS_PER_CHAR = 1.6      # v0.93 上下文估算：中文约 1 字 ≈ 1.6 token（项目惯例，粗略）


def estimate_tokens(*texts):
    """按 TOKENS_PER_CHAR 估算总 token 数（粗略，用于显示与自动压缩判断）。

    接受文本（按字符数算）或 int/float（视为已统计的字符数直接累加）。
    """
    total = 0
    for t in texts:
        if isinstance(t, (int, float)):
            total += int(t)
        else:
            total += len(str(t) or "")
    return int(total / TOKENS_PER_CHAR)


def context_window(profile_name=None, fallback=0, role=None):
    """当前生效配置的上下文窗口 token 数（拉取模型记录 / 手填）。

    profile_name 给定 → 该配置的 context_window；None → 按 role 走 pick_profile(role)
    （v0.94：对话=chat、Agent=agent 等用途行）；未指定 role 时跟随全局 pick_profile("all")。
    未知返回 fallback（0 = 无法算比例，不显示百分比、不触发自动压缩）。
    """
    prof = None
    if profile_name:
        try:
            prof = llm.profile_by_name(profile_name)
        except Exception:
            prof = None
        if prof is None:
            for p in config.profiles():
                if p.get("name") == profile_name:
                    prof = p
                    break
    else:
        try:
            prof = config.pick_profile(role or "all")
        except Exception:
            prof = None
    if prof:
        try:
            w = int(prof.get("context_window") or 0)
        except (TypeError, ValueError):
            w = 0
        if w > 0:
            return w
    return fallback


def chats_dir():
    return os.path.join(config.DATA_DIR, "chats")


def _topics_dir():
    return os.path.join(chats_dir(), "topics")


def _meta_path():
    return os.path.join(chats_dir(), "meta.json")


def _now():
    return time.time()


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if d is not None else default
    except Exception:
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _meta():
    m = _read_json(_meta_path(), {"folders": []})
    if not isinstance(m, dict):
        m = {"folders": []}
    m.setdefault("folders", [])
    return m


def _save_meta(m):
    _write_json(_meta_path(), m)


def _tid():
    return uuid.uuid4().hex[:12]


# ---------- 文件夹 ----------
def list_folders():
    return list(_meta()["folders"])


def create_folder(name):
    name = (name or "").strip()
    if not name:
        return None
    m = _meta()
    fid = _tid()
    m["folders"].append({"id": fid, "name": name})
    _save_meta(m)
    return fid


def rename_folder(fid, name):
    name = (name or "").strip()
    if not name:
        return
    m = _meta()
    for f in m["folders"]:
        if f["id"] == fid:
            f["name"] = name
            break
    _save_meta(m)


def delete_folder(fid):
    """删除文件夹：其中话题移到「未分类」根部（话题不删）。"""
    m = _meta()
    m["folders"] = [f for f in m["folders"] if f["id"] != fid]
    _save_meta(m)
    for t in list_topics():
        if t["folder"] == fid:
            move_topic(t["id"], "")


# ---------- 话题 ----------
def topic_path(tid):
    return os.path.join(_topics_dir(), "%s.json" % tid)


def list_topics():
    out = []
    try:
        for fn in os.listdir(_topics_dir()):
            if not fn.endswith(".json"):
                continue
            d = _read_json(os.path.join(_topics_dir(), fn), None)
            if not isinstance(d, dict):
                continue
            out.append({
                "id": d.get("id", fn[:-5]),
                "title": d.get("title", "未命名"),
                "folder": d.get("folder", ""),
                "updated": d.get("updated", 0),
                "msg_count": len(d.get("messages") or []),
            })
    except FileNotFoundError:
        pass
    out.sort(key=lambda x: x["updated"], reverse=True)
    return out


def create_topic(title="新话题", folder=""):
    tid = _tid()
    d = {"id": tid, "title": (title or "新话题").strip(), "folder": folder or "",
         "messages": [], "updated": _now()}
    _write_json(topic_path(tid), d)
    return tid


def load_topic(tid):
    d = _read_json(topic_path(tid), None)
    if not isinstance(d, dict):
        return None
    d.setdefault("messages", [])
    d.setdefault("folder", "")
    d.setdefault("summary", "")   # v0.90 /compress 压缩后的上下文摘要
    return d


def set_topic_summary(tid, summary):
    t = load_topic(tid)
    if not t:
        return
    t["summary"] = (summary or "").strip()
    save_topic(t)


def truncate_topic_messages(tid, keep):
    """压缩上下文后把消息截断为最近 keep 条（保留 summary 承载历史）。"""
    t = load_topic(tid)
    if not t:
        return
    msgs = t.get("messages") or []
    if len(msgs) > keep:
        t["messages"] = msgs[-keep:]
        save_topic(t)


def save_topic(topic):
    if not topic or not topic.get("id"):
        return
    topic["updated"] = _now()
    _write_json(topic_path(topic["id"]), topic)


def rename_topic(tid, title):
    t = load_topic(tid)
    if not t:
        return
    title = (title or "").strip()
    if title:
        t["title"] = title
    save_topic(t)


def move_topic(tid, folder):
    t = load_topic(tid)
    if not t:
        return
    t["folder"] = folder or ""
    save_topic(t)


def delete_topic(tid):
    try:
        os.remove(topic_path(tid))
    except OSError:
        pass


def append_message(tid, role, content, think=None):
    """追加一条消息。think（v1.47）：AI 消息的推理思考内容——仅用于 UI 展示与回顾，
    发送上下文时不会带给模型（构造 messages 只取 role/content）。"""
    t = load_topic(tid)
    if not t:
        return
    msg = {"role": role, "content": content, "ts": _now()}
    if think and str(think).strip():
        msg["think"] = str(think)
    t["messages"].append(msg)
    save_topic(t)


def recent_messages(tid, limit=MAX_HISTORY):
    t = load_topic(tid)
    if not t:
        return []
    msgs = t.get("messages") or []
    return msgs[-limit:]


def update_last_message(tid, content):
    """编辑最后一条消息内容（LM Studio 式编辑，用户/AI 输出均可）。"""
    t = load_topic(tid)
    if not t or not (t.get("messages") or []):
        return False
    t["messages"][-1]["content"] = content
    save_topic(t)
    return True


def pop_last_messages(tid, count=1):
    """删除末尾 count 条消息（重新生成/删除最后一条用）。"""
    t = load_topic(tid)
    if not t:
        return
    msgs = t.get("messages") or []
    if msgs:
        del msgs[-count:]
        save_topic(t)


def append_to_last_message(tid, content, think=None):
    """把新内容追加到最后一条消息末尾（继续生成用）。think（v1.47）：续写若产生
    新的推理思考，一并追加到该消息的 think 字段（内存与落库同步）。"""
    t = load_topic(tid)
    if not t or not (t.get("messages") or []):
        return False
    t["messages"][-1]["content"] += content
    if think and str(think).strip():
        ex = t["messages"][-1].get("think") or ""
        t["messages"][-1]["think"] = ex + str(think)
    save_topic(t)
    return True


def set_topic_messages(tid, msgs):
    t = load_topic(tid)
    if not t:
        return
    t["messages"] = list(msgs)
    save_topic(t)


def export_topic_md(tid, path):
    """导出话题为 markdown。返回 True/False。"""
    t = load_topic(tid)
    if not t:
        return False
    lines = ["# %s" % t["title"], "",
             "（星火笔 AI 对话导出 · %s）" % time.strftime(
                 "%Y-%m-%d %H:%M", time.localtime(t.get("updated", 0))), ""]
    role_name = {"user": "你", "assistant": "AI"}
    for m in t.get("messages") or []:
        lines.append("## %s" % role_name.get(m.get("role"), m.get("role", "?")))
        lines.append("")
        lines.append(str(m.get("content", "")))
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True


# ---------- 项目上下文（不含正文，vibecoding 式可选读取） ----------
def build_project_context(store, project):
    """把当前项目「除正文外」的内容组装成给 AI 的参考上下文；store 可为 None（跳过读盘部分）。

    用户约束：不选项目就不让 AI 读到项目；选择后也**绝不包含章节正文**。
    """
    if project is None:
        return ""
    parts = ["《%s》项目设定参考（**不含任何章节正文**）" % (project.title or "无题")]
    nxt = int((project.state or {}).get("next_chapter", 1))
    parts.append("进度：已写到第 %d 章（下一章 %d）。" % (max(0, nxt - 1), nxt))

    def add(title, text, limit=MAX_CONTEXT_CHARS):
        s = (text or "").strip()
        if s:
            parts.append("【%s】\n%s" % (title, s[:limit]))

    add("故事设定（剧情/世界观/特殊规则）", project.story_brief)
    add("文风偏好", project.story_style)
    add("风格要点", project.story_style_note)
    for e in (project.lore_entries or [])[:30]:
        s = (e.get("content") or "").strip()
        if s:
            parts.append("【设定锚点：%s】\n%s" % (e.get("title", ""), s[:800]))
    add("主AI知识库", project.story_knowledge)
    if project.story_characters:
        rows = ["- %s：%s" % (c.get("name", ""), str(c.get("info", ""))[:300])
                for c in project.story_characters[:20]]
        parts.append("【主AI笔记·重要角色动向】\n" + "\n".join(rows))
    if project.story_ideas:
        rows = ["- %s" % str(i)[:300] for i in project.story_ideas[:20]]
        parts.append("【主AI笔记·后续剧情灵感】\n" + "\n".join(rows))
    if store is not None:
        try:
            chars = store.list_characters()
            rows = []
            for cid, nm, _st in chars[:30]:
                card, lib = store.load_character(cid)
                if not card:
                    continue
                desc = (getattr(card, "description", "") or "").strip()[:150]
                scen = ((getattr(lib, "scenario", "") or "").strip()[:80]
                        if lib is not None else "")
                rows.append("- %s（%s）：%s%s" % (
                    nm, getattr(card, "role", "") or "",
                    desc, ("｜处境：" + scen) if scen else ""))
            if rows:
                parts.append("【角色表（前 %d 名）】\n%s"
                             % (min(len(chars), 30), "\n".join(rows)))
        except Exception:
            pass
        try:
            fs = store.load_foreshadows()
            # v1.102 复用双账本视图（事件线分组/干系人/逾期/下一步），不再手工拼旧单行格式
            try:
                import prompts as prompts_mod
                _cur = 1
                _wc = getattr(project, "written_chapters", None)
                if callable(_wc):
                    try:
                        _cur = int(_wc())
                    except Exception:
                        _cur = 1
                block = prompts_mod.open_foreshadows_text(fs, current_no=_cur)
            except Exception:
                block = ""
            if block and "（当前无开放伏笔）" not in block:
                parts.append("【伏笔台账】\n%s" % block)
            else:
                n_done = sum(1 for f in fs if f.status == "resolved")
                parts.append("【伏笔台账】（当前无开放伏笔；已回收 %d 条）" % n_done)
        except Exception:
            pass
    if project.story_break_style:
        try:
            import book_break
            data = book_break.load_break(project.story_break_style)
            learn = (data or {}).get("learning") or ""
            if learn:
                parts.append("【拆书风格·设计技法学习文本】\n%s" % learn[:2000])
        except Exception:
            pass
    parts.append("（以上均为项目设定，不含章节正文；若问题涉及具体章节内容，请明确说明。）")
    return "\n\n".join(parts)
