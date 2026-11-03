# -*- coding: utf-8 -*-
"""端到端全流程测试（真实 API）：
建项目 → AI 生成核心角色 → 逐章生成 3 章 → 导出小说/角色卡 → 重写第 2 章（世界回滚+重新生成）
→ 补回第 3 章 → 再次导出。
日志写入 e2e.log；测试项目「端到端测试」保留在 projects/ 下供查看。
"""
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "src"))
# 控制台输出统一 UTF-8，避免 GBK 编码崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config  # noqa: E402
import storage  # noqa: E402
import llm  # noqa: E402
import engine  # noqa: E402

# 给每次 LLM 调用加请求级日志，便于监控卡点（产品层已有自适应节流处理限流）
_orig_chat = llm.chat


def _chat_wrap(*args, **kwargs):
    tag = kwargs.get("tag", "?")
    # e2e 强制短超时：deepseek 高峰期偶发 10 分钟级无响应，180s 超时快速失败重试
    kwargs = dict(kwargs)
    kwargs["timeout"] = 180
    t0 = time.time()
    try:
        r = _orig_chat(*args, **kwargs)
        log("  LLM 完成: %s（%.1fs）" % (tag, time.time() - t0))
        return r
    except llm.LLMError as e:
        log("  LLM 失败: %s（%.1fs）%s" % (tag, time.time() - t0, str(e)[:120]))
        raise


llm.chat = _chat_wrap

PROJECT_TITLE = "端到端测试"
EXPORT_DIR = os.path.join(_ROOT, "output")
LOG_PATH = os.path.join(_ROOT, "e2e.log")

STORY_BRIEF = (
    "【世界观】架空低魔大陆，铁器城邦与古老秘术组织并存；失落遗迹中封存着可改写城邦命运的旧日力量。\n"
    "【开局】佣兵主角受雇护送一名神秘信使，途经黑松岭时遭遇截杀，信使临终托付一枚刻有古老符文的铜钥，"
    "叮嘱务必带到北境明珠城交给「灰袍药师」。\n"
    "【本卷主线】主角循铜钥线索追查，在明珠城结识女药师与退役军官；三股势力（城主府鹰派、秘术隐修会、"
    "南方佣兵公会）为争夺遗迹明争暗斗；主角逐渐发现铜钥与自身身世有关，昔日护送任务另有隐情。\n"
    "【结尾方向】遗迹入口在血月之夜开启，主角被迫在三股势力间做出关键抉择，卷末留下下一卷悬念。"
)


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def find_project():
    for p in storage.list_projects():
        if p["title"] == PROJECT_TITLE:
            return p["dir"]
    return None


def export_novel(store, project, tag=""):
    indices = store.list_chapter_indices()
    lines = ["%s %s" % (project.title, tag), "=" * 40, ""]
    if (project.story_brief or "").strip():
        lines += ["【故事设定】%s" % project.story_brief, ""]
    if (project.story_summary or "").strip():
        lines += ["【主AI管理笔记】%s" % project.story_summary, ""]
    total_chars = 0
    for i in indices:
        ch = store.load_chapter(i)
        if not ch:
            continue
        total_chars += len(ch.content or "")
        lines += ["", "%s" % ch.title, "-" * 30, ch.content, ""]
    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, "%s%s.txt" % (PROJECT_TITLE, tag))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log("小说已导出：%s（%d 章，正文 %d 字）" % (path, len(indices), total_chars))
    return path


def export_cards(store, tag=""):
    from gui_characters import export_character_json
    card_dir = os.path.join(EXPORT_DIR, "角色卡%s" % tag)
    os.makedirs(card_dir, exist_ok=True)
    n = 0
    for cid, name, _ in store.list_characters():
        card, lib = store.load_character(cid)
        if not card:
            continue
        data = export_character_json(card, lib)
        with open(os.path.join(card_dir, "%s.json" % name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        n += 1
    log("角色卡已导出：%d 张 → %s" % (n, card_dir))
    return card_dir


def stage_chapter(store, project, eng, ch_no):
    log("═══ 生成第 %d 章（真实API）═══" % ch_no)
    t0 = time.time()
    chapter = eng.generate_draft(project)
    if chapter is None:
        raise RuntimeError("第 %d 章草稿生成失败" % ch_no)
    eng.finalize_chapter(project, chapter)
    log("第 %d 章完成：《%s》（%d 字，耗时 %.1f 分钟）"
        % (ch_no, chapter.title, len(chapter.content or ""), (time.time() - t0) / 60))
    return chapter


def main():
    # 清空旧日志
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
    log("════ 端到端全流程测试开始（项目：%s）════" % PROJECT_TITLE)

    # 0. 清理旧测试项目
    old = find_project()
    if old:
        storage.delete_project(old)
        log("已清理旧测试项目")

    # 1. 创建项目
    project = storage.create_project(PROJECT_TITLE)
    project.story_brief = STORY_BRIEF
    project.volume_target = 0
    store = storage.ProjectStore(project.dir_name)
    store.save_project(project)
    log("① 项目已创建：%s" % PROJECT_TITLE)
    eng = engine.NovelEngine(store, lambda kind, msg: log("[%s] %s" % (kind, msg)))

    # 2. 主AI生成核心角色（角色卡生成）
    log("② 主AI生成核心角色（真实API，3张角色卡）…")
    eng.ensure_world(project)
    chars = store.list_characters()
    log("角色池：%s" % "、".join("%s[%s]" % (n, s) for _, n, s in chars))
    assert len(chars) >= 3, "应至少生成 3 张角色卡"

    # 3. 逐章生成（1-3）
    for n in (1, 2, 3):
        stage_chapter(store, project, eng, n)

    # 4. 导出（第3章后）
    log("③ 导出小说与角色卡（第3章后）…")
    export_novel(store, project, tag="_3章后")
    export_cards(store, tag="_3章后")

    # 5. 重写第 2 章（世界回滚 + 重新生成）
    log("④ 重写第 2 章（世界状态回滚到第 1 章后，删除第 2、3 章）…")
    ok = eng.rewrite_from(project, 2)
    assert ok, "rewrite_from(2) 应成功"
    project = store.load_project()
    assert project.state["next_chapter"] == 2, "进度应回退到第 2 章"
    assert store.list_chapter_indices() == [1], "第 2、3 章应被删除"
    log("回滚验证：进度=%d，现存章节=%s，快照=%s"
        % (project.state["next_chapter"], store.list_chapter_indices(),
           store.list_snapshot_indices()))
    new_ch2 = stage_chapter(store, project, eng, 2)

    # 6. 补回第 3 章
    log("⑤ 重新生成第 3 章（接续新第 2 章）…")
    stage_chapter(store, project, eng, 3)

    # 7. 最终导出
    log("⑥ 最终导出…")
    novel_path = export_novel(store, project, tag="_最终")
    card_dir = export_cards(store, tag="_最终")

    # 8. 汇总
    indices = store.list_chapter_indices()
    log("════ 汇总 ════")
    log("项目：%s（%s）" % (PROJECT_TITLE, project.dir_name))
    for i in indices:
        ch = store.load_chapter(i)
        log("  第%d章《%s》（%d字）brief：%s"
            % (ch.index, ch.title, len(ch.content or ""), (ch.brief or "")[:30]))
    log("角色卡：%d 张（含信息库）" % len(store.list_characters()))
    log("世界快照：%s" % store.list_snapshot_indices())
    log("小说导出：%s" % novel_path)
    log("角色卡导出：%s" % card_dir)
    log("管理笔记：%s" % ((project.story_summary or "")[:60] or "（尚未压缩）"))
    log("════ E2E_DONE ════")


if __name__ == "__main__":
    try:
        main()
    except llm.LLMError as e:
        log("E2E 失败（LLM）：%s" % e)
        sys.exit(2)
    except Exception as e:
        import traceback
        log("E2E 失败：%s" % e)
        log(traceback.format_exc())
        sys.exit(1)
