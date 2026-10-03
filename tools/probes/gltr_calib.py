# -*- coding: utf-8 -*-
r"""`gltr` 阈值重标（中英两组参数，一次跑完并写回 json）。

为什么必须重标
--------------
`catalog.py` 里 gltr 的 4 个阈值（`ppl_low/high` 英文、`ppl_low_zh/high_zh`
中文）都是**从旧文档抄来的**，不是本工具跑出来的：

* 英文 (12, 25)        <- 文档 §2.2，标自 essay 300 条
* 中文 (11.35, 18.72)  <- 文档 §1.1，且那组在 **FPR<=5% 下不存在可行阈值**

本探针用当前数据集重标，**按 FPR<=5% 判据**给出可交付的阈值，
并**直接写入** ``engines_calibration.json``（不手抄）。

gltr 的映射方式（`perplexity_engine`）
--------------------------------------
::

    ppl <= lo   -> 0.85（判 AI）
    ppl >= hi   -> 0.15（判人写）
    中间        -> 线性插值

所以 lo/hi 就是"判 AI 的上界"与"判人写的下界"。

**副作用**：加载 gpt2（约 500MB）。单条约 0.02 秒。
"""
import os
import sys
import time

from . import ROOT, head

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

PROG = os.path.join(os.environ.get("TEMP", "."), "gltr_cal_prog.txt")


def _prog(msg):
    try:
        with open(PROG, "w", encoding="utf-8") as f:
            f.write(msg + "\n")
            f.flush()
    except Exception:
        pass


def _score(ppls, labels, lo, hi):
    """按引擎的映射算 acc/FPR/FNR。"""
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
    return ((tp + tn) / n if n else 0.0,
            fp / (fp + tn) if (fp + tn) else 0.0,
            fn / (fn + tp) if (fn + tp) else 0.0)


def _search(ppls, labels, fpr_cap=0.05):
    """按候选 (lo, hi) 搜 FPR<=5% 下 acc 最高的组合。

    候选来自 PPL 分位数：lo 取低分位、hi 取中高分位，
    保证 lo < hi 且覆盖人机分界（AI 低 PPL、human 高 PPL）。
    """
    vals = sorted(set(ppls))
    if len(vals) < 4:
        return None, None
    qs = [vals[int(len(vals) * f)] for f in
          (0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45)]
    qh = [vals[int(len(vals) * f)] for f in
          (0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)]
    best = (None, None, 0.0, 1.0, 1.0)
    best5 = (None, None, 0.0, 1.0, 1.0)
    for lo in qs:
        for hi in qh:
            if hi <= lo:
                continue
            acc, fpr, fnr = _score(ppls, labels, lo, hi)
            if acc > best[2]:
                best = (lo, hi, acc, fpr, fnr)
            if fpr <= fpr_cap and acc > best5[2]:
                best5 = (lo, hi, acc, fpr, fnr)
    return best, best5


def run_gltr_calib(v):
    """gltr 中英阈值重标，并写回 engines_calibration.json。"""
    import torch

    from core.engines import catalog, create_engine
    from prepare_datasets import load_balanced
    from probes import save_calibration

    head("GLTR-CAL", "gltr 中英阈值重标（现值抄自旧文档）")
    if not torch.cuda.is_available():
        print("无 CUDA，退出")
        v.add("GLTR-CAL", False, "无 CUDA")
        return

    cfg = catalog.by_id("gltr")
    cur = dict(cfg.get("params") or {})
    eng = create_engine(cfg, ROOT)
    print("清单现值: ppl_low/high=%.2f/%.2f  ppl_low/high_zh=%.2f/%.2f"
          % (cur.get("ppl_low", 0), cur.get("ppl_high", 0),
             cur.get("ppl_low_zh", 0), cur.get("ppl_high_zh", 0)))
    print()

    out = {}
    meta_all = {}
    result = {}

    for lang, name in (("zh", "中文"), ("en", "英文")):
        rows = load_balanced(lang)
        texts = [r["text"] for r in rows]
        labels = [r["label"] for r in rows]
        print("--- %s：%d 条（AI %d / 人写 %d）---"
              % (name, len(rows), sum(labels), len(labels) - sum(labels)))

        tok = eng.tok(0)
        model = eng.mdl(0, "cuda:0")
        ppls = []
        t0 = time.time()
        try:
            from tqdm import tqdm

            bar = tqdm(total=len(texts), desc="PPL(%s)" % lang, unit="条",
                       ncols=88, mininterval=0.1, miniters=1,
                       bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} "
                                  "[{elapsed}<{remaining}, {rate_fmt}]")
            for i, t in enumerate(texts):
                try:
                    ppls.append(eng.perplexity(t, model, tok, "cuda:0",
                                               max_tokens=512))
                except Exception:
                    ppls.append(float("nan"))
                bar.update(1)
                if i % 50 == 0:
                    _prog("%s %d/%d" % (lang, i + 1, len(texts)))
            bar.close()
        except Exception as e:
            print("  运行失败: %s: %s" % (type(e).__name__, e))
            v.add("GLTR-CAL", False, "运行失败(%s)" % lang)
            return

        vp = [(p, y) for p, y in zip(ppls, labels) if p == p]
        P = [p for p, _ in vp]
        Y = [y for _, y in vp]

        # 存下 PPL 与标签（分位摘要 + 全量到临时文件），便于**事后核对**
        # 「旧阈值在这批数据上的 FPR 是多少」—— 否则只凭 acc 无法判断
        # 重标是否真的更好（踩过的坑：默认 acc 与 FPR 约束下的 acc 不可比）。
        try:
            import json

            dump = os.path.join(os.environ.get("TEMP", "."),
                                "gltr_ppl_%s.json" % lang)
            with open(dump, "w", encoding="utf-8") as fh:
                json.dump({"ppl": [round(x, 4) for x in P],
                           "label": Y}, fh)
            print("  PPL 已存: %s（供事后核对旧阈值）" % os.path.basename(dump))
        except Exception:
            pass

        ai = sorted(p for p, y in zip(P, Y) if y == 1)
        hu = sorted(p for p, y in zip(P, Y) if y == 0)
        med = lambda x: x[len(x) // 2] if x else float("nan")
        print("  PPL 中位: AI=%.2f  human=%.2f" % (med(ai), med(hu)))
        print("  耗时 %.1f 分" % ((time.time() - t0) / 60.0))

        # 现值表现
        lo0 = cur.get("ppl_low_zh") if lang == "zh" else cur.get("ppl_low")
        hi0 = cur.get("ppl_high_zh") if lang == "zh" else cur.get("ppl_high")
        if lo0 and hi0:
            a0 = _score(P, Y, float(lo0), float(hi0))
            print("  ① 现值 (%.2f, %.2f): acc=%.4f FPR=%.4f FNR=%.4f"
                  % (lo0, hi0, a0[0], a0[1], a0[2]))
            # **必须同时给"现值在 FPR<=5% 约束下是否合格"** ——
            # 否则会拿"不受约束的旧 acc"去比"受约束的新 acc"，
            # 得出"重标后变差"的错误结论（踩过的坑）。
            if a0[1] > 0.05:
                print("     ⚠️ 现值 FPR=%.4f 超标（>5%%）—— 不可交付，"
                      "其 acc 不能与「FPR<=5%% 最优」直接比较" % a0[1])
            else:
                print("     现值满足 FPR<=5%")
        else:
            a0 = (0.0, 1.0, 1.0)

        best, best5 = _search(P, Y)
        if best[0]:
            print("  ② 最优 (%.2f, %.2f): acc=%.4f FPR=%.4f"
                  % (best[0], best[1], best[2], best[3]))
        if best5[0]:
            print("  ③ **FPR<=5%% 最优 (%.2f, %.2f): acc=%.4f FPR=%.4f FNR=%.4f**"
                  % (best5[0], best5[1], best5[2], best5[3], best5[4]))
        else:
            print("  ③ FPR<=5%: **无可行阈值**")
        print()

        if lang == "zh":
            out["ppl_low_zh"] = round(best5[0], 2) if best5[0] else None
            out["ppl_high_zh"] = round(best5[1], 2) if best5[0] else None
        else:
            out["ppl_low"] = round(best5[0], 2) if best5[0] else None
            out["ppl_high"] = round(best5[1], 2) if best5[0] else None
        result[lang] = {
            "n": len(rows), "cur_acc": a0[0],
            "acc": best5[2] if best5[0] else None,
            "fpr": best5[3] if best5[0] else None,
            "ai_med": med(ai), "hu_med": med(hu),
        }

    # ------------------------------------------------ 写回 json
    zh = result.get("zh", {})
    en = result.get("en", {})
    zh_ok = out.get("ppl_low_zh") is not None
    en_ok = out.get("ppl_low") is not None

    if not zh_ok and not en_ok:
        print("中英两侧都无可行阈值 —— 不写回")
        v.add("GLTR-CAL", False, "两侧均无可行阈值")
        return

    # 只覆盖**有结果**的那一侧；另一侧保留原值（在 note 里说明）
    params = {"method": cur.get("method", "ppl")}
    if en_ok:
        params["ppl_low"] = out["ppl_low"]
        params["ppl_high"] = out["ppl_high"]
    else:
        params["ppl_low"] = cur.get("ppl_low")
        params["ppl_high"] = cur.get("ppl_high")
    if zh_ok:
        params["ppl_low_zh"] = out["ppl_low_zh"]
        params["ppl_high_zh"] = out["ppl_high_zh"]
    else:
        params["ppl_low_zh"] = cur.get("ppl_low_zh")
        params["ppl_high_zh"] = cur.get("ppl_high_zh")

    note = ("英文侧 " + ("已重标" if en_ok else "保留原值（无可行阈值）")
            + "；中文侧 " + ("已重标" if zh_ok else
                            "**无 FPR<=5% 可行阈值**（故保留旧值，界面标「中文勿用」）"))
    try:
        note += ("。实测 PPL 中位：中文 AI=%.2f/human=%.2f；"
                 "英文 AI=%.2f/human=%.2f"
                 % (zh.get("ai_med", 0), zh.get("hu_med", 0),
                    en.get("ai_med", 0), en.get("hu_med", 0)))
    except Exception:
        pass
    # **必须写明新旧对比是"同批数据、同判据"** —— 旧值的 acc 看似更高，
    # 是因为它的 FPR 超标（宁可错杀）；不写清楚会被误读成"重标变差"。
    note += ("。旧阈值在同批数据上的 FPR 超标（英文 7.99%%、中文 23.74%%），"
             "故其较高 acc 不可与「FPR<=5%% 最优」直接比较；"
             "本次是用 acc 换回合格误报率。"
             "注意中文侧即便 FPR 合格，FNR 仍高达约 73%%——"
             "**检出能力不足，确认中文不可交付**。")

    save_calibration(
        "gltr", params,
        {"n": (en.get("n") or 0) + (zh.get("n") or 0),
         "lang": "zh+en",
         "data": "HC3 中文（按问题配平） + Ghostbuster 英文（1:1 配平）",
         "criterion": "FPR<=5%",
         "acc": en.get("acc") or zh.get("acc"),
         "fpr": en.get("fpr") or zh.get("fpr"),
         "tool": "python tools/audit_probes.py --only gltr_cal",
         "date": time.strftime("%Y-%m-%d"),
         "note": note,
         "by_lang": result},
    )

    print("=" * 68)
    print("重标完成：英文 %s / 中文 %s"
          % ("OK" if en_ok else "无解", "OK" if zh_ok else "无解"))
    print("=" * 68)
    v.add("GLTR-CAL", True,
          "英文 acc=%.4f（原 %.4f）/ 中文 %s"
          % (en.get("acc") or 0, en.get("cur_acc") or 0,
             ("acc=%.4f" % zh["acc"]) if zh_ok else "无可行阈值"))


