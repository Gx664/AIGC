# -*- coding: utf-8 -*-
r"""英文侧 FPR<=5% 复核（TODO 收口项，2026-09-23 新增）。

为什么需要
----------
中文侧已按 **FPR<=5%** 统一复核（见 calibration.md §2.7），结论是
「只有 simpleai 可交付」。但**英文侧一直只报 acc / AUC**，没做同口径复核，
于是英文的可用性结论（catalog 里的标签）**没有依据**。

本探针把英文侧按同一把尺子量一遍：对每个引擎在英文数据上算
    * acc@0.50
    * 最优阈值与最优 acc
    * **FPR<=5% 约束下的最优 acc**  ← 查重工具真正关心的
    * AI / human 中位分

查重工具**误报比漏报严重**，FPR<=5% 那一列才是可交付性的判据。

数据与副作用
------------
* 英文：`D:\hf_cache\ghost_essay_1to1.jsonl`（Ghostbuster Student Essay）
* 引擎：simpleai（CPU 可跑）+ gltr / binoculars（gpt2 组合，约 1.9GB）
* **不加载 detectgpt / fastdetectgpt** —— 前者慢，后者需腾显存（见 TODO-5）
"""
import json
import os

from . import ROOT, head

EN_DATA = r"D:\hf_cache\ghost_essay_1to1.jsonl"
N = 200

# 要复核的引擎（都已完成英文标定的才列进来）
ENGINES = ("simpleai", "gltr", "binoculars")


def _load(n):
    """读英文 1:1 平衡集。"""
    half = max(1, n // 2)
    ai, hu = [], []
    if not os.path.isfile(EN_DATA):
        return []
    with open(EN_DATA, "r", encoding="utf-8") as f:
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


def _score_at(probs, labels, t):
    tp = sum(1 for p, y in zip(probs, labels) if p >= t and y == 1)
    fp = sum(1 for p, y in zip(probs, labels) if p >= t and y == 0)
    tn = sum(1 for p, y in zip(probs, labels) if p < t and y == 0)
    fn = sum(1 for p, y in zip(probs, labels) if p < t and y == 1)
    n = len(probs)
    return ((tp + tn) / n if n else 0.0,
            fp / (fp + tn) if (fp + tn) else 0.0,
            fn / (fn + tp) if (fn + tp) else 0.0)


def _best_threshold(probs, labels):
    best_t, best_acc, best_fpr = 0.5, -1.0, 1.0
    for t in sorted(set(probs)):
        acc, fpr, _fnr = _score_at(probs, labels, t)
        if acc > best_acc:
            best_acc, best_t, best_fpr = acc, t, fpr
    return best_t, best_acc, best_fpr


def _fpr_at_5(probs, labels):
    """FPR<=5% 约束下的最优阈值与准确率。"""
    best = (None, 0.0, 0.0)
    for t in sorted(set(probs)):
        acc, fpr, _fnr = _score_at(probs, labels, t)
        if fpr <= 0.05 and acc > best[1]:
            best = (t, acc, fpr)
    return best


def _auc(probs, labels):
    """AUC（排序判别力）。不依赖 sklearn —— 用秩和公式，避免多一个依赖。"""
    pairs = sorted(zip(probs, labels))
    n1 = sum(1 for _, y in pairs if y == 1)
    n0 = len(pairs) - n1
    if n1 == 0 or n0 == 0:
        return 0.5
    # 平均秩（处理并列分数）
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    r1 = sum(r for r, (_, y) in zip(ranks, pairs) if y == 1)
    return (r1 - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def _median(x):
    return sorted(x)[len(x) // 2] if x else float("nan")


def run_english_fpr(v):
    """对已完成英文标定的引擎做 FPR<=5% 复核。"""
    import torch

    from core.engines import catalog, create_engine

    head("EN-FPR", "英文侧 FPR<=5% 复核（acc 与可交付性是两件事）")
    print("torch %s  cuda=%s" % (torch.__version__, torch.cuda.is_available()))
    if not torch.cuda.is_available():
        print("无 CUDA，退出")
        v.add("EN-FPR", False, "无 CUDA")
        return

    rows = _load(N)
    if not rows:
        print("英文数据缺失：%s" % EN_DATA)
        v.add("EN-FPR", False, "数据缺失")
        return
    print("样本: n=%d（AI %d / 人写 %d）  数据源: Ghostbuster Student Essay"
          % (len(rows), sum(1 for _, y in rows if y == 1),
             sum(1 for _, y in rows if y == 0)))
    print()

    texts = [t for t, _ in rows]
    labels = [y for _, y in rows]
    device = "cuda:0"
    results = {}

    for eid in ENGINES:
        cfg = catalog.by_id(eid)
        if not cfg:
            print("[%s] 清单里没有该引擎，跳过" % eid)
            continue
        eng = create_engine(cfg, ROOT)
        if not eng.is_installed():
            print("[%s] 模型未下载，跳过" % eid)
            continue
        params = dict(cfg.get("params") or {})
        # 英文侧用英文阈值：gltr 的 _zh 参数对英文无影响，显式去掉更清晰
        params.pop("ppl_low_zh", None)
        params.pop("ppl_high_zh", None)

        print("[%s] params=%s  跑 %d 条... " % (eid, params, len(texts)),
              end="", flush=True)
        try:
            probs = eng.predict_paragraphs(texts, device, **params)
        except Exception as e:
            print("失败: %s: %s" % (type(e).__name__, e))
            v.add("EN-FPR", False, "引擎 %s 运行失败" % eid)
            continue
        print("done", flush=True)

        acc50, fpr50, fnr50 = _score_at(probs, labels, 0.50)
        bt, bacc, bfpr = _best_threshold(probs, labels)
        t5, acc5, fpr5 = _fpr_at_5(probs, labels)
        auc = _auc(probs, labels)
        ai_p = [p for p, y in zip(probs, labels) if y == 1]
        hu_p = [p for p, y in zip(probs, labels) if y == 0]

        print("      阈值0.50: acc=%.4f FPR=%.4f FNR=%.4f" % (acc50, fpr50, fnr50))
        print("      **AUC=%.4f**（排序判别力，与论文可比）" % auc)
        print("      最优阈值 %.4f: acc=%.4f FPR=%.4f" % (bt, bacc, bfpr))
        if t5 is not None:
            print("      **FPR<=5%%: thr=%.4f acc=%.4f FPR=%.4f**" % (t5, acc5, fpr5))
        else:
            print("      **FPR<=5%: 无可行阈值**")
        print("      AI 中位=%.4f  human 中位=%.4f" % (_median(ai_p), _median(hu_p)))
        print()

        results[eid] = {
            "n": len(probs), "acc50": acc50, "auc": auc,
            "best_t": bt, "best_acc": bacc, "best_fpr": bfpr,
            "fpr5_t": t5, "fpr5_acc": acc5,
            "ai_med": _median(ai_p), "hu_med": _median(hu_p),
        }
        eng._cache.clear()
        try:
            import gc

            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass

    # ------------------------------------------------ 汇总
    print("=" * 68)
    print("汇总：英文侧（FPR<=5% 那列决定可不可交付）")
    print("=" * 68)
    print("%-12s %5s %8s %8s %9s %9s %11s" %
          ("引擎", "n", "AUC", "acc@0.50", "最优acc", "最优阈值", "FPR<=5%"))
    deliverable = []
    for eid in ENGINES:
        r = results.get(eid)
        if not r:
            continue
        cell = ("%.4f" % r["fpr5_acc"]) if r["fpr5_acc"] else "无可行阈值"
        print("%-12s %5d %8.4f %8.4f %9.4f %9.4f %11s"
              % (eid, r["n"], r["auc"], r["acc50"], r["best_acc"], r["best_t"],
                 cell))
        if r["fpr5_acc"]:
            deliverable.append((eid, r["fpr5_acc"]))
    print()
    if deliverable:
        best = max(deliverable, key=lambda kv: kv[1])
        print("英文侧可交付（FPR<=5%% 有可行阈值）：%d/%d 个，最好的是 %s，acc=%.4f"
              % (len(deliverable), len(results), best[0], best[1]))
    else:
        print("英文侧无任何引擎满足 FPR<=5%")

    ok = bool(results)
    v.add("EN-FPR", ok,
          "复核 %d 个引擎，%d 个满足 FPR<=5%%" % (len(results), len(deliverable)))
