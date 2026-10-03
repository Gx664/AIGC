# -*- coding: utf-8 -*-
r"""`simpleai` 实跑复核（分类器，无阈值，但要实测 acc / AUC / FPR）。

为什么需要
----------
``engines_calibration.json`` 里 simpleai 的 ``acc=0.9975`` 是**从旧文档抄的**，
不是本工具跑出来的。它是中文侧**唯一可交付**的引擎，这个数字必须有据。

simpleai 是判别式分类器（RoBERTa），**没有可调阈值** ——
但它输出的概率仍要过流程里的判定点 0.50，所以：

* acc / FPR / FNR 要实测（在 0.50 判定下）
* AUC 要实测（排序判别力，与论文可比）

**副作用**：加载 simpleai 模型（约 780MB）。CPU 可跑，约 3~5 分钟。
"""
import os
import sys
import time

from . import ROOT, head

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

PROG = os.path.join(os.environ.get("TEMP", "."), "simpleai_prog.txt")


def _prog(msg):
    try:
        with open(PROG, "w", encoding="utf-8") as f:
            f.write(msg + "\n")
            f.flush()
    except Exception:
        pass


def _score(probs, labels, t=0.5):
    tp = fp = tn = fn = 0
    for p, y in zip(probs, labels):
        pred = 1 if p >= t else 0
        if pred == 1 and y == 1:
            tp += 1
        elif pred == 1 and y == 0:
            fp += 1
        elif pred == 0 and y == 0:
            tn += 1
        else:
            fn += 1
    n = len(probs)
    return ((tp + tn) / n if n else 0.0,
            fp / (fp + tn) if (fp + tn) else 0.0,
            fn / (fn + tp) if (fn + tp) else 0.0)


def _auc(probs, labels):
    """AUC（秩和公式，含并列平均秩）。"""
    pairs = sorted(zip(probs, labels))
    n1 = sum(1 for _, y in pairs if y == 1)
    n0 = len(pairs) - n1
    if n1 == 0 or n0 == 0:
        return 0.5
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


def run_simpleai_check(v):
    """simpleai 中英两侧实跑，写回 json。"""
    from core.engines import catalog, create_engine
    from prepare_datasets import load_balanced
    from probes import save_calibration

    head("SIMPLEAI", "simpleai 实跑复核（现值抄自旧文档）")
    cfg = catalog.by_id("simpleai")
    print("清单: max_len=%s" % (cfg.get("params") or {}).get("max_len"))
    print()

    res = {}
    for lang, name in (("zh", "中文"), ("en", "英文")):
        rows = load_balanced(lang)
        texts = [r["text"] for r in rows]
        labels = [r["label"] for r in rows]
        print("--- %s：%d 条 ---" % (name, len(rows)))
        eng = create_engine(cfg, ROOT)
        if not eng.is_installed():
            print("  模型未下载，跳过")
            continue
        t0 = time.time()
        try:
            from tqdm import tqdm

            # **整批一次调用 + progress_cb 逐条更新** ——
            # simpleai_engine 本来就支持 progress_cb（见其 predict_paragraphs）。
            # 不要自己分块（分块会让进度变成"每块一跳"）。
            bar = tqdm(total=len(texts), desc="simpleai(%s)" % lang,
                       unit="条", ncols=88, mininterval=0.1, miniters=1,
                       bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} "
                                  "[{elapsed}<{remaining}, {rate_fmt}]")
            last = [0]

            def _cb(done, total_):
                bar.update(done - last[0])
                last[0] = done
                if done % 100 == 0 or done == total_:
                    _prog("%s %d/%d" % (lang, done, total_))

            probs = eng.predict_paragraphs(
                texts, "cpu", progress_cb=_cb, **dict(cfg.get("params") or {}))
            bar.close()
        except Exception as e:
            import traceback

            traceback.print_exc()
            print("  运行失败: %s" % e)
            continue

        acc, fpr, fnr = _score(probs, labels)
        auc = _auc(probs, labels)
        print("  耗时 %.1f 分" % ((time.time() - t0) / 60.0))
        print("  **acc=%.4f  FPR=%.4f  FNR=%.4f  AUC=%.4f**"
              % (acc, fpr, fnr, auc))
        res[lang] = {"n": len(rows), "acc": round(acc, 4),
                     "fpr": round(fpr, 4), "fnr": round(fnr, 4),
                     "auc": round(auc, 4)}
        print()

    if not res:
        v.add("SIMPLEAI", False, "未能跑出结果")
        return

    zh = res.get("zh", {})
    en = res.get("en", {})
    save_calibration(
        "simpleai",
        dict(cfg.get("params") or {}),
        {"n": zh.get("n") or en.get("n") or 0,
         "lang": "zh+en",
         "data": "HC3 中文 / Ghostbuster 英文（各 1:1 配平）",
         "criterion": "判定点 0.50（分类器无阈值可调）",
         "acc": zh.get("acc"),
         "fpr": zh.get("fpr"),
         "auc": zh.get("auc"),
         "tool": "python tools/audit_probes.py --only simpleai",
         "date": time.strftime("%Y-%m-%d"),
         "note": ("实测（非抄录）：中文 acc=%.4f FPR=%.4f AUC=%.4f；"
                  "英文 acc=%.4f FPR=%.4f AUC=%.4f。"
                  "分类器无阈值可调，故只复核指标。"
                  "中文为唯一可交付引擎；英文 AUC 约 0.5，等于抛硬币。"
                  % (zh.get("acc", 0), zh.get("fpr", 0), zh.get("auc", 0),
                     en.get("acc", 0), en.get("fpr", 0), en.get("auc", 0))),
         "by_lang": res},
    )
    v.add("SIMPLEAI", True, "中文 acc=%.4f AUC=%.4f / 英文 AUC=%.4f"
          % (zh.get("acc", 0), zh.get("auc", 0), en.get("auc", 0)))
