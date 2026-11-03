# -*- coding: utf-8 -*-
"""文风校对功能页（v0.64 移植 novel-style-extractor 的 Gradio 布局到 PySide6）。

布局照搬原项目「📝 主工作台」：左=输入（原文/txt导入/轮次/阈值/开始停止），
右=结果（运行摘要/Top3/导出）；下方实时状态（B 一框 / C 两框 / D 三框 / 完整文本 /
每轮结果）；再往下各节点提示词设置（A/B/C/D）+ 提示词预设管理。
API 设置不在此页（设置页·用途分工·文风校对行选择），教程内容并入页内折叠。
"""
import json
import os
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGroupBox,
                               QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                               QPushButton, QSplitter, QSpinBox, QTabWidget,
                               QTextBrowser, QVBoxLayout, QWidget)

import config
import llm
import style_extract
from gui_app import set_running
from gui_theme import T


class _StyleWorker(QObject):
    """后台线程：跑 A→B→C→D 多轮迭代；用 stop_ev + llm.set_abort 支持立即停止；
    v0.83 加 _pause（轮次间隙暂停/继续）；
    v1.63 加 _retry（节点请求异常后等「继续」重试同一节点，已跑轮次保留）。"""
    stage = Signal(str, object)      # (kind, data)
    done = Signal(object)            # {"ok","error"} 或 final 结果

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._retry = threading.Event()   # v1.63 报错后「继续」唤醒

    def run(self, text, max_rounds, threshold, prompts):
        import llm
        llm.set_abort(self._stop)
        try:
            wf = style_extract.StyleExtractorWorkflow()
            for kind, data in wf.run_workflow_stream(
                    text, max_rounds=max_rounds, threshold=threshold,
                    custom_prompts=prompts,
                    stop_check=lambda: self._stop.is_set(),
                    pause_check=lambda: self._pause.is_set(),
                    retry_evt=self._retry):
                self.stage.emit(kind, data)
            self.done.emit({"ok": True})
        except llm.StopRequested:
            self.done.emit({"ok": False, "error": "已停止"})
        except Exception as e:
            self.done.emit({"ok": False, "error": str(e)})
        finally:
            llm.set_abort(None)


class StyleExtractPage(QWidget):
    """文风校对（novel-style-extractor v0.22 移植）。"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._worker = None
        self._thread = None
        self._timer = None
        self._text = ""
        self._full_text = ""
        self._all_rounds_text = ""
        self._top_prompts_text = ""
        self._cur_round = 0
        self._running = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)

        title = QLabel("文风校对 · A(提取文风)→B(生成文章)→C(评估打分)→D(优化提示词) 多轮迭代，"
                       "直到相似度达标或达到最大轮次")
        title.setStyleSheet(T("font-size:16px;color:#d4a44c;font-weight:bold;"))
        lay.addWidget(title)

        # ---------- 主区分割：左输入 / 右结果 ----------
        split = QSplitter()
        split.setChildrenCollapsible(False)

        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.addWidget(QLabel("输入"))
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("粘贴您想要分析文风的原文（或点下方导入 txt 文件）…")
        # v0.64.1 输入区最小高度兜底：页面包了滚动容器后整体不再被压扁，
        # 这里再保证原文编辑框本身始终可输入（不再塌成一条线）
        self.text_edit.setMinimumHeight(140)
        llay.addWidget(self.text_edit)
        row = QHBoxLayout()
        pick_btn = QPushButton("导入 txt 文件（支持多个）")
        pick_btn.clicked.connect(self._pick_files)
        row.addWidget(pick_btn)
        self.file_label = QLabel("未导入")
        self.file_label.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        row.addWidget(self.file_label, 1)
        llay.addLayout(row)
        pr = QHBoxLayout()
        pr.addWidget(QLabel("最大校对轮次"))
        self.round_spin = QSpinBox()
        self.round_spin.setRange(1, 999)
        self.round_spin.setValue(5)
        pr.addWidget(self.round_spin)
        pr.addSpacing(14)
        pr.addWidget(QLabel("相似度阈值"))
        self.thresh_spin = QSpinBox()
        self.thresh_spin.setRange(0, 100)
        self.thresh_spin.setValue(80)
        pr.addWidget(self.thresh_spin)
        pr.addStretch(1)
        llay.addLayout(pr)
        # v1.48 可选开关：允许 D 看到排名前三的提示词与对应分数，并在分数最高的
        # 提示词基础上改进——让 D 线性进步而不是赌哪次能做出更好的（默认关，防发散）
        chkrow = QHBoxLayout()
        self.see_top3_chk = QCheckBox("D 优化参考 Top3 提示词与分数（在最高分基础上改进，线性进步）")
        self.see_top3_chk.setToolTip(
            "开启后节点 D 优化时能看到本轮以来排名前三的提示词与对应分数，"
            "并被要求在【分数最高的提示词】基础上改进，而不是凭空重写——让分数逐步提高")
        try:
            self.see_top3_chk.setChecked(bool(config.load_config().get("style_d_see_top3")))
        except Exception:
            pass
        self.see_top3_chk.toggled.connect(self._toggle_see_top3)
        chkrow.addWidget(self.see_top3_chk)
        chkrow.addStretch(1)
        llay.addLayout(chkrow)
        btnrow = QHBoxLayout()
        self.start_btn = QPushButton("🚀 开始提炼优化")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self._start)
        btnrow.addWidget(self.start_btn)
        self.stop_btn = QPushButton("⏹ 中断任务")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        btnrow.addWidget(self.stop_btn)
        # v0.83 暂停 / 继续：轮次间隙临时挂起（不打断当前节点请求），点「继续」恢复
        self.pause_btn = QPushButton("⏸ 暂停")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._pause)
        btnrow.addWidget(self.pause_btn)
        self.resume_btn = QPushButton("▶ 继续")
        self.resume_btn.setObjectName("primary")
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self._resume)
        btnrow.addWidget(self.resume_btn)
        btnrow.addStretch(1)
        llay.addLayout(btnrow)
        split.addWidget(left)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.addWidget(QLabel("结果"))
        self.summary_view = QLabel("尚未运行。")
        self.summary_view.setWordWrap(True)
        self.summary_view.setStyleSheet(
            T("background:#1a1d23;border:1px solid #2a2e35;border-radius:6px;"
            "padding:8px;color:#d5d8de;"))
        rlay.addWidget(self.summary_view)
        rlay.addWidget(QLabel("🏆 Top 3 文风提示词（导出后可应用到项目：项目页→参考文风）"))
        self.top_view = QTextBrowser()
        rlay.addWidget(self.top_view, 1)
        ebtn = QHBoxLayout()
        export_btn = QPushButton("📥 导出 Top 3 为 txt")
        export_btn.clicked.connect(self._export_top3)
        ebtn.addWidget(export_btn)
        ebtn.addStretch(1)
        rlay.addLayout(ebtn)
        split.addWidget(right)
        split.setSizes([560, 620])
        lay.addWidget(split, 2)

        # ---------- 实时处理状态 ----------
        st_row = QHBoxLayout()
        st_row.addWidget(QLabel("🔄 实时处理状态"))
        # v0.78 运行计时：任务进行中每秒刷新，UI 保持活跃响应，用户能确认在跑而非无响应
        self.elapsed_lbl = QLabel("")
        self.elapsed_lbl.setStyleSheet(T("color:#d4a44c;font-size:12px;"))
        st_row.addWidget(self.elapsed_lbl)
        st_row.addStretch(1)
        lay.addLayout(st_row)
        bbox = QGroupBox("📥 节点B - 文章生成器（收到：{文风提示词}）")
        bb = QVBoxLayout(bbox)
        self.b_view = QTextBrowser()
        bb.addWidget(self.b_view)
        lay.addWidget(bbox)

        cbox = QGroupBox("📋 节点C - 相似度评估器（{原文} 目标风格 + {生成文章} 待评估）")
        cb = QHBoxLayout(cbox)
        self.c_original = QTextBrowser()
        self.c_generated = QTextBrowser()
        cb.addWidget(self.c_original, 1)
        cb.addWidget(self.c_generated, 1)
        lay.addWidget(cbox)

        dbox = QGroupBox("🔧 节点D - 提示词优化器（{文风提示词} + {生成文章} + {原文}）")
        db = QHBoxLayout(dbox)
        self.d_prompt = QTextBrowser()
        self.d_generated = QTextBrowser()
        self.d_original = QTextBrowser()
        db.addWidget(self.d_prompt, 1)
        db.addWidget(self.d_generated, 1)
        db.addWidget(self.d_original, 1)
        lay.addWidget(dbox)

        extra_tabs = QTabWidget()
        self.full_view = QTextBrowser()
        extra_tabs.addTab(self.full_view, "📖 本轮完整生成文本")
        self.rounds_view = QTextBrowser()
        extra_tabs.addTab(self.rounds_view, "📋 每轮详细结果")
        lay.addWidget(extra_tabs)

        # ---------- 各节点提示词设置 ----------
        lay.addWidget(QLabel("✏️ 各节点提示词设置（可用变量见下方「💡 提示词写法」；保存后永久生效）"))
        self.prompt_edits = {}
        ptab = QTabWidget()
        for key, label in (("node_a", "节点A - 文风提取器（可用变量：{原文}）"),
                           ("node_b", "节点B - 文章生成器（可用变量：{文风提示词}）"),
                           ("node_c", "节点C - 相似度评估器（可用变量：{原文} + {生成文章}）"),
                           ("node_d", "节点D - 提示词优化器（可用变量：{文风提示词} + {原文} + {生成文章}）")):
            pg = QWidget()
            pl = QVBoxLayout(pg)
            ed = QPlainTextEdit()
            ed.setPlaceholderText("输入该节点提示词…")
            ed.setMinimumHeight(100)   # v0.64.1 提示词编辑框最小高度兜底
            pl.addWidget(ed)
            self.prompt_edits[key] = ed
            ptab.addTab(pg, label)
        save_btn = QPushButton("💾 保存提示词设置")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_prompts)
        srow = QHBoxLayout()
        srow.addWidget(save_btn)
        self.prompts_status = QLabel("")
        self.prompts_status.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        srow.addWidget(self.prompts_status, 1)
        lay.addLayout(srow)
        lay.addWidget(ptab)

        # ---------- 提示词预设管理 ----------
        pres = QHBoxLayout()
        pres.addWidget(QLabel("提示词预设"))
        self.preset_combo = QComboBox()
        pres.addWidget(self.preset_combo, 1)
        apply_btn = QPushButton("📂 加载选中预设")
        apply_btn.clicked.connect(self._apply_preset)
        pres.addWidget(apply_btn)
        self.preset_name_edit = QPlainTextEdit()
        self.preset_name_edit.setMaximumHeight(30)
        self.preset_name_edit.setPlaceholderText("新预设名称")
        pres.addWidget(self.preset_name_edit)
        save_pre = QPushButton("💾 保存为预设")
        save_pre.clicked.connect(self._save_preset)
        pres.addWidget(save_pre)
        del_pre = QPushButton("🗑️ 删除选中预设")
        del_pre.clicked.connect(self._delete_preset)
        pres.addWidget(del_pre)
        lay.addLayout(pres)
        # v1.45 预设导入导出（json 文件：备份/换机迁移/分享整套四节点提示词预设）
        pres2 = QHBoxLayout()
        self.export_preset_btn = QPushButton("📤 导出预设（json）")
        self.export_preset_btn.setToolTip(
            "把当前选中预设（四节点提示词 node_a~d）导出为 json 文件——备份、换机迁移、分享给别人直接用")
        self.export_preset_btn.clicked.connect(self._export_preset)
        pres2.addWidget(self.export_preset_btn)
        self.import_preset_btn = QPushButton("📥 导入预设（json）")
        self.import_preset_btn.setToolTip(
            "从 json 文件导入预设（四节点提示词 node_a~d）到预设库并立即入库；"
            "支持本页导出的预设文件，也兼容直接含 node_a~d 的 json（预设名取文件名）")
        self.import_preset_btn.clicked.connect(self._import_preset)
        pres2.addWidget(self.import_preset_btn)
        pres2.addStretch(1)
        lay.addLayout(pres2)
        self.preset_status = QLabel("")
        self.preset_status.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(self.preset_status)

        # ---------- 提示词写法教程（折叠） ----------
        guide = QGroupBox("💡 提示词写法指南（占位符 {变量} vs 说明文字 【】）")
        gb = QVBoxLayout(guide)
        g = QTextBrowser()
        g.setOpenExternalLinks(False)
        g.setHtml(
            T("<div style='color:#d5d8de;font-size:13px;line-height:1.7'>"
            "<b>两种符号的区别：</b><br>"
            "<code>{文风提示词}</code> = 占位符，程序会把整个占位符替换成实际内容（出现几次插几次）；"
            "<code>【文风提示词】</code> = 普通说明文字，不会被替换（指令中引用时用）。<br><br>"
            "<b>可用变量：</b><br>"
            "{原文}：你上传的参考文本（目标风格）——A/C/D 可用<br>"
            "{文风提示词}：节点A提取或节点D优化后的文风特征——B/D 可用<br>"
            "{生成文章}：节点B写出的文章——C/D 可用<br><br>"
            "<b>变量顺序可自由调整</b>，文字可在占位符前后；实际内容在指令后就用「以下」指代，在前用「以上」。"
            "</div>"))
        gb.addWidget(g)
        lay.addWidget(guide)

        self.on_show()

    # ---------- 生命周期 ----------
    def on_show(self):
        try:
            wf = style_extract.StyleExtractorWorkflow()
            p = wf.load_prompts()
            for k, ed in self.prompt_edits.items():
                ed.setPlainText(p.get(k, ""))
            self._refresh_preset_combo()
        except Exception:
            pass

    def _refresh_preset_combo(self, keep=None):
        try:
            wf = style_extract.StyleExtractorWorkflow()
            names = list(wf.load_presets().keys())
            cur = self.preset_combo.currentText()
            self.preset_combo.clear()
            self.preset_combo.addItems(names)
            if keep and keep in names:
                self.preset_combo.setCurrentText(keep)
            elif cur in names:
                self.preset_combo.setCurrentText(cur)
        except Exception:
            pass

    # ---------- 输入 ----------
    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择小说 txt（支持多个，自动拼接）",
                                                "", "文本文件 (*.txt)")
        if not paths:
            return
        texts = []
        for p in paths:
            for enc in ("utf-8", "gbk", "utf-8-sig"):
                try:
                    with open(p, encoding=enc) as f:
                        texts.append(f.read())
                    break
                except UnicodeDecodeError:
                    continue
        self._text = "\n\n".join(texts)
        self.text_edit.setPlainText(self._text)
        self.file_label.setText("、".join(os.path.basename(p) for p in paths))

    # ---------- 运行 ----------
    def _toggle_see_top3(self, checked):
        """v1.48 D 节点可选开关：允许 D 看到排名前三提示词与分数、在最高分基础上改进。"""
        cfg = config.load_config()
        cfg["style_d_see_top3"] = bool(checked)
        config.save_config(cfg)

    def _start(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "缺少输入", "请输入原文文本或先导入 txt 文件。")
            return
        if self._running:
            return
        self._all_rounds_text = ""
        self._top_prompts_text = ""
        self._full_text = ""
        self.summary_view.setText("运行中…")
        self.b_view.setPlainText("")
        self.c_original.setPlainText("")
        self.c_generated.setPlainText("")
        self.d_prompt.setPlainText("")
        self.d_generated.setPlainText("")
        self.d_original.setPlainText("")
        self.full_view.setPlainText("")
        self.rounds_view.setPlainText("")
        self.top_view.setPlainText("")
        set_running(True)
        self._running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self.resume_btn.setEnabled(False)
        # v0.78 运行计时：每秒刷新「已运行 Xm Ys」，UI 保持活跃，用户能确认在跑而非无响应
        self._elapsed = 0
        self.elapsed_lbl.setText("已运行 0s")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

        prompts = {k: ed.toPlainText().strip() for k, ed in self.prompt_edits.items()}
        # v0.78.1 修复「点开始立即卡死」：①不再用 QThread+moveToThread——
        # 实测 QThread 线程长时间运行（worker 阻塞在 API/睡眠）会冻结主线程 Qt 事件循环
        # （tick 停止、窗口无响应一晚上）；改纯 Python threading.Thread 启动，
        # 信号仍走 Qt（PySide6 允许任意线程 emit，自动 Queued 到主线程）；
        # ②参数一律主线程取值传入，worker 线程绝不访问任何 QWidget
        _rounds = int(self.round_spin.value())
        _thresh = float(self.thresh_spin.value())
        self._worker = _StyleWorker()
        self._worker.stage.connect(self._on_stage)
        self._worker.done.connect(self._on_done)
        self._worker.done.connect(self._cleanup)
        self._thread = threading.Thread(
            target=self._worker.run, args=(text, _rounds, _thresh, prompts),
            daemon=True)
        self._thread.start()

    def _stop(self):
        if self._worker is not None:
            # 立即给 UI 反馈：禁用停止/暂停按钮 + 提示正在停止——
            # 此前只 set 事件，若 LLM 调用卡在网关响应，按钮无任何变化，体感「停止不生效」。
            self._worker._stop.set()
            # v1.59 立即断开：关闭当前活跃的 LLM 请求连接（阻塞的流式读取立刻抛异常），
            # 不等当前节点生成完——用户要求「点停止 → 立即发送停止指令，不要等节点结束」。
            llm.abort_active_resps()
            self.stop_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.summary_view.setText("⏹ 正在停止…（请求已断开）")

    # v0.83 暂停 / 继续：轮次间隙挂起（当前节点请求跑完才停下），点「继续」恢复
    def _pause(self):
        if self._worker is not None:
            self._worker._pause.set()
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.summary_view.setText("⏸ 已暂停：当前节点完成后挂起，点「继续」恢复。")

    def _resume(self):
        if self._worker is not None:
            self._worker._pause.clear()
            # v1.63：报错挂起时「继续」= 唤醒 retry 重试同一节点（已跑轮次保留）
            self._worker._retry.set()
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.summary_view.setText("▶ 已继续。")

    def _tick(self):
        self._elapsed += 1
        m, s = divmod(self._elapsed, 60)
        self.elapsed_lbl.setText("已运行 %d分%02d秒" % (m, s))

    def _cleanup(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.elapsed_lbl.setText("")
        self._running = False
        set_running(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        if self._worker is not None:
            self._worker._pause.clear()

    def _on_stage(self, kind, data):
        if kind == "status":
            self.summary_view.setText(str(data))
        elif kind == "a_done":
            self.b_view.setPlainText(str(data.get("文风提示词", "")))
            self.summary_view.setText("节点A完成：文风提示词已提取（下一步多轮迭代）")
        elif kind == "b_start":
            self._cur_round = data.get("round", self._cur_round)
            self.summary_view.setText("第 %s/%s 轮 - 节点B正在生成文章..." % (data.get("round"), self.round_spin.value()))
        elif kind == "b_done":
            self.c_original.setPlainText(self.text_edit.toPlainText()[:2000])
            self.c_generated.setPlainText(str(data.get("生成文章", ""))[:2000])
            gen_full = str(data.get("生成文章", ""))
            self._full_text = gen_full
            # v0.78 完整正文只存内存（导出用），界面仅显示前 8000 字——
            # 每轮 8 万字符全文塞富文本浏览器会让 Qt 文档持续膨胀，长轮次下拖垮 UI
            self.full_view.setPlainText(gen_full[:8000] + (
                "…\n（完整 %d 字已保存，导出 Top3 时含全文）" % len(gen_full)
                if len(gen_full) > 8000 else ""))
        elif kind == "c_start":
            self.summary_view.setText("第 %s/%s 轮 - 节点C正在对比评估..." % (data.get("round"), self.round_spin.value()))
        elif kind == "c_done":
            self.summary_view.setText("第 %s 轮 - 节点C完成：得分 %s/100"
                                      % (self._cur_round, data.get("score")))
        elif kind == "d_start":
            self.d_prompt.setPlainText(str(data.get("文风提示词", "")))
            # v0.78 同样截断：原文可能十万字，99 轮逐轮整文重渲染是资源占用大头
            self.d_generated.setPlainText(str(data.get("生成文章", ""))[:8000])
            self.d_original.setPlainText(str(data.get("原文", ""))[:8000])
        elif kind == "d_done":
            self.b_view.setPlainText(str(data.get("文风提示词", "")))
        elif kind == "error":
            # v1.63 节点请求异常：不终止流程，挂起等用户处理——
            # 可先换 API/调整后点「继续」重试同一节点，已跑轮次与 Top3 保留；
            # 也可点「停止」结束（已跑结果仍可导出）。
            self.summary_view.setText(
                "⚠️ 节点请求异常：{}\n\n已保留已跑轮次与Top3——可先换 API，"
                "再点「继续」重试该节点，或点「停止」结束。".format(
                    data.get("message", "未知错误")))
            self.resume_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)
        elif kind == "round_end":
            r = data.get("round")
            self.summary_view.setText(
                "📊 第 %s/%s 轮完成 - 得分：%s/100（当前Top3：%s）"
                % (r, self.round_spin.value(), data.get("score"),
                   "、".join("%s/100" % s for s in data.get("top_scores", []))))
            self._all_rounds_text += "=== 第 %s 轮 ===\n得分：%s/100\n\n" % (r, data.get("score"))
            self.rounds_view.setPlainText(self._all_rounds_text)
            self._top_prompts_text = self._build_top_text(data.get("top_style_prompts", []))
            self.top_view.setPlainText(self._top_prompts_text)
        elif kind == "final":
            result = data
            self._top_prompts_text = self._build_top_text(result.get("top_style_prompts", []))
            self.top_view.setPlainText(self._top_prompts_text)
            all_txt = ""
            for rr in result.get("all_rounds", []):
                all_txt += "=== 第 %s 轮 ===\n得分: %s\n生成文本:\n%s...\n\n%s\n\n" % (
                    rr.get("round"), rr.get("score"),
                    str(rr.get("generated_text", ""))[:1000], "-" * 80)
            self.rounds_view.setPlainText(all_txt)
            self.summary_view.setText(
                "✅ 运行完成！\n最高得分: %s\n达到阈值: %s\n总轮次: %s"
                % (result.get("best_score"),
                   "是" if result.get("reached_threshold") else "否",
                   len(result.get("all_rounds", []))))

    def _build_top_text(self, items):
        out = ""
        for i, it in enumerate(items, 1):
            out += "=== 第%s名 (得分: %s) ===\n文风提示词:\n%s\n\n样例文本:\n%s\n\n%s\n\n" % (
                i, it.get("score"), it.get("prompt"), it.get("sample_text"), "-" * 80)
        return out

    def _on_done(self, result):
        if not result.get("ok"):
            self.summary_view.setText("❌ %s" % result.get("error", "未知错误"))
        # 清理统一由 done→cleanup 信号连接执行，不再在此重复调用（避免出错时重复清理）

    # ---------- 提示词保存 / 预设 ----------
    def _save_prompts(self):
        prompts = {k: ed.toPlainText().strip() for k, ed in self.prompt_edits.items()}
        style_extract.StyleExtractorWorkflow().save_prompts(prompts)
        self.prompts_status.setText("✅ 提示词已保存（重启后仍生效）")

    def _apply_preset(self):
        name = self.preset_combo.currentText()
        if not name:
            return
        wf = style_extract.StyleExtractorWorkflow()
        merged = wf.apply_preset(name)
        for k, ed in self.prompt_edits.items():
            ed.setPlainText(merged.get(k, ""))
        self.preset_status.setText("✅ 已加载提示词预设「%s」" % name)

    def _save_preset(self):
        name = self.preset_name_edit.toPlainText().strip()
        if not name:
            self.preset_status.setText("❌ 预设名称不能为空！")
            return
        prompts = {k: ed.toPlainText().strip() for k, ed in self.prompt_edits.items()}
        style_extract.StyleExtractorWorkflow().save_preset(name, prompts)
        self.preset_name_edit.setPlainText("")
        self._refresh_preset_combo(keep=name)
        self.preset_status.setText("✅ 提示词预设「%s」保存成功！" % name)

    def _delete_preset(self):
        name = self.preset_combo.currentText()
        if not name or name == "default":
            self.preset_status.setText("❌ 不能删除 default 预设！")
            return
        style_extract.StyleExtractorWorkflow().delete_preset(name)
        self._refresh_preset_combo()
        self.preset_status.setText("✅ 预设「%s」已删除！" % name)

    # ---------- v1.45 预设导入导出（json 文件：备份 / 换机迁移 / 分享整套四节点提示词预设） ----------
    def _export_preset(self):
        name = self.preset_combo.currentText().strip()
        if not name:
            self.preset_status.setText("❌ 请先选中要导出的预设！")
            return
        wf = style_extract.StyleExtractorWorkflow()
        prompts = wf.load_presets().get(name, {})
        default = os.path.join(os.path.expanduser("~"), "Desktop",
                               "文风校对预设-%s.json" % name)
        path, _ = QFileDialog.getSaveFileName(self, "导出文风校对预设", default,
                                              "JSON 文件 (*.json)")
        if not path:
            return
        payload = {
            "app": "星火笔",
            "type": "style_extract_preset",
            "version": 1,
            "name": name,
            "prompts": {k: prompts.get(k, "") for k in ("node_a", "node_b", "node_c", "node_d")},
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "导出失败", "写入预设文件失败：%s" % e)
            return
        self.preset_status.setText("✅ 预设「%s」已导出：%s" % (name, os.path.basename(path)))

    def _import_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入文风校对预设", "",
                                              "JSON 文件 (*.json);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", "读取预设文件失败：%s" % e)
            return
        # 兼容两种结构：本页导出的 {name, prompts} 包装 / 直接含 node_a~d 的 dict
        prompts, name = None, None
        if isinstance(data, dict):
            if isinstance(data.get("prompts"), dict) and data.get("name"):
                name = str(data["name"]).strip()
                prompts = data["prompts"]
            elif any(k in data for k in ("node_a", "node_b", "node_c", "node_d")):
                name = os.path.splitext(os.path.basename(path))[0].strip()
                prompts = data
        if not prompts or not name:
            QMessageBox.warning(self, "导入失败",
                                "预设文件格式不正确（应为 name + node_a~d 四节点提示词 JSON）。")
            return
        clean = {k: str(prompts.get(k, "") or "") for k in ("node_a", "node_b", "node_c", "node_d")}
        wf = style_extract.StyleExtractorWorkflow()
        wf.save_preset(name, clean)
        self._refresh_preset_combo(keep=name)
        self.preset_status.setText("✅ 预设「%s」已导入并保存！" % name)

    # ---------- 导出 ----------
    def _export_top3(self):
        if not self._top_prompts_text.strip():
            QMessageBox.warning(self, "无可导出", "还没有可导出的 Top 3 文风提示词。")
            return
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "output")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "文风Top3_%s.txt" % time.strftime("%Y%m%d_%H%M%S"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._top_prompts_text)
        QMessageBox.information(self, "导出成功", "已导出到：\n%s\n\n（完整内容不截断）" % path)
