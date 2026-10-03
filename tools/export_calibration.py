# -*- coding: utf-8 -*-
r"""把标定结果导出为 ``engines_catalog.json``（**第二部分 -> 第一部分**的桥）。

为什么需要（架构说明）
----------------------
本项目天然分两块：

1. **exe 部分**（原作者写的 + 本次修正）—— 用户拿到的成品。
   ``app/core/engines/catalog.py`` 里的阈值是**写死**的。
2. **研究部分**（为排查项目缺陷而加）—— 标定 / 探针 / 评测，只有开发者关注。

**写死阈值是"只有第一部分"时代的做法**（那时没得选）。现在有了第二部分，
阈值该由研究产出、落盘、被程序读取 —— 否则每改一次阈值都要改代码、
重新打包 exe，而且**代码里散落的数字无法追溯是哪次标定的**。

好消息：**不需要新造机制**。``manager.EngineManager`` 早就支持本地覆盖，
合并优先级是::

    catalog.BUILTIN_ENGINES
      <  engines_remote.json      （远端拉取）
      <  **engines_catalog.json** （本地覆盖）   <- 本工具写这个
      <  engines.json             （用户自定义）

所以：

* ``catalog.py`` 的阈值**保留** —— 它是**出厂默认值**，
  exe 开箱即用（没有覆盖文件也能跑）。
* ``engines_catalog.json`` **覆盖** —— 研究部分产出，优先级更高。

用法
----
::

    python tools/export_calibration.py                  # 写到项目根
    python tools/export_calibration.py --out <dir>      # 写到指定目录
    python tools/export_calibration.py --check          # 只看差异，不写

**输出体积**：约 1~2KB（只含被标定的字段，不含 name/desc 等静态内容）。
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 输出到 app 包内：安装器只复制 app/（installer.py 的 copytree），
# 放包内才能随程序分发到用户机器。见 manager.py 的文档字符串。
APP_DIR = os.path.join(PROJECT_ROOT, "app", "core", "engines")
OUT_NAME = "engines_calibration.json"

# 标定结果表 —— **只有这里写数字**，代码里不再散落阈值。
#
# 每项：engine_id -> {参数, "_calibration": 出处与样本量}
#
# 为什么带 `_calibration`：数字必须可追溯。``manager.all()`` 合并时会把未知
# 键一并带过去（``merged.update(e)``），所以这个字段不会丢，UI/调试时能看到
# "这个阈值是哪次跑出来的"。
CALIBRATED = {
    # ------------------------------------------------------------ 中文困惑度
    # 原作者在 engines_manifest.json 填 (20, 45)，实测 FPR 95.48% —— 因为中文
    # 人写 PPL 中位仅 14.75，低于 ppl_low=20，于是人写全被判 AI。
    "zh_perplexity": {
        "params": {"ppl_low": 4.33, "ppl_high": 11.55},
        "_calibration": {
            "n": 15216,
            "lang": "zh",
            "data": "HC3 中文，按问题配对 1:1（论文 §4.1）",
            "criterion": "FPR<=5%",
            "acc": 0.8623,
            "fpr": 0.0434,
            "method": "tools/audit_probes.py --only zh_threshold",
            "date": "2026-09-23",
            "note": "阈值随样本量右移：200 条 (2.88,7.68) acc 0.6300 / "
                    "400 条 (3.72,9.92) acc 0.7875 / 15216 条 (4.33,11.55) "
                    "acc 0.8623。**仍未收敛**，扩数据后需重标。",
        },
    },
    # ----------------------------------------------------------------- gltr
    # 中文实测在 FPR<=5% 下**不存在可行阈值**（英文有）。此处保留两组原值
    # 并如实标注中文不可交付。
    "gltr": {
        "params": {
            "method": "ppl",
            "ppl_high": 25.0,
            "ppl_low": 12.0,
            "ppl_high_zh": 18.72,
            "ppl_low_zh": 11.35,
        },
        "_calibration": {
            "n": 400,
            "lang": "zh+en",
            "data": "Ghostbuster Essay / HC3-Chinese",
            "criterion": "最优阈值（中文 FPR<=5% 无解，故只能取最优）",
            "acc": 0.9367,
            "fpr": 0.0519,
            "method": "docs/FIXES.md §3.1 / §3.2",
            "date": "2026-09-23",
            "note": "英文侧已按 FPR<=5% 复核（0.9400，见 §2.9）✅；"
                    "中文侧 FPR 高达 29.58% 且 FPR<=5% 下无可行阈值，"
                    "**实际不可交付** —— 界面标「中文勿用」。",
        },
    },
    # ----------------------------------------------------------- binoculars
    # 阈值 0.615 标自 essay 120 条；换到 200 条时最优掉到 0.1288（差 4.5 倍）。
    # 保持原值并**标注漂移**，待重标后再覆盖。
    #
    # 注：``binoculars_engine.py`` 的**函数缺省** threshold=0.9015 是论文给
    # Falcon-7B 的值（本机用 gpt2 组合，不可移植），仅作兜底，正常路径都
    # 走清单参数，不会被用到。
    "binoculars": {
        "params": {"threshold": 0.615, "scale": 0.12},
        "_calibration": {
            "n": 120,
            "lang": "en",
            "data": "Ghostbuster Student Essay",
            "criterion": "最优阈值",
            "acc": 0.9417,
            "fpr": 0.0484,
            "method": "docs/FIXES.md §3.2",
            "date": "2026-09-23",
            "note": "**阈值漂移警告**：换到 essay 前 200 条时最优阈值掉到 "
                    "0.1288，0.615 下 FNR=1.0000（一条 AI 都抓不出）。"
                    "该值只在特定 120 条上成立，**待重标**。"
                    "英文 FPR<=5% 复核见 §2.9（0.9200）。",
        },
    },
    # --------------------------------------------- 曲率类：未标定，如实标注
    # 两个引擎的 threshold/scale 是**论文的默认方向**，本项目**从未标定**。
    # 列出来是为了让"未标定"这件事在落盘里可见，而不是藏在代码默认参数里。
    "fastdetectgpt": {
        "params": {"mode": "fast", "samples": 5, "threshold": 0.0, "scale": 0.6},
        "_calibration": {
            "n": 0,
            "lang": "-",
            "data": "-",
            "criterion": "**未标定**",
            "acc": None,
            "fpr": None,
            "method": "-",
            "date": "2026-09-23",
            "note": "中英两侧都未测（需可用显存 >=7GB，本机常不足）。"
                    "threshold=0.0 / scale=0.6 是**未经标定的默认值**，"
                    "界面标「未标定」以免误导。见 docs/FIXES.md §6。",
        },
    },
    "detectgpt": {
        "params": {
            "mode": "detect",
            "samples": 10,
            "mask_ratio": 0.15,
            "threshold": 0.0,
            "scale": 0.6,
        },
        "_calibration": {
            "n": 60,
            "lang": "en/zh",
            "data": "Ghostbuster Essay",
            "criterion": "最优阈值（英文）",
            "acc": 0.7000,
            "fpr": None,
            "method": "docs/FIXES.md §3",
            "date": "2026-09-23",
            "note": "英文 AUC 0.7100（论文 0.9554，差 0.245）；"
                    "中文 AUC 0.2800 **排序反向**，任何阈值都救不了 -> 勿用于中文。"
                    "threshold 仍为 0.0（未细化标定）。",
        },
    },
    # ------------------------------------------------- 结构参数（非标定值）
    # 以下三项不是"跑出来的阈值"，而是**设计参数**。列进覆盖表是为了
    # 让体检通过（audit 要求所有 params 都可追溯），并写明它们为什么不需要标定。
    "simpleai": {
        "params": {"max_len": 500},
        "_calibration": {
            "n": 400,
            "lang": "zh",
            "data": "HC3-Chinese",
            "criterion": "无需阈值（分类器直接输出概率）",
            "acc": 0.9975,
            "fpr": 0.0050,
            "method": "docs/FIXES.md §3.1",
            "date": "2026-09-23",
            "note": "max_len=500 是**截断长度**，非判别阈值。模型自带分类头，"
                    "逐段输出 AI 概率，无需标定。中文侧唯一可交付引擎"
                    "（AUC 0.9998）；英文侧 AUC 0.4993 等于抛硬币，勿用。",
        },
    },
    "raid": {
        "params": {"threshold": 0.5, "max_samples": 200},
        "_calibration": {
            "n": 0,
            "lang": "-",
            "data": "-",
            "criterion": "**不适用**（评测基准，非检测引擎）",
            "acc": None,
            "fpr": None,
            "method": "-",
            "date": "2026-09-23",
            "note": "RAID 是**评测基准**：拿它去测别的检测器。threshold=0.5 "
                    "是判 AI 的分界、max_samples=200 是抽样上限，都不是标定值。",
        },
    },
    "mgtbench": {
        "params": {"threshold": 0.5, "max_samples": 200},
        "_calibration": {
            "n": 0,
            "lang": "-",
            "data": "-",
            "criterion": "**不适用**（评测基准，非检测引擎）",
            "acc": None,
            "fpr": None,
            "method": "-",
            "date": "2026-09-23",
            "note": "MGTBench 是**评测基准**，同上。",
        },
    },
}


def _load_builtin():
    """读内置清单，用于对比差异。"""
    from core.engines import catalog

    return {e["id"]: e for e in catalog.BUILTIN_ENGINES}


def audit_coverage():
    """体检：**找出所有硬编码的标定值，看是否都被覆盖表管到**。

    这是"以后也这么执行"的落地 —— 新增引擎或改了数字后，
    跑一次本函数就能发现漏网的硬编码。

    扫描对象：内置 catalog 的 ``params`` + 各引擎的**函数缺省参数**。
    """
    from core.engines import catalog

    builtin = {e["id"]: e for e in catalog.BUILTIN_ENGINES}
    covered = set(CALIBRATED.keys())

    print("=" * 68)
    print("硬编码覆盖体检")
    print("=" * 68)
    print()
    print("A) 内置 catalog 里有 params 的引擎，是否已被覆盖表管到：")
    missing = []
    for eid in sorted(builtin):
        p = builtin[eid].get("params") or {}
        if not p:
            continue
        mark = "OK  " if eid in covered else "**漏**"
        if eid not in covered:
            missing.append(eid)
        print("   [%s] %-16s %s" % (mark, eid, p))
    print()

    print("B) 引擎函数的缺省参数（兜底值，正常路径不走）：")
    defaults = [
        ("perplexity", "ppl_low=12.0 / ppl_high=25.0（英文缺省）"),
        ("perplexity", "ppl_low_zh=None / ppl_high_zh=None（中文缺省）"),
        ("curvature", "threshold=0.0 / scale=0.6（未标定）"),
        ("binoculars", "threshold=0.9015（论文 Falcon-7B 值，不可移植）"),
    ]
    for impl, desc in defaults:
        print("   %-12s %s" % (impl, desc))
    print("   -> 这些是兜底，调用方不传参时才生效；**不能当作标定值**。")
    print()

    if missing:
        print("!! 有 %d 个引擎的 params 未纳入覆盖表: %s" % (len(missing), missing))
        print("   请把它们加进 CALIBRATED（哪怕只写 _calibration 说明未标定）。")
    else:
        print("结论：内置 catalog 的全部 params 都已被覆盖表管到。")
    return 1 if missing else 0


def build_payload():
    """构造 engines_catalog.json 的内容。"""
    return {
        "version": "1.0",
        "updated": "2026-09-23",
        "note": "标定结果覆盖表。由 tools/export_calibration.py 生成，"
                "优先级高于内置 catalog.py（见 manager.EngineManager 的合并顺序）。"
                "每一项的 _calibration 记录样本量、判据与出处，便于追溯。",
        "engines": [{"id": eid, **cfg} for eid, cfg in sorted(CALIBRATED.items())],
    }


def show_diff(payload):
    """打印「内置值 vs 覆盖值」的差异。"""
    builtin = _load_builtin()
    print("=" * 68)
    print("标定覆盖表 vs 内置 catalog.py")
    print("=" * 68)
    for e in payload["engines"]:
        eid = e["id"]
        b = builtin.get(eid)
        cal = e.get("_calibration") or {}
        print()
        print("[%s]" % eid)
        if not b:
            print("  内置清单里没有该引擎（新增）")
        else:
            bp = b.get("params") or {}
            np_ = e.get("params") or {}
            for k in sorted(set(bp) | set(np_)):
                ov, nv = bp.get(k), np_.get(k)
                mark = "  " if ov == nv else "->"
                print("  %-14s %-10s %s %-10s" % (k, ov, mark, nv))
        if cal:
            print("  依据: n=%s %s 判据=%s acc=%s"
                  % (cal.get("n"), cal.get("lang"), cal.get("criterion"),
                     cal.get("acc")))
            if cal.get("note"):
                print("  备注: %s" % cal["note"])


def main():
    ap = argparse.ArgumentParser(
        description="导出标定结果到 engines_catalog.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--out", default=APP_DIR,
                    help="输出目录（默认 app/core/engines/，随程序分发）")
    ap.add_argument("--check", action="store_true", help="只看差异，不写文件")
    ap.add_argument("--audit", action="store_true",
                    help="体检：找漏网的硬编码标定值")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if args.audit:
        return audit_coverage()

    payload = build_payload()
    show_diff(payload)

    if args.check:
        print()
        print("（--check：未写文件）")
        return 0

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, OUT_NAME)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")

    print()
    print("=" * 68)
    print("已写出: %s（%d 字节）" % (path, len(text.encode("utf-8"))))
    print("=" * 68)
    print("生效方式：EngineManager 启动时读取它，覆盖内置 catalog.py 的出厂值。")
    print("          它在 app 包内 -> 随安装器复制到用户机器，无需改代码。")
    print("          优先级：用户覆盖(engines_catalog.json/engines.json) > 本文件")
    print("                  > 内置 catalog.py。删掉它就退回出厂默认值。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

