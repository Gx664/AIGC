# -*- coding: utf-8 -*-
"""引擎管理：按「检查 / 修复 / 评测」三类展示全部引擎。

这一版把 9 个条目做成可浏览的清单：
* 左侧分类树 —— 检查引擎 / 修复引擎 / 评测基准；
* 右侧详情 —— 模型清单、体积、论文来源、说明、本地是否已下载；
* 底部动作 —— 下载模型、运行评测、添加/删除自定义引擎、检查更新。

「检查更新」会从远端清单拉新条目，所以以后发布新模型不需要重新打包。
"""
import json
import os

from core.i18n import tr
from core.settings import models_root
from ui.glass import fit_to_screen
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

_CAT_KEYS = {
    "detect": "cat_detect",
    "repair": "cat_repair",
    "benchmark": "cat_bench",
}

_MODEL_EXT = (".bin", ".safetensors", ".h5", ".msgpack", ".onnx")


def _pick_lang(zh, en):
    """按当前界面语言取文案（英文缺省时回落到中文）。"""
    from core import i18n

    if i18n.LANG == "en":
        return en or zh or ""
    return zh or en or ""


# 语言适配标注（2026-09-23 由 AUC / acc 实测得出，见 docs/FIXES.md §3.3）
#
# **本项目不是每个引擎都适合中英文**，实测结论：
#
#   simpleai        中文 AUC 0.9998            -> 只中文可用
#   zh_perplexity   中文 acc 0.6300 (FPR 4%)   -> 只中文可用（弱）
#   gltr            英文 0.9400 / 中文无阈值    -> 双语，英文好、中文不可交付
#   binoculars      英文 0.9250 / 中文 0.7250  -> 双语，英文好、中文弱
#   detectgpt       英文 0.7100 / 中文 0.2800  -> 双语，英文弱、中文反向
#   fastdetectgpt   **中英均未标定**           -> 无法下结论
#
# 两种标注各管一件事，**不要混用**：
#   _LANG_MARK   适用语言（只中文 / 只英文 / 双语）
#   _USABILITY   该语言下的可用性（仅在有实测数据时才给）
#
# ⚠️ 没有实测数据的引擎不得标可用性 —— 那会让用户以为有依据。
#    未标定时由 `engine_lang_mark()` 回落到单个符号 ❔。
#
# 判据取条目 tags 里的语言标记，故改 tags 即改界面显示。
_LANG_MARK = {"zh": "🌐 中文", "en": "🌐 英文"}

# 中文可用性标记。分档依据是**实测**，不是推测。
#
# 「中文极弱」与「中文弱」的区别：弱是"能用但差"（binoculars，最优阈值下
# 0.7250）；极弱是**实际上没法交付** —— gltr 的中文 AUC 看着有 0.7816，
# 但在查重工具真正关心的 FPR<=5% 约束下**中文不存在可行阈值**（英文有）。
_USABILITY_TAG = {
    "中文可用": "✅ 可用",
    "中文弱": "⚠️ 中文弱",
    "中文极弱": "⚠️ 中文勿用",
    "中文不可用": "❌ 中文勿用",
}

# 未标定：没有实测数据时用，明确告诉用户"这个结论还没有"。
# 与「中文不可用」不同 —— 后者是**测出来不可用**，前者是**还没测**。
_UNMEASURED_TAG = "未标定"
# 界面上**只显示这一个符号**，不带文字：列表列宽有限，文字会把引擎名挤掉；
# 含义由该行的**悬停提示**说明（i18n 的 mark_tip_unmeasured，鼠标移上去弹出）。
# **必须用 ❔ 而不是 ⚠️** —— ⚠️ 已被「有结论但弱」占用，两者语义恰相反：
# ⚠️ 是"测出来差"，❔ 是"还没测"。
_UNMEASURED_MARK = "❔"


def engine_lang_mark(engine):
    """返回语言与可用性标记（2026-09-23 起区分中/英两侧）。

    格式：``🌐 语言`` + 可用性后缀。
    例：``🌐 中文 / 英文 ⚠️ 中文弱``、``🌐 英文 ❌ 中文勿用``

    **未标定的引擎只回一个符号 ``❔``**（不带语言前缀，也不带文字）——
    没有实测数据时"适用哪门语言"同样未知，标语言反而是编造。
    含义由该行悬停提示说明（见 ``refresh()`` 里的 ``setToolTip``）。

    实测依据（docs/FIXES.md §3.3）：
        simpleai       中文 AUC 0.9998    ✅ 中文可交付
        zh_perplexity  中文 acc 0.6300    ⚠️ 中文弱
        gltr           中文无可行阈值     ⚠️ 中文勿用
        binoculars     中文 0.7250        ⚠️ 中文弱
        detectgpt      中文 AUC 0.2800    ❌ 中文反向
        fastdetectgpt  中英均未标定        ❔（不猜）

    注意 1：**语言无关的引擎返回空串**（修复 / 评测类 —— 规则降重、
    知网诊断、评测基准），它们不该显示语言前缀。

    注意 2：**英文侧目前只测了 acc/AUC，未做 FPR<=5% 复核**，
    所以英文不给可用性结论，只标「🌐 英文」。等英文侧也标定后再补。
    """
    tags = engine.get("tags") or []
    tagset = {str(t) for t in tags}
    has_zh = any("中文" in str(t) for t in tags)
    has_en = any("英文" in str(t) for t in tags)

    # 「未标定」比语言归属更重要：它表示**连适用哪门语言都还没测**。
    # 这种情况单独显示，不参与中/英前缀拼接 —— 只回一个符号。
    if _UNMEASURED_TAG in tagset:
        return _UNMEASURED_MARK

    # **语言无关**的引擎不标语言（修复 / 评测类：规则降重、知网诊断、
    # 评测基准）。它们的 tags 里既无「中文」也无「英文」，此前会落进
    # else 分支被误标成「🌐 英文」—— 那是凭空捏造的标注。
    # 修复 2026-09-23：这种情况返回空串，让调用方不显示语言前缀。
    if not has_zh and not has_en:
        return ""

    if has_zh and has_en:
        base = "%s / 英文" % _LANG_MARK["zh"]
    elif has_zh:
        base = _LANG_MARK["zh"]
    else:
        base = _LANG_MARK["en"]

    # 中文侧：只给有实测依据的结论
    if has_zh:
        for tag, mark in _USABILITY_TAG.items():
            if tag in tagset:
                return "%s %s" % (base, mark)
    return base


def engine_label(engine):
    mark = engine_lang_mark(engine)
    name = _pick_lang(engine.get("name"), engine.get("name_en")) or engine.get("id", "")
    if mark and mark not in name:
        return "%s %s" % (mark, name)
    return name


def model_state(base_dir, engine):
    """返回 builtin / ready / missing —— 供界面显示下载状态。"""
    if not engine.get("models"):
        return "builtin"
    d = os.path.join(models_root(base_dir), engine["id"])
    if os.path.isdir(d):
        for root, _dirs, files in os.walk(d):
            if any(f.endswith(_MODEL_EXT) for f in files):
                return "ready"
    return "missing"


class EngineDialog(QDialog):
    def __init__(self, mgr, base_dir, settings=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("engine_mgr_title"))
        fit_to_screen(self, 900, 620, min_w=680, min_h=460)
        self.mgr = mgr
        self.base_dir = base_dir
        self.settings = settings
        self._worker = None

        lay = QVBoxLayout(self)

        hint = QLabel(tr("engine_mgr_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#475569;font-size:12px;")
        lay.addWidget(hint)

        body = QHBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("engine_col_name"), tr("engine_col_status")])
        self.tree.setColumnWidth(0, 300)
        self.tree.setMinimumWidth(330)
        self.tree.currentItemChanged.connect(self._on_select)
        body.addWidget(self.tree, 2)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        body.addWidget(self.detail, 3)
        lay.addLayout(body, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        row = QHBoxLayout()
        self.btn_download = QPushButton(tr("engine_btn_download"))
        self.btn_bench = QPushButton(tr("engine_btn_bench"))
        self.btn_add = QPushButton(tr("btn_add_custom"))
        self.btn_del = QPushButton(tr("btn_del_custom"))
        self.btn_update = QPushButton(tr("engine_btn_check_update"))
        self.btn_close = QPushButton(tr("btn_close"))
        self.btn_download.clicked.connect(self.download_selected)
        self.btn_bench.clicked.connect(self.run_benchmark)
        self.btn_add.clicked.connect(self.add_custom)
        self.btn_del.clicked.connect(self.delete_selected)
        self.btn_update.clicked.connect(self.check_update)
        self.btn_close.clicked.connect(self.accept)
        for b in (self.btn_download, self.btn_bench, self.btn_add, self.btn_del):
            row.addWidget(b)
        row.addWidget(self.btn_update)
        row.addStretch()
        row.addWidget(self.btn_close)
        lay.addLayout(row)

        self.refresh()

    # ------------------------------------------------------------------ 列表
    def refresh(self):
        self.tree.clear()
        groups = {}
        for e in self.mgr.all():
            groups.setdefault(e.get("category", "detect"), []).append(e)
        for cat in ("detect", "repair", "benchmark"):
            items = groups.get(cat)
            if not items:
                continue
            head = QTreeWidgetItem([tr(_CAT_KEYS[cat]), "%d" % len(items)])
            head.setFlags(Qt.ItemIsEnabled)
            f = head.font(0)
            f.setBold(True)
            head.setFont(0, f)
            self.tree.addTopLevelItem(head)
            for e in items:
                state = model_state(self.base_dir, e)
                tag = tr("engine_status_" + state)
                if self.mgr.is_custom(e["id"]):
                    tag = "%s · %s" % (tag, tr("tag_custom"))
                child = QTreeWidgetItem([engine_label(e), tag])
                child.setData(0, Qt.UserRole, e["id"])
                # 未标定的引擎名字前只有一个 ❔，没有文字说明 —— 含义靠悬停提示补。
                # 只给这一种设提示：其余标记自带文字（"✅ 可用"、"⚠️ 中文弱"、
                # "❌ 中文勿用"），看一眼就懂，再加提示是冗余。
                if engine_lang_mark(e) == _UNMEASURED_MARK:
                    child.setToolTip(0, tr("mark_tip_unmeasured"))
                head.addChild(child)
            head.setExpanded(True)
        if self.tree.topLevelItemCount():
            first = self.tree.topLevelItem(0)
            if first.childCount():
                self.tree.setCurrentItem(first.child(0))

    def _current(self):
        item = self.tree.currentItem()
        if not item:
            return None
        eid = item.data(0, Qt.UserRole)
        return self.mgr.get(eid) if eid else None

    def _on_select(self, *_):
        e = self._current()
        if not e:
            return
        cat = e.get("category", "detect")
        self.btn_bench.setEnabled(cat == "benchmark")
        state = model_state(self.base_dir, e)
        self.btn_download.setEnabled(state == "missing")
        self.btn_del.setEnabled(self.mgr.is_custom(e["id"]))
        self.detail.setMarkdown(self._detail_md(e, state))

    def _detail_md(self, e, state):
        from core.engines import registered

        lines = ["### %s" % engine_label(e), ""]
        lines.append(
            "`%s` ｜ %s ｜ %s `%s`"
            % (
                e["id"],
                tr(_CAT_KEYS.get(e.get("category", "detect"), "cat_detect")),
                tr("engine_impl") + "：",
                e.get("impl", "-"),
            )
        )
        lines.append("")
        lines.append("**%s**：%s" % (tr("engine_state"), tr("engine_status_" + state)))
        if e.get("paper"):
            lines.append("")
            lines.append("**%s**：%s（%s）" % (tr("engine_paper"), e["paper"], e.get("venue", "")))
        if e.get("tags"):
            lines.append("")
            lines.append("**%s**：%s" % (tr("engine_tags"), " · ".join(e["tags"])))
        models = e.get("models") or []
        lines.append("")
        lines.append("**%s**" % tr("engine_models"))
        lines.append("")
        if models:
            lines.append("| %s | %s | %s |" % (tr("engine_col_repo"), tr("engine_col_size"), tr("engine_col_role")))
            lines.append("|---|---|---|")
            for m in models:
                if isinstance(m, dict):
                    lines.append(
                        "| `%s` | %s | %s |"
                        % (
                            m.get("repo", ""),
                            m.get("size", ""),
                            _pick_lang(m.get("role"), m.get("role_en")),
                        )
                    )
                else:
                    lines.append("| `%s` | | |" % m)
        else:
            lines.append(tr("engine_no_models"))
        desc = _pick_lang(e.get("desc"), e.get("desc_en"))
        if desc:
            lines.append("")
            lines.append("**%s**" % tr("engine_desc"))
            lines.append("")
            lines.append(desc)
        params = e.get("params") or {}
        if params:
            lines.append("")
            lines.append("**%s**: `%s`" % (tr("engine_params"), json.dumps(params, ensure_ascii=False)))
        lines.append("")
        lines.append("%s: %s" % (tr("engine_impls_loaded"), ", ".join(registered()) or "-"))
        if self.mgr.plugins_loaded:
            lines.append("")
            lines.append("%s: %s" % (tr("engine_plugins"), ", ".join(self.mgr.plugins_loaded)))
        return "\n".join(lines)

    # ------------------------------------------------------------------ 动作
    def _mirror_url(self):
        if not self.settings:
            return "https://hf-mirror.com"
        return self.settings.get("download", "hf_endpoint", default="https://hf-mirror.com")

    def download_selected(self):
        e = self._current()
        if not e:
            return
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, tr("notice"), tr("settings_download_busy"))
            return
        from ui.settings_dialog import DownloadWorker

        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.btn_download.setEnabled(False)
        self._worker = DownloadWorker(e, self.base_dir, self._mirror_url())
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_download_done)
        self._worker.start()

    def _on_progress(self, msg, pct):
        self.progress.setValue(pct)
        self.setWindowTitle("%s — %s" % (tr("engine_mgr_title"), msg))

    def _on_download_done(self, eid, ok, err):
        self.progress.setVisible(False)
        self.setWindowTitle(tr("engine_mgr_title"))
        if ok:
            QMessageBox.information(self, tr("notice"), tr("settings_download_ok") % eid)
        else:
            QMessageBox.warning(self, tr("notice"), tr("settings_download_fail") % err[:200])
        self.refresh()

    def run_benchmark(self):
        e = self._current()
        if not e or e.get("category") != "benchmark":
            return
        from ui.benchmark_dialog import BenchmarkDialog

        BenchmarkDialog(self.mgr, self.base_dir, self.settings, e["id"], self).exec()

    def check_update(self):
        cur = ""
        if self.settings:
            cur = self.settings.get("engines", "manifest_url", default="") or ""
        url, ok = QInputDialog.getText(
            self, tr("engine_btn_check_update"), tr("engine_update_prompt"), text=cur
        )
        if not ok:
            return
        url = (url or "").strip()
        if self.settings:
            self.settings.set(url, "engines", "manifest_url")
        if not url:
            return
        ok2, info = self.mgr.refresh_from_remote(url)
        if ok2:
            QMessageBox.information(self, tr("notice"), tr("engine_update_ok") % info)
            self.refresh()
        else:
            QMessageBox.warning(self, tr("notice"), tr("engine_update_fail") % info)

    def add_custom(self):
        from core.engines import registered

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("add_custom_title"))
        form = QFormLayout(dlg)
        eid = QLineEdit()
        name = QLineEdit()
        impl = QComboBox()
        impl.setEditable(True)
        impl.addItems(registered())
        cat = QComboBox()
        cat.addItems(["detect", "repair", "benchmark"])
        model = QLineEdit()
        params = QPlainTextEdit()
        params.setPlaceholderText(tr("params_placeholder"))
        form.addRow(tr("field_id"), eid)
        form.addRow(tr("field_name"), name)
        form.addRow(tr("field_impl"), impl)
        form.addRow(tr("field_category"), cat)
        form.addRow(tr("field_model"), model)
        form.addRow(tr("field_params"), params)
        btn = QPushButton(tr("btn_ok"))
        form.addRow(btn)

        def ok():
            if not eid.text().strip() or not impl.currentText().strip():
                QMessageBox.warning(dlg, tr("notice"), tr("err_id_impl"))
                return
            try:
                p = json.loads(params.toPlainText() or "{}")
            except Exception:  # noqa: BLE001
                QMessageBox.warning(dlg, tr("notice"), tr("err_json"))
                return
            mid = model.text().strip()
            self.mgr.add_custom(
                {
                    "id": eid.text().strip(),
                    "name": name.text().strip() or eid.text().strip(),
                    "impl": impl.currentText().strip(),
                    "category": cat.currentText(),
                    "model_id": mid,
                    "models": [{"repo": mid, "size": "", "role": mid}] if mid else [],
                    "size_hint": tr("tag_custom"),
                    "desc": tr("custom_desc"),
                    "params": p,
                    "update_channel": "models",
                }
            )
            dlg.accept()
            self.refresh()

        btn.clicked.connect(ok)
        dlg.exec()

    def delete_selected(self):
        e = self._current()
        if not e:
            return
        if not self.mgr.is_custom(e["id"]):
            QMessageBox.information(self, tr("notice"), tr("builtin_no_del"))
            return
        self.mgr.remove(e["id"])
        self.refresh()
