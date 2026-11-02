# -*- coding: utf-8 -*-
"""项目持久化：index / project.json / characters / chapters / foreshadows / 日志。"""
import json
import os
import re
import threading

from models import (CHAPTER_STATUS_APPROVED, CharacterCard, Chapter,
                    Foreshadow, InfoLibrary, NovelProject, now)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_DIR = os.path.join(_ROOT, "projects")
INDEX_PATH = os.path.join(PROJECTS_DIR, "index.json")

_lock = threading.Lock()
_index_lock = threading.Lock()   # 章节索引文件读-改-写串行锁

# 草稿箱备份文件名：draft_ch_<章号3位>_<YYYY-MM-DD_HHMMSS>_<tag>[-<序号>].json
# （list_chapter_drafts 靠它零读取出列表，v2.60 性能优化）
_DRAFT_RE = re.compile(r"^draft_ch_(\d+)_(\d{4}-\d{2}-\d{2}_\d{6})_(\w+?)(?:-(\d+))?\.json$")


def _read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _slug(name):
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", name.strip(), flags=re.UNICODE)
    return s or "project"


class ProjectStore:
    """单个小说项目的读写。"""

    def __init__(self, dir_name):
        self.dir_name = dir_name
        self.base = os.path.join(PROJECTS_DIR, dir_name)
        self.char_dir = os.path.join(self.base, "characters")
        self.chapter_dir = os.path.join(self.base, "chapters")
        self.project_path = os.path.join(self.base, "project.json")
        self.foreshadow_path = os.path.join(self.base, "foreshadows.json")
        self.log_path = os.path.join(self.base, "log.jsonl")

    # ---------- project ----------
    def load_project(self):
        d = _read_json(self.project_path, {})
        if not d:
            return None
        return NovelProject.from_dict(d, self.dir_name)

    def save_project(self, project):
        project.updated_at = now()
        _write_json(self.project_path, project.to_dict())

    # ---------- characters ----------
    def list_characters(self):
        out = []
        if os.path.isdir(self.char_dir):
            for fn in sorted(os.listdir(self.char_dir)):
                if fn.endswith(".json"):
                    d = _read_json(os.path.join(self.char_dir, fn))
                    if d and d.get("card"):
                        c = CharacterCard.from_dict(d["card"])
                        out.append((c.id, c.name, c.status))
        return out

    def list_character_cards(self):
        """批量读取全部角色卡（一次遍历磁盘，避免逐张读盘）。

        返回 [(CharacterCard, InfoLibrary), ...]；供角色页缓存后按分类渲染，
        角色很多（数百张）时避免每次刷新逐张 load_character 造成的卡顿。
        """
        out = []
        if os.path.isdir(self.char_dir):
            for fn in sorted(os.listdir(self.char_dir)):
                if fn.endswith(".json"):
                    d = _read_json(os.path.join(self.char_dir, fn))
                    if d and d.get("card"):
                        out.append((CharacterCard.from_dict(d["card"]),
                                    InfoLibrary.from_dict(d.get("library", {}))))
        return out

    def get_character_ids(self):
        return [cid for cid, _, _ in self.list_characters()]

    def load_character(self, char_id):
        path = os.path.join(self.char_dir, char_id + ".json")
        d = _read_json(path)
        if not d:
            return None, None
        return CharacterCard.from_dict(d.get("card", {})), InfoLibrary.from_dict(d.get("library", {}))

    def save_character(self, card, library=None):
        d = {"card": card.to_dict()}
        if library is not None:
            d["library"] = library.to_dict()
        _write_json(os.path.join(self.char_dir, card.id + ".json"), d)

    def delete_character(self, char_id):
        path = os.path.join(self.char_dir, char_id + ".json")
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    # ---------- chapters ----------
    def chapter_path(self, index):
        return os.path.join(self.chapter_dir, "ch_%03d.json" % index)

    def save_chapter(self, chapter):
        chapter.updated_at = now()
        _write_json(self.chapter_path(chapter.index), chapter.to_dict())
        self._touch_chapter_index(chapter.index,
                                  chapter.title or "第%d章" % chapter.index,
                                  chapter.status, len(chapter.content or ""),
                                  chapter.brief or "", chapter.volume)

    def set_chapter_volume(self, seq, vol):
        """归卷（v0.51 分卷）：改章节 volume 并同步索引。非法卷号返回 False。"""
        try:
            vol = int(vol)
        except (TypeError, ValueError):
            return False
        ch = self.load_chapter(seq)
        if ch is None:
            return False
        ch.volume = max(1, vol)
        self.save_chapter(ch)
        return True

    def rename_volume(self, old_vol, new_vol):
        """卷重命名/归并（v0.51 分卷）：把全部 old_vol 章节改到 new_vol，索引随 save 同步。
        返回变更章节数。"""
        try:
            old_vol, new_vol = int(old_vol), int(new_vol)
        except (TypeError, ValueError):
            return 0
        if old_vol == new_vol or old_vol < 1 or new_vol < 1:
            return 0
        changed = 0
        for i in self.list_chapter_indices():
            ch = self.load_chapter(i)
            if ch is not None and int(ch.volume or 1) == old_vol:
                ch.volume = new_vol
                self.save_chapter(ch)
                changed += 1
        return changed

    def load_chapter(self, index):
        d = _read_json(self.chapter_path(index))
        return Chapter.from_dict(d) if d else None

    def list_chapter_indices(self):
        out = []
        if os.path.isdir(self.chapter_dir):
            for fn in os.listdir(self.chapter_dir):
                m = re.match(r"ch_(\d+)\.json", fn)
                if m:
                    out.append(int(m.group(1)))
        return sorted(out)

    # ---------- 章节索引（轻量标题缓存：大项目列表刷新不再逐章读全文） ----------
    def _chapter_index_path(self):
        return os.path.join(self.base, "chapters_index.json")

    def _read_chapter_index(self):
        """读取索引元数据，返回 {章节号(int): meta}（键归一化，兼容旧字符串键）。"""
        index = _read_json(self._chapter_index_path(), {}) or {}
        meta = index.get("chapters") or {}
        return {int(k): v for k, v in meta.items()}

    def _write_chapter_index(self, meta):
        _write_json(self._chapter_index_path(), {"chapters": meta})

    def _touch_chapter_index(self, seq, title, status, chars, brief="", vol=1):
        """章节写入后更新索引条目（读-改-写原子化，多线程下不丢条目）。"""
        with _index_lock:
            meta = self._read_chapter_index()
            meta[int(seq)] = {
                "title": title, "status": status, "chars": chars,
                "brief": brief, "vol": int(vol or 1),
                "mtime": os.path.getmtime(self.chapter_path(seq)),
            }
            self._write_chapter_index(meta)

    def _drop_chapter_index(self, seq):
        with _index_lock:
            meta = self._read_chapter_index()
            if int(seq) in meta:
                del meta[int(seq)]
                self._write_chapter_index(meta)

    def _rebuild_chapter_index(self):
        """全量重建索引：只取标题/状态/字数元数据，不保留正文。

        仅在索引缺失/过期时调用（低频：外部批量改动章节文件后的自愈）。
        """
        meta = {}
        if os.path.isdir(self.chapter_dir):
            for fn in os.listdir(self.chapter_dir):
                m = re.match(r"ch_(\d+)\.json", fn)
                if not m:
                    continue
                seq = int(m.group(1))
                path = os.path.join(self.chapter_dir, fn)
                d = _read_json(path)
                if not d:
                    continue
                meta[seq] = {
                    "title": str(d.get("title") or "") or "第%d章" % seq,
                    "status": d.get("status") or CHAPTER_STATUS_APPROVED,
                    "chars": len(str(d.get("content") or "")),
                    "brief": str(d.get("brief") or ""),
                    "vol": int(d.get("volume", 1) or 1),
                    "mtime": os.path.getmtime(path),
                }
        self._write_chapter_index(meta)
        return meta

    def chapter_summaries(self):
        """返回 [(章节号, {title,status,chars}), ...] 按序号升序。

        基于 chapters_index.json 轻量索引，大项目（千章级）列表刷新毫秒级完成；
        与磁盘文件集合/mtime 不一致时（外部重写/回滚/批量删除等旁路改动）自动重建。
        """
        meta = self._read_chapter_index()
        disk = {}
        if os.path.isdir(self.chapter_dir):
            try:
                with os.scandir(self.chapter_dir) as it:
                    for e in it:
                        m = re.match(r"ch_(\d+)\.json", e.name)
                        if m:
                            try:
                                disk[int(m.group(1))] = e.stat().st_mtime
                            except OSError:
                                continue
            except OSError:
                disk = {}
        if len(meta) != len(disk) or any(
                (d.get("mtime") or 0) != disk.get(s) for s, d in meta.items()):
            meta = self._rebuild_chapter_index()
        return sorted(
            (s, {"title": d.get("title", "第%d章" % s),
                 "status": d.get("status", "approved"),
                 "chars": int(d.get("chars", 0)),
                 "brief": str(d.get("brief") or ""),
                 "vol": int(d.get("vol", 1) or 1)})
            for s, d in meta.items())

    def chapter_brief(self, index):
        """取单章梗概：优先 brief 字段，回退正文首段截取。供时间线等按需补载。"""
        d = _read_json(self.chapter_path(index))
        if not d:
            return ""
        brief = str(d.get("brief") or "").strip()
        if brief:
            return brief
        content = str(d.get("content") or "").strip()
        if not content:
            return ""
        first = next((p.strip() for p in content.split("\n") if p.strip()), content)
        return first[:90] + ("…" if len(first) > 90 else "")

    def delete_chapter(self, index):
        """删除单个章节文件（不涉及世界状态回滚）。"""
        path = self.chapter_path(index)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        self._drop_chapter_index(int(index))

    # ---------- 章节交换（排序）/ 全文搜索 / 写作统计 ----------
    def swap_chapters(self, seq_a, seq_b):
        """交换两章的全部叙事内容（标题/正文/梗概/出场角色/场景/伏笔/卷归属），章号不变。

        用于章节排序（上移/下移/任两章对调）。交换前自动把两章旧版备份进草稿箱（tag=swap），
        世界状态快照**不随交换移动**（快照按「第 N 章完成时」记录，交换后回滚语义不变）。
        返回是否成功。
        """
        try:
            a, b = int(seq_a), int(seq_b)
        except (TypeError, ValueError):
            return False
        if a == b or a < 1 or b < 1:
            return False
        ca = self.load_chapter(a)
        cb = self.load_chapter(b)
        if ca is None or cb is None:
            return False
        # 先留旧版草稿，改崩/误换可找回
        self.backup_chapter_draft(ca, "swap")
        self.backup_chapter_draft(cb, "swap")
        fields = ("title", "content", "brief", "characters", "scene",
                  "foreshadows", "volume")
        for f in fields:
            va, vb = getattr(ca, f), getattr(cb, f)
            setattr(ca, f, vb)
            setattr(cb, f, va)
        self.save_chapter(ca)
        self.save_chapter(cb)
        return True

    def search_chapters(self, keyword, limit=50):
        """全文搜索：在标题/梗概/正文中查找关键词，返回命中列表（上限 limit 条）。

        每条：{"seq","title","where","snippet","chars"}；where ∈ title|brief|content。
        """
        kw = str(keyword or "").strip()
        if not kw:
            return []
        out = []
        for i in self.list_chapter_indices():
            ch = self.load_chapter(i)
            if ch is None:
                continue
            title = ch.title or "第%d章" % i
            brief = ch.brief or ""
            content = ch.content or ""
            hit = ""
            src = ""
            for name, text in (("title", title), ("brief", brief), ("content", content)):
                idx = text.find(kw)
                if idx >= 0:
                    hit, src = name, text
                    break
            if not hit or not src:
                continue
            start = max(0, src.find(kw) - 25)
            end = min(len(src), src.find(kw) + len(kw) + 55)
            snippet = src[start:end].replace("\n", " ")
            out.append({"seq": i, "title": title, "where": hit,
                        "snippet": ("…" if start > 0 else "") + snippet
                                   + ("…" if end < len(src) else ""),
                        "chars": len(content)})
            if len(out) >= int(limit):
                break
        return out

    def project_stats(self):
        """写作统计（v0.53 仪表盘）：总章数/总字数/各卷分布/当前卷进度。"""
        summaries = self.chapter_summaries()
        project = self.load_project()
        total_chars = 0
        vol_chars = {}
        vol_counts = {}
        for _i, m in summaries:
            c = int(m.get("chars", 0))
            v = int(m.get("vol", 1))
            total_chars += c
            vol_chars[v] = vol_chars.get(v, 0) + c
            vol_counts[v] = vol_counts.get(v, 0) + 1
        written = len(summaries)
        target = project.chapter_target() if project else 0
        progress = None
        if target and target > 0:
            progress = min(100.0, written * 100.0 / target)
        return {
            "chapters": written,
            "target": target,
            "total_chars": total_chars,
            "volume_chars": [{"vol": v, "chars": vol_chars.get(v, 0),
                              "count": vol_counts.get(v, 0)}
                             for v in sorted(set(list(vol_chars) + list(vol_counts)))],
            "progress": progress,
        }

    # ---------- foreshadows ----------
    def load_foreshadows(self):
        return [Foreshadow.from_dict(d) for d in _read_json(self.foreshadow_path, [])]

    def save_foreshadows(self, items):
        _write_json(self.foreshadow_path, [f.to_dict() for f in items])

    # ---------- 世界状态快照（供章节重写回滚） ----------
    def snapshot_path(self, chapter_no):
        return os.path.join(self.base, "snapshots",
                            "world_ch_%03d.json" % int(chapter_no))

    def list_snapshot_indices(self):
        d = os.path.join(self.base, "snapshots")
        out = []
        if os.path.isdir(d):
            for fn in os.listdir(d):
                m = re.match(r"world_ch_(\d+)\.json", fn)
                if m:
                    out.append(int(m.group(1)))
        return sorted(out)

    def save_world_snapshot(self, chapter_no):
        """保存「第 chapter_no 章完成后的完整性状态」：角色卡+信息库+伏笔+管理笔记
        +主AI知识库+章节元数据（章号/标题/梗概/出场角色）。

        注意：章节**不存全文**（每份快照都是全量存档，存全文会 O(N²) 体积爆炸）——
        回退时章节内容靠 chapters/ 目录文件 + 调用方删除后续章节 + 草稿箱兜底。
        """
        chars = {}
        for cid, _, _ in self.list_characters():
            card, lib = self.load_character(cid)
            if card:
                chars[cid] = {"card": card.to_dict(),
                              "library": lib.to_dict() if lib else {}}
        project = self.load_project()
        chapters = []
        for i in self.list_chapter_indices():
            ch = self.load_chapter(i)
            if ch:
                chapters.append({"index": ch.index, "title": ch.title or "第%d章" % ch.index,
                                 "brief": ch.brief or "", "characters": list(ch.characters)})
        data = {
            "chapter": int(chapter_no),
            "characters": chars,
            "chapters": chapters,
            "foreshadows": [f.to_dict() for f in self.load_foreshadows()],
            "story_summary": (project.story_summary if project else ""),
            "story_knowledge": (project.story_knowledge if project else ""),
            "story_characters": ([dict(x) for x in project.story_characters]
                                 if project else []),
            "story_ideas": ([str(x) for x in project.story_ideas]
                            if project else []),
            "chapter_plans": ([{"start": int(x.get("start", 0) or 0),
                                "end": int(x.get("end", 0) or 0),
                                "note": str(x.get("note", "") or "")}
                               for x in project.chapter_plans]
                              if project else []),
            "created_at": now(),
        }
        _write_json(self.snapshot_path(chapter_no), data)

    def load_world_snapshot(self, chapter_no):
        return _read_json(self.snapshot_path(chapter_no))

    def rollback_world(self, snap):
        """用快照覆盖当前世界：角色卡/信息库/伏笔/管理笔记/知识库。

        章节不在此恢复：由调用方按章节号删后续章节（delete_chapters_from），
        被删章节的全文可由草稿箱（drafts/）找回。
        兼容性：旧版快照缺 story_knowledge 字段时跳过对应恢复，旧快照回滚行为不变。
        """
        snap_chars = snap.get("characters") or {}
        for cid, _, _ in self.list_characters():
            if cid not in snap_chars:
                self.delete_character(cid)
        for cid, data in snap_chars.items():
            card = CharacterCard.from_dict(data.get("card", {}))
            lib = InfoLibrary.from_dict(data.get("library", {}))
            self.save_character(card, lib)
        self.save_foreshadows([Foreshadow.from_dict(d) for d in snap.get("foreshadows", [])])
        project = self.load_project()
        if project:
            project.story_summary = str(snap.get("story_summary") or "")
            if "story_knowledge" in snap:
                project.story_knowledge = str(snap.get("story_knowledge") or "")
            if "story_characters" in snap:
                _kc = snap.get("story_characters") or []
                project.story_characters = [
                    {"name": str(x.get("name", "")), "info": str(x.get("info", ""))}
                    for x in _kc if isinstance(x, dict)]
            if "story_ideas" in snap:
                _id = snap.get("story_ideas") or []
                project.story_ideas = [str(x).strip() for x in _id if str(x).strip()]
            if "chapter_plans" in snap:
                _pl = snap.get("chapter_plans") or []
                plans = []
                for x in _pl:
                    if not isinstance(x, dict):
                        continue
                    s = int(x.get("start", 0) or 0)
                    if s <= 0:
                        continue
                    e = int(x.get("end", 0) or 0)
                    if e < s:
                        e = s
                    plans.append({"start": s, "end": e,
                                  "note": str(x.get("note", "") or "")})
                project.chapter_plans = plans
            self.save_project(project)

    def delete_chapters_from(self, start_index):
        """删除第 start_index 章及之后的所有章节文件。"""
        for i in self.list_chapter_indices():
            if i >= int(start_index):
                path = self.chapter_path(i)
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def rebuild_world_after_delete(self, kept_max):
        """删除章节后重建角色卡（v0.54 小说导入成项目回滚）：

        按「角色分章状态轨迹 chapter_states」把角色卡回退到剩余最后章节（kept_max）：
          - 不再出现在任何剩余章节的角色 → 删除角色卡（故事里已没有它）；
          - 保留的角色：信息库 events/knowledge 截断到 kept_max 章，轨迹截断到 kept_max 章，
            卡面 scenario/status 取最近一条；
          - 伏笔台账截断：planted 晚于 kept_max 的移除，resolved 晚于 kept_max 的恢复 open。
        返回受影响的角色数。正常生成的项目也会在战后更新时写入轨迹，同样适用。
        """
        kept_max = int(kept_max or 0)
        remaining = [i for i in self.list_chapter_indices() if i <= kept_max]
        touched = 0
        for cid, _name, _st in self.list_characters():
            card, lib = self.load_character(cid)
            if card is None:
                continue
            appears = False
            for i in remaining:
                ch = self.load_chapter(i)
                if ch and cid in (ch.characters or []):
                    appears = True
                    break
            if not appears:
                self.delete_character(cid)
                touched += 1
                continue
            if lib:
                lib.events = [e for e in (lib.events or [])
                              if int((e or {}).get("chapter", 0) or 0) <= kept_max]
                lib.knowledge = [k for k in (lib.knowledge or [])
                                 if int((k or {}).get("chapter", 0) or 0) <= kept_max]
            trail = [dict(e) for e in (card.chapter_states or [])
                     if int((e or {}).get("ch", 0) or 0) <= kept_max]
            card.chapter_states = trail
            if trail:
                last = trail[-1]
                scenario = str(last.get("scenario") or "").strip()
                if scenario:
                    card.scenario = scenario
                    if lib:
                        lib.scenario = scenario
                st = str(last.get("status") or "").strip()
                if st:
                    card.status = st
            card.version += 1
            self.save_character(card, lib)
            touched += 1
        # 伏笔台账截断
        kept_fs = []
        for f in self.load_foreshadows():
            if int(f.planted_chapter or 0) > kept_max:
                continue
            if int(f.resolved_chapter or 0) > kept_max:
                f.status = "open"
                f.resolved_chapter = 0
            kept_fs.append(f)
        self.save_foreshadows(kept_fs)
        return touched

    # ---------- 草稿箱（重写/删除/编辑前自动备份旧章节，可恢复找回） ----------
    def backup_chapter_draft(self, chapter, tag):
        """把章节完整内容备份到 drafts/（tag: rewrite/delete/edit）。返回备份文件名。"""
        ts = now().replace(":", "").replace(" ", "_")
        base = "draft_ch_%03d_%s_%s" % (int(chapter.index), ts, tag)
        fname = base + ".json"
        n = 2
        while os.path.exists(os.path.join(self.base, "drafts", fname)):
            fname = "%s-%d.json" % (base, n)   # 同秒重复操作防覆盖
            n += 1
        data = {"chapter": chapter.to_dict(), "tag": tag, "saved_at": now(),
                "kind": "chapter_draft"}
        _write_json(os.path.join(self.base, "drafts", fname), data)
        return fname

    def list_chapter_drafts(self):
        """列出草稿箱：按时间倒序，[{fname,index,title,tag,saved_at}]。

        v2.60 性能优化：从备份文件名直接解析 章号/时间/tag（**零 JSON 读取**），
        千级备份也毫秒级出列表；标题不在文件名里（返回空串，显示时回退"第N章"，
        查看/恢复时按需加载全文）。旧/异常文件名才回退读 JSON（保持兼容）。
        """
        d = os.path.join(self.base, "drafts")
        out = []
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d), reverse=True):
                if not fn.endswith(".json"):
                    continue
                m = _DRAFT_RE.match(fn)
                if m:
                    ts = m.group(2)  # YYYY-MM-DD_HHMMSS
                    saved = "%s %s:%s:%s" % (ts[0:10], ts[11:13], ts[13:15], ts[15:17])
                    out.append({"fname": fn, "index": int(m.group(1)),
                                "title": "", "tag": m.group(3), "saved_at": saved})
                    continue
                data = _read_json(os.path.join(d, fn))
                if not data or data.get("kind") != "chapter_draft" or not data.get("chapter"):
                    continue
                ch = Chapter.from_dict(data["chapter"])
                out.append({"fname": fn, "index": ch.index, "title": ch.title,
                            "tag": data.get("tag", ""), "saved_at": data.get("saved_at", "")})
        return out

    def load_chapter_draft(self, fname):
        data = _read_json(os.path.join(self.base, "drafts", fname))
        if not data or data.get("kind") != "chapter_draft" or not data.get("chapter"):
            return None
        return Chapter.from_dict(data["chapter"])

    def delete_chapter_draft(self, fname):
        p = os.path.join(self.base, "drafts", fname)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    def restore_chapter_draft(self, fname):
        """把草稿写回为正式章节（覆盖同章号现有内容）。恢复章号不落后于进度时自动补位进度。"""
        ch = self.load_chapter_draft(fname)
        if ch is None:
            return None
        self.save_chapter(ch)
        project = self.load_project()
        if project:
            nxt = int(project.state.get("next_chapter", 1))
            if int(ch.index) >= nxt:
                project.state["next_chapter"] = int(ch.index) + 1
                project.state["story_complete"] = False
                self.save_project(project)
        return ch

    # ---------- 分支存档（if 线：保存完整项目状态，可整体载回/切换） ----------
    def branch_path(self, name):
        return os.path.join(self.base, "branches", _slug(name) + ".json")

    def save_branch(self, name):
        """把当前项目完整状态存为分支（设定/进度/角色卡与信息库/全部章节/伏笔；日志不入分支）。

        同名分支直接覆盖（GUI 层负责确认）。返回分支文件名。
        """
        project = self.load_project()
        chars = {}
        for cid, _, _ in self.list_characters():
            card, lib = self.load_character(cid)
            if card:
                chars[cid] = {"card": card.to_dict(),
                              "library": lib.to_dict() if lib else {}}
        chapters = []
        for i in self.list_chapter_indices():
            ch = self.load_chapter(i)
            if ch:
                chapters.append(ch.to_dict())
        data = {
            "kind": "project_branch",
            "name": name,
            "saved_at": now(),
            "project": project.to_dict() if project else {},
            "characters": chars,
            "chapters": chapters,
            "foreshadows": [f.to_dict() for f in self.load_foreshadows()],
        }
        _write_json(self.branch_path(name), data)
        return _slug(name) + ".json"

    def list_branches(self):
        d = os.path.join(self.base, "branches")
        out = []
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d), reverse=True):
                if not fn.endswith(".json"):
                    continue
                data = _read_json(os.path.join(d, fn))
                if not data or data.get("kind") != "project_branch":
                    continue
                out.append({"name": data.get("name", fn), "fname": fn,
                            "saved_at": data.get("saved_at", ""),
                            "chapters": len(data.get("chapters", []))})
        return out

    def load_branch(self, name):
        return _read_json(self.branch_path(name))

    def delete_branch(self, name):
        p = self.branch_path(name)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    def apply_branch(self, data):
        """把项目整体替换为分支状态：设定/进度/角色/章节/伏笔（生成日志保留）。"""
        project = NovelProject.from_dict(data.get("project", {}) or {}, self.dir_name)
        self.save_project(project)
        for cid, _, _ in self.list_characters():
            self.delete_character(cid)
        for cid, d in (data.get("characters") or {}).items():
            self.save_character(CharacterCard.from_dict(d.get("card", {})),
                                InfoLibrary.from_dict(d.get("library", {})))
        for i in self.list_chapter_indices():
            self.delete_chapter(i)
        for d in data.get("chapters") or []:
            ch = Chapter.from_dict(d)
            self.save_chapter(ch)
        self.save_foreshadows([Foreshadow.from_dict(f) for f in data.get("foreshadows", [])])
        return project

    # ---------- 去AI味待定稿（润色结果暂存，可跨启动保留，最后统一合并回原文） ----------
    def deai_path(self, chapter_index):
        return os.path.join(self.base, "deai", "deai_ch_%03d.json" % int(chapter_index))

    def save_deai_draft(self, chapter_index, polished, mode="clean", rules="", created_at=None):
        """保存某章的润色稿为待定稿（同章旧稿直接覆盖）。"""
        data = {
            "chapter": int(chapter_index),
            "polished": polished or "",
            "mode": mode,
            "rules": rules,
            "created_at": created_at or now(),
        }
        _write_json(self.deai_path(chapter_index), data)
        return data

    def list_deai_drafts(self):
        """列出全部待定稿：按章节号倒序，[{chapter,title,mode,created_at}]。"""
        d = os.path.join(self.base, "deai")
        out = []
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d), reverse=True):
                m = re.match(r"deai_ch_(\d+)\.json", fn)
                if not m:
                    continue
                data = _read_json(os.path.join(d, fn))
                if not data or not data.get("polished"):
                    continue
                i = int(m.group(1))
                ch = self.load_chapter(i)
                out.append({
                    "chapter": i,
                    "title": ch.title if ch else "第%d章" % i,
                    "mode": data.get("mode", "clean"),
                    "created_at": data.get("created_at", ""),
                })
        return out

    def load_deai_draft(self, chapter_index):
        return _read_json(self.deai_path(chapter_index))

    def delete_deai_draft(self, chapter_index):
        p = self.deai_path(chapter_index)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    def clear_deai_drafts(self):
        d = os.path.join(self.base, "deai")
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.startswith("deai_ch_") and fn.endswith(".json"):
                    try:
                        os.remove(os.path.join(d, fn))
                    except OSError:
                        pass

    # ---------- log ----------
    def append_log(self, line):
        os.makedirs(self.base, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")

    def read_log(self, limit=500):
        if not os.path.exists(self.log_path):
            return ""
        with open(self.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[-limit:])


# ---------- registry ----------
def list_projects():
    idx = _read_json(INDEX_PATH, {}) or {}
    items = []
    for dir_name, title in idx.items():
        items.append({"dir": dir_name, "title": title})
    return items


def create_project(title, opening="", volumes=None):
    """新建项目并注册。返回 NovelProject。"""
    with _lock:
        dir_name = _slug(title)
        base_dir = os.path.join(PROJECTS_DIR, dir_name)
        n = 1
        while os.path.exists(base_dir):
            dir_name = "%s_%d" % (_slug(title), n)
            base_dir = os.path.join(PROJECTS_DIR, dir_name)
            n += 1
        project = NovelProject(dir_name, title)
        project.opening = opening or ""
        if volumes:
            project.volumes = volumes
        store = ProjectStore(dir_name)
        store.save_project(project)
        idx = _read_json(INDEX_PATH, {}) or {}
        idx[dir_name] = title
        _write_json(INDEX_PATH, idx)
        return project


def delete_project(dir_name):
    with _lock:
        import shutil
        base = os.path.join(PROJECTS_DIR, dir_name)
        if os.path.isdir(base):
            shutil.rmtree(base)
        idx = _read_json(INDEX_PATH, {}) or {}
        idx.pop(dir_name, None)
        _write_json(INDEX_PATH, idx)


# ---------- 项目整体导入导出 ----------
def export_project(dir_name, zip_path):
    """把整个项目打包为 zip（project.json/characters/chapters/foreshadows/log/snapshots）。

    包内结构即项目磁盘结构（顶层为项目目录名），未来版本目录结构不变即天然兼容。
    v0.97 加固：先写临时文件再原子改名（导出中断不产生截断包），并写入 manifest.json
    （章节/角色/快照/文件计数），供导入侧校验完整性。
    返回是否成功。
    """
    import zipfile
    base = os.path.join(PROJECTS_DIR, dir_name)
    if not os.path.isdir(base):
        return False
    tmp_path = zip_path + ".tmp"
    try:
        chs = chars = snaps = files = 0
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, names in os.walk(base):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fn in names:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, base)
                    zf.write(full, (dir_name + "/" + rel).replace("\\", "/"))
                    if re.match(r"ch_\d+\.json$", fn):
                        chs += 1
                    elif rel.startswith("characters") and fn.endswith(".json"):
                        chars += 1
                    elif rel.startswith("snapshots") and fn.endswith(".json"):
                        snaps += 1
                    files += 1
            zf.writestr(dir_name + "/manifest.json", json.dumps(
                {"format": "xinghuobi-project", "chapters": chs,
                 "characters": chars, "snapshots": snaps, "files": files},
                ensure_ascii=False))
        os.replace(tmp_path, zip_path)   # 原子替换：中断也只会留下 .tmp，不产生截断包
        return True
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False


def import_project(zip_path):
    """从 zip 导入项目到 projects/。返回 (dir_name, title, warning)；失败返回 None。

    warning：非空表示 zip 内章节/角色数比实际还原的多（zip 截断/损坏），提示用户重新导出。
    兼容性：zip 内含一个 project.json 所在目录（即项目磁盘结构，顶层目录名不限）；
    目录冲突时自动追加 _2/_3… 后缀，绝不覆盖已有项目；缺快照等可选目录也能导入。
    """
    import shutil
    import tempfile
    import zipfile
    if not os.path.isfile(zip_path):
        return None
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for m in zf.infolist():
                p = m.filename.replace("\\", "/")
                if p.startswith("/") or ".." in p.split("/"):
                    return None  # 防 zip-slip 越界
            # 统计 zip 内章节/角色条目（校验完整性用，目录名不限；须限定 /chapters/
            # 路径——快照 world_ch_001.json 也会命中裸 ch_\d+\.json 后缀）
            z_ch = sum(1 for m in zf.infolist()
                       if re.search(r"/chapters/ch_\d+\.json$", m.filename))
            z_ca = sum(1 for m in zf.infolist()
                       if "/characters/" in m.filename.replace("\\", "/")
                       and m.filename.endswith(".json"))
            with tempfile.TemporaryDirectory() as tmp:
                zf.extractall(tmp)
                proj_dir = None
                for root, dirs, files in os.walk(tmp):
                    if "project.json" in files:
                        proj_dir = root
                        break
                if proj_dir is None:
                    return None
                d = _read_json(os.path.join(proj_dir, "project.json"))
                if not d or not d.get("title"):
                    return None
                title = str(d.get("title"))
                with _lock:
                    base = _slug(title) or "project"
                    final_dir = base
                    target = os.path.join(PROJECTS_DIR, final_dir)
                    n = 2
                    while os.path.exists(target):
                        final_dir = "%s_%d" % (base, n)
                        target = os.path.join(PROJECTS_DIR, final_dir)
                        n += 1
                    shutil.copytree(proj_dir, target,
                                    ignore=shutil.ignore_patterns("__pycache__"))
                    idx = _read_json(INDEX_PATH, {}) or {}
                    idx[final_dir] = title
                    _write_json(INDEX_PATH, idx)
                # v0.97 完整性校验：zip 内章节/角色数 > 落盘还原数 → 提示不完整（可能截断/损坏）
                st = ProjectStore(final_dir)
                d_ch = len(st.list_chapter_indices())
                d_ca = len(st.list_characters())
                warning = ""
                if z_ch and d_ch < z_ch:
                    warning = "章节不完整（zip 内 %d 章，实际还原 %d 章）" % (z_ch, d_ch)
                elif z_ca and d_ca < z_ca:
                    warning = "角色卡不完整（zip 内 %d 个，实际还原 %d 个）" % (z_ca, d_ca)
                return final_dir, title, warning
    except Exception:
        return None


def example_project():
    """内置示例项目，首次运行自动创建，方便直接体验。"""
    title = "示例项目·星海孤城"
    project = create_project(title)
    project.story_brief = (
        "【世界观】大陆边陲的「铁砧城」是扼守废矿古道的中立城邦，城主府世代把持废矿，"
        "城中有三股暗流：城主府的守旧派、商会新贵、以及信奉旧神的矿工秘教。城外废矿深处"
        "埋有旧神遗迹，传说遗迹每逢血月会苏醒。\n"
        "【开局】主角（落魄佣兵，寡言但记仇，名字可随剧情自然确立）在风沙夜抵达铁砧城。"
        "城门将闭时被守城副将拦下盘问；酒吧老板娘在灯下擦杯，余光扫过他腰间的旧剑。"
        "那一夜，城主府传来一声尖叫——城主独女被发现死在密室，门上刻着旧神符号。\n"
        "【本卷主线（约12章）】主角因旧剑上的家族徽记被卷入悬案调查：结识老板娘（情报通，"
        "与城主府有旧怨）与副将（忠于城主但心存疑虑）；悬案指向废矿旧神遗迹，城中派系因"
        "遗迹利益开始分裂；主角在追查中发现自己家族的覆灭与旧神有关。\n"
        "【本卷结尾】废矿遗迹的秘密被揭开一角，主角被迫在各方势力间表明立场，"
        "城破前夜携关键情报出逃，老板娘与副将一明一暗留在城中接应。\n"
        "【下一卷承接】主角带着情报进入王都，面对上层的政治漩涡，同时旧神遗迹的线索"
        "将引向更大的阴谋。\n"
        "【节奏要求】开篇两章铺陈人物与城市氛围，中段每2-3章推进一个事件并埋设伏笔"
        "（遗迹符号、主角旧剑来历、老板娘与城主府的旧怨），保持悬疑感。"
    )
    project.volume_target = 12
    store = ProjectStore(project.dir_name)
    store.save_project(project)
    return project


def ensure_example_project():
    if not list_projects():
        try:
            example_project()
        except Exception:
            pass
    return None