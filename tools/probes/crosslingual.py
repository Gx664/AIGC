# -*- coding: utf-8 -*-
"""双语交叉验证探针：gltr / binoculars 在**同量样本**上的中英对照。

为什么需要这个探针
------------------
现有中文标定用 HC3-Chinese、英文标定用 Ghostbuster —— **两套数据不同**，
所以"gltr 中文 77.5% / 英文 93.67%"这两个数字**不可直接比较**
（docs/FIXES.md §3：同一引擎同一阈值，换数据集可从 93.67% 掉到 52.33%）。

本探针把两个引擎放在**同量**的中英样本上跑，并明确标注数据源差异。

用哪批数据
----------
本地可用：
  * 中文 `hc3_zh_1to1.jsonl`
  * 英文 `ghost_essay_1to1.jsonl`

**这两份仍是不同数据集**，所以本探针：
  1. 各 200 条，报告同量样本下的表现（消除样本量差异）
  2. 明确标注数据来源不同，**不夸大"双语对比"的结论**
  3. 给出**同数据源内**的引擎对比（这才是有效结论）

**副作用**：加载 gpt2 + gpt2-medium（约 1.9GB），吃显存但不溢出。
"""
import json
import os

from . import ROOT, head

DEFAULT_N = 200


def _load(path, n):
    half = max(1, n // 2)
    ai, hu = [], []
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            t = (row.get("text") or "").strip()
            if len(t) < 20:
                continue
            lb = str(row.get("label", "")).strip()
            if lb == "1" and len(ai) < half:
                ai.append(t)
            elif lb == "0" and len(hu) < half:
                hu.append(t)
            if len(ai) >= half and len(hu) >= half:
                break
    return [(t, 1) for t in ai] + [(t, 0) for t in hu]


def _best_threshold(probs, labels):
    best_t, best_acc = 0.5, -1.0
    for t in sorted(set(probs)):
        acc = sum(1 for p, y in zip(probs, labels)
                  if (p >= t) == (y == 1)) / len(probs)
        if acc > best_acc:
            best_acc, best_t = acc, t
    return best_t, best_acc


def _score_at(probs, labels, t):
    tp = sum(1 for p, y in zip(probs, labels) if p >= t and y == 1)
    fp = sum(1 for p, y in zip(probs, labels) if p >= t and y == 0)
    tn = sum(1 for p, y in zip(probs, labels) if p < t and y == 0)
    fn = sum(1 for p, y in zip(probs, labels) if p < t and y == 1)
    n = len(probs)
    return ((tp + tn) / n if n else 0.0,
            fp / (fp + tn) if (fp + tn) else 0.0,
            fn / (fn + tp) if (fn + tp) else 0.0)


def _fpr_at_5(probs, labels):
    """FPR<=5% 约束下的最优准确率（查重工具实际关心这个）。"""
    best = (None, 0.0)
    for t in sorted(set(probs)):
        acc, fpr, _fnr = _score_at(probs, labels, t)
        if fpr <= 0.05 and acc > best[1]:
            best = (t, acc)
    return best


def _median(x):
    return sorted(x)[len(x) // 2] if x else float("nan")


def run_crosslingual(v):
    """gltr / binoculars 同量样本的中英对照。"""
    import torch

    from core.engines import catalog, create_engine

    head("XL", "双语交叉验证：gltr / binoculars 同量样本对照")
    print("torch %s   cuda=%s" % (torch.__version__, torch.cuda.is_available()))
    if not torch.cuda.is_available():
        print("无 CUDA，退出")
        v.add("XL", False, "无 CUDA，未测")
        return
    free, total = torch.cuda.mem_get_info(0)
    print("显存 free=%.2fGB / total=%.2fGB"
         % (free / 1024 ** 3, total / 1024 ** 3))
    print()

    sources = [
        ("zh", "HC3-Chinese", r"D:\hf_cache\hc3_zh_1to1.jsonl"),
        ("en", "Ghostbuster Essay", r"D:\hf_cache\ghost_essay_1to1.jsonl"),
    ]
    data = {}
    for code, label, path in sources:
        rows = _load(path, DEFAULT_N)
        data[code] = rows
        print("载入 [%s] %-20s n=%d（AI %d / 人写 %d）"
              % (code, label, len(rows),
                 sum(1 for _, y in rows if y == 1),
                 sum(1 for _, y in rows if y == 0)))
    print()

    results = {}
    for eid in ("gltr", "binoculars"):
        cfg = catalog.by_id(eid)
        eng = create_engine(cfg, ROOT)
        params = dict(cfg.get("params") or {})
        print("=" * 68)
        print("引擎 %s   params=%s" % (eid, params))
        print("=" * 68)

        for code, label, _unused in sources:
            rows = data[code]
            if not rows:
                print("  [%s] 无数据，跳过" % code)
                continue
            texts = [t for t, _ in rows]
            labels = [y for _, y in rows]

            print("  [%s] %s  n=%d 跑... " % (code, label, len(texts)),
                  end="", flush=True)
            probs = eng.predict_paragraphs(texts, "cuda:0", **params)
            print("done", flush=True)

            t50 = _score_at(probs, labels, 0.50)
            bt, bacc = _best_threshold(probs, labels)
            bfull = _score_at(probs, labels, bt)
            t5, acc5 = _fpr_at_5(probs, labels)

            ai_p = [p for p, y in zip(probs, labels) if y == 1]
            hu_p = [p for p, y in zip(probs, labels) if y == 0]

            print("      阈值0.50: acc=%.4f FPR=%.4f FNR=%.4f"
                  % (t50[0], t50[1], t50[2]))
            print("      最优阈值 %.4f: acc=%.4f FPR=%.4f FNR=%.4f"
                  % (bt, bfull[0], bfull[1], bfull[2]))
            print("      FPR<=5%% 版: %s"
                  % (("thr=%.4f acc=%.4f" % (t5, acc5)) if t5 is not None
                     else "无可行阈值"))
            print("      AI 中位=%.4f  human 中位=%.4f  重叠=%s"
                  % (_median(ai_p), _median(hu_p),
                     "严重" if abs(_median(ai_p) - _median(hu_p)) < 0.05
                     else "可分"))
            results[(eid, code)] = {
                "n": len(texts), "acc50": t50[0], "best_t": bt,
                "best_acc": bfull[0], "best_fpr": bfull[1],
                "fpr5_t": t5, "fpr5_acc": acc5,
                "ai_med": _median(ai_p), "hu_med": _median(hu_p)}

        eng._cache.clear()
        try:
            import gc

            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass
        print()

    # ------------------------------------------------ 汇总
    print("=" * 68)
    print("汇总（同量样本，但**数据源不同** —— 见下方限制说明）")
    print("=" * 68)
    print("%-12s %-6s %6s %9s %9s %9s %9s"
          % ("引擎", "语言", "n", "acc@0.50", "最优acc", "最优阈值",
             "FPR<=5%"))
    for eid in ("gltr", "binoculars"):
        for code, _label, _p in sources:
            r = results.get((eid, code))
            if not r:
                continue
            print("%-12s %-6s %6d %9.4f %9.4f %9.4f %9s"
                  % (eid, code, r["n"], r["acc50"], r["best_acc"],
                     r["best_t"],
                     ("%.4f" % r["fpr5_acc"]) if r["fpr5_acc"] else "—"))
    print()

    print("!! 限制说明（不夸大结论）")
    print("!! 1. 中文用 HC3-Chinese、英文用 Ghostbuster Essay —— **数据源不同**，")
    print("!!    中英两列**不能直接相减**当作'语言差异'。")
    print("!! 2. 能直接比较的是**同一数据源内**两个引擎的差异。")
    print("!! 3. 要真正做双语对比，需同一批文本的中英对照版本（暂缺）。")
    print("!! 详见 docs/FIXES.md §3：同一引擎换数据集可从 93.67% 掉到 52.33%。")
    print()

    print("同数据源内的引擎对比（这才是有效结论）：")
    for code, label, _unused in sources:
        g = results.get(("gltr", code))
        b = results.get(("binoculars", code))
        if not g or not b:
            continue
        print("  [%s] %s" % (code, label))
        print("      gltr       acc@0.50=%.4f  最优=%.4f"
              % (g["acc50"], g["best_acc"]))
        print("      binoculars acc@0.50=%.4f  最优=%.4f"
              % (b["acc50"], b["best_acc"]))
        better = "gltr" if g["best_acc"] > b["best_acc"] else "binoculars"
        print("      -> 同源数据上 %s 更好（差 %.4f）"
              % (better, abs(g["best_acc"] - b["best_acc"])))

    avg = {}
    for eid in ("gltr", "binoculars"):
        accs = [results[(eid, c)]["best_acc"] for c, _l, _p in sources
                if (eid, c) in results]
        avg[eid] = sum(accs) / len(accs) if accs else 0.0
    print()
    print("两数据源平均最优准确率：gltr %.4f  binoculars %.4f"
          % (avg["gltr"], avg["binoculars"]))
    print("（平均只作参考 —— 两源权重相同，不代表真实使用分布）")

    v.add("XL", bool(results), "完成 %d 组；同源对比见上方" % len(results))
