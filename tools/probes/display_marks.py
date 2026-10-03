# -*- coding: utf-8 -*-
r"""展示层标记检查：报告四档柱状图 + 引擎语言/可用性标注。

为什么值得固化
--------------
这两样都是**用户直接看到**的东西，错了会误导，比内部指标错更严重：

* **四档百分比之和必须恰为 100** —— 曾各自 `round()` 后出现 99% / 101%
  （实测 3000 例中 1014 例），用户把四个数加起来核对会以为程序算错；
* **引擎标注决定用户选哪个引擎** —— 标错等于让人拿错工具（例如用 gltr 跑中文，
  实测 FNR 73%，等于白跑）。2026-09-23 修过一次，09-24 又改成 `❔` 单符号。

两者都是纯函数、秒级、无副作用，适合做探针；**真渲染**那部分仍归
``report_render`` / ``gui_offscreen`` 两个 heavy 探针（要 Qt 离屏）。
"""
import os
import random
import sys

from . import ROOT, head

_APP = os.path.join(ROOT, "app")


def run_display_marks(v):
    head("DISP", "展示层标记（报告四档 / 引擎标注）")
    if _APP not in sys.path:
        sys.path.insert(0, _APP)
    ok_all = True

    from core.report import _bucket_cell, _pct100

    # ------------------------------------------------ 1. 四档百分比之和
    print("--- 1. 四档百分比：和必须恰为 100 ---")
    rnd = random.Random(42)
    bad = 0
    for _ in range(500):
        raw = [rnd.random() for _ in range(4)]
        total = sum(raw)
        frac = tuple(f / total for f in raw)
        vals = _pct100(frac)
        if sum(vals) != 100 or len(vals) != 4:
            bad += 1
            if bad <= 3:
                print("   [FAIL] %r -> %r 和=%d" % (frac, vals, sum(vals)))
    print("   500 组随机占比：%d 组和不为 100" % bad)
    if bad:
        ok_all = False

    edges = [((1, 0, 0, 0), "全在一档"),
             ((0, 1, 0, 0), "全在二档"),
             ((0.25, 0.25, 0.25, 0.25), "四等分"),
             ((0.3333, 0.3333, 0.3334, 0), "近似三等分"),
             ((0.999, 0.001, 0, 0), "极端偏斜")]
    for frac, name in edges:
        vals = _pct100(frac)
        if sum(vals) != 100:
            ok_all = False
            print("   [FAIL] %s %r -> %r 和=%d" % (name, frac, vals, sum(vals)))
    print("   极端情形 %d 组通过" % len(edges))

    # 全 0 是异常输入：不能补成「绿 100%」（那会显示成"全是绿档"这种错结论）
    if any(_pct100((0, 0, 0, 0))):
        ok_all = False
        print("   [FAIL] 全 0 输入应返回全 0，实得 %r" % _pct100((0, 0, 0, 0)))
    else:
        print("   [OK  ] 全 0 输入返回全 0")
    print()

    # ------------------------------------------- 2. 柱状图 / 单元格边界
    print("--- 2. 柱状图与单元格边界（None / 全 0 / 单档）---")
    for frac, want, name in [(None, "", "None"),
                             ((0, 0, 0, 0), "", "全 0"),
                             ((1, 0, 0, 0), "<svg", "只占绿档")]:
        out = _bucket_cell(frac)
        if want == "":
            if out:
                ok_all = False
                print("   [FAIL] %s 应返回空串，实得 %r" % (name, out[:40]))
            else:
                print("   [OK  ] %s -> 空串" % name)
        elif want not in out:
            ok_all = False
            print("   [FAIL] %s 未渲染出 %s" % (name, want))
        else:
            print("   [OK  ] %s -> 含 %s" % (name, want))
    if "width='0.000%'" in _bucket_cell((1, 0, 0, 0)):
        ok_all = False
        print("   [FAIL] 单档时画出了 0 宽矩形")
    print()

    # ------------------------------------------------- 3. 引擎语言标注
    print("--- 3. 引擎语言 / 可用性标注（engine_lang_mark）---")
    try:
        from core.engines import catalog
        from ui.engine_dialog import (_UNMEASURED_MARK, engine_label,
                                      engine_lang_mark)
    except Exception as e:  # noqa: BLE001
        # 没有 PySide6 的环境下不该让整个探针挂掉
        print("   [SKIP] 无法导入 engine_dialog：%s" % e)
        v.add("DISP", not ok_all, "四档和恒为 100、柱状图边界（标注检查已跳过）")
        return

    expect = {
        "simpleai": ("✅ 可用", "🌐 中文"),
        "gltr": ("⚠️ 中文勿用", "🌐 中文 / 英文"),
        "zh_perplexity": ("⚠️ 中文弱", "🌐 中文"),
        "binoculars": ("⚠️ 中文弱", "🌐 中文 / 英文"),
        "detectgpt": ("❌ 中文勿用", "🌐 中文 / 英文"),
        "fastdetectgpt": (_UNMEASURED_MARK, ""),   # 未标定：只给符号，不带语言前缀
    }
    for eng in catalog.BUILTIN_ENGINES:
        eid = eng["id"]
        mark = engine_lang_mark(eng)
        if eid not in expect:
            # 规则 / 评测类引擎与语言无关，不该有任何语言前缀
            if mark:
                ok_all = False
                print("   [FAIL] %s 是语言无关引擎，不该有标注：%r" % (eid, mark))
            continue
        want_mark, want_prefix = expect[eid]
        if want_mark not in mark:
            ok_all = False
            print("   [FAIL] %s 标注缺 %r，实得 %r" % (eid, want_mark, mark))
        if want_prefix and want_prefix not in mark:
            ok_all = False
            print("   [FAIL] %s 缺语言前缀 %r，实得 %r" % (eid, want_prefix, mark))
        if not want_prefix and mark != _UNMEASURED_MARK:
            ok_all = False
            print("   [FAIL] %s 未标定应只回一个符号，实得 %r" % (eid, mark))
    print("   %d 个内置引擎的标注已按预期核对" % len(catalog.BUILTIN_ENGINES))

    fd = catalog.by_id("fastdetectgpt")
    label = engine_label(fd)
    if not label.startswith(_UNMEASURED_MARK):
        ok_all = False
        print("   [FAIL] 未标定引擎 label 未以 %r 开头：%r" % (_UNMEASURED_MARK, label))
    elif label.startswith("🌐"):
        ok_all = False
        print("   [FAIL] 未标定引擎 label 不该有语言前缀：%r" % label)
    else:
        print("   [OK  ] 未标定引擎 label = %r" % label)
    print()

    v.add("DISP", not ok_all, "四档和恒为 100、柱状图边界、引擎标注")
