# -*- coding: utf-8 -*-
"""星火笔·安卓版 本地 API 服务器（v0.11 全功能移植：复用桌面端 RP 引擎与全部数据层，无 PySide6 依赖）。

由 MainActivity 启动时调用：bootstrap 把数据目录指向 Android 私有目录，起 127.0.0.1 随机端口
ThreadingHTTPServer；WebView 前端（assets/www）通过 fetch 访问 /api/* 完成
项目设定/角色管理/生成审查/故事档案/去AI味/导出 全部闭环。
"""
import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import config
import engine as engine_mod
import llm
import main_ai
import storage
import book_break
import chat_lib
import web_search
import style_extract
from models import (CHAPTER_STATUS_APPROVED, Chapter, CharacterCard, Foreshadow,
                   InfoLibrary, NovelProject)

_SERVER = None
_LOCK = threading.Lock()
_TASKS = {}          # v0.12 生成任务：id -> {logs, done, error, result}
_TASK_SEQ = [0]


def _new_task():
    # 注意：本函数在 _dispatch 持 _LOCK 的上下文中被调用——不能再 acquire _LOCK（非重入锁会死锁）。
    # 任务字典读写由 GIL 保证原子性，足够安全。
    _TASK_SEQ[0] += 1
    tid = "t%d" % _TASK_SEQ[0]
    _TASKS[tid] = {"logs": [], "done": False, "error": "", "result": None,
                   # v0.15 生成前剧情点确认关卡：pending 时前端弹窗，确认后 event.set() 放行任务线程
                   "pending": False, "pending_beats": None, "pending_dir": "",
                   "event": None, "confirm_result": None,
                   # v0.28 果断停止：stop_ev 置位 → LLM 调用立即中断（不再等本次请求写完）
                   "stop_ev": threading.Event()}
    return tid


def _finish_task(tid, result=None, error=""):
    t = _TASKS.get(tid)
    if t:
        t["result"] = result
        t["error"] = error
        t["done"] = True


def _do_task_status(d):
    tid = str(d.get("task_id") or "")
    since = 0
    try:
        since = int(d.get("since") or 0)
    except (TypeError, ValueError):
        since = 0
    t = _TASKS.get(tid)
    if t is None:
        return {"error": "任务不存在"}
    logs = list(t["logs"][since:])
    out = {"ok": True, "done": t["done"], "error": t["error"],
           "result": t["result"], "logs": logs, "count": len(t["logs"])}
    # v0.21 一键成书：任务进度（已写/目标章数）
    if t.get("progress"):
        out["progress"] = t["progress"]
    # v0.15 剧情点确认关卡：任务暂停等待用户确认，把剧情点清单交给前端弹窗
    if t.get("pending"):
        out["pending"] = True
        out["beats"] = t.get("pending_beats") or []
        out["direction"] = t.get("pending_dir") or ""
    return out


def _beats_confirm_for(tid):
    """生成前剧情点确认关卡回调（任务线程内被 engine 调用）：
    标记任务 pending 并阻塞，等前端 /task_confirm 写入结果后继续。
    返回 list=用户确认后剧情点 / None=沿用主AI规划（跳过确认）。"""
    def cb(beats, direction):
        t = _TASKS[tid]
        t["pending"] = True
        t["pending_beats"] = list(beats)
        t["pending_dir"] = str(direction or "")
        t["confirm_result"] = None
        ev = threading.Event()
        t["event"] = ev
        ev.wait()
        res = t["confirm_result"]
        t["pending"] = False
        t["pending_beats"] = None
        t["pending_dir"] = ""
        t["event"] = None
        return res
    return cb


def _do_task_confirm(d):
    """前端确认/跳过剧情点确认关卡：写入结果并放行任务线程。"""
    tid = str(d.get("task_id") or "")
    t = _TASKS.get(tid)
    if t is None:
        return {"error": "任务不存在"}
    if not t.get("pending") or t["event"] is None:
        return {"error": "任务未在等待确认"}
    beats = d.get("beats")
    if isinstance(beats, list):
        beats = [str(b).strip() for b in beats if str(b).strip()] or None
    t["confirm_result"] = beats
    t["event"].set()
    return {"ok": True}


def bootstrap(files_dir):
    """把数据目录指向 Android 应用私有目录（可写），config/storage/engine 均可在运行时重定位。"""
    data_dir = os.path.join(files_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    config.DATA_DIR = data_dir
    config.CONFIG_PATH = os.path.join(data_dir, "config.json")
    storage.PROJECTS_DIR = os.path.join(files_dir, "projects")
    storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
    os.makedirs(storage.PROJECTS_DIR, exist_ok=True)
    engine_mod._ROOT = files_dir
    return data_dir


# ---------- 数据访问 ----------
_CURRENT_DIR = [None]   # 单项目语境：当前/最近导入的项目目录（无则取 index 第一个）
_NEW_MARK = "__new_project__"   # v0.16 新建语境：清空当前指向但禁止 fallback 到已有项目
_ACTIVITY = [None]      # v0.13 Java 侧 MainActivity 引用（Java 对象的 Python 代理），用于文件选择/分享

def _act_call(act, name, *args):
    """调用 Java 侧 MainActivity 的方法（v1.53 修复）。

    Chaquopy 的 callAttr 是【Java 侧】com.chaquo.python.PyObject 的 API；Python 侧拿到的是
    Java 对象的 Python 代理，直接 act.method(...) 即可。此前 10 处把方法调用写成了 callAttr
    形式（Python 侧没有这个属性），必然抛 AttributeError: 'MainActivity' object has no
    attribute 'callAttr'——方向切换/分享/选文件/语音这些桥接全是坏的。
    这里统一封装：优先直接调用，代理确实没有该方法才回退 callAttr。
    """
    fn = getattr(act, name, None)
    if callable(fn):
        return fn(*args)
    ca = getattr(act, "callAttr", None)
    if callable(ca):
        return ca(name, *args)
    raise AttributeError("Activity 上找不到可调用方法：%s" % name)


def _current():
    cur = _CURRENT_DIR[0]
    if cur == _NEW_MARK:
        return None, None
    if cur:
        store = storage.ProjectStore(cur)
        project = store.load_project()
        if project:
            return store, project
    dirs = storage.list_projects()
    if not dirs:
        return None, None
    store = storage.ProjectStore(dirs[0]["dir"])
    project = store.load_project()
    return store, project


def _engine(store, log_fn):
    return engine_mod.NovelEngine(store, log_fn)


def _logs_sink(logs):
    def fn(kind, msg):
        logs.append({"kind": kind, "msg": msg})
    return fn


def _p(d):
    return str(d.get("k") or "").strip()


# ---------- 项目 ----------
def _state(d):
    store, project = _current()
    if not project:
        return {"ok": True, "project": None}
    idxs = store.list_chapter_indices()
    return {"ok": True, "project": {
        "title": project.title, "brief": project.story_brief or "",
        "world_view": project.story_world or "", "special_rules": project.story_rules or "",
        "style": project.story_style or "",
        "style_note": project.story_style_note or "",
        "style_ref": project.story_style_ref or "",
        "tech_source": project.story_tech_source or "",
        "techniques": project.story_techniques or "",
        "writer_prompt": project.story_writer_prompt or "",
        "main_prompt": project.story_main_prompt or "",
        "title_rules": project.story_title_rules or "",
        "next_chapter": int((project.state or {}).get("next_chapter", 1) or 1),
        "chapters": len(idxs),
        "characters": len(store.list_characters()),
        "summary": (project.story_summary or "")[:120],
        "break_style": project.story_break_style or "",
    }}


def _do_project_create(d):
    name = str(d.get("name") or "").strip() or "我的故事"
    project = storage.create_project(name)
    store = storage.ProjectStore(project.dir_name)
    _CURRENT_DIR[0] = project.dir_name
    _fill_project(project, d)
    store.save_project(project)
    return {"ok": True, "name": name}


def _fill_project(project, d):
    project.title = str(d.get("name") or "").strip() or project.title
    project.story_brief = str(d.get("brief") or "").strip()
    project.story_world = str(d.get("world_view") or "").strip()
    project.story_rules = str(d.get("special_rules") or "").strip()
    project.story_style = str(d.get("style") or "").strip()
    project.story_style_note = str(d.get("style_note") or "").strip()
    project.story_style_ref = str(d.get("style_ref") or "").strip()
    project.story_tech_source = str(d.get("tech_source") or "").strip()
    tech = d.get("techniques")
    if isinstance(tech, list):
        project.story_techniques = "\n".join(str(x).strip() for x in tech if str(x).strip())
    elif isinstance(tech, str):
        project.story_techniques = tech.strip()
    project.story_writer_prompt = str(d.get("writer_prompt") or "").strip()
    project.story_main_prompt = str(d.get("main_prompt") or "").strip()
    project.story_title_rules = str(d.get("title_rules") or "").strip()
    # v1.56 拆书风格参考（一键成书「拆书设计风格」下拉所选；空=不使用）
    project.story_break_style = str(d.get("break_style") or "").strip()


def _do_project_save(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    _fill_project(project, d)
    store.save_project(project)
    return {"ok": True}


def _do_project_title_rules(d):
    """v1.65 只更新章节标题命名规则（重设计卡片/文风参考的「恢复默认规则」按钮用；
    不走 _fill_project 全量覆盖）。"""
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    project.story_title_rules = str(d.get("text") or "").strip()
    store.save_project(project)
    return {"ok": True}


# ---------- 书架（v0.16 多项目） ----------
def _do_projects(d):
    """书架：列出全部项目，标记当前项目。"""
    cur = _CURRENT_DIR[0]
    out = []
    for it in storage.list_projects():
        try:
            store = storage.ProjectStore(it["dir"])
            p = store.load_project()
            if p is None:
                continue
            idxs = store.list_chapter_indices()
            out.append({
                "dir": it["dir"],
                "title": p.title or it["title"],
                "brief": (p.story_brief or "")[:60],
                "next_chapter": int((p.state or {}).get("next_chapter", 1) or 1),
                "chapters": len(idxs),
                "characters": len(store.list_characters()),
                "current": it["dir"] == cur,
            })
        except Exception:
            continue
    return {"ok": True, "projects": out}


def _do_project_switch(d):
    dir_name = str(d.get("dir") or "").strip()
    if not any(x["dir"] == dir_name for x in storage.list_projects()):
        return {"error": "项目不存在"}
    _CURRENT_DIR[0] = dir_name
    return {"ok": True, "dir": dir_name}


def _do_project_delete(d):
    dir_name = str(d.get("dir") or "").strip()
    if not any(x["dir"] == dir_name for x in storage.list_projects()):
        return {"error": "项目不存在"}
    if _CURRENT_DIR[0] == dir_name:
        return {"error": "当前项目不能删除，请先切换到其他项目"}
    try:
        storage.delete_project(dir_name)   # 无返回值：目录删除 + index 移除
    except Exception as e:
        return {"error": "删除失败：%s" % e}
    return {"ok": True}


def _do_project_new(d):
    """新建项目语境：清空当前指向（防 fallback）；填好表单后保存走 project_create（避免误建空项目）。"""
    _CURRENT_DIR[0] = _NEW_MARK
    return {"ok": True}


def _do_voice_input(d):
    """唤起系统语音识别（RecognizerIntent）：结果经 Java onActivityResult → 前端 __voiceReady 回调。"""
    act = _ACTIVITY[0]
    if act is None:
        return {"error": "当前环境不支持系统语音识别（桌面测试环境）"}
    try:
        _act_call(act, "launchVoiceInput")
        return {"ok": True}
    except Exception as e:
        return {"error": "语音识别唤起失败：%s" % e}


def _do_lore_list(d):
    store, project = _current()
    if project is None:
        return {"ok": True, "entries": []}
    return {"ok": True, "entries": project.lore_entries or []}


def _do_lore_save(d):
    store, project = _current()
    if project is None:
        return {"error": "无项目"}
    entries = d.get("entries")
    if isinstance(entries, list):
        clean = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            title = str(e.get("title") or "").strip()
            if not title:
                continue
            clean.append({
                "id": str(e.get("id") or ""),
                "title": title,
                "keys": [str(k).strip() for k in (e.get("keys") or []) if str(k).strip()],
                "content": str(e.get("content") or "").strip(),
                "always": bool(e.get("always")),
            })
        project.lore_entries = clean
        store.save_project(project)
    return {"ok": True}


# ---------- 章节写作计划 ----------
def _do_plan_get(d):
    store, project = _current()
    if project is None:
        return {"ok": True, "plans": []}
    return {"ok": True, "plans": project.chapter_plans or []}


def _do_plan_add(d):
    store, project = _current()
    if project is None:
        return {"error": "无项目"}
    try:
        s = int(d.get("start") or 1)
        e = int(d.get("end") or s)
    except (TypeError, ValueError):
        return {"error": "章数须为整数"}
    note = str(d.get("note") or "").strip()
    if not note:
        return {"error": "计划内容不能为空"}
    if e < s:
        e = s
    plans = [p for p in (project.chapter_plans or []) if not (s <= int(p.get("start", 0)) <= e)]
    plans.append({"start": s, "end": e, "note": note})
    project.chapter_plans = plans
    store.save_project(project)
    return {"ok": True}


def _do_plan_del(d):
    store, project = _current()
    if project is None:
        return {"error": "无项目"}
    try:
        idx = int(d.get("index")) if d.get("index") is not None else -1
    except (TypeError, ValueError):
        return {"error": "索引无效"}
    plans = list(project.chapter_plans or [])
    if 0 <= idx < len(plans):
        plans.pop(idx)
        project.chapter_plans = plans
        store.save_project(project)
    return {"ok": True}


# ---------- 角色 ----------
def _character_list(d):
    store, project = _current()
    if store is None:
        return {"ok": True, "characters": []}
    out = []
    for cid, name, status in store.list_characters():
        card, _ = store.load_character(cid)
        out.append({"id": cid, "name": name, "status": status,
                    "category": (card.category if card else "") or "",
                    # v1.51 废弃角色库：附废弃原因与章节，前端「废弃库」视图展示
                    "reason": (card.discarded_reason if card else "") or "",
                    "dch": int(card.discarded_chapter or 0) if card else 0})
    return {"ok": True, "characters": out}


def _do_character_get(d):
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    cid = str(d.get("cid") or "")
    card, lib = store.load_character(cid)
    if card is None:
        return {"error": "找不到角色"}
    return {"ok": True, "card": card.to_dict(), "lib": lib.to_dict() if lib else {}}


def _do_character_save(d):
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    cd = d.get("card") or {}
    cid = str(cd.get("id") or "")
    if not cid:
        return {"error": "缺少角色 id"}
    card, lib = store.load_character(cid)
    if card is None:
        card = CharacterCard(str(cd.get("name") or "无名"))
        lib = None
    name = str(cd.get("name") or "").strip()
    if name:
        card.name = name
    for f in ("role", "description", "scenario", "personality", "values", "goals",
              "fears", "speech_style", "backstory", "relationships", "appearance",
              "first_mes", "mes_example", "system_prompt", "age", "gender", "category"):
        if f in cd:
            setattr(card, f, str(cd.get(f) or ""))
    if "status" in cd:
        card.status = str(cd.get("status") or "active")
    if "traits" in cd and isinstance(cd.get("traits"), list):
        card.traits = [str(t).strip() for t in cd["traits"] if str(t).strip()]
    if lib is None:
        lib = InfoLibrary(cid)
    ld = d.get("lib") or {}
    if "scenario" in ld:
        lib.scenario = str(ld.get("scenario") or "")
    if "notes" in ld:
        lib.notes = str(ld.get("notes") or "")
    for f in ("events", "knowledge", "secrets"):
        if f in ld and isinstance(ld.get(f), list):
            setattr(lib, f, [dict(x) for x in ld[f] if isinstance(x, dict)]
                    if f != "secrets" else [str(x) for x in ld[f] if str(x).strip()])
    store.save_character(card, lib)
    return {"ok": True, "id": card.id}


def _do_character_create(d):
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    name = str(d.get("name") or "").strip()
    if not name:
        import name_gen
        name = name_gen.generate_name()
    card = CharacterCard(name)
    card.role = str(d.get("role") or "").strip()
    card.category = str(d.get("category") or "").strip()
    store.save_character(card, InfoLibrary(card.id))
    return {"ok": True, "id": card.id, "name": card.name}


def _do_character_delete(d):
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    cid = str(d.get("cid") or "")
    store.delete_character(cid)
    return {"ok": True}


def _do_character_batch(d):
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    status = str(d.get("status") or "")
    cids = d.get("cids") or []
    n = 0
    for cid in cids:
        card, lib = store.load_character(str(cid))
        if card:
            card.status = status or card.status
            store.save_character(card, lib or InfoLibrary(card.id))
            n += 1
    return {"ok": True, "count": n}


def _do_character_ai(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "请先创建项目"}
    desc = str(d.get("desc") or "").strip()
    if not desc:
        return {"error": "描述不能为空"}
    try:
        data = main_ai.generate_character_ai(desc, project, store)
        card = main_ai.character_from_data(data, created_by="ai")
    except Exception as e:
        traceback.print_exc()
        return {"error": "生成失败：%s" % e}
    store.save_character(card, InfoLibrary(card.id))
    return {"ok": True, "id": card.id, "name": card.name, "role": card.role}


def _do_character_ai_batch(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "请先创建项目"}
    desc = str(d.get("desc") or "").strip()
    if not desc:
        return {"error": "描述不能为空"}
    try:
        cards_data = main_ai.generate_batch_roles(desc, project, store)
    except Exception as e:
        traceback.print_exc()
        return {"error": "拆解失败：%s" % e}
    out = []
    for data in cards_data:
        try:
            card = main_ai.character_from_data(data, created_by="ai")
            store.save_character(card, InfoLibrary(card.id))
            out.append({"id": card.id, "name": card.name, "role": card.role})
        except Exception:
            continue
    return {"ok": True, "created": out}


def _do_character_import(d):
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    try:
        data = json.loads(str(d.get("json_text") or "{}"))
    except Exception as e:
        return {"error": "JSON 解析失败：%s" % e}
    try:
        name = str((data.get("data") or {}).get("name") or data.get("name") or "").strip()
        if not name:
            return {"error": "缺少角色名 name"}
        card = CharacterCard(name)
        cd = data.get("data") or data
        for f in ("role", "description", "scenario", "personality", "values", "goals",
                  "fears", "speech_style", "backstory", "relationships", "appearance",
                  "first_mes", "mes_example", "system_prompt"):
            if cd.get(f):
                setattr(card, f, str(cd.get(f)))
        store.save_character(card, InfoLibrary(card.id))
    except Exception as e:
        traceback.print_exc()
        return {"error": "导入失败：%s" % e}
    return {"ok": True, "id": card.id, "name": card.name}


def _do_classify(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "请先创建项目"}
    try:
        roles = main_ai.classify_characters(project, store)
    except Exception as e:
        traceback.print_exc()
        return {"error": "分类失败：%s" % e}
    return {"ok": True, "roles": roles or {}}


# ---------- 风格 / 技巧（AI 提炼，前端确认后随 project_save 写入） ----------
def _do_style_extract(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "请先创建项目"}
    try:
        points = main_ai.extract_style_points(project, store)
    except Exception as e:
        traceback.print_exc()
        return {"error": "提炼失败：%s" % e}
    return {"ok": True, "points": points or []}


# v0.83 撤销「写作技巧库」功能（tech_extract 路由移除；主AI可直接联网搜索/锚点/提示词控制）


# ---------- 生成 / 定稿 / 全自动 ----------
def _run_generate_task(store, project, d, logs, tid=None):
    """在后台线程执行：逐章生成或全自动连写；logs 实时累积供 task_status 轮询。
    tid 非空且 confirm_beats=True 时启用生成前剧情点确认关卡（v0.15）。
    v0.28：绑定线程级停止事件，停止即立即中断当前 LLM 请求。"""
    t = _TASKS.get(tid) if tid else None
    _abort_ev = t["stop_ev"] if t else None
    if _abort_ev is not None:
        llm.set_abort(_abort_ev)
    try:
        return _run_generate_task_inner(store, project, d, logs, tid)
    finally:
        if _abort_ev is not None:
            llm.set_abort(None)


def _run_generate_task_inner(store, project, d, logs, tid=None):
    eng = engine_mod.NovelEngine(store, _logs_sink(logs))
    t = _TASKS.get(tid) if tid else None   # 停止检查用
    confirm_beats = bool(d.get("confirm_beats")) and tid is not None
    beats_confirm = _beats_confirm_for(tid) if confirm_beats else None
    mode = str(d.get("mode") or "one")
    if mode == "auto":
        try:
            n = max(1, min(50, int(d.get("chapters") or 1)))
        except (TypeError, ValueError):
            n = 1
        directive = str(d.get("directive") or "").strip()
        done = []
        for i in range(n):
            if t.get("stop"):
                return {"ok": True, "partial": True, "done": done,
                        "error": "已停止（写完当前章后停）"}
            try:
                logs.append({"kind": "info", "msg": "═══ 全自动连写 第 %d/%d 章 ═══" % (i + 1, n)})
                ch = eng.generate_draft(project, user_directive=directive,
                                        user_feedback="", user_draft="",
                                        beats_confirm=beats_confirm)
                eng.finalize_chapter(project, ch)
                done.append({"seq": ch.index, "title": ch.title or ""})
                directive = ""
            except llm.StopRequested:
                return {"ok": True, "partial": True, "done": done,
                        "error": "已停止：立即中断当前章节写作"}
            except Exception as e:
                return {"ok": True, "partial": True, "done": done,
                        "error": "第 %d 章失败：%s" % (len(done) + 1, e)}
        return {"ok": True, "done": done}
    # 逐章
    beats = d.get("beats")
    if isinstance(beats, list):
        beats = [str(b).strip() for b in beats if str(b).strip()] or None
    directive = str(d.get("directive") or "").strip()
    draft = str(d.get("draft") or "").strip()
    try:
        ch = eng.generate_draft(
            project,
            user_directive=directive,
            user_feedback="",
            user_draft=draft,
            beats_override=beats,
            beats_confirm=beats_confirm)
    except Exception as e:
        traceback.print_exc()
        return {"error": "生成失败：%s" % e}
    return _chapter_payload(ch, logs)


def _do_generate(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "请先在「项目」页创建/保存项目"}
    tid = _new_task()
    t = _TASKS[tid]

    def work():
        try:
            result = _run_generate_task(store, project, d, t["logs"], tid)
            _finish_task(tid, result=result)
        except Exception as e:
            traceback.print_exc()
            _finish_task(tid, error="生成失败：%s" % e)

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "task_id": tid}


def _do_book_auto(d):
    """一键成书（v0.21）：描述小说想法 + 总章节数 + 本次生成到多少章 → AI 自动立项（书名/剧情/世界观/规则）
    → 创建项目（书架可见）→ 自动生成核心角色 → 全自动连写 N 章；随时可停止。

    total_chapters：全书计划总章节数（写入项目 volume_target，供主AI规划节奏与完本判断）；
    chapters：本次连写目标（可小于总章节数。continue 模式下为目标章号：从当前进度续写到它）。
    continue：v0.42 继续写——非空时在「当前项目」上从 next_chapter 自动连写剩余章节
    （跳过立项/建项目/核心角色；失败或停止后可点「继续写」往前推进）。
    v1.56 新建模式可选套用面板 AI 设置（与 PC gui_book._BookWorker.run 同语义，只在新建分支生效、
    继续模式不覆盖项目已有设置）：book_title=手动书名/项目名（留空才由 AI 起名）；style_note=文风参考·
    风格要点；style_ref=参考文风样本；main_prompt=主AI全局提示词；writer_prompt=正文AI角色提示词；
    break_style=拆书设计风格名（仅当拆书风格库存在该风格时套用，失败只记 warn 不中断成书）；
    scene_cards_active=从总库勾选带入本项目的情景卡名列表（复制卡内容进 project.scene_cards）。
    任务化：t["stop"] 置位即停止（写完当前章后结束，项目保留书架）。返回 task_id。"""
    idea = str(d.get("idea") or "").strip()
    cont = bool(d.get("continue"))
    if not idea and not cont:
        return {"error": "请先描述你想写什么小说"}
    try:
        chapters = max(1, min(100, int(d.get("chapters") or 5)))
    except (TypeError, ValueError):
        return {"error": "章节数需为正整数"}
    try:
        total_chapters = max(1, min(3000, int(d.get("total_chapters") or 0)))
    except (TypeError, ValueError):
        total_chapters = 0
    auto_chapters = bool(d.get("auto_chapters"))   # v1.45 AI 自动判断章节数
    tid = _new_task()
    t = _TASKS[tid]

    def work():
        llm.set_abort(t["stop_ev"])
        try:
            logs = t["logs"]

            def sink(kind, msg):
                logs.append({"kind": kind, "msg": msg})

            store = eng = project = None
            done_init = 0
            title = ""
            if cont:
                # ① 继续写：载入当前项目（不重新立项）
                pd = _CURRENT_DIR[0] if _CURRENT_DIR else ""
                if not pd:
                    _finish_task(tid, error="当前没有可继续的项目——请先从头「开始一键成书」创建。")
                    return
                store = storage.ProjectStore(pd)
                project = store.load_project()
                if project is None:
                    _finish_task(tid, error="项目不存在或已损坏，无法继续。")
                    return
                done_init = max(0, int(project.state.get("next_chapter", 1)) - 1)
                # v1.57 全书完成后点「继续写」= 主动要求继续，解除完结标记再写
                # （生成页全自动连写受完结标记保护，不会误续写）
                if project.state.get("story_complete"):
                    project.state["story_complete"] = False
                    store.save_project(project)
                    sink("info", "已解除完结状态，继续自动连写剩余章节。")
                title = project.title or "当前项目"
                sink("info", "继续模式：在《%s》上从第 %d 章继续自动连写…" % (title, done_init + 1))
            else:
                sink("info", "开始一键成书：正在由 AI 立项…")
                # 1) 书名/项目名：用户手动指定优先（v1.56 book_title），留空才由 AI 按想法起名
                #    （失败回退自动名）——书名同时作为项目标题与后续全部日志里的书名。
                title = str(d.get("book_title") or "").strip()
                if not title:
                    try:
                        title = main_ai.plan_title(idea)
                    except Exception as e:
                        sink("warn", "起书名失败（%s），使用自动书名。" % e)
                title = (title or "").strip() or "AI 新书"
                sink("info", "书名确定：《%s》" % title)

                # 2) AI 起草三栏设定（剧情/世界观/规则）
                sink("info", "正在起草故事设定（剧情 / 世界观 / 特殊规则）…")
                data = main_ai.plan_story_ai("", idea, "%d 章" % chapters,
                                             ("story", "world", "rules"))
                if not isinstance(data, dict):
                    data = {}
                story = str(data.get("story") or "").strip()
                world = str(data.get("world") or "").strip()
                rules = str(data.get("rules") or "").strip()
                if not (story or world or rules):
                    _finish_task(tid, error="AI 没有生成出故事设定，请换个想法重试。")
                    return
                sink("info", "故事设定起草完成（剧情 %d 字 / 世界观 %d 字 / 规则 %d 字）。"
                     % (len(story), len(world), len(rules)))

                # v1.45「AI 自动判断章节数」：按想法+三栏设定判断全书总章数，本次连写也直接写到该数
                if auto_chapters:
                    ai_total = main_ai.plan_chapters(
                        idea, story=story, world=world, rules=rules,
                        author_constraint=idea,
                        default=(int(total_chapters or 0) or 30))
                    total_chapters = max(1, int(ai_total))
                    chapters = total_chapters
                    sink("info", "AI 自动判断：本书全书约 %d 章，本次连写直接写到该数。"
                         % total_chapters)

                # 3) 创建项目并填入设定，切为当前项目（停止后也在书架可见、可正常管理）
                project = storage.create_project(title)
                store = storage.ProjectStore(project.dir_name)
                project.story_brief = story
                project.story_world = world
                project.story_rules = rules
                # v1.56 一键成书套用面板 AI 设置（与 PC gui_book._BookWorker.run 同语义：
                # 新建时把面板的文风/提示词/拆书风格/情景卡全部写入新项目，主AI每章注入）。
                sn = str(d.get("style_note") or "").strip()
                if sn:
                    project.story_style_note = sn
                    sink("info", "已套用文风参考·风格要点（%d 字）。" % len(sn))
                bs = str(d.get("break_style") or "").strip()
                if bs:
                    # 拆书设计风格：仅当风格库确实有该风格才套用；查库失败/不存在只记 warn，
                    # 绝不中断成书（风格为空或无效时项目按无拆书风格走）。
                    try:
                        if book_break.load_break(bs) is not None:
                            project.story_break_style = bs
                            sink("info", "已套用拆书设计风格：%s（主AI每章学习其剧情设计技法）。" % bs)
                        else:
                            sink("warn", "拆书设计风格「%s」不存在，未套用（可到拆书工坊保存后重试）。" % bs)
                    except Exception as e:
                        sink("warn", "拆书设计风格「%s」套用失败（%s），已跳过。" % (bs, e))
                sr = str(d.get("style_ref") or "").strip()
                if sr:
                    project.story_style_ref = sr
                    sink("info", "已套用参考文风样本（%d 字）。" % len(sr))
                mp = str(d.get("main_prompt") or "").strip()
                if mp:
                    project.story_main_prompt = mp
                    sink("info", "已套用主AI全局提示词（%d 字）。" % len(mp))
                wp = str(d.get("writer_prompt") or "").strip()
                if wp:
                    project.story_writer_prompt = wp
                    sink("info", "已套用正文AI角色提示词（%d 字）。" % len(wp))
                # 从总库勾选的情景卡名 → 把总库卡内容复制进新项目库 project.scene_cards
                # （source="user"，与总库独立；主AI每章按正文类型从中选卡）。
                raw_sc = d.get("scene_cards_active")
                sc_names = ([str(x).strip() for x in raw_sc if str(x).strip()]
                            if isinstance(raw_sc, list) else [])
                if sc_names:
                    try:
                        _lib_sc = {str(c.get("name") or "").strip(): c
                                   for c in (config.load_config()
                                             .get("writer_scene_cards") or [])
                                   if isinstance(c, dict)
                                   and str(c.get("name") or "").strip()
                                   and str(c.get("content") or "").strip()}
                        project.scene_cards = [{"name": nm,
                                                "content": str(_lib_sc[nm].get("content") or ""),
                                                "source": "user",
                                                "category": str(_lib_sc[nm].get("category") or "")}
                                               for nm in sc_names if nm in _lib_sc]
                    except Exception as e:
                        project.scene_cards = []
                        sink("warn", "情景卡带入失败（%s），本项目库留空。" % e)
                    if project.scene_cards:
                        project.scene_cards_active = [c["name"] for c in project.scene_cards]
                        sink("info", "已把 %d 张总库情景卡带入新项目（主AI每章按正文类型从中选卡，"
                             "缺匹配类型时自做一张只进本库）。" % len(project.scene_cards))
                if total_chapters > 0:
                    project.volume_target = total_chapters
                    project.state["volume_plan"] = {
                        "target_chapters": total_chapters,
                        "description": "一键成书设定的全书总章节计划",
                    }
                store.save_project(project)
                _CURRENT_DIR[0] = project.dir_name
                sink("info", "项目已创建：《%s》（书架里现在就能看到它）%s"
                     % (title, "；全书计划 %d 章" % total_chapters if total_chapters > 0 else ""))

                # 4) 自动生成核心角色 + 连写 N 章
                eng = engine_mod.NovelEngine(store, sink)
                try:
                    eng.ensure_world(project)
                except Exception as e:
                    sink("warn", "自动生成核心角色失败（%s），将直接开始写作。" % e)

            if eng is None:
                eng = engine_mod.NovelEngine(store, sink)

            # 连写循环（继续模式从断点绝对章号续写；新建模式从第 1 章写起）
            target_ch = max(1, int(chapters))
            if cont and target_ch <= done_init:
                sink("info", "《%s》已写到第 %d 章，没有需要继续写的章节。" % (title, done_init))
                _finish_task(tid, result={
                    "ok": True,
                    "msg": "《%s》已写到第 %d 章，无需继续。" % (title, done_init),
                    "dir": project.dir_name, "title": title, "chapters": done_init})
                return
            last = done_init
            for ch_no in range(done_init + 1, target_ch + 1):
                if t.get("stop"):
                    sink("info", "已收到停止指令，暂停自动生成（已写 %d 章，项目已建好可在书架继续）。" % last)
                    break
                sink("info", "═══ 全自动连写 第 %d/%d 章 ═══" % (ch_no, target_ch))
                try:
                    ch = eng.generate_draft(project, beats_confirm=None)
                    if ch is not None:
                        eng.finalize_chapter(project, ch)
                except llm.StopRequested:
                    sink("info", "已停止：立即中断当前章节写作（已写 %d 章，项目已建好可在书架继续）。" % last)
                    break
                except llm.LLMError as e:
                    sink("warn", "第 %d 章失败：%s（已写 %d 章，可点「继续写」往前推进）。" % (ch_no, e, last))
                    break
                except Exception as e:
                    sink("error", "第 %d 章异常：%s" % (ch_no, e))
                    break
                last = ch_no
                t["progress"] = {"done": last, "total": target_ch}
            done = last
            sink("info", "一键成书结束：共完成 %d 章。可在书架找到《%s》继续编辑/生成。"
                 % (done, title))
            _finish_task(tid, result={
                "ok": True,
                "msg": "已创建《%s》并完成 %d 章；停止后项目保留在书架，可随时继续。"
                       % (title, done),
                "dir": project.dir_name, "title": title, "chapters": done,
            })
        except Exception as e:
            traceback.print_exc()
            _finish_task(tid, error="一键成书失败：%s" % e)
        finally:
            llm.set_abort(None)

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "task_id": tid}


def _do_book_stop(d):
    """停止一键成书（v0.28 立即生效：中断当前 LLM 请求，项目保留书架）。"""
    tid = str(d.get("task_id") or "")
    t = _TASKS.get(tid)
    if t is None:
        return {"error": "任务不存在"}
    t["stop"] = True
    t["stop_ev"].set()   # 立即中断当前请求，不再等本章写完
    llm.abort_active_resps()   # v1.43 立即断流：close 在途连接（流式读取立刻抛 StopRequested）
    return {"ok": True}


def _do_generate_auto(d):
    """全自动连写别名（前端 doGenerate 使用 generate_auto 路由，适配 mode=auto）。"""
    d = dict(d)
    d["mode"] = "auto"
    return _do_generate(d)


def _do_finalize(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    seq = int(d.get("seq") or 0)
    ch = store.load_chapter(seq)
    if ch is None:
        return {"error": "找不到第 %d 章草稿" % seq}
    t = str(d.get("title") or "").strip()
    c = str(d.get("content") or "").strip()
    if t:
        ch.title = t
    if c:
        ch.content = c
    eng = engine_mod.NovelEngine(store, _logs_sink([]))
    try:
        eng.finalize_chapter(project, ch)
    except Exception as e:
        traceback.print_exc()
        return {"error": "定稿失败：%s" % e}
    return {"ok": True}


def _do_regenerate(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "请先创建项目"}
    seq = int(d.get("seq") or 0)
    feedback = str(d.get("feedback") or "").strip()
    ch = store.load_chapter(seq)
    if ch is None:
        return {"error": "找不到第 %d 章草稿" % seq}
    logs = []
    eng = engine_mod.NovelEngine(store, _logs_sink(logs))
    try:
        nch = eng.generate_draft(project, user_directive="", user_feedback=feedback,
                                 user_draft="", beats_override=None, beats_confirm=None)
    except Exception as e:
        traceback.print_exc()
        return {"error": "重新生成失败：%s" % e}
    return _chapter_payload(nch, logs)


def _chapter_payload(ch, logs):
    reasoning = ch.reasoning or {}
    review = reasoning.get("review") or {}
    return {
        "ok": True, "title": ch.title or "第 %d 章" % ch.index, "content": ch.content,
        "seq": ch.index,
        "review": {
            "approved": str(review.get("approved")).strip().lower() == "true",
            "pacing": review.get("pacing") or "",
            "issues": [str(x) for x in (review.get("issues") or [])][:6],
            "cliches": [str(x) for x in (review.get("cliches") or [])][:4],
            "scores": review.get("scores") or {},
        },
        "beats": reasoning.get("beats") or [],
        "intent": str((reasoning.get("consolidation") or {}).get("planning_note") or ""),
        "deai": (reasoning.get("deai_report") or {}),
        "logs": logs[-80:],
    }


# ---------- 章节 / 草稿箱 / 时间线 ----------
def _do_chapters(d):
    store, project = _current()
    if store is None or project is None:
        return {"ok": True, "chapters": []}
    out = []
    for idx in store.list_chapter_indices():
        ch = store.load_chapter(idx)
        if ch:
            out.append({"seq": idx, "title": ch.title or "",
                        "status": ch.status or "draft",
                        "chars": len(ch.content or ""),
                        "brief": (ch.content or "")[:40],
                        "vol": int(getattr(ch, "volume", 1) or 1)})
    return {"ok": True, "chapters": out}


def _do_chapter(d):
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    seq = int(d.get("seq") or 0)
    ch = store.load_chapter(seq)
    if ch is None:
        return {"error": "找不到章节"}
    reasoning = ch.reasoning or {}
    review = reasoning.get("review") or {}
    return {"ok": True, "seq": seq, "title": ch.title or "", "content": ch.content or "",
            "volume": int(getattr(ch, "volume", 1) or 1),
            "review": review, "beats": reasoning.get("beats") or [],
            "intent": str((reasoning.get("consolidation") or {}).get("planning_note") or ""),
            "deai": reasoning.get("deai_report") or {},
            "foreshadows": ch.foreshadows or []}


def _do_volume_set(d):
    """分卷（v0.17）：单章归卷，非法卷号拒绝。"""
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    seq = int(d.get("seq") or 0)
    try:
        vol = int(d.get("vol") or 1)
    except (TypeError, ValueError):
        return {"error": "卷号非法"}
    if store.set_chapter_volume(seq, vol):
        return {"ok": True, "seq": seq, "vol": vol}
    return {"error": "归卷失败：章节不存在或卷号非法"}


def _do_chapter_delete(d):
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    seq = int(d.get("seq") or 0)
    ch = store.load_chapter(seq)
    if ch is None:
        return {"error": "找不到章节"}
    try:
        store.backup_chapter_draft(ch, "delete")
        store.delete_chapter(seq)
        # v0.27 删除后重建角色卡：按分章状态轨迹回退到剩余最后章节（小说导入成项目）
        remain = store.list_chapter_indices()
        store.rebuild_world_after_delete(max(remain) if remain else 0)
    except Exception as e:
        return {"error": "删除失败：%s" % e}
    return {"ok": True}


def _do_drafts_list(d):
    store, project = _current()
    if store is None:
        return {"ok": True, "drafts": []}
    return {"ok": True, "drafts": store.list_chapter_drafts()}


def _do_draft_restore(d):
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    fname = str(d.get("fname") or "")
    try:
        ch = store.restore_chapter_draft(fname)
    except Exception as e:
        return {"error": "恢复失败：%s" % e}
    if ch is None:
        return {"error": "草稿不存在"}
    return {"ok": True, "seq": ch.index, "title": ch.title or ""}


def _do_draft_delete(d):
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    fname = str(d.get("fname") or "")
    store.delete_chapter_draft(fname)
    return {"ok": True}


def _do_timeline(d):
    store, project = _current()
    if store is None or project is None:
        return {"ok": True, "timeline": []}
    out = []
    for idx in store.list_chapter_indices():
        ch = store.load_chapter(idx)
        if ch:
            out.append({"seq": idx, "title": ch.title or "",
                        "status": ch.status or "draft", "chars": len(ch.content or ""),
                        "brief": (ch.content or "")[:90],
                        "foreshadows": ch.foreshadows or [],
                        "vol": int(getattr(ch, "volume", 1) or 1)})
    return {"ok": True, "timeline": out}


# ---------- 伏笔看板 ----------
def _overdue(f, current_no, threshold):
    if f.status == "open" and f.planted_chapter and current_no > 0:
        return current_no - f.planted_chapter > threshold
    return False


def _do_foreshadows(d):
    store, project = _current()
    if store is None or project is None:
        return {"ok": True, "foreshadows": [], "stats": {}}
    import prompts as prompts_mod
    threshold = prompts_mod._foreshadow_overdue_chapters()
    current_no = int((project.state or {}).get("next_chapter", 1) or 1)
    fs = []
    for f in store.load_foreshadows():
        fs.append({"id": f.id, "text": f.text, "f_type": f.f_type,
                   "target_char": f.target_char, "status": f.status,
                   "planted_chapter": f.planted_chapter,
                   "resolved_chapter": f.resolved_chapter,
                   "overdue": _overdue(f, current_no, threshold)})
    open_n = sum(1 for f in fs if f["status"] == "open")
    resolved_n = sum(1 for f in fs if f["status"] == "resolved")
    overdue_n = sum(1 for f in fs if f["overdue"])
    return {"ok": True, "foreshadows": fs,
            "stats": {"open": open_n, "resolved": resolved_n, "overdue": overdue_n},
            "threshold": threshold}


def _do_fore_mark(d):
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    ids = set(str(x) for x in (d.get("ids") or []))
    status = str(d.get("status") or "resolved")
    fs = store.load_foreshadows()
    for f in fs:
        if f.id in ids:
            f.status = status
    store.save_foreshadows(fs)
    return {"ok": True}


# ---------- 管理笔记 / 去AI味 / 编辑审稿 ----------
def _do_note_get(d):
    store, project = _current()
    if project is None:
        return {"ok": True, "note": ""}
    return {"ok": True, "note": project.story_summary or ""}


def _do_knowledge_get(d):
    """主AI知识库（v0.19）：主AI长期记忆（联网灵感/设定落定/伏笔关键信息），只读展示。"""
    store, project = _current()
    if project is None:
        return {"ok": True, "knowledge": ""}
    return {"ok": True, "knowledge": project.story_knowledge or ""}


def _do_logs_get(d):
    """生成日志（v0.19）：近 300 条生成/推理日志（与 PC 端同源 read_log）。"""
    store, project = _current()
    if store is None or project is None:
        return {"ok": True, "logs": ""}
    return {"ok": True, "logs": store.read_log(300)}


def _do_chapter_edit(d):
    """编辑已归档章节（v0.19）：修改标题/正文，原版自动备份到草稿箱（对齐 PC 章节管理）。"""
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    seq = int(d.get("seq") or 0)
    ch = store.load_chapter(seq)
    if ch is None:
        return {"error": "找不到章节"}
    title = str(d.get("title") or "").strip()
    if title:
        ch.title = title
    content = d.get("content")
    if isinstance(content, str):
        ch.content = content
    try:
        store.backup_chapter_draft(ch, "edit")
        store.save_chapter(ch)
    except Exception as e:
        return {"error": "保存失败：%s" % e}
    return {"ok": True, "seq": seq, "title": ch.title, "chars": len(ch.content or "")}


def _do_polish(d):
    """AI 段落工具（v0.20）：选中文本就地润色/扩写/缩写/去AI味。"""
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    text = str(d.get("text") or "").strip()
    if not text:
        return {"error": "请先选中要处理的文本"}
    if len(text) > 6000:
        return {"error": "选中文本过长（最多 6000 字），请分段处理"}
    mode = str(d.get("mode") or "polish")
    if mode not in ("polish", "expand", "shorten", "deai"):
        mode = "polish"
    try:
        # v1.68 传 store 启用「涉及人物读取推理」（配置开关 tool_ctx_* 控制，安卓无设置页按默认全开）
        out = main_ai.polish_paragraph(project, text, mode, store=store)
    except Exception as e:
        traceback.print_exc()
        return {"error": "处理失败：%s" % e}
    return {"ok": True, "text": out}


def _do_search(d):
    """全文搜索（v0.20）：在标题/梗概/正文中查关键词。"""
    store, project = _current()
    if store is None:
        return {"ok": True, "results": []}
    kw = str(d.get("kw") or "").strip()
    if not kw:
        return {"ok": True, "results": []}
    try:
        results = store.search_chapters(kw)
    except Exception as e:
        traceback.print_exc()
        return {"error": "搜索失败：%s" % e}
    return {"ok": True, "kw": kw, "results": results}


def _do_swap(d):
    """章节交换/排序（v0.20）：交换两章叙事内容（章号不变，旧版自动备份草稿箱）。"""
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    try:
        a = int(d.get("a") or 0)
        b = int(d.get("b") or 0)
    except (TypeError, ValueError):
        return {"error": "章号非法"}
    ok = store.swap_chapters(a, b)
    if not ok:
        return {"error": "交换失败：章节不存在或章号非法/相同"}
    store.append_log("【交换】第 %d 章与第 %d 章内容互换（排序调整，旧版已备份草稿箱）。" % (a, b))
    return {"ok": True, "a": a, "b": b}


def _do_stats(d):
    """写作统计（v0.20）：总章数/总字数/各卷分布/当前卷进度。"""
    store, project = _current()
    if store is None:
        return {"ok": True, "stats": None}
    try:
        stats = store.project_stats()
    except Exception as e:
        traceback.print_exc()
        return {"error": "统计失败：%s" % e}
    return {"ok": True, "stats": stats}


def _do_rewrite(d):
    """重写此章（v0.20 补齐）：回滚世界状态到该章前，删除该章及之后章节，可重新生成。

    与 PC 端「重写此章」同语义：先用草稿箱留存旧章节（engine.rewrite_from 内部处理）。
    """
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    seq = int(d.get("seq") or 0)
    if seq < 1:
        return {"error": "章号非法"}
    eng = engine_mod.NovelEngine(store, _logs_sink([]))
    try:
        ok = eng.rewrite_from(project, seq)
    except Exception as e:
        traceback.print_exc()
        return {"error": "重写失败：%s" % e}
    if not ok:
        return {"error": "无法回滚：该章之前没有世界状态快照（每章完成后才会留存快照）。"}
    return {"ok": True, "seq": seq}


def _do_volume_merge(d):
    """整卷合并（v0.20 补齐）：把旧卷全部章节并入目标卷（对齐 PC 分卷管理）。"""
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    try:
        old_vol = int(d.get("old_vol") or 0)
        new_vol = int(d.get("new_vol") or 0)
    except (TypeError, ValueError):
        return {"error": "卷号非法"}
    n = store.rename_volume(old_vol, new_vol)
    if n <= 0:
        return {"error": "没有可合并的章节（卷号相同/不存在/非法）。"}
    store.append_log("【分卷】第 %d 卷 %d 章并入第 %d 卷。" % (old_vol, n, new_vol))
    return {"ok": True, "moved": n, "old_vol": old_vol, "new_vol": new_vol}


def _do_deai_run(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    seq = int(d.get("seq") or 0)
    ch = store.load_chapter(seq)
    if ch is None:
        return {"error": "找不到章节"}
    mode = str(d.get("mode") or "clean")
    rules = str(d.get("rules") or "")
    directive = str(d.get("directive") or "")
    try:
        polished = main_ai.deai_chapter(project, store, ch, mode=mode,
                                        rules=rules, directive=directive)
    except Exception as e:
        traceback.print_exc()
        return {"error": "治理失败：%s" % e}
    return {"ok": True, "seq": seq, "polished": polished}


def _do_deai_apply(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    seq = int(d.get("seq") or 0)
    polished = str(d.get("polished") or "")
    if not polished:
        return {"error": "缺少治理后正文"}
    ch = store.load_chapter(seq)
    if ch is None:
        return {"error": "找不到章节"}
    ch.content = polished
    eng = engine_mod.NovelEngine(store, _logs_sink([]))
    try:
        eng.apply_deai(project, seq, polished)
    except Exception as e:
        traceback.print_exc()
        return {"error": "合并失败：%s" % e}
    return {"ok": True, "seq": seq}


def _do_editor_review(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    seq = int(d.get("seq") or 0)
    ch = store.load_chapter(seq)
    if ch is None:
        return {"error": "找不到章节"}
    try:
        data = main_ai.editor_review_chapter(project, store, ch)
    except Exception as e:
        traceback.print_exc()
        return {"error": "审稿失败：%s" % e}
    return {"ok": True, "data": data if isinstance(data, dict) else {}}


# ---------- 项目对接（v0.13：与 PC 端互导） ----------
def _do_project_export(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    import time as _time
    base = os.path.dirname(storage.PROJECTS_DIR)
    exp = os.path.join(base, "export")
    os.makedirs(exp, exist_ok=True)
    safe = "".join(c for c in (project.title or "项目") if c not in '\\/:*?"<>|') or "项目"
    fname = "星火笔_%s_%s.zip" % (safe, _time.strftime("%Y%m%d_%H%M%S"))
    path = os.path.join(exp, fname)
    ok = storage.export_project(store.dir_name, path)
    if not ok:
        return {"error": "打包失败"}
    shared = False
    act = _ACTIVITY[0]
    if act is not None:
        try:
            _act_call(act, "shareFile", path)
            shared = True
        except Exception:
            shared = False
    return {"ok": True, "path": path, "shared": shared}


def _do_project_import(d):
    fname = str(d.get("fname") or "").strip()
    if not fname or "/" in fname or "\\" in fname or ".." in fname:
        return {"error": "文件名不合法"}
    path = os.path.join(os.path.dirname(storage.PROJECTS_DIR), "imports", fname)
    if not os.path.isfile(path):
        return {"error": "导入文件不存在"}
    r = storage.import_project(path)
    if not r:
        return {"error": "导入失败：zip 无效或不含项目"}
    _CURRENT_DIR[0] = r[0]
    return {"ok": True, "dir": r[0], "title": r[1]}


def _do_pick_import(d):
    act = _ACTIVITY[0]
    if act is None:
        return {"error": "当前环境不支持系统文件选择（桌面测试环境）"}
    _act_call(act, "pickZip")
    return {"ok": True}


def _do_orientation(d):
    """切换屏幕方向（sensor/portrait/landscape）：经 Java 桥设置 Activity。
    v1.52 起界面只有一套 PC 版布局（左侧导航 + 右侧工作区），方向只影响可用宽度。
    v1.53 起改走 _act_call 直接调用 Java 方法——此前用 callAttr（Java 侧 API）必然报
    "'MainActivity' object has no attribute 'callAttr'"，切方向一直失败。
    默认值由 Java 侧持久化（首次安装 = landscape）。"""
    mode = (d.get("mode") or "sensor").strip().lower()
    if mode not in ("sensor", "portrait", "landscape"):
        mode = "sensor"
    act = _ACTIVITY[0]
    if act is None:
        return {"ok": False, "error": "当前环境无 Activity（仅安卓端可用）"}
    try:
        _act_call(act, "setOrientation", mode)
        print("[orientation] requested mode=%s" % mode, flush=True)
        return {"ok": True, "mode": mode}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": "setOrientation failed: %s" % e}


# ---------- 导出 ----------
def _do_export_epub(d):
    """EPUB3 电子书导出（纯标准库实现）+ 有 Activity 时弹系统分享面板。"""
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    from export_utils import export_novel_epub
    exp = os.path.join(os.path.dirname(storage.PROJECTS_DIR), "export")
    os.makedirs(exp, exist_ok=True)
    safe = "".join(c for c in (project.title or "小说") if c not in '\\/:*?"<>|') or "小说"
    path = os.path.join(exp, "%s.epub" % safe)
    try:
        ok = export_novel_epub(project, store, path)
    except Exception as e:
        traceback.print_exc()
        return {"error": "EPUB 导出失败：%s" % e}
    if not ok:
        return {"error": "EPUB 导出失败：没有已归档章节"}
    shared = False
    act = _ACTIVITY[0]
    if act is not None:
        try:
            _act_call(act, "shareFile", path)
            shared = True
        except Exception:
            pass
    return {"ok": True, "path": path, "shared": shared}


def _do_export_txt(d):
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    exp = os.path.join(os.path.dirname(storage.PROJECTS_DIR), "export")
    os.makedirs(exp, exist_ok=True)
    safe = "".join(c for c in (project.title or "小说") if c not in '\\/:*?"<>|') or "小说"
    full = os.path.join(exp, "%s.txt" % safe)
    folder = os.path.join(exp, "%s_分章" % safe)
    os.makedirs(folder, exist_ok=True)
    lines = ["《%s》" % (project.title or ""), "", "（%s）" % (project.story_brief or ""), ""]
    n = 0
    last_vol = None
    for idx in store.list_chapter_indices():
        ch = store.load_chapter(idx)
        if not ch:
            continue
        vol = int(getattr(ch, "volume", 1) or 1)
        if vol != last_vol:
            last_vol = vol
            lines.append("═" * 20)
            lines.append("第 %d 卷" % vol)
            lines.append("═" * 20)
            lines.append("")
        lines.append("第 %d 章 %s" % (idx, ch.title or ""))
        lines.append("")
        lines.append(ch.content or "")
        lines.append("")
        vol_dir = os.path.join(folder, "第%d卷" % vol)
        os.makedirs(vol_dir, exist_ok=True)
        with open(os.path.join(vol_dir, "第%d章.txt" % idx), "w", encoding="utf-8") as f:
            f.write("第 %d 章 %s\n\n%s\n" % (idx, ch.title or "", ch.content or ""))
        n += 1
    with open(full, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    # v0.19：TXT 导出后自动弹系统分享（与 EPUB 一致）
    shared = False
    act = _ACTIVITY[0]
    if act is not None:
        try:
            _act_call(act, "shareFile", full)
            shared = True
        except Exception:
            pass
    return {"ok": True, "files": [full, folder], "chapters": n, "shared": shared}


# ---------- 拆书工坊（v0.55） ----------
def _imports_dir():
    return os.path.join(os.path.dirname(storage.PROJECTS_DIR), "imports")


def _do_pick_txt(d):
    """唤起系统文件选择器选小说 txt → Java 保存到 imports/picked.txt → 前端 __breakTxtReady。"""
    act = _ACTIVITY[0]
    if act is None:
        return {"error": "当前环境无 Activity（桌面测试环境不可用）"}
    try:
        _act_call(act, "pickTxt")
        return {"ok": True}
    except Exception as e:
        return {"error": "文件选择唤起失败：%s" % e}


def _do_break_parse(d):
    """解析已导入的 txt（imports/picked.txt）→ 分卷分章统计（供前端预览）。"""
    fname = str(d.get("fname") or "picked.txt").strip()
    path = os.path.join(_imports_dir(), fname)
    if not os.path.exists(path):
        return {"error": "文件不存在（请先在拆书页选择 txt 导入）"}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        return {"error": "读取失败：%s" % e}
    parsed = book_break.parse_novel(text)
    vols = [{"no": v["no"], "title": v["title"], "chapters": len(v["chapters"])}
            for v in parsed["volumes"]]
    return {"ok": True, "fname": fname,
            "volumes": vols, "vol_count": len(vols),
            "chapter_count": parsed["total_chapters"],
            "chars": parsed["total_chars"]}


def _do_break_import_doc(d):
    """导入外部拆书文档（txt/md/json 全文）为一个拆书风格（对称补齐导出）。

    传 fname 时从 imports/ 读文件内容；传 content 时直接用文本。
    """
    name = str(d.get("name") or "").strip()
    content = str(d.get("content") or "").strip()
    fname = str(d.get("fname") or "").strip()
    if not content and fname:
        path = os.path.join(_imports_dir(), fname)
        if not os.path.exists(path):
            return {"error": "文件不存在（请先选择拆书文档）"}
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return {"error": "读取失败：%s" % e}
    if not content.strip():
        return {"error": "内容为空"}
    r = book_break.import_break_from_text(name, content)
    if r.get("ok"):
        return {"ok": True, "name": r.get("name")}
    return {"error": r.get("error") or "导入失败"}


def _do_break_start(d):
    """开始拆书（任务化）：读 imports/picked.txt → 四阶段管线 → 结果存任务。可停止。"""
    fname = str(d.get("fname") or "picked.txt").strip()
    path = os.path.join(_imports_dir(), fname)
    if not os.path.exists(path):
        return {"error": "文件不存在（请先导入 txt）"}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        return {"error": "读取失败：%s" % e}
    if not (text or "").strip():
        return {"error": "文件内容为空"}
    title = str(d.get("title") or "拆书分析").strip() or "拆书分析"
    restart = bool(d.get("restart"))   # v0.39 重新开始：清空进度全部重来（不做续传）
    tid = _new_task()
    t = _TASKS[tid]

    def work():
        llm.set_abort(t["stop_ev"])
        try:
            logs = t["logs"]

            def sink(kind, msg):
                logs.append({"kind": kind, "msg": msg})

            settings = book_break.break_settings()
            job_dir = None
            if restart:
                sink("info", "重新开始拆书：已清除上次进度，全部重来（不再续传）…")
            else:
                job_dir = book_break.job_dir_for(text, settings, title, label="break")
                resumed = False
                if not os.path.exists(os.path.join(job_dir, "done.json")):
                    for _f in ("title_summ.json", "skeleton.json", "doc.json"):
                        if os.path.exists(os.path.join(job_dir, _f)):
                            resumed = True
                            break
                    if not resumed and os.path.isdir(os.path.join(job_dir, "vol_notes")):
                        resumed = True
                if resumed:
                    sink("info", "检测到未完成的拆书任务，自动续传（跳过已完成阶段）…")
            breaker = book_break.NovelBreaker(
                log=sink, stop_check=lambda: t.get("stop"), settings=settings)

            def progress(stage, done, total):
                t["progress"] = {"stage": stage, "done": done, "total": total}

            try:
                result = breaker.run(text, title, progress_cb=progress,
                                     job_dir=job_dir)
            except llm.StopRequested:
                result = {"ok": False, "error": "已停止"}
            if result.get("ok"):
                if job_dir:
                    book_break.rm_job(job_dir)
                _finish_task(tid, result={
                    "ok": True, "doc": result["doc"], "learning": result["learning"],
                    "stats": result["stats"]})
            else:
                _finish_task(tid, error=result.get("error") or "拆书未完成")
        finally:
            llm.set_abort(None)

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "task_id": tid}


def _do_break_stop(d):
    tid = str(d.get("task_id") or "")
    t = _TASKS.get(tid)
    if t is None:
        return {"error": "任务不存在"}
    t["stop"] = True
    t["stop_ev"].set()   # v0.28 立即中断当前 LLM 请求（中间结果已落盘，可续传）
    llm.abort_active_resps()   # v1.43 立即断流：close 在途连接（流式读取立刻抛 StopRequested）
    return {"ok": True}


def _do_break_save(d):
    """把拆书结果（doc/learning）保存为拆书风格。"""
    name = str(d.get("name") or "").strip()
    doc = str(d.get("doc") or "").strip()
    if not name:
        return {"error": "请填写风格名称"}
    if not doc:
        return {"error": "拆书结果为空"}
    book_break.save_break(name, doc, str(d.get("learning") or ""))
    return {"ok": True, "name": name}


def _do_breaks_list(d):
    return {"ok": True, "breaks": book_break.list_breaks()}


def _do_break_load(d):
    name = str(d.get("name") or "").strip()
    data = book_break.load_break(name)
    if data is None:
        return {"error": "风格不存在"}
    return {"ok": True, "break": data}


def _do_break_delete(d):
    name = str(d.get("name") or "").strip()
    r = book_break.delete_break(name)
    return {"ok": True} if r.get("ok") else {"error": "风格不存在"}


def _do_break_apply(d):
    """把拆书风格应用到当前项目（主AI学习其设计技法）。"""
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    name = str(d.get("name") or "").strip()
    if book_break.load_break(name) is None:
        return {"error": "风格不存在"}
    project.story_break_style = name
    store.save_project(project)
    return {"ok": True, "name": name}


def _do_break_export(d):
    """导出拆书风格文档为 txt → 系统分享（有 Activity 时）。"""
    name = str(d.get("name") or "").strip()
    data = book_break.load_break(name)
    if data is None:
        return {"error": "风格不存在"}
    exp = os.path.join(os.path.dirname(storage.PROJECTS_DIR), "export")
    os.makedirs(exp, exist_ok=True)
    safe = "".join(c for c in name if c not in '\\/:*?"<>|') or "拆书文档"
    path = os.path.join(exp, "拆书-%s.txt" % safe)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 拆书风格：%s\n\n%s\n" % (name, data["doc"]))
    shared = False
    act = _ACTIVITY[0]
    if act is not None:
        try:
            _act_call(act, "shareFile", path)
            shared = True
        except Exception:
            pass
    return {"ok": True, "path": path, "shared": shared}


# ---------- 文风校对（v0.36 移植 novel-style-extractor：A提取→B生成→C评分→D优化 多轮迭代） ----------
def _do_stylecheck_prompts(d):
    """当前四节点提示词 + 预设库（结构）。"""
    wf = style_extract.StyleExtractorWorkflow()
    return {"ok": True, "prompts": wf.prompts, "presets": wf.load_presets()}


def _do_stylecheck_prompts_save(d):
    prompts = d.get("prompts") or {}
    wf = style_extract.StyleExtractorWorkflow()
    merged = dict(wf.prompts)
    for node in ("node_a", "node_b", "node_c", "node_d"):
        if node in prompts:
            merged[node] = str(prompts[node])
    wf.save_prompts(merged)
    return {"ok": True}


def _do_stylecheck_presets_save(d):
    name = str(d.get("name") or "").strip()
    prompts = d.get("prompts") or {}
    if not name:
        return {"error": "请填写预设名称"}
    style_extract.StyleExtractorWorkflow().save_preset(name, {
        k: str(prompts.get(k) or "") for k in ("node_a", "node_b", "node_c", "node_d")})
    return {"ok": True}


def _do_stylecheck_presets_delete(d):
    name = str(d.get("name") or "").strip()
    if not name:
        return {"error": "请选择预设"}
    style_extract.StyleExtractorWorkflow().delete_preset(name)
    return {"ok": True}


def _do_stylecheck_presets_apply(d):
    name = str(d.get("name") or "").strip()
    if not name:
        return {"error": "请选择预设"}
    merged = style_extract.StyleExtractorWorkflow().apply_preset(name)
    return {"ok": True, "prompts": merged}


def _do_stylecheck_start(d):
    """开始文风校对（任务化）：原文 content 或 imports/picked.txt → A/B/C/D 多轮迭代 → 结果存任务。可停止。"""
    content = str(d.get("content") or "").strip()
    fname = str(d.get("fname") or "").strip()
    if not content and fname:
        path = os.path.join(_imports_dir(), fname)
        if not os.path.exists(path):
            return {"error": "文件不存在（请先在文风校对页导入 txt）"}
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return {"error": "读取失败：%s" % e}
    if not content.strip():
        return {"error": "请先粘贴原文或导入 txt"}
    try:
        max_rounds = max(1, min(999, int(d.get("max_rounds") or 5)))
    except (TypeError, ValueError):
        max_rounds = 5
    try:
        threshold = max(0.0, min(100.0, float(d.get("threshold") or 80.0)))
    except (TypeError, ValueError):
        threshold = 80.0
    tid = _new_task()
    t = _TASKS[tid]

    def work():
        llm.set_abort(t["stop_ev"])
        try:
            logs = t["logs"]

            def sink(kind, msg):
                logs.append({"kind": kind, "msg": msg})

            wf = style_extract.StyleExtractorWorkflow()
            final = None
            rounds = []
            cur_round = 0
            try:
                for k, data in wf.run_workflow_stream(
                        content, max_rounds=max_rounds, threshold=threshold,
                        stop_check=lambda: t.get("stop")):
                    if k == "status":
                        sink("info", data)
                    elif k == "a_done":
                        sink("info", "节点A 完成：已提炼文风提示词。")
                    elif k == "b_start":
                        cur_round = data.get("round") or 0
                        sink("info", "第 %d 轮 · 节点B 生成文章…" % cur_round)
                    elif k == "b_done":
                        sink("info", "第 %d 轮 · 节点B 完成（生成 %d 字）。"
                             % (cur_round, len(data.get("生成文章") or "")))
                    elif k == "c_done":
                        sink("info", "第 %d 轮 · 节点C 评分：%.1f 分。"
                             % (cur_round, data.get("score")))
                    elif k == "round_end":
                        rounds.append({"round": data.get("round"), "score": data.get("score")})
                        sink("info", "第 %d 轮结束：%.1f 分（Top：%s）。" % (
                            data.get("round"), data.get("score"),
                            "、".join("%.1f" % s for s in (data.get("top_scores") or []))))
                    elif k == "d_done":
                        sink("info", "节点D 优化完成，下一轮使用新文风提示词。")
                    elif k == "final":
                        final = data
            except llm.StopRequested:
                sink("warn", "已停止。")
                _finish_task(tid, error="已停止")
                return
            if final is None:
                _finish_task(tid, error="文风校对未完成")
                return
            _finish_task(tid, result={
                "ok": True,
                "top": final.get("top_style_prompts") or [],
                "best_score": final.get("best_score"),
                "reached_threshold": final.get("reached_threshold"),
                "rounds": rounds})
        except Exception as e:
            traceback.print_exc()
            _finish_task(tid, error="文风校对失败：%s" % e)
        finally:
            llm.set_abort(None)

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "task_id": tid}


def _do_stylecheck_stop(d):
    tid = str(d.get("task_id") or "")
    t = _TASKS.get(tid)
    if t is None:
        return {"error": "任务不存在"}
    t["stop"] = True
    t["stop_ev"].set()
    llm.abort_active_resps()   # v1.43 立即断流：close 在途连接（流式读取立刻抛 StopRequested）
    return {"ok": True}


def _do_stylecheck_export(d):
    """导出 Top3 文风提示词为 txt → 系统分享（有 Activity 时）。"""
    text = str(d.get("text") or "").strip()
    if not text:
        return {"error": "导出内容为空"}
    exp = os.path.join(os.path.dirname(storage.PROJECTS_DIR), "export")
    os.makedirs(exp, exist_ok=True)
    path = os.path.join(exp, "文风校对Top3.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    shared = False
    act = _ACTIVITY[0]
    if act is not None:
        try:
            _act_call(act, "shareFile", path)
            shared = True
        except Exception:
            pass
    return {"ok": True, "path": path, "shared": shared}


# ---------- 小说导入成项目（v0.27：把 txt 小说还原成完整项目，可停止） ----------
def _do_import_start(d):
    """读 imports/picked.txt → 全流程还原为项目（任务化，可停止）。

    流程：解析（保留全章正文）→ 拆书（四阶段，中间结果复用）→ 设定合成（剧情/世界观/规则/
    文风/锚点/伏笔）→ 逐块人物抽取（新角色+分章状态轨迹）→ 批量角色卡 → 落库。
    还原后项目与逐章生成一致；删除章节后角色卡按分章状态轨迹自动回退。
    """
    fname = str(d.get("fname") or "picked.txt").strip()
    path = os.path.join(_imports_dir(), fname)
    if not os.path.exists(path):
        return {"error": "文件不存在（请先选择小说 txt 导入）"}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        return {"error": "读取失败：%s" % e}
    if not (text or "").strip():
        return {"error": "文件内容为空"}
    title = str(d.get("title") or "导入小说").strip() or "导入小说"
    options = {
        "save_break": bool(d.get("save_break", True)),
        "characters": bool(d.get("characters", True)),
        "chapters": bool(d.get("chapters", True)),
    }
    import novel_import
    tid = _new_task()
    t = _TASKS[tid]

    def work():
        llm.set_abort(t["stop_ev"])
        try:
            logs = t["logs"]

            def sink(kind, msg):
                logs.append({"kind": kind, "msg": msg})

            def progress(stage, done, total):
                t["progress"] = {"stage": stage, "done": done, "total": total}

            settings = book_break.break_settings()
            restart = bool(d.get("restart"))   # v0.39 重新开始：清空进度全部重来
            job_dir = None
            if restart:
                sink("info", "重新开始导入：已清除上次进度，全部重来（不再续传）…")
            else:
                job_dir = book_break.job_dir_for(text, settings, title, label="import")
                resumed = False
                if not os.path.exists(os.path.join(job_dir, "done.json")):
                    for _f in ("meta.json", "settings.json", "summary.json"):
                        if os.path.exists(os.path.join(job_dir, _f)):
                            resumed = True
                            break
                    if not resumed and (os.path.isdir(os.path.join(job_dir, "chunks"))
                                        or os.path.isdir(os.path.join(job_dir, "cards"))):
                        resumed = True
                if resumed:
                    sink("info", "检测到未完成的小说导入任务，自动续传（跳过已完成环节）…")
            try:
                importer = novel_import.NovelImporter(
                    log=sink, stop_check=lambda: t.get("stop"), settings=settings)
                result = importer.run(text, title, options, progress_cb=progress,
                                      job_dir=job_dir)
            except llm.StopRequested:
                result = {"ok": False, "error": "已停止"}
            if result.get("ok"):
                _CURRENT_DIR[0] = result["dir"]
                if job_dir:
                    book_break.rm_job(job_dir)
                _finish_task(tid, result=result)
            else:
                _finish_task(tid, error=result.get("error") or "导入未完成")
        except Exception as e:
            traceback.print_exc()
            _finish_task(tid, error="导入失败：%s" % e)
        finally:
            llm.set_abort(None)

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "task_id": tid}


def _do_import_stop(d):
    """停止导入（v0.28 立即生效：中断当前请求；已完成的拆书/分析中间结果落盘，可续传）。"""
    tid = str(d.get("task_id") or "")
    t = _TASKS.get(tid)
    if t is None:
        return {"error": "任务不存在"}
    t["stop"] = True
    t["stop_ev"].set()
    llm.abort_active_resps()   # v1.43 立即断流：close 在途连接（流式读取立刻抛 StopRequested）
    return {"ok": True}


# ---------- AI 对话（v1.47：与桌面 gui_chat 语义对齐——话题/流式/项目上下文/联网/消息操作） ----------
_CHAT_SYSTEM = ("你是星火笔内嵌的 AI 对话助手。当前会话用于测试 API 调用效果与交流小说内容。"
                "回答用中文，简洁准确。")
_CHAT_SYSTEM_CONTINUE = ("你是星火笔内嵌的 AI 对话助手。请从用户给出的最后一段内容末尾继续往下写，"
                         "不要重复已有内容，直接续写。回答用中文。")
_CHAT_WEB_RESULTS = 5        # 联网搜索条数（与桌面 WEB_RESULTS 一致）


def _chat_system(use_project, use_web, text, kind="chat"):
    """组装系统提示（语义同桌面 gui_chat._send_text/_continue_last；不选项目就完全读不到项目）。"""
    system = _CHAT_SYSTEM_CONTINUE if kind == "continue" else _CHAT_SYSTEM
    if use_project:
        store, project = _current()
        try:
            ctx = chat_lib.build_project_context(store, project)
        except Exception:
            ctx = ""
        if ctx:
            system += "\n\n以下是当前项目设定参考（不含正文）：\n" + ctx
    if use_web and text:
        try:
            hits = web_search.search(str(text)[:120], max_results=_CHAT_WEB_RESULTS)
        except Exception:
            hits = []
        if hits:
            lines = ["%d. %s（%s）\n%s" % (i + 1, h.get("title", ""), h.get("url", ""),
                                           h.get("snippet", "")) for i, h in enumerate(hits)]
            system += "\n\n【联网搜索结果（仅供参考，引用需注明来源）】\n" + "\n".join(lines)
    return system


def _chat_history(tid):
    """最近消息 + 已压缩摘要（同桌面 chat_lib.recent_messages 语义）。"""
    msgs = []
    try:
        t = chat_lib.load_topic(tid)
        if t and t.get("summary"):
            msgs.append({"role": "system",
                         "content": "【此前对话摘要（已压缩，回答相关问题时参考）】\n" + t["summary"]})
    except Exception:
        pass
    try:
        for m in chat_lib.recent_messages(tid):
            msgs.append({"role": m.get("role"), "content": m.get("content")})
    except Exception:
        pass
    return msgs


def _chat_profile_name():
    try:
        return (config.load_config().get("chat_profile") or "").strip() or None
    except Exception:
        return None


def _chat_kick(tid, use_project, use_web, kind, text=""):
    """启动 AI 对话任务：流式分片写入任务日志（kind=chunk/think），完成/失败写回话题存储。

    kind: chat（追加 assistant 消息）/ continue（追加到最后一条 AI 回复）。
    """
    messages = [{"role": "system",
                 "content": _chat_system(use_project, use_web, text, kind)}] + _chat_history(tid)
    if kind == "continue":
        messages.append({"role": "user",
                         "content": "请从上面最后一条 AI 回复的末尾继续写（不重复已有内容，直接续写）。"})
    task_id = _new_task()
    t0_box = [time.time()]

    def work():
        t = _TASKS[task_id]
        llm.set_abort(t["stop_ev"])
        think_buf = []
        try:
            def on_chunk(piece):
                t["logs"].append({"kind": "chunk", "msg": piece})
            def on_think(piece):
                t["logs"].append({"kind": "think", "msg": piece})
                think_buf.append(piece)
            out_text = llm.chat(messages, role="chat", profile=_chat_profile_name(),
                                on_chunk=on_chunk, on_think=on_think, think_role="chat")
            prof = None
            pname = _chat_profile_name()
            if pname:
                for p in config.profiles():
                    if p.get("name") == pname:
                        prof = p
                        break
            else:
                prof = config.pick_profile("chat")
            think = "".join(think_buf) or None
            if kind == "continue":
                chat_lib.append_to_last_message(tid, out_text, think=think)
            else:
                chat_lib.append_message(tid, "assistant", out_text, think=think)
            _finish_task(task_id, result={
                "ok": True, "text": out_text, "elapsed": time.time() - t0_box[0],
                "profile": (prof or {}).get("name", "?"), "model": (prof or {}).get("model", "?"),
                "error": None, "stopped": False, "kind": kind, "tid": tid, "think": think})
        except llm.StopRequested:
            _finish_task(task_id, error="已停止", result={
                "ok": False, "text": "", "elapsed": time.time() - t0_box[0],
                "profile": "AI对话", "model": "?", "error": "已停止",
                "stopped": True, "kind": kind, "tid": tid, "think": None})
        except Exception as e:
            traceback.print_exc()
            _finish_task(task_id, error=str(e), result={
                "ok": False, "text": "", "elapsed": time.time() - t0_box[0],
                "profile": "AI对话", "model": "?", "error": str(e),
                "stopped": False, "kind": kind, "tid": tid, "think": None})
        finally:
            llm.set_abort(None)

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "task_id": task_id, "tid": tid}


def _do_chat_topics(d):
    return {"ok": True,
            "topics": chat_lib.list_topics(),
            "folders": chat_lib.list_folders()}


def _do_chat_open(d):
    tid = str(d.get("tid") or "")
    t = chat_lib.load_topic(tid)
    if t is None:
        return {"error": "话题不存在"}
    return {"ok": True, "tid": tid,
            "title": t.get("title", "未命名"),
            "summary": t.get("summary") or "",
            "messages": t.get("messages") or []}


def _do_chat_create(d):
    title = str(d.get("title") or "").strip() or "新话题"
    tid = chat_lib.create_topic(title)
    return {"ok": True, "tid": tid}


def _do_chat_rename(d):
    tid = str(d.get("tid") or "")
    if chat_lib.load_topic(tid) is None:
        return {"error": "话题不存在"}
    chat_lib.rename_topic(tid, str(d.get("title") or "").strip())
    return {"ok": True}


def _do_chat_delete(d):
    tid = str(d.get("tid") or "")
    chat_lib.delete_topic(tid)
    return {"ok": True}


def _do_chat_send(d):
    """发送：自动兜底建话题（同桌面），落库用户消息后立即起流式任务。"""
    text = str(d.get("text") or "").strip()
    if not text:
        return {"error": "消息为空"}
    tid = str(d.get("tid") or "")
    if not tid or chat_lib.load_topic(tid) is None:
        tid = chat_lib.create_topic("新话题")
    chat_lib.append_message(tid, "user", text)
    return _chat_kick(tid, bool(d.get("use_project")), bool(d.get("use_web")), "chat", text)


def _do_chat_continue(d):
    tid = str(d.get("tid") or "")
    t = chat_lib.load_topic(tid)
    if t is None:
        return {"error": "话题不存在"}
    msgs = t.get("messages") or []
    if not msgs or msgs[-1].get("role") != "assistant":
        return {"error": "最后一条不是 AI 回复，无法继续生成。"}
    return _chat_kick(tid, bool(d.get("use_project")), bool(d.get("use_web")), "continue", "")


def _do_chat_regen(d):
    """重生成：删掉最后一条 AI 回复，用其前一条用户消息重新请求（同桌面 _regenerate_last）。"""
    tid = str(d.get("tid") or "")
    t = chat_lib.load_topic(tid)
    if t is None:
        return {"error": "话题不存在"}
    msgs = t.get("messages") or []
    if msgs and msgs[-1].get("role") == "assistant":
        msgs.pop()
        chat_lib.save_topic(t)
    if not msgs or msgs[-1].get("role") != "user":
        return {"error": "没有用户消息可用于重新生成。"}
    return _chat_kick(tid, bool(d.get("use_project")), bool(d.get("use_web")),
                      "chat", msgs[-1].get("content", ""))


def _do_chat_edit_last(d):
    """编辑最后一条消息内容（同桌面 _edit_last；编辑的是用户消息时前端紧接重生成）。"""
    tid = str(d.get("tid") or "")
    t = chat_lib.load_topic(tid)
    if t is None:
        return {"error": "话题不存在"}
    msgs = t.get("messages") or []
    if not msgs:
        return {"error": "没有可编辑的消息"}
    content = str(d.get("content") or "").strip()
    if not content:
        return {"error": "内容为空"}
    msgs[-1]["content"] = content
    chat_lib.save_topic(t)
    return {"ok": True, "role": msgs[-1].get("role", "assistant")}


def _do_chat_delete_last(d):
    tid = str(d.get("tid") or "")
    t = chat_lib.load_topic(tid)
    if t is None:
        return {"error": "话题不存在"}
    msgs = t.get("messages") or []
    if not msgs:
        return {"error": "没有消息可删除"}
    chat_lib.pop_last_messages(tid, 1)
    return {"ok": True}


def _do_chat_stop(d):
    """停止 AI 对话（v1.43 停止红线：置停止事件 + 立即断流，不等当前回复写完）。"""
    tid = str(d.get("task_id") or "")
    t = _TASKS.get(tid)
    if t is None:
        return {"error": "任务不存在"}
    t["stop"] = True
    t["stop_ev"].set()
    llm.abort_active_resps()
    return {"ok": True}


def _do_chat_export(d):
    """导出话题为 md 并弹系统分享（同桌面 _export_topic）。"""
    tid = str(d.get("tid") or "")
    t = chat_lib.load_topic(tid)
    if not t:
        return {"error": "话题不存在"}
    exp = os.path.join(os.path.dirname(storage.PROJECTS_DIR), "export")
    os.makedirs(exp, exist_ok=True)
    safe = "".join(c for c in (t.get("title") or "对话") if c not in '\\/:*?"<>|') or "对话"
    path = os.path.join(exp, "星火笔-对话-%s.md" % safe)
    if not chat_lib.export_topic_md(tid, path):
        return {"error": "导出失败：话题不存在或写入失败"}
    shared = False
    act = _ACTIVITY[0]
    if act is not None:
        try:
            _act_call(act, "shareFile", path)
            shared = True
        except Exception:
            pass
    return {"ok": True, "path": path, "shared": shared}


# ---------- 情景写作提示词（总库 / 项目库，v1.56 移植：镜像 PC gui_scene_cards.py） ----------
_SC_CARD_SEP = "【卡名】"        # 批量导入/导出的卡分隔标记：一行 【卡名】名称 开始一张卡


def _sc_cards():
    """全局总库卡库（config["writer_scene_cards"]）：[{name, category, content}]。"""
    return [dict(c) for c in (config.load_config().get("writer_scene_cards") or [])
            if isinstance(c, dict)]


def _sc_persist(cards):
    """写回总库（save_config）。"""
    cfg = config.load_config()
    cfg["writer_scene_cards"] = cards
    config.save_config(cfg)


def _sc_parse_import(text, fallback_name=""):
    """解析导入文本为卡列表（镜像 gui_scene_cards._parse_import）。

    支持【卡名】分隔的多卡文本；无分隔标记时整段作为一张卡（卡名取 fallback_name 或「未命名」）。
    卡首行【分类】行解析为 category（兼容旧文件）；fallback_name 形如「[武打]夜战夺镖」（v1.30
    批量导出的细分文件名）时拆分出 category/卡名（内容含【分类】行时以内容为准）。
    返回 [{"name","content","category"}]（内容为空的段丢弃）。
    """
    text = (text or "").strip()
    if not text:
        return []
    cards = []
    parts = []
    cur = None
    for line in text.split("\n"):
        if line.startswith(_SC_CARD_SEP):
            if cur:
                parts.append(cur)
            cur = {"name": line[len(_SC_CARD_SEP):].strip(), "lines": []}
            continue
        if cur is None:
            cur = {"name": "", "lines": []}
        cur["lines"].append(line)
    if cur:
        parts.append(cur)
    fb_cat = fb_name = ""
    if fallback_name.startswith("[") and "]" in fallback_name:
        _rb = fallback_name.find("]")
        fb_cat = fallback_name[1:_rb].strip()
        fb_name = fallback_name[_rb + 1:].strip()
    for p in parts:
        lines = list(p["lines"])
        category = ""
        if lines and lines[0].startswith("【分类】"):
            category = lines[0][len("【分类】"):].strip()
            lines = lines[1:]
        content = "\n".join(lines).strip()
        if not content:
            continue
        name = p["name"] or (fb_name or fallback_name) or "未命名"
        if not category:
            category = fb_cat
        cards.append({"name": name, "content": content, "category": category})
    return cards


def _sc_export_text(cards):
    """多卡导出为可再导入的文本（每卡以 【卡名】名称 开头；有分类附【分类】行）。"""
    out = []
    for c in cards:
        nm = str(c.get("name") or "").strip() or "未命名"
        ct = str(c.get("content") or "").strip()
        cat = str(c.get("category") or "").strip()
        if ct:
            head = "%s%s" % (_SC_CARD_SEP, nm)
            if cat:
                head += "\n【分类】%s" % cat
            out.append("%s\n%s" % (head, ct))
    return "\n\n".join(out)


def _sc_file_safe(name):
    """卡名 → 合法文件名（替换 Windows 非法字符）。"""
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    return (name or "未命名").strip() or "未命名"


def _sc_txt_dir():
    """导出目录（与 break_export / export_txt 同一处：应用 files 目录下的 export）。"""
    exp = os.path.join(os.path.dirname(storage.PROJECTS_DIR), "export")
    os.makedirs(exp, exist_ok=True)
    return exp


def _sc_share(path):
    """有 Activity 时弹系统分享；返回是否已分享（与 _do_break_export 同款）。"""
    shared = False
    act = _ACTIVITY[0]
    if act is not None:
        try:
            _act_call(act, "shareFile", path)
            shared = True
        except Exception:
            pass
    return shared


def _sc_generate_content(type_name, detail, text, mode):
    """调用主AI生成/提取情景卡规则文本（mode=gen|extract）；返回 (content, error)。"""
    name = str(type_name or "").strip()
    if not name:
        return "", "请填写情景类型名"
    try:
        if mode == "extract":
            if not str(text or "").strip():
                return "", "请先粘贴参考文本"
            content = main_ai.extract_scene_card(name, str(text))
        else:
            content = main_ai.generate_scene_card(name, str(detail or "").strip() or None)
    except Exception as e:
        traceback.print_exc()
        return "", "%s" % e
    content = (content or "").strip()
    if not content:
        return "", "AI 未返回有效内容"
    return content, ""


def _do_scene_cards_list(d):
    """总库卡列表 + 当前提取提示词（空=用内置初始）。"""
    cfg = config.load_config()
    cards = [{"name": str(c.get("name") or "").strip(),
              "category": str(c.get("category") or "").strip(),
              "content": str(c.get("content") or "").strip()}
             for c in (cfg.get("writer_scene_cards") or []) if isinstance(c, dict)]
    return {"ok": True, "cards": cards,
            "extract_prompt": str(cfg.get("extract_scene_card_prompt") or "")}


def _do_scene_cards_save(d):
    """新增/保存一张总库卡（镜像 PC _card_save）：old_name 为原卡名（改名时用），
    按新名 upsert，空内容拒绝，「未分类」归类为空分类。"""
    name = str(d.get("name") or "").strip() or "未命名"
    content = str(d.get("content") or "").strip()
    category = str(d.get("category") or "").strip()
    if category == "未分类":
        category = ""
    if not content:
        return {"error": "卡内容不能为空"}
    old_name = str(d.get("old_name") or "").strip()
    cards = _sc_cards()
    hit = None
    for c in cards:
        if old_name and str(c.get("name") or "").strip() == old_name:
            hit = c
            break
    if hit is None:
        for c in cards:
            if str(c.get("name") or "").strip() == name:
                hit = c
                break
    if hit is not None:
        hit["name"] = name
        hit["content"] = content
        hit["category"] = category
    else:
        cards.append({"name": name, "content": content, "category": category})
    _sc_persist(cards)
    return {"ok": True, "count": len(cards), "name": name}


def _do_scene_cards_delete(d):
    """删除一张总库卡（按名字；卡名不存在时静默保持原库）。"""
    name = str(d.get("name") or "").strip()
    if not name:
        return {"error": "请指定要删除的卡名"}
    cards = [c for c in _sc_cards() if str(c.get("name") or "").strip() != name]
    _sc_persist(cards)
    return {"ok": True, "count": len(cards)}


def _do_scene_cards_generate(d):
    """AI 一键生成某类型情景卡规则草稿（不落库，用户确认后走 scene_cards_save）。"""
    content, err = _sc_generate_content(d.get("type_name"), d.get("detail"), "", "gen")
    if err:
        return {"error": "AI 生成情景卡失败：%s" % err}
    return {"ok": True, "content": content}


def _do_scene_cards_extract(d):
    """从参考文本提取某类型情景卡规则草稿（不落库；提取提示词取 config extract_scene_card_prompt）。"""
    content, err = _sc_generate_content(d.get("type_name"), "", d.get("text"), "extract")
    if err:
        return {"error": "提取情景卡失败：%s" % err}
    return {"ok": True, "content": content}


def _do_scene_cards_prompt_get(d):
    """当前「从文本提取」提取提示词（空串=用内置初始）。"""
    return {"ok": True,
            "prompt": str(config.load_config().get("extract_scene_card_prompt") or "")}


def _do_scene_cards_prompt_save(d):
    """保存提取提示词（空 → None=回内置初始，与 PC 一致）。"""
    text = str(d.get("prompt") or "").strip()
    cfg = config.load_config()
    cfg["extract_scene_card_prompt"] = text or None
    config.save_config(cfg)
    return {"ok": True, "prompt": text}


def _do_scene_cards_prompt_reset(d):
    """恢复内置初始提取提示词（清空 config 自定义）并返回该初始提示词文本。"""
    import prompts as prompts_mod
    cfg = config.load_config()
    cfg["extract_scene_card_prompt"] = None
    config.save_config(cfg)
    return {"ok": True, "prompt": prompts_mod._DEFAULT_EXTRACT_SYS}


def _do_scene_cards_import_txt(d):
    """导入【卡名】分隔的多卡文本（镜像 _parse_import）：新卡追加；同名卡内容/分类覆盖，
    added 统计「导入+覆盖」张数（PC 单文件导入同口径，PC 的覆盖确认弹窗由前端负责）。"""
    text = str(d.get("text") or "")
    fallback = str(d.get("fallback_name") or d.get("fname") or "").strip()
    # v1.56 只传 fname 时从 imports/ 读文件（仿 _do_break_import_doc：Android 选文件后
    # Java 侧把内容存成 imports/picked.txt，前端只回传文件名）
    if not text.strip():
        fname = str(d.get("fname") or "").strip()
        if fname:
            path = os.path.join(_imports_dir(), fname)
            if not os.path.exists(path):
                return {"error": "文件不存在（请先选择 txt 文件）"}
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception as e:
                return {"error": "读取失败：%s" % e}
    if not text.strip():
        return {"error": "导入内容为空"}
    parsed = _sc_parse_import(text, fallback_name=fallback)
    if not parsed:
        return {"error": "文本里没有可导入的卡（内容为空）"}
    cards = _sc_cards()
    added = 0
    for c in parsed:
        nm = str(c.get("name") or "").strip() or "未命名"
        hit = None
        for x in cards:
            if str(x.get("name") or "").strip() == nm:
                hit = x
                break
        if hit is not None:
            hit["content"] = c["content"]
            hit["category"] = c.get("category") or ""
        else:
            cards.append({"name": nm, "content": c["content"],
                          "category": c.get("category") or ""})
        added += 1
    _sc_persist(cards)
    return {"ok": True, "added": added, "count": len(cards)}


def _do_scene_cards_export(d):
    """导出单张总库卡为 txt → 系统分享（文件名=卡名）。"""
    name = str(d.get("name") or "").strip()
    if not name:
        return {"error": "请指定要导出的卡名"}
    hit = None
    for c in _sc_cards():
        if str(c.get("name") or "").strip() == name:
            hit = c
            break
    if hit is None:
        return {"error": "卡不存在"}
    content = str(hit.get("content") or "").strip()
    if not content:
        return {"error": "卡内容为空，没有可导出的"}
    path = os.path.join(_sc_txt_dir(), "情景卡-%s.txt" % _sc_file_safe(name))
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"ok": True, "path": path, "shared": _sc_share(path)}


def _do_scene_cards_export_all(d):
    """批量导出总库全部卡为一个 txt（每卡【卡名】分隔，可整批再导入）→ 系统分享。"""
    cards = [c for c in _sc_cards() if str(c.get("content") or "").strip()]
    if not cards:
        return {"error": "卡库为空，没有可导出的"}
    path = os.path.join(_sc_txt_dir(), "星火笔情景卡_导出.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_sc_export_text(cards))
    return {"ok": True, "path": path, "shared": _sc_share(path), "cards": len(cards)}


def _do_scene_cards_project_list(d):
    """当前项目主AI可用库（project.scene_cards）+ 启用卡名（scene_cards_active）。"""
    store, project = _current()
    if project is None:
        return {"ok": True, "cards": [], "active": []}
    cards = [{"name": str(c.get("name") or "").strip(),
              "category": str(c.get("category") or "").strip(),
              "content": str(c.get("content") or "").strip()}
             for c in (getattr(project, "scene_cards", None) or [])
             if isinstance(c, dict) and str(c.get("name") or "").strip()]
    active = [str(x).strip() for x in (getattr(project, "scene_cards_active", None) or [])
              if str(x).strip()]
    if not active:
        active = [c["name"] for c in cards]
    return {"ok": True, "cards": cards, "active": active}


def _do_scene_cards_project_add(d):
    """从总库把勾选的卡复制进本项目库（source="user"，同名跳过）并启用；保存项目。"""
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    raw = d.get("names")
    names = [str(x).strip() for x in raw if str(x).strip()] if isinstance(raw, list) else []
    if not names:
        return {"error": "请选择要从总库加入本项目的情景卡"}
    lib = {str(c.get("name") or "").strip(): c for c in _sc_cards()
           if str(c.get("name") or "").strip() and str(c.get("content") or "").strip()}
    if not lib:
        return {"error": "总库为空——先到情景提示词页新增/AI 生成/导入几张卡。"}
    project.scene_cards = [c for c in (getattr(project, "scene_cards", None) or [])
                           if isinstance(c, dict)]
    exist = {str(c.get("name") or "").strip() for c in project.scene_cards}
    added = 0
    for nm in names:
        if nm in exist or nm not in lib:
            continue
        project.scene_cards.append({"name": nm,
                                    "content": str(lib[nm].get("content") or ""),
                                    "source": "user",
                                    "category": str(lib[nm].get("category") or "")})
        exist.add(nm)
        added += 1
    project.scene_cards_active = [str(c.get("name") or "").strip()
                                  for c in project.scene_cards
                                  if str(c.get("name") or "").strip()]
    store.save_project(project)
    store.append_log("【情景卡】从总库加入本项目 %d 张（本项目库 %d 张）。"
                     % (added, len(project.scene_cards)))
    return {"ok": True, "added": added, "count": len(project.scene_cards)}


def _do_scene_cards_project_remove(d):
    """把一张卡移出本项目库（只解除本项目可用，不影响总库）；保存项目。"""
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    name = str(d.get("name") or "").strip()
    if not name:
        return {"error": "请指定要移出的卡名"}
    project.scene_cards = [c for c in (getattr(project, "scene_cards", None) or [])
                           if isinstance(c, dict)
                           and str(c.get("name") or "").strip() != name]
    project.scene_cards_active = [str(c.get("name") or "").strip()
                                  for c in project.scene_cards
                                  if str(c.get("name") or "").strip()]
    store.save_project(project)
    store.append_log("【情景卡】已把「%s」移出本项目主AI可用库。" % name)
    return {"ok": True, "count": len(project.scene_cards)}


def _do_scene_cards_project_to_library(d):
    """把一张本项目卡放入总库（所有项目可用）；总库已有同名卡则跳过不覆盖。"""
    store, project = _current()
    if project is None:
        return {"error": "无项目"}
    name = str(d.get("name") or "").strip()
    if not name:
        return {"error": "请指定要放入总库的卡名"}
    hit = None
    for c in (getattr(project, "scene_cards", None) or []):
        if (isinstance(c, dict) and str(c.get("name") or "").strip() == name
                and str(c.get("content") or "").strip()):
            hit = c
            break
    if hit is None:
        return {"error": "本项目库里找不到这张卡（或内容为空）"}
    lib = _sc_cards()
    if any(str(x.get("name") or "").strip() == name for x in lib):
        return {"ok": True, "added": 0, "skipped": True, "count": len(lib)}
    lib.append({"name": name, "content": str(hit.get("content") or "").strip(),
                "category": str(hit.get("category") or "")})
    _sc_persist(lib)
    if store is not None:
        store.save_project(project)
    return {"ok": True, "added": 1, "skipped": False, "count": len(lib)}


def _do_scene_cards_adapt(d):
    """按本项目正文AI基础文风适配项目库情景卡（任务化，可停止；只改项目库、不动总库）。

    任务化走既有 task_status 轮询 + book_stop 停止机制（与 _do_book_auto 同款）。"""
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    cards = [c for c in (getattr(project, "scene_cards", None) or [])
             if isinstance(c, dict) and str(c.get("name") or "").strip()
             and str(c.get("content") or "").strip()]
    if not cards:
        return {"error": "本项目情景卡库为空——先把总库的卡加入本项目再适配。"}
    tid = _new_task()
    t = _TASKS[tid]

    def work():
        llm.set_abort(t["stop_ev"])
        try:
            logs = t["logs"]

            def sink(kind, msg):
                logs.append({"kind": kind, "msg": msg})

            sink("info", "主AI按本项目正文文风适配 %d 张项目库情景卡（保持卡名/分类/情景内核，"
                 "只调整写法表述；只改项目库、不动总库）…" % len(cards))
            data = main_ai.adapt_project_scene_cards(project, cards)
            by_name = {}
            for item in ((data.get("adapted") or []) if isinstance(data, dict) else []):
                if not isinstance(item, dict):
                    continue
                nm = str(item.get("name") or "").strip()
                ct = str(item.get("content") or "").strip()
                if nm and ct:
                    by_name[nm] = ct
            ok_n, failed = 0, []
            for c in cards:
                nm = str(c.get("name") or "").strip()
                new_ct = by_name.get(nm)
                if new_ct:
                    c["content"] = new_ct
                    ok_n += 1
                else:
                    failed.append(nm)
            try:
                store.save_project(project)
            except Exception as e:
                sink("warn", "适配结果写回项目失败：%s" % e)
            if ok_n:
                sink("info", "已按项目正文文风适配 %d 张情景卡（总库未动）。" % ok_n)
            if failed:
                sink("warn", "以下 %d 张卡适配无效（主AI未返回）：%s"
                     % (len(failed), "、".join(failed)))
            _finish_task(tid, result={"ok": True, "cards": ok_n, "failed": failed})
        except llm.StopRequested:
            _finish_task(tid, error="已停止")
        except Exception as e:
            traceback.print_exc()
            _finish_task(tid, error="情景卡适配失败：%s" % e)
        finally:
            llm.set_abort(None)

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "task_id": tid}


# ---------- 项目页（v1.56 移植：AI 起草设定 / 批量重设计章节名 / 分支存档） ----------
def _do_plan_story(d):
    """AI 按想法起草故事设定三栏（镜像 PC 项目页 plan_story_ai 用法）。

    notes=现有栏内容草稿（传给 AI 作续写基础，可空）；idea=小说想法；
    constraint=总章节数约束（如「30 章」）；targets 勾选 story/world/rules（为空=三栏全生成）。"""
    idea = str(d.get("idea") or "").strip()
    if not idea:
        return {"error": "请先描述你想写什么小说"}
    notes = str(d.get("notes") or "").strip()
    constraint = str(d.get("constraint") or "").strip()
    raw = d.get("targets")
    targets = tuple(str(x).strip() for x in raw if str(x).strip()) if isinstance(raw, list) else ()
    targets = tuple(x for x in targets if x in ("story", "world", "rules"))
    if not targets:
        targets = ("story", "world", "rules")
    try:
        data = main_ai.plan_story_ai(notes, idea, constraint, targets)
    except Exception as e:
        traceback.print_exc()
        return {"error": "AI 起草故事设定失败：%s" % e}
    if not isinstance(data, dict):
        data = {}
    return {"ok": True, "story": str(data.get("story") or "").strip(),
            "world": str(data.get("world") or "").strip(),
            "rules": str(data.get("rules") or "").strip()}


def _do_retitle(d):
    """批量重设计第 start~end 章标题（任务化，可停止；只改标题，不碰正文与章节顺序）。"""
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    try:
        start = int(d.get("start") or 0)
        end = int(d.get("end") or 0)
    except (TypeError, ValueError):
        return {"error": "章号须为整数"}
    if start > end:
        start, end = end, start
    if start < 1:
        return {"error": "章号非法"}
    if store.load_chapter(start) is None:
        return {"error": "第 %d 章还不存在，无法重设计章节名。" % start}
    # v1.58 默认读该章完整正文取题（更贴合内容，避免只看开头被带偏）；前端可取消勾选省 token
    with_content = bool(d.get("content", True))
    # v1.64 生成页「重新设计章节名」卡片内的命名规则输入框：提交时一并持久化（与文风参考 ③.8 同字段）
    tr = d.get("title_rules")
    if isinstance(tr, str):
        project.story_title_rules = tr.strip()
        store.save_project(project)
    tid = _new_task()
    t = _TASKS[tid]

    def work():
        llm.set_abort(t["stop_ev"])
        try:
            logs = t["logs"]
            logs.append({"kind": "info", "msg": "开始重设计第 %d~%d 章章节名"
                         "%s（按本书类型与书名气质）…"
                         % (start, end, "（读取完整正文）" if with_content
                            else "（只看梗概，省 token）")})
            ok, fail = main_ai.retitle_chapters(project, store, start, end,
                                                with_content=with_content)
            logs.append({"kind": "info", "msg": "章节标题重设计完成：成功 %d 章，未处理 %d 章"
                         "（原标题保留）。" % (ok, fail)})
            _finish_task(tid, result={"ok": True, "changed": ok, "failed": fail,
                                      "start": start, "end": end})
        except llm.StopRequested:
            _finish_task(tid, error="已停止")
        except Exception as e:
            traceback.print_exc()
            _finish_task(tid, error="章节标题重设计失败：%s" % e)
        finally:
            llm.set_abort(None)

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "task_id": tid}


def _do_branch_list(d):
    """分支存档列表（if 线）：[{name, fname, saved_at, chapters}]。"""
    store, project = _current()
    if store is None:
        return {"ok": True, "branches": []}
    return {"ok": True, "branches": store.list_branches()}


def _do_branch_save(d):
    """把当前项目完整状态存为分支（同名直接覆盖，前端负责确认）。"""
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    name = str(d.get("name") or "").strip()
    if not name:
        return {"error": "请填写分支名"}
    try:
        store.save_branch(name)
    except Exception as e:
        traceback.print_exc()
        return {"error": "分支保存失败：%s" % e}
    store.append_log("分支已保存：《%s》" % name)
    return {"ok": True, "name": name}


def _do_branch_load(d):
    """载入分支：把当前项目整体替换为分支状态（设定/进度/角色/章节/伏笔）。"""
    store, project = _current()
    if store is None or project is None:
        return {"error": "无项目"}
    name = str(d.get("name") or "").strip()
    if not name:
        return {"error": "请选择要载入的分支"}
    data = store.load_branch(name)
    if not data:
        return {"error": "分支数据缺失或已损坏"}
    try:
        store.apply_branch(data, name)
    except Exception as e:
        traceback.print_exc()
        return {"error": "载入分支失败：%s" % e}
    store.append_log("已载入分支：《%s》。" % name)
    return {"ok": True, "name": name}


def _do_branch_delete(d):
    """删除一个分支存档（只删分支文件，不影响当前项目）。"""
    store, project = _current()
    if store is None:
        return {"error": "无项目"}
    name = str(d.get("name") or "").strip()
    if not name:
        return {"error": "请选择要删除的分支"}
    store.delete_branch(name)
    return {"ok": True, "name": name}


# ---------- 码字（v1.56 移植：＋新建下一章 / AI 续写） ----------
def _write_continue_prompt(project, ahead, n, directive="", store=None):
    """码字页 AI 续写提示词（镜像 PC gui_write._continue_prompt）：
    以光标前文为衔接续写约 n 字；directive=用户附加方向（优先级最高）；
    文风要求/主AI笔记/人物读取推理三块按 config tool_ctx_* 开关选择性注入（省 token 可关）。"""
    cfg = config.load_config()
    sys = ("你是资深网络小说作者，保持《%s》的文风与叙事节奏续写正文。"
           "要求：衔接自然、细节饱满、人物语言与情绪符合前文，禁止复述前文内容"
           "、禁止加作者旁白；只输出续写正文。" % (project.title or "本书"))
    user = "【前文】\n%s\n\n【续写要求】请紧接上文自然续写约 %d 字。" % (
        (ahead or "")[-1600:] if ahead else "（本书开篇）", n)
    if (directive or "").strip():
        user += "\n【用户指定方向（优先级最高，必须满足）】%s" % directive.strip()
    import prompts as prompts_mod
    blocks = prompts_mod.writing_ctx_blocks(
        project, store,
        ctx_style=bool(cfg.get("tool_ctx_style", True)),
        ctx_notes=bool(cfg.get("tool_ctx_notes", True)),
        ctx_rp=bool(cfg.get("tool_ctx_rp", True)))
    if blocks:
        user += "\n\n【任务上下文】\n" + "\n".join(blocks)
    return sys, user


def _do_chapter_new(d):
    """＋新建下一章（镜像 PC 码字页 _new_chapter 的下一章定位）：

    章号 = max(项目 next_chapter, 已有最大章号+1)（避免覆盖已归档章节）；预建一张空章节
    （status=draft，前端随后用 chapter_edit 保存正文），并返回与 chapter 路由完全相同的载荷。
    """
    store, project = _current()
    if store is None or project is None:
        return {"error": "请先创建/载入项目"}
    try:
        nxt = int((project.state or {}).get("next_chapter", 1) or 1)
    except (TypeError, ValueError):
        nxt = 1
    nxt = max(1, nxt)
    done = store.list_chapter_indices()
    if done:
        nxt = max(nxt, max(done) + 1)
    if store.load_chapter(nxt) is None:
        ch = Chapter(index=nxt)
        ch.title = "第%d章" % nxt
        store.save_chapter(ch)
        store.append_log("码字：新建第 %d 章（保存正文后正式归档）。" % nxt)
    return _do_chapter({"seq": nxt})


def _do_write_continue(d):
    """码字页 AI 续写（任务化，可停止）：text=光标前文、hint=想写什么（可选）、n≈续写字数。

    结果 result={"ok":True,"text":str}；停止走既有 book_stop（按 task_id）。"""
    store, project = _current()
    if store is None or project is None:
        return {"error": "请先创建/载入项目"}
    text = str(d.get("text") or "")
    if not text.strip():
        return {"error": "请先输入正文（续写需要前文衔接）"}
    hint = str(d.get("hint") or "").strip()
    try:
        n = int(d.get("n") or 400)
    except (TypeError, ValueError):
        n = 400
    if n < 1:
        n = 1
    tid = _new_task()
    t = _TASKS[tid]

    def work():
        llm.set_abort(t["stop_ev"])
        try:
            sys, user = _write_continue_prompt(project, text[-1600:], n, hint, store)
            out = (llm.chat_text(sys, user, role="write_tool") or "").strip()
            if not out:
                _finish_task(tid, error="模型返回为空，请重试。")
                return
            t["logs"].append({"kind": "info", "msg": "AI 续写完成（%d 字）。" % len(out)})
            _finish_task(tid, result={"ok": True, "text": out})
        except llm.StopRequested:
            _finish_task(tid, error="已停止")
        except Exception as e:
            traceback.print_exc()
            _finish_task(tid, error="续写失败：%s" % e)
        finally:
            llm.set_abort(None)

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "task_id": tid}


# ---------- 设置 ----------
# v1.56 用途分工/思考强度的功能键全集（14 项，与 PC 设置页「用途分工」各行一一对应）：
# 主AI决断与校验 / 正文写作 / 角色推理 / 去AI味 / 审查AI / 码字AI / 拆书工坊 / 小说导入 /
# 情景提示词制作 / 文风校对四节点（A 提取·B 生成·C 评分·D 优化）/ AI 对话。
_ROLE_KEYS = ("decide", "write", "reason", "deai", "review", "write_tool", "break",
              "import", "scene_card", "style_a", "style_b", "style_c", "style_d", "chat")
# 各功能思考强度可选值（""=跟随全局 reasoning_effort）
_THINK_LEVELS = ("", "off", "low", "medium", "high", "max")


def _do_settings_get(d):
    cfg = config.load_config()
    profs = cfg.get("api_profiles") or []
    p = profs[0] if profs else {}
    return {"ok": True,
            "base_url": p.get("base_url") or "",
            "api_key": p.get("api_key") or "",
            "model": p.get("model") or "",
            "temperature": cfg.get("temperature"),
            "max_tokens": cfg.get("max_tokens"),
            "chapter_target_chars": cfg.get("chapter_target_chars"),
            # v1.56 正文长度上下限（0=自动：下限=目标×0.8、上限=目标×1.15）
            "chapter_min_chars": cfg.get("chapter_min_chars"),
            "chapter_max_chars": cfg.get("chapter_max_chars"),
            "max_workers": cfg.get("max_workers"),
            "request_timeout": cfg.get("request_timeout"),
            "retry_times": cfg.get("retry_times"),
            "retry_interval": cfg.get("retry_interval"),
            "rate_limit_min_wait": cfg.get("rate_limit_min_wait"),
            "compress_interval": cfg.get("compress_interval"),
            "writer_recent_chapters": cfg.get("writer_recent_chapters"),
            # v1.60 主AI判断可读前几章正文（出场决断/综合校验/审查；0=不看，默认1）
            "main_recent_chapters": cfg.get("main_recent_chapters"),
            "foreshadow_overdue_chapters": cfg.get("foreshadow_overdue_chapters"),
            "web_search_enabled": cfg.get("web_search_enabled"),
            "auto_rewrite": cfg.get("auto_rewrite"),
            "reasoning_effort": cfg.get("reasoning_effort"),
            # v1.56 推理编排模式（sequential=决断/推理/写作串行；parallel=推理并行）
            "reasoning_mode": cfg.get("reasoning_mode"),
            # v1.56 码字 AI 任务上下文开关（续写/段落工具共用，省 token 可关；默认全开）
            "tool_ctx_style": cfg.get("tool_ctx_style"),
            "tool_ctx_notes": cfg.get("tool_ctx_notes"),
            "tool_ctx_rp": cfg.get("tool_ctx_rp"),
            "proofread_enabled": cfg.get("proofread_enabled"),
            "proofread_rules": cfg.get("proofread_rules"),
            "tone_words_custom": cfg.get("tone_words_custom") or [],
            # v0.56 拆书设置（v0.31 加三档模式；v0.32 智能模式三档子模式 + 模型上下文）
            "break_profile": cfg.get("break_profile") or "",
            "break_mode": cfg.get("break_mode") or "smart",
            "break_smart_sub": cfg.get("break_smart_sub") or "balanced",
            "model_context_window": cfg.get("model_context_window", 0),
            "break_token_per_part": cfg.get("break_token_per_part", 8000),
            "break_overlap_token": cfg.get("break_overlap_token", 0),
            "break_l3_batch": cfg.get("break_l3_batch", 0),
            "break_parallel": cfg.get("break_parallel", False),
            "break_parallel_n": cfg.get("break_parallel_n", 2),
            "break_prompt": cfg.get("break_prompt") or "",
            # v0.29 小说导入成项目：单独 API（默认跟随拆书）+ 小说整体规划
            "import_profile": cfg.get("import_profile") or "",
            "import_intro": cfg.get("import_intro") or "",
            # v0.36 文风校对：单独 API（留空跟随全局用途分工）
            "style_profile": cfg.get("style_profile") or "",
            # v1.56 情景提示词制作：单独 API（留空跟随全局用途分工）
            "scene_card_profile": cfg.get("scene_card_profile") or "",
            # v0.37 文风校对四节点各选 API（style_profiles dict，每节点留空跟随全局）
            "style_profiles": cfg.get("style_profiles") or {},
            # v1.47 AI 对话单独选 API（留空跟随全局/当前配置）
            "chat_profile": cfg.get("chat_profile") or "",
            "profiles": profs,
            "current_profile": cfg.get("current_profile"),
            # v1.56 各功能思考强度（{"decide":"low",...}，空=跟随全局 reasoning_effort）
            "role_thinking": cfg.get("role_thinking") or {},
            "role_profiles": cfg.get("role_profiles") or {}}


def _do_settings_save(d):
    cfg = config.load_config()
    profs = cfg.setdefault("api_profiles", [])
    base = str(d.get("base_url") or "").strip()
    key = str(d.get("api_key") or "").strip()
    model = str(d.get("model") or "").strip()
    if profs:
        p = profs[0]
        if base:
            p["base_url"] = base
        if key:
            p["api_key"] = key
        if model:
            p["model"] = model
    else:
        profs.append({"name": "默认配置",
                      "base_url": base or "https://api.deepseek.com/v1",
                      "api_key": key, "model": model, "role": "all"})
    if not cfg.get("current_profile"):
        cfg["current_profile"] = "默认配置"
    _fill_cfg(cfg, d)
    config.save_config(cfg)
    return {"ok": True}


def _fill_cfg(cfg, d):
    int_keys = ("max_tokens", "chapter_target_chars", "chapter_min_chars",
                "chapter_max_chars", "max_workers", "request_timeout", "retry_times",
                "retry_interval", "rate_limit_min_wait", "compress_interval",
                "writer_recent_chapters", "main_recent_chapters",
                "foreshadow_overdue_chapters")
    for k in int_keys:
        if k in d:
            try:
                cfg[k] = int(d[k])
            except (TypeError, ValueError):
                pass
    if "temperature" in d:
        try:
            cfg["temperature"] = float(d["temperature"])
        except (TypeError, ValueError):
            pass
    for k in ("web_search_enabled", "auto_rewrite", "proofread_enabled",
              # v1.56 码字 AI 任务上下文开关（续写/段落工具共用）
              "tool_ctx_style", "tool_ctx_notes", "tool_ctx_rp"):
        if k in d:
            cfg[k] = bool(d[k])
    if "reasoning_effort" in d:
        cfg["reasoning_effort"] = str(d["reasoning_effort"]) or None
    # v1.56 推理编排模式（sequential=串行 / parallel=推理并行；非法值忽略）
    if "reasoning_mode" in d:
        m = str(d["reasoning_mode"] or "").strip()
        if m in ("sequential", "parallel"):
            cfg["reasoning_mode"] = m
    if "proofread_rules" in d:
        cfg["proofread_rules"] = str(d["proofread_rules"]) or None
    if "tone_words_custom" in d and isinstance(d["tone_words_custom"], list):
        cfg["tone_words_custom"] = [str(x).strip() for x in d["tone_words_custom"]
                                    if str(x).strip()]
    # v0.56 拆书设置
    if "break_profile" in d:
        cfg["break_profile"] = str(d["break_profile"]) or None
    if "import_profile" in d:
        cfg["import_profile"] = str(d["import_profile"]) or None
    if "import_intro" in d:
        cfg["import_intro"] = str(d["import_intro"]) or None
    if "style_profile" in d:
        cfg["style_profile"] = str(d["style_profile"]) or None
    if "style_profiles" in d and isinstance(d["style_profiles"], dict):
        cfg["style_profiles"] = {
            k: (str(v) or None) for k, v in d["style_profiles"].items()
            if k in ("node_a", "node_b", "node_c", "node_d")}
    if "chat_profile" in d:
        cfg["chat_profile"] = str(d["chat_profile"]).strip() or None
    # v1.56 情景卡辅助配置（留空 = None，跟随全局；与 PC 端字段保持一致）
    if "scene_card_profile" in d:
        cfg["scene_card_profile"] = str(d["scene_card_profile"]).strip() or None
    if "break_mode" in d:
        m = str(d["break_mode"])
        if m in ("simple", "smart", "advanced"):
            cfg["break_mode"] = m
    if "break_smart_sub" in d:
        m = str(d["break_smart_sub"])
        if m in ("conservative", "balanced", "aggressive"):
            cfg["break_smart_sub"] = m
    if "model_context_window" in d:
        try:
            cfg["model_context_window"] = max(0, min(10000000, int(d["model_context_window"])))
        except (TypeError, ValueError):
            pass
    if "break_token_per_part" in d:
        try:
            cfg["break_token_per_part"] = max(1000, int(d["break_token_per_part"]))
        except (TypeError, ValueError):
            pass
    if "break_overlap_token" in d:
        try:
            cfg["break_overlap_token"] = max(0, int(d["break_overlap_token"]))
        except (TypeError, ValueError):
            pass
    if "break_l3_batch" in d:
        try:
            cfg["break_l3_batch"] = max(0, min(60, int(d["break_l3_batch"])))
        except (TypeError, ValueError):
            pass
    if "break_parallel" in d:
        cfg["break_parallel"] = bool(d["break_parallel"])
    if "break_parallel_n" in d:
        try:
            cfg["break_parallel_n"] = max(1, min(8, int(d["break_parallel_n"])))
        except (TypeError, ValueError):
            pass
    if "break_prompt" in d:
        cfg["break_prompt"] = str(d["break_prompt"]) or None
    # v1.56 用途分工（14 个功能键）与各功能思考强度：
    # role_profiles = 功能 → API 配置名；role_thinking = 功能 → 思考档位（""=跟随全局）
    if "role_thinking" in d and isinstance(d["role_thinking"], dict):
        cfg["role_thinking"] = {
            k: str(v) for k, v in d["role_thinking"].items()
            if k in _ROLE_KEYS and str(v) in _THINK_LEVELS}
    if "role_profiles" in d and isinstance(d["role_profiles"], dict):
        cfg["role_profiles"] = {k: str(v) for k, v in d["role_profiles"].items()
                                if k in _ROLE_KEYS and v}
    if "current_profile" in d and str(d["current_profile"]):
        cfg["current_profile"] = str(d["current_profile"])


def _do_profiles_save(d):
    cfg = config.load_config()
    name = str(d.get("name") or "").strip()
    if not name:
        return {"error": "配置名不能为空"}
    profs = cfg.setdefault("api_profiles", [])
    for p in profs:
        if p.get("name") == name:
            for k in ("base_url", "api_key", "model", "role"):
                if d.get(k) is not None:
                    p[k] = str(d[k])
            break
    else:
        profs.append({"name": name,
                      "base_url": str(d.get("base_url") or "https://api.deepseek.com/v1"),
                      "api_key": str(d.get("api_key") or ""),
                      "model": str(d.get("model") or ""),
                      "role": str(d.get("role") or "all")})
    if not cfg.get("current_profile"):
        cfg["current_profile"] = name
    config.save_config(cfg)
    return {"ok": True}


def _do_profiles_delete(d):
    cfg = config.load_config()
    name = str(d.get("name") or "").strip()
    profs = cfg.get("api_profiles") or []
    cfg["api_profiles"] = [p for p in profs if p.get("name") != name]
    config.save_config(cfg)
    return {"ok": True}


def _do_fetch_models(d):
    cfg = config.load_config()
    profs = cfg.get("api_profiles") or []
    p = profs[0] if profs else {}
    base = str(d.get("base_url") or p.get("base_url") or "")
    key = str(d.get("api_key") or p.get("api_key") or "")
    if not base:
        return {"error": "未填写 API 地址（base_url）。"}
    if not key:
        return {"error": "未填写 API Key。"}
    try:
        # v1.13 去掉硬编码 20s：跟随设置页「请求超时」（与 PC 端 fetch_models_detailed 一致）
        data = llm.fetch_models(base, key)
    except Exception as e:
        return {"error": "拉取模型失败：%s" % e}
    return {"ok": True, "models": data}


_ROUTES = {
    "state": _state,
    "projects": _do_projects,
    "project_new": _do_project_new,
    "project_switch": _do_project_switch,
    "project_delete": _do_project_delete,
    "project_create": _do_project_create,
    "project_save": _do_project_save,
    "project_title_rules": _do_project_title_rules,
    "voice_input": _do_voice_input,
    "lore_list": _do_lore_list,
    "lore_save": _do_lore_save,
    "plan_get": _do_plan_get,
    "plan_add": _do_plan_add,
    "plan_del": _do_plan_del,
    "characters": _character_list,
    "character_get": _do_character_get,
    "character_save": _do_character_save,
    "character_create": _do_character_create,
    "character_delete": _do_character_delete,
    "character_batch": _do_character_batch,
    "character_ai": _do_character_ai,
    "character_ai_batch": _do_character_ai_batch,
    "character_import": _do_character_import,
    "classify": _do_classify,
    "style_extract": _do_style_extract,
    "generate": _do_generate,
    "generate_auto": _do_generate_auto,
    "book_auto": _do_book_auto,
    "book_stop": _do_book_stop,
    "task_status": _do_task_status,
    "task_confirm": _do_task_confirm,
    "finalize": _do_finalize,
    "regenerate": _do_regenerate,
    "chapters": _do_chapters,
    "chapter": _do_chapter,
    "chapter_delete": _do_chapter_delete,
    "volume_set": _do_volume_set,
    "drafts_list": _do_drafts_list,
    "draft_restore": _do_draft_restore,
    "draft_delete": _do_draft_delete,
    "timeline": _do_timeline,
    "foreshadows": _do_foreshadows,
    "fore_mark": _do_fore_mark,
    "note_get": _do_note_get,
    "knowledge": _do_knowledge_get,
    "logs": _do_logs_get,
    "chapter_edit": _do_chapter_edit,
    "polish": _do_polish,
    "search": _do_search,
    "swap": _do_swap,
    "stats": _do_stats,
    "rewrite": _do_rewrite,
    "volume_merge": _do_volume_merge,
    "deai_run": _do_deai_run,
    "deai_apply": _do_deai_apply,
    "editor_review": _do_editor_review,
    "project_export": _do_project_export,
    "project_import": _do_project_import,
    "pick_import": _do_pick_import,
    "orientation": _do_orientation,
    "export_epub": _do_export_epub,
    "export_txt": _do_export_txt,
    "pick_txt": _do_pick_txt,
    "break_parse": _do_break_parse,
    "break_import_doc": _do_break_import_doc,
    "break_start": _do_break_start,
    "break_stop": _do_break_stop,
    "break_save": _do_break_save,
    "breaks_list": _do_breaks_list,
    "break_load": _do_break_load,
    "break_delete": _do_break_delete,
    "break_apply": _do_break_apply,
    "break_export": _do_break_export,
    "stylecheck_prompts": _do_stylecheck_prompts,
    "stylecheck_prompts_save": _do_stylecheck_prompts_save,
    "stylecheck_presets_save": _do_stylecheck_presets_save,
    "stylecheck_presets_delete": _do_stylecheck_presets_delete,
    "stylecheck_presets_apply": _do_stylecheck_presets_apply,
    "stylecheck_start": _do_stylecheck_start,
    "stylecheck_stop": _do_stylecheck_stop,
    "stylecheck_export": _do_stylecheck_export,
    "import_start": _do_import_start,
    "import_stop": _do_import_stop,
    "chat_topics": _do_chat_topics,
    "chat_open": _do_chat_open,
    "chat_create": _do_chat_create,
    "chat_rename": _do_chat_rename,
    "chat_delete": _do_chat_delete,
    "chat_send": _do_chat_send,
    "chat_continue": _do_chat_continue,
    "chat_regen": _do_chat_regen,
    "chat_edit_last": _do_chat_edit_last,
    "chat_delete_last": _do_chat_delete_last,
    "chat_stop": _do_chat_stop,
    "chat_export": _do_chat_export,
    "settings_get": _do_settings_get,
    "settings_save": _do_settings_save,
    "profiles_save": _do_profiles_save,
    "profiles_delete": _do_profiles_delete,
    "fetch_models": _do_fetch_models,
    # ---------- v1.56 情景卡总库（config.writer_scene_cards）----------
    "scene_cards_list": _do_scene_cards_list,
    "scene_cards_save": _do_scene_cards_save,
    "scene_cards_delete": _do_scene_cards_delete,
    "scene_cards_generate": _do_scene_cards_generate,
    "scene_cards_extract": _do_scene_cards_extract,
    "scene_cards_prompt_get": _do_scene_cards_prompt_get,
    "scene_cards_prompt_save": _do_scene_cards_prompt_save,
    "scene_cards_prompt_reset": _do_scene_cards_prompt_reset,
    "scene_cards_import_txt": _do_scene_cards_import_txt,
    "scene_cards_export": _do_scene_cards_export,
    "scene_cards_export_all": _do_scene_cards_export_all,
    # ---------- v1.56 项目情景卡库（project.scene_cards）----------
    "scene_cards_project_list": _do_scene_cards_project_list,
    "scene_cards_project_add": _do_scene_cards_project_add,
    "scene_cards_project_remove": _do_scene_cards_project_remove,
    "scene_cards_project_to_library": _do_scene_cards_project_to_library,
    "scene_cards_adapt": _do_scene_cards_adapt,
    # ---------- v1.56 项目页：立项 / 重定标题 / 分支 ----------
    "plan_story": _do_plan_story,
    "retitle": _do_retitle,
    "branch_list": _do_branch_list,
    "branch_save": _do_branch_save,
    "branch_load": _do_branch_load,
    "branch_delete": _do_branch_delete,
    # ---------- v1.56 码字：新建章节 / 续写 ----------
    "chapter_new": _do_chapter_new,
    "write_continue": _do_write_continue,
}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _cors_headers(self):
        # WebView 以 file:// 加载前端（origin=null）fetch 本机 http 服务——
        # 必须返回 CORS 许可头，否则浏览器策略拦截全部 API 请求（安卓端功能全挂的根因）
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        # fetch POST（application/json）触发 CORS 预检：直接放行
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _dispatch(self, method):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/").split("/api/")[-1]
            fn = _ROUTES.get(path)
            if fn is None:
                self._send(404, {"error": "no such api: %s" % path})
                return
            if method == "GET":
                q = parse_qs(parsed.query)
                d = {k: v[0] for k, v in q.items()}
            else:
                ln = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(ln) if ln else b""
                d = json.loads(raw.decode("utf-8")) if raw else {}
            if path == "fetch_models":
                # v1.13 网络请求不持全局锁（拉取模型可能数十秒，期间 task_status 等轮询不该全被堵死）
                out = fn(d)
            else:
                with _LOCK:
                    out = fn(d)
            self._send(200, out)
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": "server error: %s" % e})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")


def start_server(port=0):
    global _SERVER
    if _SERVER is None:
        _SERVER = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        threading.Thread(target=_SERVER.serve_forever, daemon=True).start()
    return _SERVER.server_address[1]


def start_app(files_dir, activity=None):
    """MainActivity 入口：bootstrap 数据目录 + 起本地服务器 + 记住 Activity（文件选择/分享桥）。

    返回 WebView 需要的端口。
    """
    bootstrap(files_dir)
    if activity is not None:
        _ACTIVITY[0] = activity
    return start_server(0)
