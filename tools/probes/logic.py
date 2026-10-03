# -*- coding: utf-8 -*-
"""逻辑类探针：Binoculars 公式复刻、参数合并顺序、license/i18n/报告转义。

来源（原 3 个独立脚本，逻辑一字未改）：
  probe_binoculars_engine_math.py
  probe_style_loop_and_param_merge.py
  probe_license_i18n_report_escape.py
"""
import math

from . import head


# ---------------------------------------------------------------- bino math
def run_bino_math(v):
    """Binoculars 公式恒判 AI —— binoculars_engine.py:54-58。"""
    head("2.1", "Binoculars 公式恒判 AI —— binoculars_engine.py:54-58")
    print("原始代码:")
    print("    log_ppl   = -lp_obs")
    print("    cross_ppl = math.exp(min(-lp_perf, 700.0))")
    print("    score     = log_ppl / max(cross_ppl, 1e-6)")
    print("    out.append(squash(threshold - score, 0.0, scale))")
    print()

    from core.engines.base import squash

    def repro(lp_obs, lp_perf, threshold=0.9015, scale=0.12):
        log_ppl = -lp_obs
        cross_ppl = math.exp(min(-lp_perf, 700.0))
        score = log_ppl / max(cross_ppl, 1e-6)
        return squash(threshold - score, 0.0, scale), score

    def paper(lp_obs, lp_perf):
        return math.exp(-lp_obs) / math.exp(-lp_perf)

    cases = [
        ("典型 AI 文本", -5.0, -3.2),
        ("典型人写文本", -12.0, -8.0),
        ("极端人写(高困惑)", -20.0, -15.0),
        ("极端 AI(低困惑)", -2.0, -1.8),
    ]
    for name, a, b in cases:
        got, sc = repro(a, b)
        print("%-18s lp_obs=%-7.1f lp_perf=%-7.1f score=%.6f 判AI=%.6f (论文式B=%.4f)"
              % (name, a, b, sc, got, paper(a, b)))
    print()
    print("论文式 B 在 6~55 量级；本实现 score 恒在 0.00x 量级；")
    print("阈值 0.9015 与 score 量纲不匹配 -> squash 恒接近 1.0")
    vals = [repro(a, b)[0] for _, a, b in cases]
    v.add("2.1", min(vals) > 0.95,
          "四组输入概率 %.4f~%.4f，全部判 AI" % (min(vals), max(vals)))


# ------------------------------------------------- 死循环 + 参数覆盖顺序
def run_style_loop_and_param(v):
    """2.6 死循环隐患 / 2.7 参数覆盖顺序。"""
    head("2.6", "死循环隐患 —— therapy.py:243-248 / 152-168")
    from core.aigc_rules import (
        COLLOQUIAL_FIXES,
        NUMBERED_MARKERS,
        SEQ_MARKERS,
    )

    print("A) _style_fix:")
    print("     for word, repl in COLLOQUIAL_FIXES.items():")
    print("         while word in text:")
    print("             text = text.replace(word, repl, 1)")
    print("   若 repl 里含 word -> 替换后仍命中 -> 无限循环")
    bad_style = [(w, r) for w, r in COLLOQUIAL_FIXES.items() if w in r]
    print("   COLLOQUIAL_FIXES 共 %d 条，自激 %d 条"
          % (len(COLLOQUIAL_FIXES), len(bad_style)))
    for w, r in bad_style:
        print("      BAD %r -> %r" % (w, r))
    print("   前 8 条规则样本:")
    for w, r in list(COLLOQUIAL_FIXES.items())[:8]:
        print("      %r -> %r" % (w, r))

    print()
    print("B) _break_parallel:")
    print("     while True:")
    print("         m = pattern.search(text)")
    print("         if not m: break")
    print("         text = text[:m.start()] + repl + text[m.end():]")
    print("   若 repl 被 pattern 命中 -> 无限循环")
    bad_par = []
    for nm, tbl in (("NUMBERED_MARKERS", NUMBERED_MARKERS),
                    ("SEQ_MARKERS", SEQ_MARKERS)):
        for pattern, repl in tbl:
            if pattern.search(repl):
                bad_par.append((nm, pattern.pattern, repl))
    print("   NUMBERED=%d 条, SEQ=%d 条, 自激 %d 条"
          % (len(NUMBERED_MARKERS), len(SEQ_MARKERS), len(bad_par)))
    for nm, p, r in bad_par:
        print("      BAD [%s] pattern=%r repl=%r" % (nm, p, r))

    print()
    print("实测调用（当前规则表）:")
    from core import therapy

    probe = [
        "首先，要重视这一问题。其次，要落实到行动。最后，要总结经验。",
        "说白了，这个方案真的强。总的来说，值得推广。",
        "一方面要抓效率，另一方面要抓质量，总的来说要两手抓。",
    ]
    for t in probe:
        c1, c2 = [], []
        therapy._style_fix(t, c1)
        therapy._break_parallel(t, c2)
        print("   输入 %r -> style %d 处, parallel %d 处" % (t[:22], len(c1), len(c2)))
    v.add("2.6", bool(bad_style) or bool(bad_par),
          "口语化自激 %d 条，模板自激 %d 条；当前规则表未触发实测卡死"
          % (len(bad_style), len(bad_par)))

    head("2.7", "引擎清单参数覆盖用户参数 —— main_window.py:86-90")
    print('    eparams = dict(cfg.get("params", {}))')
    print('    if "max_len" in self.params:')
    print('        eparams["max_len"] = self.params["max_len"]')
    print("    run_params = dict(self.params)")
    print('    run_params.update(eparams)')
    print()
    cfg = {"params": {"threshold": 0.3, "ppl_high": 25.0}}
    user = {"threshold": 0.7, "min_para_len": 20, "use_gpu": True}
    ep = dict(cfg.get("params", {}))
    if "max_len" in user:
        ep["max_len"] = user["max_len"]
    rp = dict(user)
    rp.update(ep)
    print("清单默认 threshold=0.3，用户界面设 0.7")
    print("   合并后 run_params['threshold'] = %r" % rp["threshold"])
    print("   完整 run_params = %r" % rp)
    print()
    extra = [k for k in rp if k in ("engine", "min_para_len", "use_cluster",
                                    "rewrite", "suggest_threshold", "use_gpu")]
    print("非引擎参数也会 ** 展开进 predict_paragraphs(): %r" % extra)
    print("引擎签名以 **kwargs 兜底，不会 TypeError，但语义混乱")
    v.add("2.7", rp["threshold"] != user["threshold"],
          "用户 threshold=0.7 被清单覆盖为 %r" % rp["threshold"])


# --------------------------------------------- license / i18n / 报告转义
def run_license_i18n(v):
    """2.8 license / 2.9 i18n 拼接键 / 2.10 report.py 未转义。"""
    import os
    import shutil
    import tempfile

    head("2.8", "license 校验空壳 —— license.py:29-32")
    print('    def _validate(self, key):')
    print('        return bool(key) and key.startswith("AIGC-PRO-") and len(key) >= 20')
    print()
    from core.license import License

    class L(License):
        def __init__(self):
            pass

    lic = L()
    tests = ["AIGC-PRO-0000000000000000", "AIGC-PRO-" + "x" * 11,
             "AIGC-PRO-AAAAAAAAAAAA", "", "AIGC-PRO-12345678901", "abc"]
    for k in tests:
        print("   _validate(%-30r) = %s" % (k, lic._validate(k)))

    print()
    tmp = tempfile.mkdtemp(prefix="aigc_lic_")
    try:
        real = License(tmp)
        print("   初始 current_tier() = %r" % real.current_tier())
        ok2, msg = real.activate("AIGC-PRO-0000000000000000")
        print("   activate('AIGC-PRO-0000000000000000') -> %s / %s" % (ok2, msg))
        print("   之后 current_tier() = %r" % real.current_tier())
        kp = os.path.join(tmp, "license.key")
        print("   license.key 内容 = %r" % open(kp, encoding="utf-8").read())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    print("注: 该文件写入临时目录，已清理")
    v.add("2.8", lic._validate("AIGC-PRO-0000000000000000"),
          "任意 AIGC-PRO- 开头且长度>=20 的字符串即通过")

    head("2.9", "i18n 拼接键缺失 —— engine_dialog.py:145 / rewrite_dialog.py:405")
    import core.i18n as i18n

    d = None
    for nm in ("DICTS", "_DICTS", "TEXTS", "_TEXTS", "STRINGS"):
        if hasattr(i18n, nm):
            d = getattr(i18n, nm)
            print("词典对象: i18n.%s" % nm)
            break
    if d is None:
        print("未找到词典变量名，列出模块级 dict:")
        for k, val in vars(i18n).items():
            if isinstance(val, dict) and len(val) > 50:
                print("   %s (len=%d)" % (k, len(val)))
        d = {"zh": {}, "en": {}}
    zh, en = d.get("zh", {}), d.get("en", {})
    print("   zh 键数 = %d, en 键数 = %d" % (len(zh), len(en)))
    print()
    print("枚举代码里字符串拼接出来的 tr() 键:")
    combos = [("engine_dialog.py:145", "engine_status_" + s)
              for s in ("builtin", "ready", "missing")]
    combos += [("rewrite_dialog.py:405", "rewrite_sev_" + s)
               for s in ("high", "medium", "low")]
    missing = []
    for src, key in combos:
        got = i18n.tr(key)
        found = got is not None and got != key
        if not found:
            missing.append((src, key))
        print("   %-9s %-26s tr() -> %r   (%s)"
              % ("OK" if found else "MISSING", key, got, src))
    print()
    print("缺失 %d 个" % len(missing))
    for src, key in missing:
        print("   %s 需要 %s" % (src, key))
    v.add("2.9", bool(missing),
          "缺失拼接键: %s" % ([k for _, k in missing] or "无"))

    head("2.10", "report.py 未转义文件名 —— report.py:20")
    print('    html = ["<h2>%s</h2>" % file_name, ...]')
    print("   file_name 来自 os.path.basename(self.path)，未 escape()")
    print("   而 snippet 那行做了 escape()")
    print()
    from core.report import build_report, escape

    bad_name = 'a&b<c>d"e".txt'
    html = build_report(["这是一段测试文本"], [0.9], 0.9, bad_name, "test", 0.5)
    first = html[:120]
    print("   build_report(file_name=%r) 前 120 字符:" % bad_name)
    print("   %r" % first)
    leaked = "<c>" in first or "&b" in first
    print()
    print("   是否原样泄漏未转义字符: %s" % leaked)
    print("   正确应为: <h2>%s</h2>" % escape(bad_name))
    print()
    print("   注: Qt 的 setHtml 对未闭合标签会静默吞内容，Win 文件名允许 & 号")
    v.add("2.10", leaked, "文件名 %r 未转义直接拼进 HTML" % bad_name)
