# -*- coding: utf-8 -*-
r"""`zh_perplexity` 引擎的阈值标定（用 tqdm 显示进度）。

背景（TODO-8 方案 A）
--------------------
原作者在 `engines_manifest.json` 里已备好 `zh_perplexity` 条目：
    模型 `uer/gpt2-chinese-cluecorpussmall`
    阈值 `ppl_low=20 / ppl_high=45`

但那是他的数字。本探针用**本项目的数据**重标，并给出多组指标对照：
    1. 原作者阈值 (20, 45)
    2. 本次实测最优阈值
    3. **FPR<=5% 约束下的最优** <- 查重工具实际关心这个

数据来源（2026-09-23 更换）
--------------------------
原先直接读 `hc3_zh_1to1.jsonl` 的前 N 条 —— 该文件**丢了 question**，
且样本量是随手定的（200 -> 400）。现改用 `prepare_datasets.load_balanced`：

* 论文 §5.3 口径：`We extracted all the <question, answer> pairs`
* 论文 §4.1 口径：不平衡时 `randomly sample one answer from humans and
  one answer from ChatGPT`（本实现按**问题配对**，更严）

即：数据由 loader 负责展开/去重/配平，**原始文件不动**。

进度用 tqdm 显示（每条一个 tick）。

**副作用**：加载 gpt2-chinese（401MB，fp16 约 0.2GB）。实测单条 0.027 秒，
15216 条约 7 分钟。
"""
import sys
import os

from . import ROOT, head

# 新 loader 在 tools/ 下（探针在 tools/probes/），加一级路径
_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

REPO = "uer/gpt2-chinese-cluecorpussmall"
CACHE = r"D:\hf_cache\zh_gpt2"

# 原作者在 engines_manifest.json 里填的阈值
AUTHOR_LOW, AUTHOR_HIGH = 20.0, 45.0

# 历史标定值（供对照，见 docs/FIXES.md §3.1）
PREV_200 = (2.88, 7.68, 0.6300)      # 200 条时
PREV_400 = (3.72, 9.92, 0.7875)      # 400 条时


def _load(limit=0):
    """取 1:1 平衡的中文集（论文 §4.1 口径，按问题配对）。

    :param limit: 最多取多少条；0 = 全部
    """
    from prepare_datasets import load_balanced

    rows = load_balanced("zh")
    if limit:
        rows = rows[:limit]
    return [(r["text"], r["label"]) for r in rows]



def _score_at(ppls, labels, lo, hi):
    """按 perplexity_engine 的映射算 acc。

    引擎规则（perplexity_engine.py:71-77）：
        ppl <= lo  -> 0.85（判 AI）
        ppl >= hi  -> 0.15（判人写）
        中间       -> 线性插值
    再与阈值 0.50 比较（0.85/0.15 对称，故等价于 ppl <= (lo+hi)/2 判 AI）。
    """
    tp = fp = tn = fn = 0
    for p, y in zip(ppls, labels):
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
    n = len(ppls)
    acc = (tp + tn) / n if n else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    fnr = fn / (fn + tp) if (fn + tp) else 0.0
    return acc, fpr, fnr


def _scan(ppls, labels):
    """按中位点扫描 (lo, hi) 组合，返回最优与 FPR<=5% 版。"""
    vals = sorted(set(ppls))
    if not vals:
        return None, None
    mids = vals[::max(1, len(vals) // 60)]        # 最多 60 个候选中点
    best = (None, None, 0.0, 1.0)
    best5 = (None, None, 0.0, 1.0)
    for m in mids:
        lo, hi = m * 0.6, m * 1.6                  # 以中点为基准开区间
        acc, fpr, fnr = _score_at(ppls, labels, lo, hi)
        if acc > best[2]:
            best = (lo, hi, acc, fpr)
        if fpr <= 0.05 and acc > best5[2]:
            best5 = (lo, hi, acc, fpr)
    return best, best5


def run_zh_threshold(v):
    """标定 zh_perplexity 的阈值（tqdm 进度）。"""
    import torch

    from core.engines import catalog, create_engine

    head("ZH-TH", "zh_perplexity 阈值标定（gpt2-chinese-cluecorpussmall）")
    print("torch %s  cuda=%s" % (torch.__version__, torch.cuda.is_available()))
    if not torch.cuda.is_available():
        print("无 CUDA，退出")
        v.add("ZH-TH", False, "无 CUDA")
        return

    rows = _load(0)                     # 0 = 用全部（论文 §4.1 平衡集）
    n_ai = sum(1 for _, y in rows if y == 1)
    print("样本: n=%d（AI %d / 人写 %d） 来源: prepare_datasets.load_balanced('zh')"
          % (len(rows), n_ai, len(rows) - n_ai))
    print()

    # 用 gltr 的配置拿到引擎实例（impl 相同），但换成中文模型
    cfg = catalog.by_id("gltr")
    eng = create_engine(cfg, ROOT)
    orig_load = eng._load

    def patched(r, kind, dev, **kw):
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if kind == "tokenizer":
            return AutoTokenizer.from_pretrained(REPO, cache_dir=CACHE)
        m = AutoModelForCausalLM.from_pretrained(
            REPO, cache_dir=CACHE, torch_dtype=torch.float16)
        m = m.to(dev or "cpu")
        m.eval()
        return m

    eng._load = patched
    eng._cache.clear()
    tok = eng.tok(0)
    model = eng.mdl(0, "cuda:0")
    print("模型: %s  dtype=%s" % (REPO, next(model.parameters()).dtype))

    # tqdm 进度：显示条数 / 百分比 / 速率 / 剩余时间
    # （长任务必须可观测 —— 即带进度输出）
    try:
        from tqdm import tqdm
        it = tqdm(rows, desc="PPL 打分", unit="条", ncols=90,
                  mininterval=0.1, miniters=1,
                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} "
                             "[{elapsed}<{remaining}, {rate_fmt}]")
    except Exception:
        it = rows

    ppls, labels = [], []
    for t, y in it:
        try:
            p = eng.perplexity(t, model, tok, "cuda:0", max_tokens=512)
        except Exception:
            p = float("nan")
        ppls.append(p)
        labels.append(y)

    valid = [(p, y) for p, y in zip(ppls, labels) if p == p]
    vp = [p for p, _ in valid]
    vy = [y for _, y in valid]
    ai_p = sorted([p for p, y in zip(vp, vy) if y == 1])
    hu_p = sorted([p for p, y in zip(vp, vy) if y == 0])
    med = lambda x: x[len(x) // 2] if x else float("nan")

    print()
    print("PPL 分布（%d 条有效）：" % len(vp))
    print("  AI    中位=%.2f  p10=%.2f  p90=%.2f" % (med(ai_p), ai_p[len(ai_p)//10], ai_p[len(ai_p)*9//10]))
    print("  human 中位=%.2f  p10=%.2f  p90=%.2f" % (med(hu_p), hu_p[len(hu_p)//10], hu_p[len(hu_p)*9//10]))
    print()

    a = _score_at(vp, vy, AUTHOR_LOW, AUTHOR_HIGH)
    print("① 原作者阈值 (%.1f, %.1f):  acc=%.4f  FPR=%.4f  FNR=%.4f"
          % (AUTHOR_LOW, AUTHOR_HIGH, a[0], a[1], a[2]))

    best, best5 = _scan(vp, vy)
    if best[0]:
        print("② 本批实测最优 (%.2f, %.2f):  acc=%.4f  FPR=%.4f"
              % (best[0], best[1], best[2], best[3]))
    if best5[0]:
        print("③ **本批 FPR<=5%% 最优 (%.2f, %.2f): acc=%.4f  FPR=%.4f**"
              % (best5[0], best5[1], best5[2], best5[3]))
    else:
        print("③ 本批 FPR<=5% 最优: 无可行阈值")
    print()

    # ---------------------------------------------------- 历史对照
    print("=" * 68)
    print("历史标定对照（看阈值是否随样本量收敛）")
    print("=" * 68)
    print("%-16s %-16s %8s %8s" % ("样本量", "FPR<=5% 阈值", "acc", "FPR"))
    for label, (lo, hi, acc) in (
        ("200 条", PREV_200),
        ("400 条", PREV_400),
    ):
        print("%-16s (%.2f, %.2f)%s%8.4f %8s"
              % (label, lo, hi, " " * 4, acc, "--"))
    if best5[0]:
        cur = _score_at(vp, vy, best5[0], best5[1])
        print("%-16s (%.2f, %.2f)%s%8.4f %8.4f   <- 本批 %d 条"
              % ("本批", best5[0], best5[1], " " * 4, cur[0], cur[1], len(vp)))
        print()
        print("对照：200 条 -> 400 条时 acc 从 0.6300 涨到 0.7875（差 15.75 点）；")
        print("      本批 %d 条的结果见上 —— 若与 400 条接近，说明已收敛。" % len(vp))
    print()
    print("对照：simpleai 中文 acc=0.9975 FPR=0.0050（基准）")

    eng._load = orig_load
    eng._cache.clear()

    ok = bool(vp)
    v.add("ZH-TH", ok, "原阈值 acc=%.4f / 实测最优 acc=%.4f" % (a[0], best[2] if best[0] else 0.0))
