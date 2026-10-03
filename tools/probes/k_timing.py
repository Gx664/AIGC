# -*- coding: utf-8 -*-
"""采样数 k 的耗时基准探针：实测 k=5 / 20 / 100 的单条耗时。

为什么要实测
------------
`FIXES.md §2` 记：

    论文 k = 100（σ̃ 的精度收敛点）   项目 k = 5（fast）/ 10（detect）
    把采样数提到 100，重测 σ 归一化是否转为正收益（代价：慢 10~20 倍）

那个"慢 10~20 倍"是**估算**。本探针实测真实倍率，供决定是否改 k。

方法
----
同一批样本（HC3 中文 10 条），同一引擎（fastdetectgpt / gpt-neo-2.7B），
只改 `samples`，测单条耗时。用 10 条取中位，避免单次波动。

**副作用**：加载 gpt-neo-2.7B（fp16 约 5.3GB）。k=100 时很慢，故样本量降到
10 条并逐条打进度。
"""
import json
import time

from . import ROOT, head

ZH_DATA = r"D:\hf_cache\hc3_zh_1to1.jsonl"

# 每种 k 跑几条 —— 按实测成本分配（见下方估算）
#
# 基准：60 条 / samples=10 → 1732 秒 → 28.9 秒/条，即一次生成约 5 秒。
# k 近似线性增长：
#   k=5   →  10 条 ≈  5 分钟
#   k=20  →  10 条 ≈ 17 分钟
#   k=100 →  10 条 ≈ 80 分钟  ← 超 30 分钟红线，故降到 2 条 ≈ 16 分钟
K_PLAN = [
    (5, 10),
    (20, 10),
    (100, 2),
]


def _load(n):
    half = max(1, n // 2)
    ai, hu = [], []
    with open(ZH_DATA, "r", encoding="utf-8") as f:
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
    return ai + hu


def run_k_timing(v):
    """实测 samples=5 / 20 / 100 的单条耗时。"""
    import torch

    from core.engines import catalog, create_engine

    head("K-TIME", "采样数 k 的耗时基准实测")
    print("torch %s  cuda=%s" % (torch.__version__, torch.cuda.is_available()))
    if not torch.cuda.is_available():
        print("无 CUDA，退出")
        v.add("K-TIME", False, "无 CUDA，未测")
        return
    free, total = torch.cuda.mem_get_info(0)
    print("显存 free=%.2fGB / total=%.2fGB"
         % (free / 1024 ** 3, total / 1024 ** 3))
    print()

    texts = _load(10)
    print("样本池: %d 条（HC3 中文）" % len(texts))
    print("计划（k, 条数）: %s" % K_PLAN)
    print()

    cfg = catalog.by_id("fastdetectgpt")
    base = dict(cfg.get("params") or {})
    eng = create_engine(cfg, ROOT)
    print("引擎: fastdetectgpt  params(基)=%s" % base)
    print("模型: %s" % cfg.get("model_id"))
    print()

    t0 = time.time()
    try:
        model = eng.mdl(0, "cuda:0")
    except Exception as e:
        print("加载失败: %s: %s" % (type(e).__name__, e))
        v.add("K-TIME", False, "模型加载失败")
        return
    print("模型加载 %.1f 秒，dtype=%s"
         % (time.time() - t0, next(model.parameters()).dtype))
    print()

    results = {}
    total_t0 = time.time()
    for k, nlines in K_PLAN:
        params = dict(base)
        params["samples"] = k
        print("=" * 68)
        print("k = %d   跑 %d 条   预计约 %.0f 分钟"
              % (k, nlines, 28.9 * k / 5.0 * nlines / 60.0))
        print("=" * 68)
        times = []
        for i in range(min(nlines, len(texts))):
            t1 = time.time()
            try:
                eng.predict_paragraphs([texts[i]], "cuda:0", **params)
            except Exception as e:
                print("  第 %d 条失败: %s: %s" % (i + 1, type(e).__name__, e))
                continue
            dt = time.time() - t1
            times.append(dt)
            print("  第 %2d 条: %7.1f 秒   本档累计 %.1f 分   总耗时 %.1f 分"
                  % (i + 1, dt, sum(times) / 60.0,
                     (time.time() - total_t0) / 60.0), flush=True)
        if not times:
            print("  无有效计时")
            results[k] = None
            continue
        warm = times[1:] if len(times) > 1 else times
        med = sorted(warm)[len(warm) // 2]
        results[k] = med
        print("  中位（剔除首条预热）= %.1f 秒   外推 200 条 = %.0f 分钟"
              % (med, med * 200 / 60.0))
        print()

    # ------------------------------------------------ 汇总
    print("=" * 68)
    print("汇总：采样数 → 单条耗时")
    print("=" * 68)
    print("%6s %12s %14s %14s" % ("k", "单条中位(s)", "200 条(分钟)", "相对 k=5"))
    ref = results.get(K_PLAN[0][0])
    for k, _n in K_PLAN:
        med = results.get(k)
        if med is None:
            print("%6d  未测" % k)
            continue
        ratio = (med / ref) if ref else float("nan")
        print("%6d %12.1f %14.0f %13.2fx" % (k, med, med * 200 / 60.0, ratio))
    print()
    print("对照论文：k = 100（σ̃ 精度收敛点）")
    print("判读：若 200 条超过 30 分钟，需先与用户确认再跑全量。")

    ok = bool(results)
    v.add("K-TIME", ok, "k→耗时: %s"
          % ", ".join("k=%d %.1fs" % (k, r) for k, r in results.items() if r))
