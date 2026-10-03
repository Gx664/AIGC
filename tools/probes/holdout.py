# -*- coding: utf-8 -*-
r"""留出集验证：标定/评测分开，看指标是否"过拟合"。

为什么必须做
------------
论文（arXiv:2301.07597 附录 A.1.2）明确区分两类数据：

> In order to meet the "out-of-domain" claim ... we **do not include them in
> the threshold determination** and only use tune threshold on from CC News,
> CNN, and PubMed.

即：**定阈值的数据不能用来报指标**。本项目此前是**同批数据既标定又评测**，
报出来的 acc 会偏乐观（阈值是在同一批数据上搜出来的最优值）。

本探针把数据按**问题**拆成两份：

* **标定集**（默认 70%）—— 搜阈值
* **留出集**（默认 30%）—— 用标定集定的阈值报指标，**不参与搜索**

**为什么按问题拆而不是按条拆**：同一 question 下的「人写 + AI」是一对
对照样本。若拆到两边，留出集里会出现"标定集见过的同题文本"，
等价于变相泄漏。故整题进同一边。

用法
----
::

    python tools/probes/holdout.py            # 按组运行（heavy）
    python tools/audit_probes.py --only holdout

**副作用**：加载 gpt2-chinese（约 0.2GB）。实测单条 0.027 秒。
"""
import collections
import os
import sys

from . import ROOT, head

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

HOLDOUT_RATIO = 0.30
SEED = 42


def _load():
    """取 1:1 配平的中文集，**带 question**（拆分要用）。"""
    from prepare_datasets import load_balanced, load_hc3

    rows = load_balanced("zh")
    # load_balanced 只回 text/label/source，question 在原始 pair 里；
    # 按 (text,label) 反查即可（配平抽样保留了原记录，这里重新对齐）
    qmap = {}
    for r in load_hc3():
        qmap[(r["text"], r["label"])] = r.get("question") or ""
    for r in rows:
        r["question"] = qmap.get((r["text"], r["label"]), "")
    return rows


def _split_by_question(rows, ratio=HOLDOUT_RATIO, seed=SEED):
    """按问题分组拆分，保证同题只在一边。"""
    import random

    by_q = collections.defaultdict(list)
    for r in rows:
        by_q[r.get("question") or ("_solo_%d" % id(r))].append(r)
    qs = sorted(by_q)
    rnd = random.Random(seed)
    rnd.shuffle(qs)
    n_hold = max(1, int(len(qs) * ratio))
    hold_qs = set(qs[:n_hold])
    cal, hold = [], []
    for q in qs:
        (hold if q in hold_qs else cal).extend(by_q[q])
    return cal, hold


def _score_at(probs, labels, lo, hi):
    """按 perplexity_engine 的映射算 acc/FPR。"""
    tp = fp = tn = fn = 0
    for p, y in zip(probs, labels):
        if p <= lo:
            prob = 0.85
        elif p >= hi:
            prob = 0.15
        else:
            prob = 0.85 - 0.7 * (p - lo) / max(hi - lo, 1e-6)
        pred = 1 if prob >= 0.50 else 0
        if pred == 1 and y == 1:
            tp += 1
        elif pred == 1 and y == 0:
            fp += 1
        elif pred == 0 and y == 0:
            tn += 1
        else:
            fn += 1
    n = len(probs)
    acc = (tp + tn) / n if n else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    fnr = fn / (fn + tp) if (fn + tp) else 0.0
    return acc, fpr, fnr


def _scan_fpr5(ppls, labels):
    """在 FPR<=5% 约束下搜最优 (lo, hi)。"""
    vals = sorted(set(ppls))
    if not vals:
        return None
    mids = vals[::max(1, len(vals) // 60)]
    best = (None, None, 0.0, 1.0)
    for m in mids:
        lo, hi = m * 0.6, m * 1.6
        acc, fpr, _fnr = _score_at(ppls, labels, lo, hi)
        if fpr <= 0.05 and acc > best[2]:
            best = (lo, hi, acc, fpr)
    return best


def run_holdout(v):
    """标定/评测分开，检验指标是否过拟合。"""
    import torch

    from core.engines import catalog, create_engine

    head("HOLDOUT", "留出集验证：标定集定阈值，留出集报指标")
    if not torch.cuda.is_available():
        print("无 CUDA，退出")
        v.add("HOLDOUT", False, "无 CUDA")
        return

    rows = _load()
    cal, hold = _split_by_question(rows)
    print("总样本 %d（问题数 %d）" % (len(rows), len(set(r["question"] for r in rows))))
    print("  标定集 %d 条（%.0f%%）" % (len(cal), 100 - HOLDOUT_RATIO * 100))
    print("  留出集 %d 条（%.0f%%）—— 不参与定阈值" % (len(hold), HOLDOUT_RATIO * 100))
    # 防泄漏自检：两边问题集合不得相交
    qc = set(r["question"] for r in cal)
    qh = set(r["question"] for r in hold)
    print("  问题级不重叠: %s（交集 %d）" % (not (qc & qh), len(qc & qh)))
    print()

    cfg = catalog.by_id("zh_perplexity")
    eng = create_engine(cfg, ROOT)

    REPO = "uer/gpt2-chinese-cluecorpussmall"
    CACHE = r"D:\hf_cache\zh_gpt2"
    orig = eng._load

    def patched(r, kind, dev, **kw):
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if kind == "tokenizer":
            return AutoTokenizer.from_pretrained(REPO, cache_dir=CACHE)
        m = AutoModelForCausalLM.from_pretrained(
            REPO, cache_dir=CACHE, torch_dtype=torch.float16)
        return m.to(dev or "cpu").eval()

    eng._load = patched
    eng._cache.clear()
    tok = eng.tok(0)
    model = eng.mdl(0, "cuda:0")

    def ppls_of(rows_, tag):
        try:
            from tqdm import tqdm
            it = tqdm(rows_, desc=tag, unit="条", ncols=80, mininterval=0.1, miniters=1,
                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} "
                                 "[{elapsed}<{remaining}, {rate_fmt}]")
        except Exception:
            it = rows_
        out = []
        for r in it:
            try:
                out.append(eng.perplexity(r["text"], model, tok, "cuda:0", max_tokens=512))
            except Exception:
                out.append(float("nan"))
        return out

    cal_p = ppls_of(cal, "标定集 PPL")
    cal_y = [r["label"] for r in cal]
    hold_p = ppls_of(hold, "留出集 PPL")
    hold_y = [r["label"] for r in hold]

    cv = [(p, y) for p, y in zip(cal_p, cal_y) if p == p]
    hv = [(p, y) for p, y in zip(hold_p, hold_y) if p == p]
    cp = [p for p, _ in cv]
    cy = [y for _, y in cv]
    hp = [p for p, _ in hv]
    hy = [y for _, y in hv]

    print()
    print("=" * 68)
    print("结果：阈值在标定集搜出，在留出集验证")
    print("=" * 68)

    best = _scan_fpr5(cp, cy)
    if not best[0]:
        print("标定集上 FPR<=5% 无可行阈值 -> 无法验证")
        v.add("HOLDOUT", False, "标定集无可行阈值")
        return

    lo, hi = best[0], best[1]
    cal_acc, cal_fpr, _ = _score_at(cp, cy, lo, hi)
    hold_acc, hold_fpr, hold_fnr = _score_at(hp, hy, lo, hi)

    print("标定集搜出的阈值: (%.2f, %.2f)" % (lo, hi))
    print()
    print("%-14s %8s %8s %8s" % ("数据集", "acc", "FPR", "FNR"))
    print("%-14s %8.4f %8.4f %8s" % ("标定集", cal_acc, cal_fpr, "—"))
    print("%-14s %8.4f %8.4f %8.4f" % ("**留出集**", hold_acc, hold_fpr, hold_fnr))
    print()
    drop = cal_acc - hold_acc
    print("acc 落差: %.4f（%.2f 个百分点）" % (drop, drop * 100))
    if drop > 0.05:
        print("-> **落差 > 5 点：存在过拟合**。同批数据报的 acc 偏乐观。")
    elif drop > 0.02:
        print("-> 落差 2~5 点：轻微过拟合，可接受。")
    else:
        print("-> 落差 < 2 点：**未见过拟合**，同批评估的结论基本可信。")

    # 对照：在留出集上"再搜一次"最优（论文口径下的乐观上界）
    best_h = _scan_fpr5(hp, hy)
    if best_h[0]:
        print()
        print("对照：若在留出集上重新搜阈值，可得 (%.2f, %.2f) acc=%.4f"
              % (best_h[0], best_h[1], best_h[2]))
        print("      两者差距 = 阈值对数据的敏感度（越大越说明标定不稳）。")

    eng._load = orig
    eng._cache.clear()
    v.add("HOLDOUT", True, "留出集 acc=%.4f（标定集 %.4f，落差 %.2f 点）"
          % (hold_acc, cal_acc, drop * 100))

