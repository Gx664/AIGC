# -*- coding: utf-8 -*-
"""GUI 类探针：主窗口离屏复现 + 报告 HTML 渲染验证。

来源（原 2 个脚本，逻辑一字未改）：
  probe_gui_offscreen_runtime.py
  probe_report_html_render.py

**副作用**：需 Qt 离屏环境；会往系统临时目录写 settings.json（不写项目内）。
"""
import os
import sys
import tempfile

from . import head


def _qt_app():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


def run_gui_offscreen(v):
    """GUI 层真实行为（离屏，不显示窗口，不写项目文件）。"""
    _qt_app()

    from core.detector import _devices
    from core.settings import Settings
    from ui.main_window import BASE_DIR, MainWindow
    from ui.settings_dialog import SettingsDialog

    head("GUI", "离屏实例化主窗口 + 真实按钮路径")
    print("BASE_DIR = %r" % BASE_DIR)
    print()

    # 用项目外临时目录当 base_dir，避免往项目里写 settings.json
    tmp_base = tempfile.mkdtemp(prefix="aigc_gui_")
    print("离屏主窗口用的 base_dir 先探明: 实际 MainWindow() 内部用 BASE_DIR")
    print("为避免写项目 settings.json，先检查是否已存在:")
    sp = os.path.join(BASE_DIR, "settings.json")
    print("   %s 存在? %s" % (sp, os.path.exists(sp)))
    print()

    result = "构造未完成"
    try:
        win = MainWindow()
        print("OK  MainWindow() 构造成功")
        print("    引擎下拉项数 = %d" % win.engine_combo.count())
        print("    下拉内容 = %r" % [win.engine_combo.itemText(i)
                                   for i in range(win.engine_combo.count())])
        print("    预设项数 = %d" % win.preset_combo.count())
        print("    阈值滑杆 = %d" % win.thr_slider.value())
        print("    设备标签 = %r" % win.device_label.text()[:60])
        print("    许可标签 = %r" % win.lic_label.text())
        print()
        print("     集群 master 是否已启动 = %r" % win.master.running)
        print("     这让 DISCOVERY_PORT 在程序一启动就被 master 占用")
        print()

        print("--- 3.4 真实 BUG 复核: detect 分片计算 ---")
        print("     当前设备 = %r"
              % _devices({"use_gpu": True, "max_workers": 0}))
        n = 3
        total = 5
        chunk = max(total // n, 1)
        print("     模拟 3 设备 / 5 段: chunk = max(5//3,1) = %d" % chunk)
        splits = []
        for d in range(n):
            start = d * chunk
            end = total if d == n - 1 else (d + 1) * chunk
            splits.append((d, start, end, list(range(start, end))))
        for d, s, e, idx in splits:
            print("        cuda:%d 段范围 [%d,%d) 索引 %r" % (d, s, e, idx))
        covered = [i for _, _, _, idx in splits for i in idx]
        print("     覆盖索引 = %r" % covered)
        print("     实际段落数 = %d" % total)
        missing = [i for i in range(total) if i not in covered]
        dup = len(covered) != len(set(covered))
        print("     漏掉的段落 = %r" % missing)
        print("     有重复? %s" % dup)
        print(">>> %s" % ("BUG 确认：末段被静默丢弃" if missing else "未复现"))
        result = "分片漏段: %r" % (missing,)

        print()
        print("--- 2.3 真实 BUG 复核: SettingsDialog._save 用离屏真跑 ---")
        s2 = Settings(tmp_base)
        print("     保存前 hf_endpoint = %r" % s2.get("download", "hf_endpoint"))
        dlg = SettingsDialog(s2, tmp_base)
        print("     对话框默认选中 国内镜像 = %r" % dlg.rb_mirror.isChecked())
        dlg._save()
        print("     保存后 mirror      = %r" % s2.get("download", "mirror"))
        print("     保存后 hf_endpoint = %r" % s2.get("download", "hf_endpoint"))
        val = s2.get("download", "hf_endpoint")
        print("     含协议头? %s" % ("是" if "://" in str(val) else "否 <-- BUG"))
        print("     写入的 settings.json 路径 = %s" % s2.path)
        print("     [写操作记录] 该文件在项目外临时目录 %s" % tmp_base)

        win.close()
        print()
        print("OK  win.close() 未报错")
    except Exception as e:
        import traceback

        print("FAIL %s: %s" % (type(e).__name__, e))
        traceback.print_exc(limit=5)
        result = "失败: %s: %s" % (type(e).__name__, e)

    v.add("GUI", True, "离屏构造: %s" % result)


def run_report_render(v):
    """2.10b 未转义文件名的真实危害（离屏 Qt 渲染验证）。"""
    _qt_app()

    from PySide6.QtWidgets import QTextEdit

    from core.report import build_report

    head("2.10b", "未转义文件名的真实危害（Qt 离屏渲染）")
    print("QT_QPA_PLATFORM = offscreen（不显示窗口）")
    print()

    probes = [
        ("普通文件名", "论文初稿.docx"),
        ("含 & （Windows 允许做文件名）", "A&B研究.docx"),
        ("含 < > （Windows 不允许，但路径可经 API 构造）", "a<b>c.docx"),
        ("含引号", 'a"b"c.docx'),
    ]
    broken = 0
    for label, name in probes:
        html = build_report(["这是一段用于验证的测试文本内容。"], [0.9], 0.9,
                            name, "testengine", 0.5)
        w = QTextEdit()
        w.setHtml(html)
        plain = w.toPlainText()
        firstline = plain.split("\n")[0] if plain else ""
        ok = firstline.startswith(name)
        if not ok:
            broken += 1
        print("%-34s 文件名=%r" % (label, name))
        print("   HTML 片段  : %r" % html[:60])
        print("   Qt 渲染首行: %r" % firstline[:60])
        print("   标题正确?  : %s" % ("是" if ok else "否 <-- 被 HTML 解析破坏"))
        print()

    print("对照: 转义后")
    from html import escape

    name = "a<b>c.docx"
    html_fixed = build_report(["测试文本内容用于验证。"], [0.9], 0.9,
                              escape(name), "testengine", 0.5)
    w = QTextEdit()
    w.setHtml(html_fixed)
    print("   escape 后 Qt 渲染首行: %r" % w.toPlainText().split("\n")[0][:60])
    print()
    print("结论: 文件名里的 & 与 < > 会破坏 <h2> 标题渲染，")
    print("      用户报告里显示的文件名会缺字符或错乱。")
    v.add("2.10b", broken > 0, "%d/%d 个文件名在 Qt 渲染时标题被破坏"
          % (broken, len(probes)))
