# -*- coding: utf-8 -*-
"""降重对话框：检测 → 诊断 → 治疗 闭环的界面。

左侧段落清单（勾选要处理的段落），右侧诊断报告 / 治疗前后对比，
底部可调改写参数（可随预设存档），支持导出诊断 JSON 与降重后 TXT。
"""

import json
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.diagnosis import diagnose, pattern_name, risk_label
from core.detector import detect_local
from core.engines import create_engine
from core.i18n import get_lang, tr
from core.therapy import export_text, treat
from ui.glass import GlassButton, GlassPanel, fit_to_screen


class RewriteWorker(QThread):
    step = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, paragraphs, indices, options):
        super().__init__()
        self.paragraphs = paragraphs
        self.indices = indices
        self.options = options

    def run(self):
        try:
            result = treat(self.paragraphs, self.indices, self.options)
            self.done.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class AutoWorker(QThread):
    """自动降重闭环：规则改写 → 本地模型复检 AI 率 → 仍超标就对高危段落再改。

    循环直到 AI 率达标（≤ 目标值）或达到最大轮数，防止无限循环。
    """

    round_info = Signal(int, float, int, int)  # 轮次, 该轮 AI 率, 改写段数, 总轮数
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, paragraphs, indices, options, engine_cfg, base_dir,
                 detect_params, target_ai, max_rounds, detect_threshold=0.5):
        super().__init__()
        self.paragraphs = paragraphs
        self.indices = indices
        self.options = options
        self.engine_cfg = engine_cfg
        self.base_dir = base_dir
        self.detect_params = detect_params
        self.target_ai = target_ai
        self.max_rounds = max_rounds
        self.detect_threshold = detect_threshold

    def _recheck(self, paras):
        cfg = self.engine_cfg
        engine = create_engine(cfg, self.base_dir)
        engine.install(None)  # 已装好的模型这里直接通过
        run_params = dict(self.detect_params)
        run_params.update(cfg.get("params", {}))
        return detect_local(cfg, self.base_dir, paras, run_params)

    def run(self):
        try:
            paras = list(self.paragraphs)
            cur = list(self.indices)
            history = []
            last_probs = None
            last_treat = None
            for rnd in range(1, self.max_rounds + 1):
                if not cur:
                    break
                last_treat = treat(paras, cur, self.options)
                for r in last_treat["paragraphs"]:
                    if r["changed"]:
                        paras[r["index"] - 1] = r["revised"]
                last_probs = self._recheck(paras)
                valid = [p for p in last_probs if p is not None]
                ratio = sum(valid) / len(valid) if valid else 0.0
                history.append({
                    "round": rnd,
                    "ai_ratio": ratio,
                    "rewritten": last_treat["summary"]["rewritten"],
                    "selected": len(cur),
                })
                self.round_info.emit(
                    rnd, ratio, last_treat["summary"]["rewritten"], self.max_rounds
                )
                if ratio <= self.target_ai:
                    break
                # 下一轮只处理仍高于目标线的段落
                cur = [
                    i + 1 for i, p in enumerate(last_probs)
                    if p is not None and p > self.target_ai
                ]
            diag = diagnose(paras, last_probs, self.detect_threshold)
            self.done.emit({
                "paragraphs": paras,
                "probs": last_probs,
                "ai_ratio": history[-1]["ai_ratio"] if history else 0.0,
                "history": history,
                "diag": diag,
                "treat": last_treat,
            })
        except Exception as e:
            self.failed.emit(str(e))


class RewriteDialog(QDialog):
    def __init__(self, paragraphs, probs, diagnosis, base_dir, settings,
                 parent=None, engine_cfg=None, detect_params=None,
                 detect_threshold=0.5):
        super().__init__(parent)
        self.setWindowTitle(tr("rewrite_title"))
        fit_to_screen(self, 1180, 760, min_w=820, min_h=560)
        self.paragraphs = paragraphs
        self.probs = probs or []
        self.diag = diagnosis
        self.base_dir = base_dir
        self.settings = settings
        self.engine_cfg = engine_cfg
        self.detect_params = detect_params or {}
        self.detect_threshold = detect_threshold
        self.last_result = None
        self.worker = None
        self._build_ui()
        self._fill_list()

    # ── 界面 ──
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        s = self.diag.get("summary", {})
        self.summary_label = QLabel(
            tr("rewrite_summary")
            % (
                risk_label(s.get("overall_risk", "low"), get_lang()),
                s.get("high_risk_paras", 0),
                s.get("medium_risk_paras", 0),
                s.get("total_paragraphs", 0),
            )
        )
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size:14px;font-weight:600;color:#1d4ed8;")
        root.addWidget(self.summary_label)

        if s.get("style_warnings"):
            warn = QLabel(tr("rewrite_style_warn") % "；".join(s["style_warnings"][:5]))
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#b45309;font-size:13px;")
            root.addWidget(warn)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setSizes([330, 830])
        root.addWidget(splitter, 1)

        root.addWidget(self._build_bottom())

    def _build_left(self):
        panel = GlassPanel()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 12, 12, 12)
        head = QLabel(tr("rewrite_para_list"))
        head.setStyleSheet("font-weight:700;color:#1e293b;")
        lay.addWidget(head)
        self.para_list = QListWidget()
        self.para_list.currentItemChanged.connect(self.on_select_para)
        lay.addWidget(self.para_list, 1)
        return panel

    def _build_right(self):
        panel = GlassPanel()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 12, 12, 12)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_diag_tab(), tr("rewrite_tab_diag"))
        self.tabs.addTab(self._build_treat_tab(), tr("rewrite_tab_treat"))
        lay.addWidget(self.tabs, 1)
        return panel

    def _build_diag_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        self.diag_text = QTextEdit()
        self.diag_text.setReadOnly(True)
        self.diag_text.setStyleSheet(
            "QTextEdit{background:rgba(255,255,255,200);border:none;border-radius:10px;"
            "font-size:13px;line-height:150%;}"
        )
        lay.addWidget(self.diag_text, 1)
        return w

    def _build_treat_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        mid = QSplitter(Qt.Horizontal)
        self.orig_text = QTextEdit()
        self.orig_text.setReadOnly(True)
        self.rev_text = QTextEdit()
        self.rev_text.setReadOnly(True)
        for t in (self.orig_text, self.rev_text):
            t.setStyleSheet(
                "QTextEdit{background:rgba(255,255,255,200);border:none;border-radius:10px;"
                "font-size:13px;line-height:150%;}"
            )
        o_head = QLabel(tr("rewrite_original"))
        r_head = QLabel(tr("rewrite_revised"))
        for h in (o_head, r_head):
            h.setStyleSheet("font-weight:700;color:#334155;")
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(o_head)
        ll.addWidget(self.orig_text, 1)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(r_head)
        rl.addWidget(self.rev_text, 1)
        mid.addWidget(left)
        mid.addWidget(right)
        mid.setSizes([540, 540])
        lay.addWidget(mid, 1)
        self.change_text = QTextEdit()
        self.change_text.setReadOnly(True)
        self.change_text.setMaximumHeight(150)
        self.change_text.setStyleSheet(
            "QTextEdit{background:rgba(255,255,255,180);border:none;border-radius:10px;"
            "font-size:12px;color:#475569;}"
        )
        lay.addWidget(self.change_text)
        return w

    def _build_bottom(self):
        panel = GlassPanel()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 10, 12, 10)

        # 自动降重闭环：改写 → 复检 → 循环到达标
        auto_row = QHBoxLayout()
        auto_row.addWidget(QLabel(tr("rewrite_auto_target")))
        self.auto_target = QSpinBox()
        self.auto_target.setRange(5, 60)
        self.auto_target.setSuffix("%")
        self.auto_target.setValue(int(
            self.settings.get("rewrite", "auto_target_ai", default=0.25) * 100
        ))
        self.auto_target.setToolTip(tr("rewrite_auto_hint"))
        auto_row.addWidget(self.auto_target)
        auto_row.addWidget(QLabel(tr("rewrite_auto_rounds")))
        self.auto_rounds = QSpinBox()
        self.auto_rounds.setRange(1, 5)
        self.auto_rounds.setValue(int(
            self.settings.get("rewrite", "max_rounds", default=3)
        ))
        auto_row.addWidget(self.auto_rounds)
        self.btn_auto = GlassButton(tr("rewrite_auto_btn"))
        self.btn_auto.clicked.connect(self.run_auto)
        auto_row.addStretch()
        auto_row.addWidget(self.btn_auto)
        lay.addLayout(auto_row)

        opt_row = QHBoxLayout()
        self.chk_word = QCheckBox(tr("rewrite_opt_word"))
        self.chk_sentence = QCheckBox(tr("rewrite_opt_sentence"))
        self.chk_parallel = QCheckBox(tr("rewrite_opt_parallel"))
        self.chk_dash = QCheckBox(tr("rewrite_opt_dash"))
        self.chk_split = QCheckBox(tr("rewrite_opt_split"))
        self.chk_style = QCheckBox(tr("rewrite_opt_style"))
        for c in (self.chk_word, self.chk_sentence, self.chk_parallel,
                  self.chk_dash, self.chk_split, self.chk_style):
            opt_row.addWidget(c)
        self._apply_options_from_settings()
        opt_row.addStretch()
        opt_row.addWidget(QLabel(tr("rewrite_target")))
        self.target_ratio = QSpinBox()
        self.target_ratio.setRange(10, 80)
        self.target_ratio.setSuffix("%")
        self.target_ratio.setValue(int(
            self.settings.get("rewrite", "target_ratio", default=0.40) * 100
        ))
        self.target_ratio.setToolTip(
            tr("rewrite_target_hint")
        )
        opt_row.addWidget(self.target_ratio)
        lay.addLayout(opt_row)

        btn_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        btn_row.addWidget(self.progress, 1)

        self.btn_treat = GlassButton(tr("rewrite_btn_run"), primary=True)
        self.btn_treat.clicked.connect(self.run_treat)
        self.btn_export_json = GlassButton(tr("rewrite_btn_json"))
        self.btn_export_json.clicked.connect(self.export_json)
        self.btn_export_txt = GlassButton(tr("rewrite_btn_txt"))
        self.btn_export_txt.clicked.connect(self.export_txt)
        self.btn_close = GlassButton(tr("btn_close"))
        self.btn_close.clicked.connect(self.accept)
        for b in (self.btn_treat, self.btn_export_json, self.btn_export_txt, self.btn_close):
            btn_row.addWidget(b)
        lay.addLayout(btn_row)
        return panel

    # ── 数据 ──
    def _fill_list(self):
        self.para_list.clear()
        for p in self.diag.get("paragraphs", []):
            idx = p["index"]
            level = p["risk_level"]
            prob = p.get("ai_prob")
            prob_s = "AI %d%%" % (prob * 100) if prob is not None else tr("rewrite_no_prob")
            snippet = p["text"][:28].replace("\n", " ")
            item = QListWidgetItem(
                tr("rewrite_item") % (idx, risk_label(level, get_lang()), prob_s, snippet)
            )
            item.setData(Qt.UserRole, idx)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if level in ("high", "medium") else Qt.Unchecked)
            if level == "high":
                item.setForeground(Qt.darkRed)
            elif level == "medium":
                item.setForeground(Qt.darkYellow)
            self.para_list.addItem(item)
        if self.para_list.count():
            self.para_list.setCurrentRow(0)

    def _apply_options_from_settings(self):
        r = self.settings.get("rewrite", default={})
        self.chk_word.setChecked(r.get("word_level", True))
        self.chk_sentence.setChecked(r.get("sentence_level", True))
        self.chk_parallel.setChecked(r.get("parallel", True))
        self.chk_dash.setChecked(r.get("dash_fix", True))
        self.chk_split.setChecked(r.get("split_long", True))
        self.chk_style.setChecked(r.get("style_guard", True))

    def _collect_options(self):
        return {
            "word_level": self.chk_word.isChecked(),
            "sentence_level": self.chk_sentence.isChecked(),
            "parallel": self.chk_parallel.isChecked(),
            "dash_fix": self.chk_dash.isChecked(),
            "split_long": self.chk_split.isChecked(),
            "style_guard": self.chk_style.isChecked(),
            "target_ratio": self.target_ratio.value() / 100.0,
        }

    def _selected_indices(self):
        out = []
        for i in range(self.para_list.count()):
            item = self.para_list.item(i)
            if item.checkState() == Qt.Checked:
                out.append(item.data(Qt.UserRole))
        return out

    # ── 事件 ──
    def on_select_para(self, cur, prev):
        if cur is None:
            return
        idx = cur.data(Qt.UserRole)
        p = next((x for x in self.diag.get("paragraphs", []) if x["index"] == idx), None)
        if not p:
            return
        lines = []
        lines.append(tr("rewrite_para_head") % (idx, risk_label(p["risk_level"], get_lang()), p["risk_score"]))
        lines.append("")
        lines.append(tr("rewrite_diag_text") % p["text"])
        lines.append("")
        if p["patterns"]:
            lines.append(tr("rewrite_diag_patterns"))
            for pat in p["patterns"]:
                name = pat["zh"] if get_lang() == "zh" else pat["en"]
                lines.append("• %s（%s）" % (name, tr("rewrite_sev_" + pat["severity"])))
                for ev in pat["evidence"]:
                    lines.append("    - %s" % ev)
        if p["suggested_actions"]:
            lines.append("")
            lines.append(tr("rewrite_diag_actions"))
            for a in p["suggested_actions"]:
                lines.append("• %s" % (a["zh"] if get_lang() == "zh" else a["en"]))
        self.diag_text.setPlainText("\n".join(lines))

    def run_treat(self):
        indices = self._selected_indices()
        if not indices:
            QMessageBox.information(self, tr("notice"), tr("rewrite_none_selected"))
            return
        options = self._collect_options()
        for k, v in options.items():
            self.settings.set(v, "rewrite", k)
        self.settings.save()
        self.btn_treat.setEnabled(False)
        self.progress.setValue(0)
        self.worker = RewriteWorker(self.paragraphs, indices, options)
        self.worker.done.connect(self.on_treat_done)
        self.worker.failed.connect(self.on_treat_failed)
        self.worker.start()

    def on_treat_done(self, result):
        self.last_result = result
        self.btn_treat.setEnabled(True)
        self.progress.setValue(100)
        # 展示第一个被改的段落
        target = next((r for r in result["paragraphs"] if r["changed"]), None)
        if target:
            self._show_para_result(target)
        s = result["summary"]
        msg = tr("rewrite_done_box") % (s["rewritten"], s["selected"], s["avg_mod_ratio"] * 100)
        if s["style_warnings"]:
            msg += "\n\n" + tr("rewrite_style_warn") % "；".join(s["style_warnings"][:5])
        QMessageBox.information(self, tr("rewrite_done_title"), msg)

    def on_treat_failed(self, msg):
        self.btn_treat.setEnabled(True)
        QMessageBox.warning(self, tr("rewrite_fail_title"), msg)

    # ---- 自动降重闭环 ----
    def run_auto(self):
        indices = self._selected_indices()
        if not indices:
            QMessageBox.information(self, tr("notice"), tr("rewrite_none_selected"))
            return
        if not self.engine_cfg:
            QMessageBox.warning(self, tr("rewrite_fail_title"), tr("rewrite_auto_no_engine"))
            return
        options = self._collect_options()
        for k, v in options.items():
            self.settings.set(v, "rewrite", k)
        target_ai = self.auto_target.value() / 100.0
        max_rounds = self.auto_rounds.value()
        self.settings.set(target_ai, "rewrite", "auto_target_ai")
        self.settings.set(max_rounds, "rewrite", "max_rounds")
        self.settings.save()
        self.btn_treat.setEnabled(False)
        self.btn_auto.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.change_text.setPlainText("")
        self.tabs.setCurrentIndex(1)
        self.auto_worker = AutoWorker(
            self.paragraphs,
            indices,
            options,
            self.engine_cfg,
            self.base_dir,
            self.detect_params,
            target_ai,
            max_rounds,
            self.detect_threshold,
        )
        self.auto_worker.round_info.connect(self.on_auto_round)
        self.auto_worker.done.connect(self.on_auto_done)
        self.auto_worker.failed.connect(self.on_auto_failed)
        self.auto_worker.start()

    def on_auto_round(self, rnd, ratio, rewritten, max_rounds):
        self.progress.setValue(min(int(rnd * 100.0 / max_rounds), 99))
        cur = self.change_text.toPlainText()
        line = tr("rewrite_auto_round_log") % (rnd, rewritten, ratio * 100)
        self.change_text.setPlainText((cur + "\n" if cur else "") + line)

    def on_auto_done(self, result):
        self.btn_treat.setEnabled(True)
        self.btn_auto.setEnabled(True)
        self.progress.setValue(100)
        # 用最终结果刷新界面数据
        self.paragraphs = result["paragraphs"]
        self.probs = result["probs"] or []
        self.diag = result["diag"]
        self.last_result = result["treat"]
        self._refresh_summary()
        self._fill_list()
        target = next((r for r in (self.last_result or {}).get("paragraphs", []) if r["changed"]), None)
        if target:
            self._show_para_result(target)
        # 汇总报告
        hist_lines = []
        for h in result["history"]:
            hist_lines.append(
                tr("rewrite_auto_round_log") % (h["round"], h["rewritten"], h["ai_ratio"] * 100)
            )
        verdict = (
            tr("rewrite_auto_reached")
            if result["ai_ratio"] <= self.auto_target.value() / 100.0
            else tr("rewrite_auto_not_reached")
        )
        msg = "%s\n\n%s\n\n%s %.1f%%" % (
            tr("rewrite_auto_done_rounds") % len(result["history"]),
            "\n".join(hist_lines),
            tr("rewrite_auto_final_ratio"),
            result["ai_ratio"] * 100,
        )
        if verdict:
            msg += "\n" + verdict
        QMessageBox.information(self, tr("rewrite_auto_done_title"), msg)

    def on_auto_failed(self, msg):
        self.btn_treat.setEnabled(True)
        self.btn_auto.setEnabled(True)
        QMessageBox.warning(self, tr("rewrite_fail_title"), msg)

    def _refresh_summary(self):
        s = self.diag.get("summary", {})
        self.summary_label.setText(
            tr("rewrite_summary")
            % (
                risk_label(s.get("overall_risk", "low"), get_lang()),
                s.get("high_risk_paras", 0),
                s.get("medium_risk_paras", 0),
                s.get("total_paragraphs", 0),
            )
        )

    def _show_para_result(self, r):
        self.orig_text.setPlainText(r["original"])
        self.rev_text.setPlainText(r["revised"])
        lines = [tr("rewrite_ratio") % (r["index"], r["mod_ratio"] * 100)]
        for c in r["changes"]:
            lines.append("[%s] %s → %s" % (c["level"], c["from"], c["to"]))
        if r["remaining"]:
            lines.append("")
            lines.append(tr("rewrite_remaining") % "；".join(r["remaining"]))
        for n in r["notes"]:
            lines.append("")
            lines.append("⚠ " + n)
        self.change_text.setPlainText("\n".join(lines))
        self.tabs.setCurrentIndex(1)

    def export_json(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("rewrite_export_json"), "diagnosis.json", "JSON (*.json)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.diag, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, tr("rewrite_export_ok"), path)

    def export_txt(self):
        if not self.last_result:
            QMessageBox.information(self, tr("notice"), tr("rewrite_run_first"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("rewrite_export_txt"), "rewritten.txt", "TXT (*.txt)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(export_text(self.last_result))
        QMessageBox.information(self, tr("rewrite_export_ok"), path)

    def closeEvent(self, e):
        for w in (self.worker, getattr(self, "auto_worker", None)):
            if w and w.isRunning():
                w.wait(3000)
        e.accept()
