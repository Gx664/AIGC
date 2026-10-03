# -*- coding: utf-8 -*-
r"""单条耗时预估（跑全量前必做）。

用法::

    python tools/estimate_timing.py --engine zh_perplexity --n 5
    python tools/estimate_timing.py --engine gltr --n 5

为什么先测 3~5 条：全量动辄上千条，跑错参数要好几个小时才看得出来。
先测单条耗时 -> 乘条数 -> 判断能不能一次跑完（>30 分钟就先报告）。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from prepare_datasets import load_balanced  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="单条耗时预估")
    ap.add_argument("--engine", default="zh_perplexity", help="引擎 id")
    ap.add_argument("--n", type=int, default=5, help="试跑条数")
    ap.add_argument("--total", type=int, default=0, help="全量条数（用于外推）")
    ap.add_argument("--lang", default="zh", help="zh / en")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    import torch
    from core.engines import catalog, create_engine

    print("torch %s  cuda=%s" % (torch.__version__, torch.cuda.is_available()))
    if torch.cuda.is_available():
        free, total = torch.cuda.mem_get_info(0)
        print("显存 free=%.2fGB / total=%.2fGB" % (free / 1024 ** 3, total / 1024 ** 3))
    print()

    cfg = catalog.by_id(args.engine)
    if not cfg:
        print("引擎 %s 不在清单里" % args.engine)
        return 2
    eng = create_engine(cfg, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not eng.is_installed():
        print("引擎 %s 的模型未下载" % args.engine)
        return 2
    params = dict(cfg.get("params") or {})

    rows = load_balanced(args.lang)
    texts = [r["text"] for r in rows[: args.n]]
    print("引擎=%s  params=%s" % (args.engine, params))
    print("试跑 %d 条（取自 load_balanced('%s') 前 %d 条）" % (len(texts), args.lang, args.n))
    print()

    # 首次调用含模型加载，单独计时
    t0 = time.time()
    eng.predict_paragraphs(texts[:1], "cuda:0", **params)
    t_load = time.time() - t0
    print("  第 1 条（含模型加载）: %.1f 秒" % t_load)
    if torch.cuda.is_available():
        print("  加载后显存 free=%.2fGB" % (torch.cuda.mem_get_info(0)[0] / 1024 ** 3))

    t0 = time.time()
    eng.predict_paragraphs(texts[1:], "cuda:0", **params)
    t_rest = time.time() - t0
    per = t_rest / max(1, len(texts) - 1)
    print("  其后 %d 条: %.1f 秒，单条 %.3f 秒" % (len(texts) - 1, t_rest, per))
    print()

    total = args.total or len(rows)
    est = per * total / 60.0
    print("外推：%d 条 x %.3f 秒 = %.1f 分钟" % (total, per, est))
    if est > 30:
        print("!! 预计超过 30 分钟，先报告用户再跑")
    else:
        print("可以一次跑完（< 30 分钟）")

    free = torch.cuda.mem_get_info(0)[0] / 1024 ** 3 if torch.cuda.is_available() else 0
    if free < 2.0:
        print("!! 显存余量 < 2GB，可能变慢或溢出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
