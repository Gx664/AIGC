# -*- coding: utf-8 -*-
"""GLTR 困惑度检测引擎：语言模型困惑度越低越像机器写的。

阈值为什么分语言（实测标定，2026-09-23）
----------------------------------------
``ppl_low`` / ``ppl_high`` 把 PPL 线性映射到 [0.85, 0.15]。实测（各 300 条
1:1 平衡样本，gpt2）：

===========  =============  ============  ============
语言          AI PPL 中位     human 中位     现阈值准确率
===========  =============  ============  ============
英文          12.96          29.50         93.67%
中文          12.06          17.18         68.33%
===========  =============  ============  ============

现有 (12, 25) 是**英文的最优值**；中文下 human 的 PPL 中位仅 17.18，落进了
插值区间，判别力被稀释。所以中文单独用标定出的 (11.35, 18.72)，准确率
68.33% → 74.67%（FPR 58.45% → 29.58%）。两组阈值存在 catalog 的 params 里，
按文本语言自动切换。

数据来源：Ghostbuster Student Essay（英）/ HC3-Chinese（中），
详见 docs/FIXES.md §3

中文专用条目（``zh_perplexity``，2026-09-23 加入内置清单）
--------------------------------------------------------
同一条 ``impl`` 被两个条目共用，靠 ``models`` 字段指向不同底座：

============================  ==================  ==================
条目                          底座                 阈值 (low, high)
============================  ==================  ==================
``gltr``                      gpt2（英文）         (12, 25) 英 / (11.35, 18.72) 中
``zh_perplexity``             gpt2-chinese        (2.88, 7.68)
============================  ==================  ==================

``zh_perplexity`` 的阈值标自 HC3-Chinese 200 条 1:1，取的是 **FPR<=5% 版**
（原作者原填 (20, 45)，实测 FPR 高达 95% —— 中文人写 PPL 中位仅 13.64，
低于 ``ppl_low=20``，于是人写文本全被判 AI）。改用 (2.88, 7.68) 后
acc 0.5200 → 0.6300、FPR 0.9500 → 0.0400。详见 docs/FIXES.md §3.1。

**两套阈值量纲差约 5 倍，不可互换。**

注：论文 GLTR（arXiv:1906.04043）的主特征是逐 token rank 四档分布
（§4 实测 AUC 0.87），本实现用的是整段平均 PPL（Test-1 路线的退化版，
AUC 0.71）。按 rank 四档 + 逻辑回归重做需训练，未做。
"""
from .base import BaseEngine
from .registry import register


def _is_chinese(text):
    """粗判语言：CJK 字符占比是否过半（只看前 200 字，够用且快）。"""
    s = text[:200]
    if not s:
        return False
    cjk = sum(1 for c in s if "\u4e00" <= c <= "\u9fff")
    return cjk * 2 >= len(s)


@register("perplexity")
class PerplexityEngine(BaseEngine):
    """统计派方法：PPL ≤ ppl_low 判 0.85，≥ ppl_high 判 0.15，中间线性插值。"""

    type = "perplexity"
    MODEL_KINDS = ("causal",)
    MODELS = (("gpt2", "causal", "困惑度打分模型"),)

    def __init__(self, cfg, base_dir):
        super().__init__(cfg, base_dir)
        # 逐段四档占比（绿, 黄, 红, 紫），供界面展示。
        #
        # 为什么用**实例属性**而不是改返回值：``predict_paragraphs`` 约定返回
        # ``list[float]``，被 detector / benchmark / cluster 三处共用；改返回
        # 结构要动整条数据通路，而四档**只有本引擎**有（其他 5 个引擎没有这个
        # 概念）。故走旁路：跑完存这里，界面按需取，**调用方一行不用改**。
        # 未跑过时为 None。
        self.last_buckets = None

    def predict_paragraphs(
        self,
        paragraphs,
        device,
        ppl_high=25.0,
        ppl_low=12.0,
        ppl_high_zh=None,
        ppl_low_zh=None,
        method="ppl",
        max_tokens=512,
        progress_cb=None,
        **kwargs
    ):
        """按 ``method`` 选判别方式。

        ==========  ====================================================
        method      做法
        ==========  ====================================================
        ``ppl``     Test-1 退化版：整段平均 PPL 线性映射（历史默认，保持兼容）
        ``rank``    论文 §3 的 Test-2：逐 token 的 rank 四档分布（见下）
        ==========  ====================================================

        为什么默认仍是 ``ppl``：``rank`` 路线实测**并未更优**（见类 docstring
        的对照数据），默认切换会让已有阈值失效。要论文原样请显式传
        ``method="rank"``。
        """
        if str(method).lower() == "rank":
            return self._run_rank(
                paragraphs, device, max_tokens, progress_cb, ppl_low, ppl_high,
                ppl_low_zh, ppl_high_zh,
            )
        tok = self.tok(0)
        model = self.mdl(0, device)
        out = []
        buckets = []                 # 逐段四档（绿, 黄, 红, 紫）
        total = len(paragraphs)
        for i, p in enumerate(paragraphs):
            # 中文用中文标定的一组阈值（未配置时退回通用值）。
            # 注意：`zh_perplexity` 条目**只给了一组**阈值（没有 _zh 后缀），
            # 因为它的底座本身就是中文模型；此时上面的判断自然不生效，
            # 走 else 分支用条目自带的那组。两套阈值量纲差 5 倍
            # （gpt2 用 12/25，gpt2-chinese 用 2.88/7.68），不能混用。
            if _is_chinese(p) and ppl_low_zh and ppl_high_zh:
                lo, hi = float(ppl_low_zh), float(ppl_high_zh)
            else:
                lo, hi = float(ppl_low), float(ppl_high)
            ppl = self.perplexity(p, model, tok, device)
            if ppl <= lo:
                prob = 0.85
            elif ppl >= hi:
                prob = 0.15
            else:
                t = (ppl - lo) / max(hi - lo, 1e-6)
                prob = 0.85 - 0.7 * t
            out.append(prob)
            # 四档与判别分数独立：仅用于界面展示（论文的 Test-2 分布），
            # 不参与 prob 计算，故不影响任何已有阈值。
            buckets.append(self._rank_buckets(p, model, tok, device, max_tokens))
            if progress_cb:
                progress_cb(i + 1, total)
        self.last_buckets = buckets
        return out

    # ------------------------------------------------------ Test-2 rank 四档
    def _run_rank(
        self, paragraphs, device, max_tokens, progress_cb,
        ppl_low, ppl_high, ppl_low_zh, ppl_high_zh,
    ):
        """GLTR §3 Test-2：逐 token 的 rank 落在哪一档，输出四档占比。

        档位与论文完全一致（arXiv:1906.04043 §3）：

        ======  ============  ==========
        档位     rank 上限     论文配色
        ======  ============  ==========
        绿      <= 10         绿色
        黄      <= 100        黄色
        红      <= 1000       红色
        紫      其余          紫色
        ======  ============  ==========

        聚合：论文**从不把四档压成一个数**（它的产物是涂色图 + 直方图），
        但本项目接口约定返回 ``list[float]``，所以必须补一步聚合。
        实测 6 种聚合里 ``绿 - 紫`` 最好（中文 74.5% / 英文 94.67%），
        故取它，再线性映到 [0, 1] 区间中央的 0.5±0.35 带。

        **已知局限**：这样聚合后与 PPL 路线基本打平（中文还略差）。
        原因是四档信息集中在绿/紫两端，压扁就丢了；论文的 AUC 0.87
        来自「四档 + 逻辑回归」，需训练才能复现（未做）。
        """
        tok = self.tok(0)
        model = self.mdl(0, device)
        out = []
        buckets = []
        total = len(paragraphs)
        for i, p in enumerate(paragraphs):
            frac = self._rank_buckets(p, model, tok, device, max_tokens)
            buckets.append(frac)
            if frac is None:
                out.append(0.5)
            else:
                green, _yellow, _red, purple = frac
                score = green - purple
                # score 理论范围 [-1, 1]，实测集中在 [-0.2, 0.4]；
                # 直接线性映射到 0.85/0.15 两端，与 PPL 路线的输出口径一致
                prob = 0.5 + 0.35 * max(-1.0, min(1.0, score * 2.5))
                out.append(prob)
            if progress_cb:
                progress_cb(i + 1, total)
        self.last_buckets = buckets
        return out

    def _rank_buckets(self, text, model, tok, device, max_tokens):
        """算四档占比 (绿, 黄, 红, 紫)；文本过短时返回 None。

        rank 的定义：该位置真实 token 在模型预测分布里排第几（0 起）。
        用词表全排序的实际名次，不用近似 —— 论文的档位边界（10/100/1000）
        就是按真实名次定的。
        """
        import torch

        ids = self._encode_capped(text, tok, max_tokens, model).to(device)
        L = ids.size(1)
        if L < 2:
            return None
        with torch.no_grad():
            logits = model(ids).logits
        logp = torch.log_softmax(logits[:, :-1, :], dim=-1)[0]
        tgt = ids[0, 1:]
        # 每个位置的 rank = 有多少 token 的概率比真实 token 高
        rank = (logp > logp.gather(-1, tgt.unsqueeze(-1))).sum(dim=-1)
        n = int(rank.numel())
        if n == 0:
            return None
        r = rank.tolist()
        green = sum(1 for x in r if x <= 10) / n
        yellow = sum(1 for x in r if 10 < x <= 100) / n
        red = sum(1 for x in r if 100 < x <= 1000) / n
        purple = sum(1 for x in r if x > 1000) / n
        return green, yellow, red, purple

