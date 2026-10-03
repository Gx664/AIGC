# -*- coding: utf-8 -*-
r"""中文底座对照探针：gpt2 vs gpt2-chinese-cluecorpussmall。

背景（待办 3）
--------------
`catalog.py` 的 gltr 只挂一个模型（`gpt2`，英文模型）。中文文本经 gpt2 的
byte-level BPE 分词后 token 数暴涨（217 汉字 → 中位 363 / 最长 1756 token），
PPL 分布与英文差异大，中文阈值只能另标（11.35/18.72），且实测 **无可行阈值
满足 FPR≤5%**（见 calibration.md §2.7）。

原作者在 `engines_manifest.json` 里已写过 `zh_perplexity` 条目，指向
`uer/gpt2-chinese-cluecorpussmall`（中文 GPT-2，CLUECorpusSmall 训练），
并填了中文阈值 `ppl_low=20 / ppl_high=45` —— **说明他本有此意**。

本探针回答：**换中文底座能否改善中文判别力？**

做法
----
同一批 HC3 中文样本（200 条 1:1），分别用两个底座跑纯 PPL，对比：
  1. AI / human 的 PPL 分布（中位数、分位）
  2. 按各分位点扫描的最优阈值与准确率
  3. **FPR≤5% 约束下的最优准确率** ← 关键（查重不能误报）
  4. 与 simpleai 的 99.75% 对比，看是否值得接进去

**只读项目源码，不改任何文件**；结果打到控制台。

模型位置：`D:\hf_cache\zh_gpt2\`（已下载，401MB）—— 运行时改 `_load` 的
repo 参数加载，**不改项目配置**。
"""
import json

from . import ROOT, head

N = 200
ZH_DATA = r"D:\hf_cache\hc3_zh_1to1.jsonl"


def _load_zh(n):
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
    return [(t, 1) for t in ai] + [(t, 0) for t in hu]


def _pct(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    i = min(int(q / 100.0 * len(sorted_vals)), len(sorted_vals) - 1)
    return sorted_vals[i]


def _scan(ppls, labels):
    """按 PPL 阈值扫描，返回最优与 FPR<=5% 版。

    PPL 越低越像 AI —— 与 gltr 引擎的映射方向一致（ppl<=lo 判 AI）。
    """
    best = (None, 0.0, 1.0, 1.0)
    best5 = (None, 0.0, 1.0, 1.0)
    for t in sorted(set(ppls)):
        tp = sum(1 for p, y in zip(ppls, labels) if p <= t and y == 1)
        fp = sum(1 for p, y in zip(ppls, labels) if p <= t and y == 0)
        tn = sum(1 for p, y in zip(ppls, labels) if p > t and y == 0)
        fn = sum(1 for p, y in zip(ppls, labels) if p > t and y == 1)
        nn = len(ppls)
        acc = (tp + tn) / nn
        fpr = fp / (fp + tn) if (fp + tn) else 0.0
        fnr = fn / (fn + tp) if (fn + tp) else 0.0
        if acc > best[1]:
            best = (t, acc, fpr, fnr)
        if fpr <= 0.05 and acc > best5[1]:
            best5 = (t, acc, fpr, fnr)
    return best, best5


def run_zh_backbone(v):
    """对比 gpt2 与 gpt2-chinese 在中文上的 PPL 判别力。"""
    import torch

    from core.engines import catalog, create_engine

    head("ZH-BB", "中文底座对照：gpt2 vs gpt2-chinese-cluecorpussmall")
    print("torch %s  cuda=%s" % (torch.__version__, torch.cuda.is_available()))
    free, total = torch.cuda.mem_get_info(0)
    print("显存 free=%.2fGB / total=%.2fGB"
         % (free / 1024 ** 3, total / 1024 ** 3))
    print()

    rows = _load_zh(N)
    texts = [t for t, _ in rows]
    labels = [y for _, y in rows]
    print("样本: n=%d（AI %d / 人写 %d），数据 %s"
          % (len(texts), sum(labels), len(labels) - sum(labels), ZH_DATA))
    print()

    cfg = catalog.by_id("gltr")
    eng = create_engine(cfg, ROOT)

    backbones = [
        ("gpt2（现用·英文模型）", "gpt2", None),
        ("gpt2-chinese（待评估）", "uer/gpt2-chinese-cluecorpussmall",
         r"D:\hf_cache\zh_gpt2"),
    ]

    summary = {}
    for label, repo, cache in backbones:
        print("=" * 68)
        print("底座：%s" % label)
        print("  repo=%s" % repo)
        print("=" * 68)

        orig_load = eng._load

        def patched(r, kind, dev, _repo=repo, _cache=cache, **kw):
            if _cache:
                from transformers import AutoModelForCausalLM, AutoTokenizer

                if kind == "tokenizer":
                    return AutoTokenizer.from_pretrained(
                        _repo, cache_dir=_cache)
                m = AutoModelForCausalLM.from_pretrained(
                    _repo, cache_dir=_cache, torch_dtype=torch.float16)
                m = m.to(dev or "cpu")          # ← 必须迁移到目标设备
                m.eval()
                return m
            return orig_load(_repo if _repo else r, kind, dev, **kw)

        eng._load = patched
        eng._cache.clear()
        try:
            tok = eng.tok(0)
            model = eng.mdl(0, "cuda:0")
            nparam = sum(p.numel() for p in model.parameters()) / 1e6
            print("  加载成功  参数量 ~%.0fM" % nparam)
        except Exception as e:
            print("  加载失败: %s: %s" % (type(e).__name__, e))
            eng._load = orig_load
            eng._cache.clear()
            summary[label] = None
            continue

        sample = texts[0]
        try:
            n_tok = len(tok(sample)["input_ids"])
            print("  分词: %d 字符 -> %d token（首样本，512 上限）"
                  % (len(sample), n_tok))
        except Exception as e:
            print("  分词统计失败: %s" % e)

        ppls = []
        fail = 0
        first_err = ""
        for i, t in enumerate(texts):
            try:
                p = eng.perplexity(t, model, tok, "cuda:0", max_tokens=512)
            except Exception as e:
                p = float("nan")
                fail += 1
                if not first_err:
                    first_err = "%s: %s" % (type(e).__name__, str(e)[:200])
            ppls.append(p)
            if (i + 1) % 50 == 0:
                print("    [%d/%d] %.0f%%" % (i + 1, len(texts),
                                              (i + 1) * 100.0 / len(texts)),
                      flush=True)
        if first_err:
            print("    !! 首条失败原因: %s" % first_err)

        valid = [(p, y) for p, y in zip(ppls, labels) if p == p]
        vp = [p for p, _ in valid]
        vy = [y for _, y in valid]
        ai_p = sorted([p for p, y in zip(vp, vy) if y == 1])
        hu_p = sorted([p for p, y in zip(vp, vy) if y == 0])

        print()
        print("  PPL 分布（%d 条有效，%d 条失败）：" % (len(vp), fail))
        print("    AI    中位=%8.2f  p10=%7.2f  p90=%8.2f"
              % (_pct(ai_p, 50), _pct(ai_p, 10), _pct(ai_p, 90)))
        print("    human 中位=%8.2f  p10=%7.2f  p90=%8.2f"
              % (_pct(hu_p, 50), _pct(hu_p, 10), _pct(hu_p, 90)))
        gap = abs(_pct(ai_p, 50) - _pct(hu_p, 50))
        print("    中位差=%.2f  %s"
              % (gap, "重叠严重" if gap < 2.0 else "可分"))

        best, best5 = _scan(vp, vy)
        print()
        if not vp:
            print("  !! 无有效 PPL，跳过阈值扫描")
            summary[label] = None
            eng._load = orig_load
            eng._cache.clear()
            del model, tok
            try:
                import gc

                gc.collect()
                torch.cuda.empty_cache()
            except Exception:
                pass
            print()
            continue
        print("  阈值扫描（PPL<=t 判 AI）：")
        print("    最优:      thr=%.2f acc=%.4f FPR=%.4f FNR=%.4f" % best)
        print("    FPR<=5%%:  %s"
              % (("thr=%.2f acc=%.4f FNR=%.4f"
                  % (best5[0], best5[1], best5[3]))
                 if best5[0] is not None else "**无可行阈值**"))

        summary[label] = {"ai_med": _pct(ai_p, 50), "hu_med": _pct(hu_p, 50),
                          "best": best, "best5": best5, "n": len(vp)}

        eng._load = orig_load
        eng._cache.clear()
        del model, tok
        try:
            import gc

            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass
        print()

    # ------------------------------------------------ 汇总
    print("=" * 68)
    print("汇总")
    print("=" * 68)
    print("%-24s %9s %9s %9s %9s %9s"
          % ("底座", "AI中位", "human中位", "最优acc", "FPR", "FPR<=5%"))
    for label, s in summary.items():
        if not s:
            print("%-24s 加载失败" % label)
            continue
        b5 = s["best5"][1] if s["best5"][0] is not None else float("nan")
        print("%-24s %9.2f %9.2f %9.4f %9.4f %9s"
              % (label, s["ai_med"], s["hu_med"], s["best"][1], s["best"][2],
                 ("%.4f" % b5) if b5 == b5 else "无"))
    print()
    print("参照：simpleai（分类模型）中文 acc=99.75% FPR=0.50%")
    print("判读：只有 gltr 的 FPR<=5% 版接近 simpleai，才值得换底座接进 catalog。")
    print()

    ok = any(s and s["best5"][0] is not None for s in summary.values() if s)
    v.add("ZH-BB", ok, "对照完成：%s"
          % ", ".join("%s FPR<=5%%acc=%s"
                      % (k.split("（")[0],
                         ("%.4f" % s["best5"][1]) if s and s["best5"][0]
                         else "无")
                      for k, s in summary.items()))
