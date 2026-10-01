# -*- coding: utf-8 -*-
r"""`binoculars` 英文阈值重标（现有值已被证明失效）。

为什么必须重标
--------------
清单里的 `threshold=0.615` 标自 **essay 120 条**，但换到 essay 前 200 条时
最优阈值掉到 **0.1288**（差 4.5 倍）—— 0.615 下 **FNR=1.0000，一条 AI 都抓不出**
（见 `docs/FIXES.md` §3.2）。这是典型的「小样本阈值漂移」。

本探针用**配平后的全量英文数据**（essay+wp+reuter，5,984 条）重标，
并给出：
  1. 现有阈值 0.615 在本次数据上的表现
  2. 本次 FPR<=5% 约束下的最优阈值  <- 应采用
  3. 本次无约束最优阈值（对照）

**判据用 FPR<=5%**：查重工具误报比漏报严重。

**副作用**：加载 gpt2 + gpt2-medium（约 1.9GB）。
单条约 0.08 秒（比 gltr 慢一倍，要跑两个模型），5984 条约 8 分钟。
"""
import os
import sys

from . import ROOT, head

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

CUR_THRESHOLD = 0.615        # 清单现值（essay 120 条标定），仅用于打印对照
SCALE = 0.12

# 进度文件：长任务用。每块完成后覆写，独立于 stdout。
# 为什么不只靠 tqdm：tqdm 写的是 stderr 且带 \r，一旦输出被重定向或走管道
# （如 `| Select-Object`）就看不见了。写文件则**任何情况下都可轮询**。
PROG_PATH = os.path.join(os.environ.get("TEMP", "."), "bino_cal_prog.txt")


def _prog(done, total, t0):
    """**只写进度文件**，不打印。

    为什么不 print：tqdm 正在画进度条，再 print 会插队，终端里就变成
    "进度条一行 + 文本一行"交替刷新 —— 看起来像离散输出（用户实测反馈）。
    进度文件供进程外轮询（重定向/管道时 tqdm 会失效）。
    """
    import time

    pct = done * 100.0 / total if total else 0.0
    el = time.time() - t0
    eta = (el / done * (total - done)) if done else 0.0
    msg = ("binoculars %d/%d  %.1f%%  已用 %.1f 分  预计还需 %.1f 分"
           % (done, total, pct, el / 60.0, eta / 60.0))
    try:
        with open(PROG_PATH, "w", encoding="utf-8") as f:
            f.write(msg + "\n")
            f.flush()
    except Exception:
        pass



def run_binoculars_calib(v):
    """binoculars 英文阈值重标（直接在 B 口径搜，并写回 json）。"""
    import math
    import time

    import torch

    from core.engines import catalog, create_engine
    from prepare_datasets import balance, load_ghost
    from probes import save_calibration

    head("BINO-CAL", "binoculars 英文阈值重标（现有 0.615 已失效）")
    if not torch.cuda.is_available():
        print("无 CUDA，退出")
        v.add("BINO-CAL", False, "无 CUDA")
        return

    rows = balance(load_ghost())
    texts = [r["text"] for r in rows]
    labels = [r["label"] for r in rows]
    ai = sum(labels)
    print("数据: Ghostbuster 配平 %d 条（AI %d / 人写 %d）" % (len(rows), ai, len(rows) - ai))
    print("      来源 ghostbuster/essay + wp + reuter")
    print()

    cfg = catalog.by_id("binoculars")
    eng = create_engine(cfg, ROOT)
    cur = dict(cfg.get("params") or {})
    scale = float(cur.get("scale", 0.12))
    print("清单现值: threshold=%.4f scale=%.2f"
          % (cur.get("threshold", 0), scale))
    print()

    # ---- 口径说明：threshold 作用在 squash **之前**的 B 值上 ----
    #   p = squash(threshold - B, 0, scale)
    # 所以要搜阈值，必须在 **B 口径** 上搜，而不是在输出概率上搜。
    # 做法：跑一次拿到输出概率 p，反解出 B（squash 单调可逆），
    #       再对 B 扫阈值 —— 判 AI 的条件是 B <= threshold。
    import warnings
    warnings.simplefilter("ignore")

    # 用一个**固定且已知**的中心跑一次，便于反解 B
    # 取 center=0 时：p = 1/(1+exp(-(-B)/scale)) = sigmoid(-B/scale)
    print("跑 %d 条（反解 B，预计 %.1f 分钟）..." % (len(texts), len(texts) * 0.06 / 60))
    t0 = time.time()
    try:
        from tqdm import tqdm

        bar = tqdm(total=len(texts), desc="binoculars", unit="条", ncols=88, mininterval=0.1, miniters=1,
                   bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} "
                              "[{elapsed}<{remaining}, {rate_fmt}]")
        last = [0]

        def _cb(done, total_):
            bar.update(done - last[0])
            last[0] = done
            if done % 50 == 0 or done == total_:
                _prog(done, total_, t0)

        probs = eng.predict_paragraphs(
            texts, "cuda:0", threshold=0.0, scale=scale, progress_cb=_cb)
        bar.close()
    except Exception as e:
        import traceback

        traceback.print_exc()
        print("运行失败: %s: %s" % (type(e).__name__, e))
        v.add("BINO-CAL", False, "运行失败")
        return

    # 反解 B：p = sigmoid(-B/scale)  =>  B = -scale * logit(p)
    B = []
    for p in probs:
        p = min(max(p, 1e-9), 1 - 1e-9)
        B.append(-scale * math.log(p / (1 - p)))

    ai_b = sorted(b for b, y in zip(B, labels) if y == 1)
    hu_b = sorted(b for b, y in zip(B, labels) if y == 0)
    med = lambda x: x[len(x) // 2] if x else float("nan")
    print()
    print("=" * 68)
    print("B 值分布（B 越小越像 AI；threshold 判据：B <= threshold 判 AI）")
    print("=" * 68)
    print("  AI    B 中位=%.4f  p10=%.4f  p90=%.4f"
          % (med(ai_b), ai_b[len(ai_b) // 10], ai_b[len(ai_b) * 9 // 10]))
    print("  human B 中位=%.4f  p10=%.4f  p90=%.4f"
          % (med(hu_b), hu_b[len(hu_b) // 10], hu_b[len(hu_b) * 9 // 10]))
    print()

    def score_at(t):
        tp = fp = tn = fn = 0
        for b, y in zip(B, labels):
            pred = 1 if b <= t else 0
            if pred == 1 and y == 1:
                tp += 1
            elif pred == 1 and y == 0:
                fp += 1
            elif pred == 0 and y == 0:
                tn += 1
            else:
                fn += 1
        n = len(B)
        return ((tp + tn) / n if n else 0.0,
                fp / (fp + tn) if (fp + tn) else 0.0,
                fn / (fn + tp) if (fn + tp) else 0.0)

    a_cur = score_at(cur.get("threshold", 0.0))
    print("① 清单现值 threshold=%.4f: acc=%.4f FPR=%.4f FNR=%.4f"
          % (cur.get("threshold", 0), a_cur[0], a_cur[1], a_cur[2]))

    cands = sorted(set(round(b, 4) for b in B))
    b5 = (None, 0.0, 1.0, 1.0)
    bo = (None, 0.0, 1.0, 1.0)
    for t in cands:
        acc, fpr, fnr = score_at(t)
        if fpr <= 0.05 and acc > b5[1]:
            b5 = (t, acc, fpr, fnr)
        if acc > bo[1]:
            bo = (t, acc, fpr, fnr)

    if b5[0] is not None:
        print("② **FPR<=5%% 最优 threshold=%.4f: acc=%.4f FPR=%.4f FNR=%.4f**"
              % (b5[0], b5[1], b5[2], b5[3]))
    else:
        print("② FPR<=5%: 无可行阈值")
    print("③ 无约束最优 threshold=%.4f: acc=%.4f FPR=%.4f" % (bo[0], bo[1], bo[2]))
    print()

    if b5[0] is None:
        v.add("BINO-CAL", False, "无可行阈值")
        return

    # ---- 写回标定 json（不再手抄）----
    #
    # 用 try 包住：note 里是自然语言（含 % 等字符），万一格式化出错，
    # 也不该让跑了 5 分钟的结果全丢 —— 至少把参数写进去。
    try:
        note = ("旧值 0.615 标自 essay 120 条，在本数据上 FNR=%.4f、acc=%.4f"
                "（几乎一条 AI 都抓不出）。本值在 B 口径下按 FPR<=5%% 搜得；"
                "判据 B <= threshold 判 AI。" % (a_cur[2], a_cur[0]))
    except Exception:
        note = "旧值 0.615 失效；本值按 FPR<=5% 在 B 口径搜得。"

    save_calibration(
        "binoculars",
        {"threshold": round(b5[0], 4), "scale": scale},
        {
            "n": len(rows),
            "lang": "en",
            "data": "Ghostbuster essay+wp+reuter，1:1 配平",
            "criterion": "FPR<=5%",
            "acc": round(b5[1], 4),
            "fpr": round(b5[2], 4),
            "fnr": round(b5[3], 4),
            "tool": "python tools/audit_probes.py --only bino_cal",
            "date": time.strftime("%Y-%m-%d"),
            "note": note,
            "dist": {"ai_median_B": round(med(ai_b), 4),
                     "human_median_B": round(med(hu_b), 4)},
        },
    )
    print("阈值更新: %.4f -> %.4f（acc %.4f -> %.4f）"
          % (cur.get("threshold", 0), b5[0], a_cur[0], b5[1]))
    v.add("BINO-CAL", True,
          "现值 acc=%.4f / 重标 acc=%.4f（threshold %.4f->%.4f）"
          % (a_cur[0], b5[1], cur.get("threshold", 0), b5[0]))



