# -*- coding: utf-8 -*-
"""拆书工坊（v0.55）：导入 txt 长篇小说 → 拆书（AI 提取小说设计细纲）→
保存为「拆书风格」→ 应用到当前项目让主AI学习其剧情推动/伏笔设计技法 → 导出。

管线（book_break.NovelBreaker）：L1 标题流分批+全书骨架（核心人物/全局伏笔池/技法）
→ L2 逐卷事件细纲（事件拆分/章数/推动方式/冲突/高潮/伏笔埋收/日常式伏笔）
→ L3 汇总压缩 ≤5 万字拆书文档 + 设计技法学习文本（注入主AI）。
"""
import os
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QSpinBox, QSplitter, QTextBrowser,
                               QVBoxLayout, QWidget)

import book_break
import llm  # noqa: F401  （捕获异常用）
from gui_app import APP, VERSION, current_project, log_fn, set_running, busy_guard
from gui_theme import T


class BreakSettingsBox(QWidget):
    """拆书参数设置（v0.58 三档模式；拆书工坊页与小说导入成项目页共用）。

    简单模式：每部分 token（1000~32000）+ 并行/串行（基本参数）；
    智能模式（默认）：每部分 token（1000~64000）+ 并行/串行 + 并行数 + 总体提示词；
    高级模式：每部分 token 不卡上限（到 200 万）+ 重叠 token（相邻部分首尾衔接）
             + 并行/串行 + 并行数 + 总体提示词 + L3 分批汇总（每批单元数，0=一次合并）。

    保存写回 config（与引擎 break_settings 同键）；页面启动任务前会自动保存一次，
    保证「界面看到什么，跑起来就用什么」。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # v0.60 布局修复：参数原先挤在一行（8 组控件）→ 窗口窄时被压缩（模式下拉只显示一个字、
        # 数值显示不全）——拆成两行 + 每个控件设最小宽度，标签随控件一起显隐
        # 第 1 行：拆书模式 / 档位（智能）/ 模型上下文长度
        row0 = QHBoxLayout()
        row0.addWidget(QLabel("拆书模式"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("简单模式（基本参数）", "simple")
        self.mode_combo.addItem("智能模式（按上下文自动定档，默认）", "smart")
        self.mode_combo.addItem("高级模式（全参数放开）", "advanced")
        self.mode_combo.setMinimumWidth(200)
        self.mode_combo.setToolTip(
            "智能模式=按模型上下文长度自动切分，分「保守/正常/激进」三档（能探测到上下文就用，"
            "探测不到按 262144 兜底，也可手填）；\n"
            "高级模式=把每部分 token / 重叠 / L3 分批等参数全部开放给你（现代大上下文随便填大，"
            "设置大一点一次多拆点，早点搞完）；\n"
            "简单模式=只留基本参数，怕智能模式抽风时用来兜底。")
        self.mode_combo.currentIndexChanged.connect(self._on_mode)
        row0.addWidget(self.mode_combo)
        row0.addSpacing(16)

        self.lbl_sub = QLabel("档位（智能）")
        row0.addWidget(self.lbl_sub)
        self.smart_sub_combo = QComboBox()
        self.smart_sub_combo.addItem("保守（约上下文30%）", "conservative")
        self.smart_sub_combo.addItem("正常（约上下文50%）", "balanced")
        self.smart_sub_combo.addItem("激进（约上下文70%）", "aggressive")
        self.smart_sub_combo.setMinimumWidth(160)
        self.smart_sub_combo.setToolTip(
            "智能模式按模型上下文长度自动定每部分大小：\n"
            "保守≈上下文的 30%（稳）；正常≈50%（均衡）；激进≈70%（最快，输入×0.75 安全系数后"
            "仍留给输出余量）。\n"
            "1M 上下文激进档 ≈ 73 万 token 一段（约 53 万章采样输入），2 千万字的长文拆得更快；"
            "262144 上下文三档 ≈ 7.9 万 / 13.1 万 / 18.4 万 token。")
        row0.addWidget(self.smart_sub_combo)
        row0.addSpacing(16)

        self.lbl_ctx = QLabel("模型上下文长度")
        row0.addWidget(self.lbl_ctx)
        self.ctx_spin = QSpinBox()
        self.ctx_spin.setRange(0, 10000000)
        self.ctx_spin.setSingleStep(1024)
        self.ctx_spin.setValue(0)
        self.ctx_spin.setMinimumWidth(110)
        self.ctx_spin.setToolTip(
            "智能模式用的模型上下文长度（token）。0=自动：优先用「拉取模型」时网关返回的上下文，"
            "没有则按 262144 兜底。知道实际值（如 1000000）就填上，三档会自动换算每部分大小。")
        row0.addWidget(self.ctx_spin)
        row0.addStretch(1)
        lay.addLayout(row0)

        # 第 2 行：每部分 token / 重叠 token / L3 分批 / 并行·串行 / 并行数
        row1 = QHBoxLayout()
        self.lbl_token = QLabel("每部分 token")
        row1.addWidget(self.lbl_token)
        self.token_spin = QSpinBox()
        self.token_spin.setSingleStep(1000)
        self.token_spin.setValue(8000)
        self.token_spin.setMinimumWidth(110)
        self.token_spin.setToolTip(
            "拆书按多少 token 切分一次调用：预算越大每部分含的章越多、调用次数越少。\n"
            "换算：每部分章数 ≈ 预算×0.75 ÷ (每章采样约640字×1.6 token/字)。\n"
            "简单模式限 32000、高级模式不卡上限（到 200 万）——现代大上下文直接填大，早点搞完。")
        row1.addWidget(self.token_spin)
        row1.addSpacing(16)

        self.lbl_overlap = QLabel("重叠 token")
        row1.addWidget(self.lbl_overlap)
        self.overlap_spin = QSpinBox()
        self.overlap_spin.setSingleStep(1000)
        self.overlap_spin.setValue(0)
        self.overlap_spin.setMinimumWidth(110)
        self.overlap_spin.setToolTip(
            "高级模式：每部分与下一部分**重叠**多少 token 的内容（0=不重叠）。\n"
            "开重叠可保证相邻批次首尾衔接连贯——交界处的事件/伏笔/人物动向不会被切碎漏掉。")
        row1.addWidget(self.overlap_spin)
        row1.addSpacing(16)

        self.lbl_l3 = QLabel("L3 分批汇总")
        row1.addWidget(self.lbl_l3)
        self.l3_spin = QSpinBox()
        self.l3_spin.setRange(0, book_break.L3_BATCH_MAX)
        self.l3_spin.setValue(0)
        self.l3_spin.setMinimumWidth(90)
        self.l3_spin.setToolTip(
            "高级模式后手：L3 汇总时每批最多合并多少个单元（0=一次合并全部）。\n"
            "担心一次汇总上下文不够 → 设小（如 20~40）：每批先汇总成分卷文档，最后再合并成"
            "最终拆书文档，单次调用体量可控，长文也不怕。")
        row1.addWidget(self.l3_spin)
        row1.addSpacing(16)

        self.lbl_par = QLabel("并行 / 串行")
        row1.addWidget(self.lbl_par)
        self.par_combo = QComboBox()
        self.par_combo.addItem("串行（稳，不易限流）", False)
        self.par_combo.addItem("并行（更快，注意限流）", True)
        self.par_combo.setMinimumWidth(130)
        self.par_combo.setToolTip(
            "并行时多个「标题批 / 卷细纲单元」同时请求（L1 骨架、L3 汇总始终串行）。\n"
            "串行最稳；并行加速明显但并发请求容易触发 429 限流（拆书调用量大，建议先用串行）")
        row1.addWidget(self.par_combo)
        row1.addSpacing(16)

        self.lbl_parn = QLabel("并行数")
        row1.addWidget(self.lbl_parn)
        self.par_n_spin = QSpinBox()
        self.par_n_spin.setRange(1, 8)
        self.par_n_spin.setValue(2)
        self.par_n_spin.setMinimumWidth(60)
        self.par_n_spin.setToolTip("并行拆书时的并发请求数（1-8）。建议 ≤ 你的 API 限流允许的并发")
        row1.addWidget(self.par_n_spin)
        row1.addStretch(1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("拆书总体提示词（大方向；留空=照常）"))
        row2.addStretch(1)
        # v1.44 拆书参数预设导入导出：json 文件备份/迁移/分享整套拆书设置
        self.export_preset_btn = QPushButton("导出预设（json）")
        self.export_preset_btn.setToolTip(
            "把当前整套拆书参数（模式/档位/token/重叠/并行/L3/总体提示词）导出为 json 文件——"
            "备份、换机迁移、分享配置给别人用")
        self.export_preset_btn.clicked.connect(self.export_preset)
        row2.addWidget(self.export_preset_btn)
        self.import_preset_btn = QPushButton("导入预设（json）")
        self.import_preset_btn.setToolTip(
            "从 json 文件导入整套拆书参数并立即生效（覆盖当前设置并保存）；"
            "支持本页导出的预设文件，也兼容手工编辑的 json（见导出文件内注释结构）")
        self.import_preset_btn.clicked.connect(self.import_preset)
        row2.addWidget(self.import_preset_btn)
        self.save_btn = QPushButton("保存拆书设置")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self.save)
        row2.addWidget(self.save_btn)
        lay.addLayout(row2)

        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText(
            "例①：重点分析日常情节与人物塑造——日常对话怎么藏伏笔、配角怎么立住；\n"
            "例②：更看重脑洞与哲思——世界观创意、每次反转背后的思想主题。")
        self.prompt_edit.setMaximumHeight(64)
        lay.addWidget(self.prompt_edit)

        self.hint = QLabel("")
        self.hint.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(self.hint)
        self._on_mode()
        self.load()

    # ---------- 模式切换：显隐字段（含标签）+ 调 token 上限 ----------
    def _on_mode(self, _idx=None):
        mode = self.mode_combo.currentData() or "smart"
        adv = mode == "advanced"
        smt = mode in ("smart", "advanced")
        smart = mode == "smart"
        # 智能模式：档位 + 上下文（自动换算每部分 token），隐藏手填 token/重叠/L3
        self.lbl_sub.setVisible(smart)
        self.smart_sub_combo.setVisible(smart)
        self.lbl_ctx.setVisible(smart)
        self.ctx_spin.setVisible(smart)
        self.lbl_token.setVisible(not smart)
        self.token_spin.setVisible(not smart)
        self.lbl_overlap.setVisible(adv)
        self.overlap_spin.setVisible(adv)
        self.lbl_l3.setVisible(adv)
        self.l3_spin.setVisible(adv)
        self.lbl_parn.setVisible(smt)
        self.par_n_spin.setVisible(smt)
        self._adv_label = getattr(self, "_adv_label", None)
        if mode == "advanced":
            self.token_spin.setRange(1000, book_break.TOKEN_PER_PART_MAX)
            self.overlap_spin.setRange(0, book_break.OVERLAP_TOKEN_MAX)
        elif mode == "smart":
            self.token_spin.setRange(1000, 64000)
            self.overlap_spin.setRange(0, 64000)
        else:
            self.token_spin.setRange(1000, 32000)
            self.overlap_spin.setRange(0, 32000)

    def mode(self):
        return self.mode_combo.currentData() or "smart"

    def load(self):
        """从 config 回填（模式/档位/上下文/token/重叠/并行/提示词/L3）。"""
        try:
            import config as app_config
            cfg = app_config.load_config()
            mode = str(cfg.get("break_mode") or "smart")
            if mode not in ("simple", "smart", "advanced"):
                mode = "smart"
            idx = self.mode_combo.findData(mode)
            if idx < 0:
                idx = self.mode_combo.findData("smart")
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(idx)
            self.mode_combo.blockSignals(False)
            self._on_mode()
            sub = str(cfg.get("break_smart_sub") or "balanced")
            sidx = self.smart_sub_combo.findData(sub)
            self.smart_sub_combo.setCurrentIndex(sidx if sidx >= 0 else 1)
            self.ctx_spin.setValue(max(0, int(cfg.get("model_context_window") or 0)))
            self.token_spin.setValue(max(1000, int(cfg.get("break_token_per_part", 8000))))
            self.overlap_spin.setValue(max(0, int(cfg.get("break_overlap_token") or 0)))
            self.par_n_spin.setValue(max(1, min(8, int(cfg.get("break_parallel_n") or 2))))
            pi = self.par_combo.findData(bool(cfg.get("break_parallel")))
            self.par_combo.setCurrentIndex(pi if pi >= 0 else 0)
            self.l3_spin.setValue(max(0, min(book_break.L3_BATCH_MAX,
                                             int(cfg.get("break_l3_batch") or 0))))
            self.prompt_edit.setPlainText(cfg.get("break_prompt") or "")
        except Exception:
            pass

    def save(self):
        """写回 config（引擎 break_settings 读取同键）。返回当前拆书 settings。"""
        import config as app_config
        cfg = app_config.load_config()
        cfg["break_mode"] = self.mode_combo.currentData() or "smart"
        cfg["break_smart_sub"] = self.smart_sub_combo.currentData() or "balanced"
        cfg["model_context_window"] = int(self.ctx_spin.value())
        cfg["break_token_per_part"] = int(self.token_spin.value())
        cfg["break_overlap_token"] = int(self.overlap_spin.value())
        cfg["break_parallel"] = bool(self.par_combo.currentData())
        cfg["break_parallel_n"] = int(self.par_n_spin.value())
        cfg["break_l3_batch"] = int(self.l3_spin.value())
        cfg["break_prompt"] = self.prompt_edit.toPlainText().strip()
        app_config.save_config(cfg)
        app_config._cache = None
        mode = self.mode()
        mode_name = {"simple": "简单", "smart": "智能", "advanced": "高级"}.get(mode, "智能")
        ovl = int(self.overlap_spin.value())
        l3 = int(self.l3_spin.value())
        if mode == "smart":
            ctx, src = book_break.context_with_source(book_break.break_settings())
            sub = self.smart_sub_combo.currentData() or "balanced"
            eff = book_break.smart_token_per_part(
                {"smart_sub": sub, "model_context": int(self.ctx_spin.value())}, ctx)
            self.hint.setText(
                "✓ 拆书设置已保存（智能·%s：上下文 %d token（%s）→ 每部分 %d token；"
                "API 在「设置·API 配置·用途分工」选）。"
                % ({"conservative": "保守", "balanced": "正常", "aggressive": "激进"}.get(sub, "正常"),
                   ctx, src, eff))
        else:
            self.hint.setText(
                "✓ 拆书设置已保存（%s模式：每部分 %d token%s%s；API 在「设置·API 配置·用途分工」选）。"
                % (mode_name, self.token_spin.value(),
                   ("，重叠 %d token" % ovl) if ovl else "",
                   ("，L3 分批 %d 单元/批" % l3) if l3 else ""))
        return book_break.break_settings()

    # ---------- v1.44 拆书参数预设导入导出（json 文件：备份/迁移/分享整套拆书设置） ----------
    def _preset_values(self):
        """收集当前整套拆书参数（所见即所得，与 save() 写 config 的键一致）。"""
        return {
            "break_mode": self.mode_combo.currentData() or "smart",
            "break_smart_sub": self.smart_sub_combo.currentData() or "balanced",
            "model_context_window": int(self.ctx_spin.value()),
            "break_token_per_part": int(self.token_spin.value()),
            "break_overlap_token": int(self.overlap_spin.value()),
            "break_parallel": bool(self.par_combo.currentData()),
            "break_parallel_n": int(self.par_n_spin.value()),
            "break_l3_batch": int(self.l3_spin.value()),
            "break_prompt": self.prompt_edit.toPlainText().strip(),
        }

    def export_preset(self):
        """导出当前整套拆书参数为 json 预设文件（备份 / 换机迁移 / 分享给别的机器）。"""
        import json
        import datetime

        vals = self._preset_values()
        mode_name = {"simple": "简单", "smart": "智能", "advanced": "高级"}.get(
            vals["break_mode"], "智能")
        default = os.path.join(os.path.expanduser("~"), "Desktop",
                               "拆书工坊预设-%s.json" % mode_name)
        path, _ = QFileDialog.getSaveFileName(
            self, "导出拆书参数预设", default, "JSON 文件 (*.json)")
        if not path:
            return
        payload = {
            "app": "星火笔",
            "type": "break_settings_preset",
            "version": 1,
            "saved_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "settings": vals,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "导出失败", "写入预设文件失败：%s" % e)
            return
        log_fn("info", "拆书参数预设已导出：%s" % path)
        self.hint.setText("✓ 拆书参数预设已导出：%s" % os.path.basename(path))

    def import_preset(self):
        """从 json 预设文件导入整套拆书参数并立即生效（写回 config）。

        兼容两种结构：本页导出的 {"settings": {...}} 包装，或直接是设置 dict。
        """
        import json

        def _safe_int(v, default=0):
            try:
                return int(v)
            except (TypeError, ValueError):
                return default

        path, _ = QFileDialog.getOpenFileName(
            self, "导入拆书参数预设", "", "JSON 文件 (*.json);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", "读取预设文件失败：%s" % e)
            return
        settings = data.get("settings") if isinstance(data, dict) else None
        if not isinstance(settings, dict):
            settings = data
        if not isinstance(settings, dict):
            QMessageBox.warning(self, "导入失败",
                                "预设文件格式不正确（缺少 settings 对象）。")
            return

        # 先设模式（触发 _on_mode 更新显隐与 token 上限），再设其余控件
        mode = str(settings.get("break_mode") or "smart")
        if mode not in ("simple", "smart", "advanced"):
            mode = "smart"
        idx = self.mode_combo.findData(mode)
        self.mode_combo.setCurrentIndex(idx if idx >= 0 else 1)
        sub = str(settings.get("break_smart_sub") or "balanced")
        sidx = self.smart_sub_combo.findData(sub)
        self.smart_sub_combo.setCurrentIndex(sidx if sidx >= 0 else 1)
        self.ctx_spin.setValue(_safe_int(settings.get("model_context_window")))
        self.token_spin.setValue(_safe_int(settings.get("break_token_per_part"), 8000))
        self.overlap_spin.setValue(_safe_int(settings.get("break_overlap_token")))
        pv = bool(settings.get("break_parallel", False))
        pi = self.par_combo.findData(pv)
        self.par_combo.setCurrentIndex(pi if pi >= 0 else 0)
        self.par_n_spin.setValue(_safe_int(settings.get("break_parallel_n"), 2))
        self.l3_spin.setValue(_safe_int(settings.get("break_l3_batch")))
        self.prompt_edit.setPlainText(str(settings.get("break_prompt") or ""))
        self.save()   # 写回 config（引擎 break_settings 同键），并刷新提示
        log_fn("info", "拆书参数预设已导入：%s" % path)
        self.hint.setText("✓ 已导入拆书参数预设并保存：%s" % os.path.basename(path))


class _BreakWorker(QObject):
    """后台拆书线程载体：信号回传日志/进度/结果（v0.55 断点续传 + 立即停止）。"""

    log = Signal(str, str)
    progress = Signal(str, int, int)   # (stage, done, total)
    done = Signal(object)

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()
        self._pause = threading.Event()   # v0.82 暂停：临时挂起拆书，点「继续」恢复
        self._job_dir = None

    def stop(self):
        self._stop.set()
        # 立即停止：主动 close 在途 LLM 请求连接（流式读取立刻抛 StopRequested），
        # 不再等当前拆书节点自然结束
        import llm
        llm.abort_active_resps()

    def pause(self):
        self._pause.set()

    def resume(self):
        self._pause.clear()

    def _resumed(self, job_dir):
        """job 目录已有部分中间结果且未完成 → 续传。"""
        if not job_dir:
            return False
        import os
        return (os.path.exists(os.path.join(job_dir, "done.json")) is False
                and (os.path.exists(os.path.join(job_dir, "title_summ.json"))
                     or os.path.exists(os.path.join(job_dir, "skeleton.json"))
                     or os.path.exists(os.path.join(job_dir, "doc.json"))
                     or os.path.isdir(os.path.join(job_dir, "vol_notes"))))

    def run(self, text, title, restart=False):
        import llm
        llm.set_abort(self._stop)
        try:
            job_dir = None
            if restart:
                # v0.69 重新开始：不做断点续传，全部重来（job 目录直接不建）
                self.log.emit("info", "重新开始拆书：已清除上次进度，全部重来（不再续传）…")
            else:
                settings = book_break.break_settings()
                job_dir = book_break.job_dir_for(text, settings, title, label="break")
                if self._resumed(job_dir):
                    self.log.emit("info", "检测到未完成的拆书任务，自动续传（跳过已完成阶段）…")
            breaker = book_break.NovelBreaker(
                log=lambda k, m: self.log.emit(k, m),
                stop_check=lambda: self._stop.is_set(),
                pause_check=lambda: self._pause.is_set())
            try:
                result = breaker.run(text, title, progress_cb=self._on_progress,
                                     job_dir=job_dir)
            except llm.StopRequested:
                result = {"ok": False, "error": "已停止"}
            if result.get("ok") and job_dir:
                book_break.rm_job(job_dir)
            self.done.emit(result)
        finally:
            llm.set_abort(None)

    def _on_progress(self, stage, done, total):
        self.progress.emit(stage, done, total)


class SceneCardExtractWorker(QObject):
    """情景卡拆书后台线程载体（v1.26）：从已导入的 txt 全文拆出全部情景卡草稿。

    独立于拆书 running 锁；llm.set_abort(stop_event) 实现立即停止。
    v1.36：card_ready 信号——每拆出一张卡草稿立即发给主线程实时入列，
    长小说停止/失败后已拆出的卡保留在结果列表可直接保存。
    """

    log = Signal(str, str)
    done = Signal(object)        # 成功：card 列表 [{"name","content","category"}]
    stopped = Signal()
    card_ready = Signal(object)  # v1.36 逐张：实时回调的卡 {"name","content","category"}

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        # 立即停止：主动 close 在途 LLM 请求连接（流式读取立刻抛 StopRequested），不再等当前卡生成完
        import llm
        llm.abort_active_resps()

    def run(self, text, prompt=""):
        import llm
        import scene_card_extract
        llm.set_abort(self._stop)
        try:
            try:
                cards = scene_card_extract.extract_scene_cards_from_novel(
                    text,
                    prompt=prompt or "",
                    sink=lambda k, m: self.log.emit(k, m),
                    stop_check=lambda: self._stop.is_set(),
                    on_card=lambda c: self.card_ready.emit(c))
            except llm.StopRequested:
                self.log.emit("info", "情景卡拆书已停止（当前环节已中断，"
                                      "已拆出的卡保留在结果列表可直接勾选保存）。")
                self.stopped.emit()
                return
            except Exception as e:
                # v1.29 兜底：非停止的异常（LLM 调用失败等）也要复位按钮——否则
                # _sc_start 的 _sc_worker 永不复位、拆书按钮永久卡死"正在运行"。
                # 注意必须放在 except llm.StopRequested 之后（StopRequested 是
                # LLMError(Exception) 子类，先捕获才能保住"停止"语义）。
                self.log.emit("err", "情景卡拆书失败，请重试：%s" % e)
                self.stopped.emit()
                return
            self.log.emit("done_ok", "已完成，共 %d 张卡草稿。" % len(cards))
            self.done.emit(cards)
        finally:
            llm.set_abort(None)


class BreakPage(QWidget):
    """拆书工坊页面。"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._worker = None
        self._sc_worker = None   # v1.30 修复：情景卡拆书 worker 标记必须初始化，
        # 否则第一次点「开始情景卡拆书」时 _sc_start 读不存在的属性 → AttributeError → 点了没反应
        self._source_path = ""
        self._source_text = ""
        self._result = None        # {"doc","learning","stats"}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        # ---------- 顶部：导入 + 项目风格 ----------
        bar = QHBoxLayout()
        open_btn = QPushButton("导入小说 txt")
        open_btn.setObjectName("primary")
        open_btn.setToolTip("选择一部小说 txt（支持数千章的长篇网文），自动分卷分章后拆书")
        open_btn.clicked.connect(self._open_file)
        bar.addWidget(open_btn)
        self.file_label = QLabel("未导入")
        self.file_label.setStyleSheet(T("color:#d4a44c;font-weight:bold;"))
        self.file_label.setToolTip("当前已导入的 txt 文件（点「清除已导入」可换文件）")
        bar.addWidget(self.file_label)
        self.clear_file_btn = QPushButton("✕ 清除已导入")
        self.clear_file_btn.setEnabled(False)
        self.clear_file_btn.setToolTip("去掉已导入的 txt，回到未导入状态（可重新选文件）")
        self.clear_file_btn.clicked.connect(self._clear_source)
        bar.addWidget(self.clear_file_btn)
        bar.addWidget(QLabel("当前项目拆书风格"))
        self.style_combo = QComboBox()
        self.style_combo.setMinimumWidth(200)
        self.style_combo.setToolTip("选中的拆书风格会让主AI学习其剧情推动/伏笔设计技法（不抄情节）")
        bar.addWidget(self.style_combo)
        apply_btn = QPushButton("应用到当前项目")
        apply_btn.clicked.connect(self._apply_style)
        bar.addWidget(apply_btn)
        bar.addStretch(1)
        lay.addLayout(bar)

        self.preview_label = QLabel("尚未导入小说。选择一部 txt 后，这里会显示分卷分章结果预览。")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(self.preview_label)

        ctl = QHBoxLayout()
        self.start_btn = QPushButton("开始拆书")
        self.start_btn.setObjectName("primary")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start)
        ctl.addWidget(self.start_btn)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        ctl.addWidget(self.stop_btn)
        # v0.82 暂停 / 继续：临时挂起拆书（当前环节之间停下），不中断进度，之后点继续恢复
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._pause)
        ctl.addWidget(self.pause_btn)
        self.resume_btn = QPushButton("继续")
        self.resume_btn.setObjectName("primary")
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self._resume)
        ctl.addWidget(self.resume_btn)
        # v0.69 重新开始拆书：清空进度全部重来（不做断点续传）
        self.restart_btn = QPushButton("重新开始拆书")
        self.restart_btn.setToolTip("清除本次小说的拆书进度，从头重新拆书（不再续传）")
        self.restart_btn.setEnabled(False)
        self.restart_btn.clicked.connect(self._ask_restart)
        ctl.addWidget(self.restart_btn)
        self.export_btn = QPushButton("导出拆书文档（txt）")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_doc)
        ctl.addWidget(self.export_btn)
        self.save_btn = QPushButton("保存为拆书风格…")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_style)
        ctl.addWidget(self.save_btn)
        imp_btn = QPushButton("导入拆书文档…")
        imp_btn.setToolTip("导入别人/别处拆好的拆书文档（txt/md 或风格库导出的 JSON），"
                           "直接保存为拆书风格，可应用到当前项目让主AI学习")
        imp_btn.clicked.connect(self._import_break)
        ctl.addWidget(imp_btn)
        del_btn = QPushButton("删除选中风格")
        del_btn.clicked.connect(self._delete_style)
        ctl.addWidget(del_btn)
        ctl.addStretch(1)
        lay.addLayout(ctl)

        # v0.58 拆书参数（三档模式：简单/智能/高级；token/重叠/并行/提示词/L3 分批都在功能页内，
        # 设置页只保留「用哪个 API 拆书」的用途分工选择，不再混搭）
        self.settings_box = BreakSettingsBox()
        lay.addWidget(self.settings_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        # ---------- 主区分割：左日志 / 右拆书结果与风格库 ----------
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)

        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.addWidget(QLabel("拆书过程日志"))
        self.log_view = QTextBrowser()
        self.log_view.setOpenExternalLinks(False)
        llay.addWidget(self.log_view, 1)
        split.addWidget(left)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.addWidget(QLabel("拆书结果（拆书文档 ≤8 万字，尽量保留细节 / 设计技法学习文本给主AI）"))
        self.result_view = QTextBrowser()
        self.result_view.setOpenExternalLinks(False)
        rlay.addWidget(self.result_view, 1)
        split.addWidget(right)
        split.setSizes([420, 720])
        lay.addWidget(split, 1)

        # ---------- 情景卡拆书（v1.26）：从本小说 txt 拆出全部情景卡草稿（同类/相似度高自动合并） ----------
        sc_box = QGroupBox("📇 情景卡拆书（从上面导入的小说 txt 拆出全部正文AI情景卡草稿；"
                           "不同打斗/开篇/矛盾引爆/分手/绝境等拆得详细，同类与相似度高的自动合并）")
        sclay = QVBoxLayout(sc_box)
        scrow = QHBoxLayout()
        self.sc_start_btn = QPushButton("开始情景卡拆书")
        self.sc_start_btn.setObjectName("accent")
        self.sc_start_btn.setToolTip("对已导入的小说全文分片抽取候选情景 → 按相似度合并去重 → "
                                     "逐类生成卡草稿（核心定位+分节+自检清单）。\n"
                                     "走「用途分工·情景提示词制作」配置的 API（未指定跟随通用）。")
        self.sc_start_btn.clicked.connect(self._sc_start)
        scrow.addWidget(self.sc_start_btn)
        self.sc_stop_btn = QPushButton("停止")
        self.sc_stop_btn.setObjectName("danger")
        self.sc_stop_btn.setEnabled(False)
        self.sc_stop_btn.clicked.connect(self._sc_stop)
        scrow.addWidget(self.sc_stop_btn)
        scrow.addWidget(QLabel("（勾选后点「存进总库」，卡名=情景类型、分类已保留，可到「情景提示词」页再编辑/分类）"))
        scrow.addStretch(1)
        sclay.addLayout(scrow)
        sprow = QHBoxLayout()
        sprow.addWidget(QLabel("控制性提示词（可选，指定拆卡方向）："))
        self.sc_prompt_edit = QLineEdit()
        self.sc_prompt_edit.setPlaceholderText(
            "例：重点拆装逼打脸/战斗按流派细分/日常温馨情景；跳过感情戏；注意开篇悬念写法…")
        self.sc_prompt_edit.setToolTip("情景卡拆书的方向控制（类似拆书工坊的「总体提示词」）：\n"
                                       "指定优先拆哪些情景、哪些可以不拆、注意哪些写法差异；\n"
                                       "留空 = 按通用思路把全书情景都拆出来。")
        sprow.addWidget(self.sc_prompt_edit, 1)
        sclay.addLayout(sprow)
        self.sc_log_view = QTextBrowser()
        self.sc_log_view.setOpenExternalLinks(False)
        self.sc_log_view.setMaximumHeight(90)
        sclay.addWidget(self.sc_log_view)
        self.sc_result_list = QListWidget()
        self.sc_result_list.setMinimumHeight(120)
        self.sc_result_list.setMaximumHeight(170)
        self.sc_result_list.setToolTip("勾选要存入总库的卡草稿（默认全选；可不想要的取消勾选）")
        self.sc_result_list.itemChanged.connect(self._sc_update_save_btn)
        sclay.addWidget(self.sc_result_list)
        scrow3 = QHBoxLayout()
        self.sc_save_btn = QPushButton("存进总库（勾选 0 张）")
        self.sc_save_btn.setObjectName("primary")
        self.sc_save_btn.setEnabled(False)
        self.sc_save_btn.clicked.connect(self._sc_save)
        scrow3.addWidget(self.sc_save_btn)
        scrow3.addStretch(1)
        sclay.addLayout(scrow3)
        lay.addWidget(sc_box)

        foot = QHBoxLayout()
        foot.addWidget(QLabel("风格库（已保存的拆书风格）"))
        foot.addStretch(1)
        # v1.42 补上「导出选中风格」：之前只能导出本次拆书结果，库里已保存的风格无法再导出
        exp_style_btn = QPushButton("导出选中风格（txt）")
        exp_style_btn.setToolTip("导出风格库中当前选中的拆书风格文档为 txt（导入/保存进库的文档也能导出）")
        exp_style_btn.clicked.connect(self._export_style)
        foot.addWidget(exp_style_btn)
        lay.addLayout(foot)
        self.style_list = QListWidget()
        self.style_list.itemDoubleClicked.connect(lambda _i: self._show_style())
        lay.addWidget(self.style_list)

        self._worker = _BreakWorker()
        self._worker.log.connect(self._on_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self.refresh_styles()

    # ---------- 风格库 ----------
    def refresh_styles(self):
        cur = self.style_combo.currentText()
        self.style_combo.clear()
        self.style_list.clear()
        for it in book_break.list_breaks():
            name = it["name"]
            self.style_combo.addItem(name)
            self.style_list.addItem(
                "%s　·　%s　· 文档%d字" % (name, it.get("saved_at", ""), it.get("doc_chars", 0)))
        if cur:
            idx = self.style_combo.findText(cur)
            if idx >= 0:
                self.style_combo.setCurrentIndex(idx)
        # 当前项目风格
        _, project = current_project()
        if project and project.story_break_style:
            idx = self.style_combo.findText(project.story_break_style)
            if idx >= 0:
                self.style_combo.setCurrentIndex(idx)

    def _show_style(self):
        item = self.style_list.currentItem()
        if not item:
            return
        name = item.text().split("　")[0]
        data = book_break.load_break(name)
        if data:
            self.result_view.setPlainText(data.get("doc") or "")

    def _apply_style(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        name = self.style_combo.currentText().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请先选一个拆书风格（风格库为空时先拆书并保存）。")
            return
        project.story_break_style = name
        store.save_project(project)
        log_fn("info", "当前项目已应用拆书风格：%s（主AI将学习其剧情设计技法）" % name)
        QMessageBox.information(self, "已应用",
                                "《%s》已应用到「%s」。\n\n主AI在剧情决断/校验/审查时"
                                "会参考该拆书提炼的「设计技法学习文本」——学它的剧情推动、"
                                "伏笔设计、人物塑造方法，不照抄情节。\n\n可在「项目」页随时换回。"
                                % (name, project.title))

    def _delete_style(self):
        item = self.style_list.currentItem()
        if not item:
            return
        name = item.text().split("　")[0]
        if QMessageBox.question(self, "删除", "删除拆书风格「%s」？" % name) \
                != QMessageBox.StandardButton.Yes:
            return
        book_break.delete_break(name)
        self.refresh_styles()
        log_fn("info", "已删除拆书风格：%s" % name)

    def _export_style(self):
        """v1.42 导出风格库中当前选中的拆书风格为 txt（保存进库/导入进库的文档都能再导出）。"""
        item = self.style_list.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先在风格库列表中选中要导出的拆书风格。")
            return
        name = item.text().split("　")[0]
        default = os.path.join(os.path.expanduser("~"), "Desktop", "%s-拆书风格.txt" % name)
        path, _ = QFileDialog.getSaveFileName(self, "导出拆书风格", default, "文本文件 (*.txt)")
        if not path:
            return
        r = book_break.export_break(name, path)
        if r.get("ok"):
            log_fn("info", "拆书风格已导出：%s" % path)
            QMessageBox.information(self, "已导出", "拆书风格已导出到：\n%s" % path)
        else:
            QMessageBox.warning(self, "导出失败", str(r.get("error", "未知错误")))

    # ---------- 导入 / 开始 / 停止 / 导出 ----------
    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择小说 txt", "", "文本文件 (*.txt);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            QMessageBox.warning(self, "读取失败", str(e))
            return
        self._source_path = path
        self._source_text = text
        self.file_label.setText(os.path.basename(path))
        self.file_label.setToolTip(path)
        self.clear_file_btn.setEnabled(True)
        parsed = book_break.parse_novel(text)
        total_chars = parsed["total_chars"]
        preview = "\n".join(
            "第%d卷%s · %d章" % (v["no"], ("《%s》" % v["title"]) if v["title"] else "",
                                 len(v["chapters"]))
            for v in parsed["volumes"][:40])
        if len(parsed["volumes"]) > 40:
            preview += "\n…（共 %d 卷）" % len(parsed["volumes"])
        self.preview_label.setText(
            "已导入：%s\n共 %d 卷 / %d 章 / %.1f 万字（拆书全程可随时停止，每卷单独调用模型，"
            "数千章的长篇也能拆）。\n\n卷结构预览：\n%s" % (
                os.path.basename(path), len(parsed["volumes"]),
                parsed["total_chapters"], total_chars / 10000, preview))
        self.start_btn.setEnabled(True)
        self.log_view.clear()
        self.result_view.clear()
        self._result = None
        self.export_btn.setEnabled(False)

    def _clear_source(self):
        """去掉已导入的 txt，回到未导入状态（可重新选文件）。"""
        self._source_path = ""
        self._source_text = ""
        self._result = None
        self.file_label.setText("未导入")
        self.file_label.setToolTip("当前已导入的 txt 文件（点「清除已导入」可换文件）")
        self.clear_file_btn.setEnabled(False)
        self.preview_label.setText("尚未导入小说。选择一部 txt 后，这里会显示分卷分章结果预览。")
        self.start_btn.setEnabled(False)
        self.restart_btn.setEnabled(False)
        self.log_view.clear()
        self.result_view.clear()

    # ---------- 情景卡拆书（v1.26） ----------
    def _sc_start(self):
        if not self._source_text or not self._source_text.strip():
            QMessageBox.warning(self, "提示", "请先导入小说 txt（顶部「导入小说 txt」）。")
            return
        if self._sc_worker is not None:
            QMessageBox.information(self, "提示", "情景卡拆书正在运行，先点「停止」再重新开始。")
            return
        self.sc_log_view.clear()
        self.sc_result_list.clear()
        self.sc_save_btn.setEnabled(False)
        self.sc_save_btn.setText("存进总库（勾选 0 张）")
        self.sc_start_btn.setEnabled(False)
        self.sc_stop_btn.setEnabled(True)
        worker = SceneCardExtractWorker()
        worker.log.connect(self._sc_on_log)
        worker.done.connect(self._sc_on_done)
        worker.stopped.connect(self._sc_on_stopped)
        worker.card_ready.connect(self._sc_on_card)   # v1.36 逐张实时入列
        self._sc_worker = worker
        set_running(True)
        threading.Thread(target=worker.run,
                         args=(self._source_text,
                               self.sc_prompt_edit.text().strip()),
                         daemon=True).start()
        self.sc_log_view.append("开始情景卡拆书（分片抽取候选 → 相似度合并 → 逐类生成卡草稿）…")

    def _sc_stop(self):
        if self._sc_worker is not None:
            self.sc_log_view.append("→ 正在停止（中断当前环节，已拆出的卡保留在结果列表，可直接保存）…")
            self._sc_worker.stop()

    def _sc_on_log(self, kind, msg):
        self.sc_log_view.append(msg)
        log_fn(kind, "[情景卡拆书] " + msg)

    def _sc_add_card_item(self, c):
        """把一张卡草稿加进结果列表（v1.36：完成全量入列与逐张实时入列共用）。"""
        nm = str(c.get("name") or "").strip()
        ct = str(c.get("content") or "").strip()
        cat = str(c.get("category") or "").strip()
        preview = ct[:48] + ("…" if len(ct) > 48 else "")
        label = ("【%s】%s（%d 字）：%s" % (cat, nm, len(ct), preview)
                 if cat else "%s（%d 字）：%s" % (nm, len(ct), preview))
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, c)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        self.sc_result_list.addItem(item)

    def _sc_on_card(self, c):
        """v1.36 逐张实时入列：每拆出一张卡草稿立即显示，长小说可边拆边看/随时停止。"""
        self._sc_add_card_item(c)
        self._sc_update_save_btn()

    def _sc_on_done(self, cards):
        self._sc_worker = None
        set_running(False)
        self.sc_start_btn.setEnabled(True)
        self.sc_stop_btn.setEnabled(False)
        self.sc_result_list.clear()
        for c in cards:
            self._sc_add_card_item(c)
        self._sc_update_save_btn()

    def _sc_on_stopped(self):
        self._sc_worker = None
        set_running(False)
        self.sc_start_btn.setEnabled(True)
        self.sc_stop_btn.setEnabled(False)

    def _sc_update_save_btn(self):
        n = 0
        for i in range(self.sc_result_list.count()):
            if self.sc_result_list.item(i).checkState() == Qt.CheckState.Checked:
                n += 1
        self.sc_save_btn.setEnabled(n > 0)
        self.sc_save_btn.setText("存进总库（勾选 %d 张）" % n)

    def _sc_save(self):
        cfg = None
        lib = []
        try:
            import config as _cfg
            cfg = _cfg.load_config()
            lib = list(cfg.get("writer_scene_cards") or [])
        except Exception:
            cfg = None
        names = {str(c.get("name") or "").strip() for c in lib}
        added = skipped = 0
        for i in range(self.sc_result_list.count()):
            it = self.sc_result_list.item(i)
            if it.checkState() != Qt.CheckState.Checked:
                continue
            c = it.data(Qt.ItemDataRole.UserRole) or {}
            nm = str(c.get("name") or "").strip()
            if not nm or nm in names:
                skipped += 1
                continue
            lib.append({"name": nm,
                        "content": str(c.get("content") or "").strip(),
                        "category": str(c.get("category") or "").strip()})
            names.add(nm)
            added += 1
        if added == 0:
            QMessageBox.information(self, "无需保存", "勾选的卡都是总库已存在的（共跳过 %d 张）。" % skipped)
            return
        if cfg is not None:
            cfg["writer_scene_cards"] = lib
            try:
                import config as _cfg2
                _cfg2.save_config(cfg)
            except Exception as e:
                QMessageBox.warning(self, "保存失败", "写入总库失败：%s" % e)
                return
        log_fn("info", "情景卡拆书结果存进总库 %d 张（重名跳过 %d 张）。" % (added, skipped))
        QMessageBox.information(self, "已存入总库",
                                "已把 %d 张卡草稿存进总库（同名跳过 %d 张）。\n"
                                "到「情景提示词」页可再编辑/分类/加入本项目或一键成书。"
                                % (added, skipped))
        self.sc_result_list.clear()
        self.sc_save_btn.setEnabled(False)
        self.sc_save_btn.setText("存进总库（勾选 0 张）")

    def _start(self, restart=False):
        if not self._source_text:
            return
        self.settings_box.save()   # 界面看到什么，跑起来就用什么（含模式/token/重叠/并行/L3）
        if self._worker is None or self._worker._stop.is_set():
            self._worker = _BreakWorker()
            self._worker.log.connect(self._on_log)
            self._worker.progress.connect(self._on_progress)
            self._worker.done.connect(self._on_done)
        self._log_items = []
        self.log_view.clear()
        self.result_view.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.restart_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self.resume_btn.setEnabled(False)
        title = os.path.splitext(os.path.basename(self._source_path))[0]
        set_running(True)
        threading.Thread(target=self._worker.run,
                         args=(self._source_text, title, restart),
                         daemon=True).start()

    def _ask_restart(self):
        """v0.69 重新开始拆书：清空进度全部重来（不做断点续传）。"""
        if busy_guard(self):
            return
        ret = QMessageBox.question(
            self, "重新开始拆书",
            "将清除本次小说的拆书进度，从头重新拆书（不再续传）。\n\n确定继续吗？")
        if ret == QMessageBox.StandardButton.Yes:
            self._start(restart=True)

    def _stop(self):
        if self._worker is not None:
            self._worker.stop()
            self.stop_btn.setEnabled(False)
            self.stop_btn.setText("正在停止…")

    # v0.82 暂停 / 继续：临时挂起拆书（当前环节之间停下），不中断进度
    def _pause(self):
        if self._worker is not None:
            self._worker.pause()
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.log_view.appendPlainText("⏸ 已暂停：当前环节完成后挂起，点「继续」恢复。")

    def _resume(self):
        if self._worker is not None:
            self._worker.resume()
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.log_view.appendPlainText("▶ 已继续。")

    def _export_doc(self):
        data = self._result
        if not data or not data.get("doc"):
            QMessageBox.warning(self, "提示", "还没有拆书结果。")
            return
        default = os.path.join(os.path.expanduser("~"), "Desktop", "拆书文档.txt")
        path, _ = QFileDialog.getSaveFileName(self, "导出拆书文档", default, "文本文件 (*.txt)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(data["doc"])
        log_fn("info", "拆书文档已导出：%s" % path)
        QMessageBox.information(self, "已导出", "拆书文档已保存到：\n%s" % path)

    def _save_style(self):
        data = self._result
        if not data or not data.get("doc"):
            QMessageBox.warning(self, "提示", "还没有拆书结果。")
            return
        default = os.path.splitext(os.path.basename(self._source_path))[0]
        name, ok = _ask_name(self, "保存为拆书风格", "风格名称", default)
        if not ok:
            return
        book_break.save_break(name, data["doc"], data.get("learning") or "")
        self.refresh_styles()
        log_fn("info", "拆书风格已保存：%s（可在当前项目应用，让主AI学习其设计技法）" % name)

    def _import_break(self):
        """导入外部拆书文档（txt/md/json）为一个拆书风格。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择拆书文档", "", "拆书文档 (*.txt *.md *.json);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            QMessageBox.warning(self, "读取失败", str(e))
            return
        if not (content or "").strip():
            QMessageBox.warning(self, "提示", "文件内容为空。")
            return
        default = os.path.splitext(os.path.basename(path))[0]
        name, ok = _ask_name(self, "保存为拆书风格", "风格名称", default)
        if not ok:
            return
        r = book_break.import_break_from_text(name, content)
        if r.get("ok"):
            self.refresh_styles()
            log_fn("info", "拆书文档已导入为风格「%s」（可应用到当前项目让主AI学习）" % name)
            QMessageBox.information(self, "已导入",
                                    "拆书文档已导入为拆书风格「%s」。\n\n"
                                    "顶部选中它 → 「应用到当前项目」，主AI就会学习其"
                                    "剧情推动/伏笔设计技法（不抄情节）。" % name)
        else:
            QMessageBox.warning(self, "导入失败", str(r.get("error", "未知错误")))

    # ---------- 信号处理 ----------
    def _on_log(self, kind, msg):
        colors = {"info": T("#d7dce4"), "warn": T("#c9a832"), "error": T("#c96f6f")}
        cursor = self.log_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertHtml("<div style='color:%s;margin:2px 0;font-size:12px;'>%s</div>"
                          % (colors.get(kind, T("#d7dce4")), str(msg).replace("<", "&lt;")))
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_progress(self, stage, done, total):
        stage_names = {"title": "L1 章节标题概览", "skeleton": "L1 全书骨架",
                       "volume": "L2 卷细纲", "merge": "L3 汇总文档"}
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(done)
        self.progress_bar.setFormat("%s %d/%d" % (stage_names.get(stage, stage), done, total))

    def _on_done(self, payload):
        set_running(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("停止")
        self.restart_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        if self._worker is not None:
            self._worker._pause.clear()   # 复位暂停状态（完成/停止后）
        self.progress_bar.setVisible(False)
        if not payload.get("ok"):
            if payload.get("error") == "已停止":
                log_fn("warn", "拆书已停止（已完成的卷保留在日志，可重新开始）。")
            else:
                # v0.72 失败弹窗直接给出恢复入口：继续拆书（补跑）/ 重新开始 / 取消
                err = str(payload.get("error", "未知错误"))
                try:
                    mb = QMessageBox(self)
                    mb.setWindowTitle("拆书未完成")
                    mb.setText("拆书未全部完成：\n%s\n\n接下来怎么处理？" % err)
                    b_go = mb.addButton("继续拆书（只补跑失败环节）",
                                        QMessageBox.ButtonRole.AcceptRole)
                    b_rst = mb.addButton("重新开始拆书（清空进度从头来）",
                                         QMessageBox.ButtonRole.DestructiveRole)
                    mb.addButton("取消", QMessageBox.ButtonRole.RejectRole)
                    mb.exec()
                    clicked = mb.clickedButton()
                    if clicked is b_go:
                        self._start(restart=False)
                    elif clicked is b_rst:
                        self._start(restart=True)
                except Exception:
                    pass
            return
        self._result = payload
        stats = payload.get("stats") or {}
        doc = payload.get("doc") or ""
        learning = payload.get("learning") or ""
        self.result_view.setPlainText(doc)
        self.export_btn.setEnabled(True)
        self.save_btn.setEnabled(True)   # v0.58 修复：拆完即可直接「保存为拆书风格」，无需导出再导入
        log_fn("info", "拆书完成：%d 卷 / %d 章 → 文档 %d 字 / 学习文本 %d 字。"
               % (stats.get("volumes", 0), stats.get("chapters", 0),
                  len(doc), len(learning)))
        QMessageBox.information(
            self, "拆书完成",
            "拆书完成：%d 卷 / %d 章 → 拆书文档 %d 字（≤8 万）。\n\n"
            "接下来：\n① 「保存为拆书风格」直接存入风格库（无需导出再导入）；\n"
            "② 在顶部选该风格 → 「应用到当前项目」，主AI就会学习它的"
            "剧情推动 / 伏笔设计 / 人物塑造技法（不抄情节）；\n"
            "③ 「导出拆书文档」可存为 txt 留存。"
            % (stats.get("volumes", 0), stats.get("chapters", 0), len(doc)))

    def on_show(self):
        self.refresh_styles()
        # 回填拆书参数（模式/token/重叠/并行/提示词/L3，config 为准）
        self.settings_box.load()


def _ask_name(parent, title, label, default=""):
    """简单命名输入对话框（QInputDialog 复用）。"""
    from PySide6.QtWidgets import QDialog, QDialogButtonBox, QInputDialog
    from PySide6.QtWidgets import QFormLayout
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    lay = QFormLayout(dlg)
    edit = QLineEdit(default)
    lay.addRow(label, edit)
    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                            | QDialogButtonBox.StandardButton.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addRow(btns)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        name = edit.text().strip()
        if name:
            return name, True
    return "", False