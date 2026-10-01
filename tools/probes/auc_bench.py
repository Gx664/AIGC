# -*- coding: utf-8 -*-
"""AUC 基准探针：给出与论文**可比**的指标。

为什么需要
----------
论文报的是 **AUC / AUROC**（只看排序，与阈值无关）：

| 论文 | 指标 | 值 |
|---|---|---|
| GLTR (1906.04043 §4) | AUC（四档 + 逻辑回归） | 0.87 |
| DetectGPT (2301.11305) | AUROC | 0.9554 |
| Fast-DetectGPT (2310.05130 Table 1) | AUROC | 0.9887 |

而项目一直报 **acc**（依赖阈值）。**两者不可直接比较** ——
`docs/FIXES.md §2` 已记：阈值本身的统计误差（±0.05）
比搜索步长（0.0025）大 20 倍，即 **acc 被阈值漂移严重干扰**。

AUC 排除阈值因素，直接量"排序判别力"。算出来才能回答"与论文差多少"。

做法
----
复用已有标定数据（`docs/FIXES.md` §3 里的逐条分数不存盘了，
故本探针**现场重跑**轻量引擎），对每个引擎算：
  * AUC（`sklearn.metrics.roc_auc_score`）
  * 最优 acc（对照）
  * AUC 与论文对照

**副作用**：gltr / binoculars 需加载 gpt2 组合（约 1.9GB）。
"""
import json
import os
import time

from . import head

ZH_DATA = r"D:\hf_cache\hc3_zh_1to1.jsonl"
EN_DATA = r"D:\hf_cache\ghost_essay_1to1.jsonl"
N = 200

# 进度文件：长任务用。每完成一条就覆写，独立于主输出，
# 便于外部轮询「跑到第几条」（主输出重定向到文件时看不到实时行）。
PROG_PATH = os.path.join(os.environ.get("TEMP", "."), "auc_prog.txt")


def _prog(tag, done, total, t0):
    """写进度文件 + 打印，保证进程外可观测。"""
    pct = done * 100.0 / total if total else 0.0
    el = time.time() - t0
    eta = (el / done * (total - done)) if done else 0.0
    msg = ("%s  %d/%d  %.1f%%  已用 %.1f 分  预计还需 %.1f 分"
           % (tag, done, total, pct, el / 60.0, eta / 60.0))
    try:
        with open(PROG_PATH, "w", encoding="utf-8") as f:
            f.write(msg + "\n")
            f.flush()
    except Exception:
        pass
    print("      %s" % msg, flush=True)

# 论文报告的 AUROC（见模块 docstring）
PAPER_AUROC = {
    "gltr": ("0.87", "AUC，四档分布 + 逻辑回归（§4 Table 1）"),
    "detectgpt": ("0.9554", "AUROC，5-model 生成（Fast-DetectGPT Table 1 引用）"),
    "fastdetectgpt": ("0.9887", "AUROC，5-model 生成（Table 1）"),
    "binoculars": ("—", "论文报 F1 0.90（阈值 0.901），未报 AUROC"),
}


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


def _best_acc(probs, labels):
    best_t, best_acc = 0.5, -1.0
    for t in sorted(set(probs)):
        acc = sum(1 for p, y in zip(probs, labels)
                  if (p >= t) == (y == 1)) / len(probs)
        if acc > best_acc:
            best_acc, best_t = acc, t
    return best_t, best_acc


def run_auc(v):
    """算各引擎的 AUC，与论文对照。"""
    import torch
    from sklearn.metrics import roc_auc_score

    from core.engines import catalog, create_engine

    head("AUC", "AUC 基准：与论文可比的指标")
    print("torch %s  cuda=%s" % (torch.__version__, torch.cuda.is_available()))
    print()

    datasets = [
        ("zh", "HC3-Chinese", ZH_DATA),
        ("en", "Ghostbuster Essay", EN_DATA),
    ]
    data = {}
    for code, label, path in datasets:
        rows = _load(path, N)
        data[code] = rows
        print("载入 [%s] %-20s n=%d（AI %d / 人写 %d）"
              % (code, label, len(rows),
                 sum(1 for _, y in rows if y == 1),
                 sum(1 for _, y in rows if y == 0)))
    print()

    # simpleai 也一起算（它是中文的可用基线）
    # PATH 环境变量已有数据时只跑指定引擎（避免重跑已算过的）
    only = os.environ.get("AUC_ONLY", "").strip()
    if only:
        engines = [e.strip() for e in only.split(",") if e.strip()]
        print("!! 只跑指定引擎（AUC_ONLY=%s）" % only)
        print()
    else:
        engines = ["simpleai", "gltr", "binoculars", "detectgpt"]
    results = {}

    for eid in engines:
        try:
            cfg = catalog.by_id(eid)
        except Exception as e:
            print("引擎 %s 取配置失败: %s" % (eid, e))
            continue
        impl = cfg.get("impl", "")
        params = dict(cfg.get("params") or {})
        # detectgpt 走 detect 模式（T5 掩码扰动），单条约 29 秒 —— 用 60 条
        n_this = 60 if eid == "detectgpt" else N
        print("=" * 68)
        print("引擎 %s（impl=%s）params=%s  n=%d" % (eid, impl, params, n_this))
        print("=" * 68)
        try:
            eng = create_engine(cfg, os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
        except Exception as e:
            print("  构造失败: %s: %s" % (type(e).__name__, e))
            continue

        for code, label, path in datasets:
            if n_this != N:
                rows = _load(path, n_this)
            else:
                rows = data[code]
            if not rows:
                continue
            texts = [t for t, _ in rows]
            labels = [y for _, y in rows]
            print("  [%s] %s n=%d 开始..." % (code, label, len(texts)),
                  flush=True)
            t_start = time.time()

            def _cb(done, total, _code=code, _t=t_start):
                # 每 10% 报一次，避免逐条刷屏；首条也报
                if done == 1 or done == total or (done * 10) % total < 1:
                    _prog(_code, done, total, _t)

            try:
                probs = eng.predict_paragraphs(texts, "cuda:0", **params,
                                               progress_cb=_cb)
            except TypeError:
                # 引擎签名不支持 progress_cb 时退回无回调
                probs = eng.predict_paragraphs(texts, "cuda:0", **params)
            except Exception as e:
                print("失败: %s: %s" % (type(e).__name__, str(e)[:120]))
                continue
            print("    [%s] 完成，耗时 %.1f 分"
                  % (code, (time.time() - t_start) / 60.0), flush=True)
            try:
                auc = roc_auc_score(labels, probs)
            except Exception as e:
                print("    AUC 计算失败: %s" % e)
                continue
            bt, bacc = _best_acc(probs, labels)
            results[(eid, code)] = {"auc": auc, "acc": bacc, "thr": bt,
                                    "n": len(texts)}
            print("    n=%d  AUC = %.4f    最优阈值 %.4f → acc %.4f"
                  % (len(texts), auc, bt, bacc))

        try:
            eng._cache.clear()
            import gc

            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass
        print()

    # ------------------------------------------------ 汇总
    print("=" * 68)
    print("汇总：AUC（与论文直接可比）")
    print("=" * 68)
    print("%-12s %-6s %9s %9s %9s   %s"
          % ("引擎", "语言", "AUC", "最优acc", "阈值", "论文 AUROC"))
    for eid in engines:
        for code, _l, _p in datasets:
            r = results.get((eid, code))
            if not r:
                continue
            paper = PAPER_AUROC.get(eid, ("—", ""))[0]
            print("%-12s %-6s %9.4f %9.4f %9.4f   %s"
                  % (eid, code, r["auc"], r["acc"], r["thr"], paper))
    print()
    print("论文基准（供对照）：")
    for eid, (val, note) in PAPER_AUROC.items():
        print("  %-14s %-8s %s" % (eid, val, note))
    print()
    print("判读要点：")
    print("  1. AUC 与阈值无关 —— 排除了 docs/FIXES.md §2 记的'阈值漂移'干扰")
    print("  2. 项目未做训练，而 GLTR 论文的 0.87 来自'四档 + 逻辑回归'")
    print("     —— 若本项 AUC 低于 0.87，差距可能来自'无训练'而非'实现错'")
    print("  3. 中英数据源不同（HC3 vs Ghostbuster），跨语言列不可直接相减")

    ok = bool(results)
    v.add("AUC", ok, "算得 %d 组 AUC" % len(results))
