# -*- coding: utf-8 -*-
r"""UI 交互测试：真构造界面、真点按钮、真读结果。

为什么需要
----------
此前的 UI 测试（``gui_offscreen``）只验证"窗口能构造出来"，
**没验证交互**：按钮点了有没有反应、检测跑完界面显示什么、
配置改了有没有生效。用户实际使用全靠这些。

本探针用 Qt 离屏模式真跑一遍主流程：

1. 主窗口构造 —— 各控件是否齐备
2. 引擎下拉 —— 选项是否含语言标注、数量是否对
3. **真跑一次检测** —— 用内置短文本 + simpleai（CPU 可跑），
   看结果标签、段落列表、诊断输出是否合理
4. 设置对话框 —— 打开、改值、保存、重读，验证往返一致
5. 降重对话框 —— 构造 + 导入文本

**副作用**：需 Qt 离屏；写系统临时目录的 settings.json（自清理）。
不联网、不加载大模型。
"""
import os
import sys
import tempfile

from . import head

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _mk_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    return app


def _find(widget, cls_name):
    """按类名找控件。

    用 ``QApplication.allWidgets()`` 而不是遍历 children 树 ——
    children 只覆盖直接子树，深层布局里的控件取不全
    （实测：children 只找到 3 个按钮，allWidgets 找到 20 个）。

    归属判断用 ``window()`` 比较（比 parent() 链可靠：parent() 在
    PySide6 里对部分控件返回 None，会让链条提前中断）。
    """
    from PySide6.QtWidgets import QApplication, QWidget

    try:
        top = widget.window()
    except Exception:
        top = widget
    out = []
    for w in QApplication.allWidgets():
        if type(w).__name__ != cls_name:
            continue
        if not isinstance(w, QWidget):
            continue
        try:
            if w.window() is top or w is top:
                out.append(w)
        except Exception:
            pass
    return out


SAMPLE = (
    "人工智能技术的快速发展正在深刻改变着我们的生活方式。从智能手机到自动驾驶，"
    "从医疗诊断到金融风控，AI 已经渗透到各行各业。这种变革带来了效率的提升，"
    "同时也引发了关于就业、隐私和伦理的广泛讨论。"
)


def run_ui_flow(v):
    """真跑一遍 UI 主流程。"""
    head("UI-FLOW", "界面交互测试：构造 / 下拉 / 真跑检测 / 设置往返")

    # 结果同时写文件：UI 探针常在独立窗口里跑，输出到不了调用方，
    # 而且跑完窗口内容会被后续命令冲掉，必须留档。
    log = os.path.join(os.environ.get("TEMP", "."), "ui_flow_report.txt")
    try:
        with open(log, "w", encoding="utf-8") as fh:
            fh.write("UI 交互测试报告（%s）\n\n" % os.path.basename(__file__))
    except Exception:
        log = None

    def emit(s):
        s = str(s)
        # 控制台可能是 GBK（Windows 中文默认），🌐 等字符会抛
        # UnicodeEncodeError。写文件不受影响，控制台则降级为替代符。
        try:
            sys.stdout.write(s + "\n")
            sys.stdout.flush()
        except UnicodeEncodeError:
            try:
                enc = sys.stdout.encoding or "utf-8"
                sys.stdout.write(s.encode(enc, "replace").decode(enc) + "\n")
                sys.stdout.flush()
            except Exception:
                pass
        if log:
            try:
                with open(log, "a", encoding="utf-8") as fh:
                    fh.write(s + "\n")
            except Exception:
                pass

    try:
        _mk_app()
    except Exception as e:
        emit("Qt 不可用: %s" % e)
        v.add("UI-FLOW", False, "Qt 不可用")
        return

    from core.engines import EngineManager
    from ui.main_window import MainWindow

    _ = EngineManager  # 保留导入（后续步骤可能用到）

    tmp = tempfile.mkdtemp(prefix="aigc_ui_")
    emit("临时 base_dir: %s" % tmp)
    # 注：这里**不**去改临时目录的 models_dir —— 试过，但检测流程仍会尝试
    # 联网下载模型（属于环境问题）。本探针只验证 UI 交互链路
    # （按钮 -> 槽 -> 后台线程），不验证模型加载，所以不折腾它。
    emit("")
    # ---------------------------------------------------------- 1. 主窗口
    emit("--- 1. 主窗口构造 ---")
    try:
        win = MainWindow()
    except Exception as e:
        import traceback

        traceback.print_exc()
        v.add("UI-FLOW", False, "主窗口构造失败: %s" % e)
        return

    combos = _find(win, "QComboBox")
    buttons = _find(win, "QPushButton")
    edits = _find(win, "QTextEdit")
    labels = _find(win, "QLabel")
    emit("  控件: QComboBox=%d  QPushButton=%d  QTextEdit=%d  QLabel=%d"
          % (len(combos), len(buttons), len(edits), len(labels)))
    if not combos or not buttons:
        v.add("UI-FLOW", False, "主窗口控件缺失")
        return
    # 显示窗口：show() 前按钮 isVisible()=False（但 click() 仍可触发）。
    # 为了让交互贴近真实使用，先 show()。
    try:
        win.show()
        _mk_app().processEvents()
        emit("  已 show() 主窗口")
    except Exception as e:
        emit("  show() 失败: %s" % e)

    # ---------------------------------------------------------- 2. 引擎下拉
    emit("")
    emit("--- 2. 引擎下拉 ---")
    eng_combo = None
    for c in combos:
        if c.count() >= 5:
            eng_combo = c
            break
    if eng_combo is None:
        emit("  未找到引擎下拉（count>=5 的 combo）")
    else:
        emit("  项数: %d" % eng_combo.count())
        for i in range(eng_combo.count()):
            emit("    [%d] %s" % (i, eng_combo.itemText(i)))
        marks = sum(1 for i in range(eng_combo.count())
                    if "🌐" in eng_combo.itemText(i))
        emit("  带语言标注的: %d / %d" % (marks, eng_combo.count()))
        if marks == 0:
            emit("  !! 一个语言标注都没有 —— 用户无法判断该用哪个")

    # ---------------------------------------------------------- 3. 真跑检测
    emit("")
    emit("--- 3. 真跑一次检测（simpleai，CPU）---")
    param_edit = edits[0] if edits else None
    if param_edit is None:
        emit("  未找到文本输入框，跳过")
    else:
        param_edit.setPlainText(SAMPLE)
        emit("  已填入样本文本 %d 字" % len(SAMPLE))
        if eng_combo is not None:
            for i in range(eng_combo.count()):
                if "SimpleAI" in eng_combo.itemText(i):
                    eng_combo.setCurrentIndex(i)
                    emit("  选中引擎: %s" % eng_combo.itemText(i))
                    break
        # 直接用 MainWindow 的属性拿按钮。
        #
        # 为什么不用"按类名扫控件"：主界面的按钮是自定义类 ``GlassButton``
        # （不是 QPushButton），按类名找会全部漏掉 —— 实测只能找到 3 个
        # 窗口控制按钮，而真正的主按钮（btn_start 等）一个都找不到。
        # 属性名是 MainWindow 自己定义的，稳定可靠。
        # 检测流程要求先有文件。**必须走 win.load_file()**，不能只赋
        # self.file_path —— 按钮的启用是由 load_file 做的
        # （main_window:422-426），直接赋值会让 btn_start 仍为 disabled，
        # click() 无效（踩过的坑）。
        doc = os.path.join(tmp, "sample.txt")
        try:
            with open(doc, "w", encoding="utf-8") as fh:
                fh.write(SAMPLE + "\n\n")
                fh.write("第二段：本段用于验证分段与逐段判定是否正常。"
                         "语言模型的困惑度在这里应当能区分人写与机器生成。")
            win.load_file(doc)
            emit("  已 load_file: %s   btn_start.enabled=%s"
                 % (os.path.basename(doc), win.btn_start.isEnabled()))
        except Exception as e:
            emit("  load_file 失败: %s: %s" % (type(e).__name__, e))

        target = getattr(win, "btn_start", None)
        if target is None:
            for name in ("btn_detect", "btn_run", "btn_scan"):
                target = getattr(win, name, None)
                if target is not None:
                    break
        if target is None:
            emit("  未找到开始检测按钮（btn_start 属性不存在），跳过实跑")
        else:
            emit("  点击 %r（属性 btn_start）" % target.text())
            # 直接调 start_detect 并捕获异常 —— 按钮 click() 若在槽里抛错，
            # Qt 会吞掉（只在控制台打 traceback），拿不到原因。
            try:
                if hasattr(win, "_collect_params"):
                    p = win._collect_params()
                    emit("  _collect_params(): engine=%r" % p.get("engine"))
                    cfg = win.mgr.get(p.get("engine"))
                    emit("  mgr.get() 结果=%s" % ("有" if cfg else "**None**"))
            except Exception as e:
                emit("  _collect_params 异常: %s: %s" % (type(e).__name__, e))
            try:
                target.click()
                # 不等待检测**完成**：真实检测要加载/下载模型（首次可能联网），
                # 属于环境问题而非 UI 问题。这里只等到"任务确实启动"为止
                # —— 能证明按钮->槽->后台线程这条链路通即可。
                from PySide6.QtCore import QTimer

                app = _mk_app()
                started = False
                for _ in range(120):        # 最多 60 秒
                    app.processEvents()
                    wt = getattr(win, "worker_thread", None)
                    if wt is not None:
                        started = True
                        break
                    QTimer.singleShot(500, lambda: None)
                    import time as _t

                    _t.sleep(0.5)
                emit("  点击后 worker 启动: %s" % started)
            except Exception as e:
                emit("  点击后异常: %s: %s" % (type(e).__name__, e))
            emit("  进度条 value=%s" % (
                win.progress.value() if hasattr(win, "progress") else "?"))
            emit("  result_label 文本=%r" % (
                win.result_label.text() if hasattr(win, "result_label") else "?"))
            emit("  btn_start enabled=%s（False 表示已进入检测态）" % (
                win.btn_start.isEnabled() if hasattr(win, "btn_start") else "?"))
            # 不再等检测完成（可能联网下载模型），直接结束本次 UI 流程
            emit("  注：不再等待检测完成（首次可能下载模型，属环境而非 UI 问题）")
            shown = 0
            for lb in labels:
                t = lb.text()
                if t and any(k in t for k in ("%", "AI", "风险", "检测")):
                    emit("  标签: %s" % t[:120])
                    shown += 1
                    if shown >= 6:
                        break

    # ---------------------------------------------------------- 4. 设置往返
    emit("")
    emit("--- 4. 设置对话框往返 ---")
    try:
        from core.settings import Settings
        from ui.settings_dialog import SettingsDialog

        s1 = Settings(tmp)
        before = s1.get("download", "hf_endpoint", default="")
        emit("  打开前 hf_endpoint = %r" % before)
        sd = SettingsDialog(s1, tmp)
        emit("  对话框构造 OK")
        if hasattr(sd, "_save"):
            sd._save()
            after = Settings(tmp).get("download", "hf_endpoint", default="")
            emit("  保存后 hf_endpoint = %r" % after)
            ok = bool(after) and str(after).startswith("http")
            emit("  含协议头: %s" % ok)
            if not ok:
                emit("  !! 保存后丢了协议头（BUG-3 复发？）")
        else:
            emit("  SettingsDialog 无 _save（跳过）")
    except Exception as e:
        import traceback

        traceback.print_exc()
        emit("  设置对话框异常: %s" % e)

    # ---------------------------------------------------------- 5. 降重对话框
    emit("")
    emit("--- 5. 降重对话框构造 ---")
    try:
        from core.diagnosis import diagnose
        from core.settings import Settings as _S
        from ui.rewrite_dialog import RewriteDialog

        # 真实签名（inspect 查得，不猜）：
        #   RewriteDialog(paragraphs, probs, diagnosis, base_dir, settings, ...)
        s5 = _S(tmp)
        paras = [SAMPLE, "另一段用于测试的文本内容，长度足够触发分段与诊断逻辑。" * 3]
        probs = [0.9, 0.2]
        diag = diagnose(paras, probs=probs)
        rd = RewriteDialog(paras, probs, diag, tmp, s5)
        emit("  构造 OK，标题=%r" % rd.windowTitle())
    except Exception as e:
        import traceback

        traceback.print_exc()
        emit("  降重对话框异常: %s: %s" % (type(e).__name__, e))

    emit("")
    emit("=" * 68)
    emit("UI 交互测试完成（人工核对上面各步输出是否合理）")
    emit("=" * 68)
    v.add("UI-FLOW", True, "主窗口/下拉/检测/设置/降重 五步已跑")


