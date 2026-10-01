# -*- coding: utf-8 -*-
"""Binoculars 双模型零样本检测引擎。

原理（arXiv:2401.12070v3 §3.3 式 4）
-----------------------------------
::

    B_{M1,M2}(s) = logPPL_{M1}(s) / log-xPPL_{M1,M2}(s)

分子是**对数困惑度**（式 2）::

    logPPL_M(s) = -1/L * sum_i log(Y_{i,x_i})

分母是**对数交叉困惑度**（式 3）::

    log-xPPL_{M1,M2}(s) = -1/L * sum_i M1(s)_i * log( M2(s)_i )

注意分子分母**都留在 log 域**（论文 LaTeX 源里两处都带 \\log 前缀），
比值量级在 0.7~1.2。B 越小越像 AI。

论文 Table 1 的参考数据：ChatGPT 生成的 capybara 文本 B = 0.73，
global threshold = 0.901。

实现要点（实测踩过的坑）
------------------------
1. 分母**不能**写成 exp(-lp_perf) —— 那会把量从 log 域(~1) 拉到实数域
   (~20-3000)，比值直接掉到 0.00x 量级，与阈值 0.901 量纲不匹配，
   squash 会恒饱和到 1.0（所有文本都判 AI）。
2. 分母必须是**交叉**困惑度，即 M1 的概率分布与 M2 的对数概率逐 token
   点积（见 BaseEngine.cross_perplexity），而不是"M2 自身的平均 NLL"。
3. 两个模型必须**共享词表**（论文 §3.1 的约束）。

关于默认模型组合
----------------
论文默认用 Falcon-7B-Instruct（分子）+ Falcon-7B（分母），阈值 0.901 是在
该组合的 reference dataset 上调出来的。本项目为控制体积改用
gpt2 + gpt2-medium（同词表、合计约 1.9GB、CPU 可跑）。
**换了模型组合就必须重标阈值**，0.9015 只作为初始值。

TODO（切回论文原版模型）
-------------------------------------------------
切回 Falcon-7B-Instruct + Falcon-7B（约 15GB）。
"""
from .base import BaseEngine, squash
from .registry import register


@register("binoculars")
class BinocularsEngine(BaseEngine):
    """双模型交叉困惑度比。"""

    type = "binoculars"
    MODEL_KINDS = ("causal", "causal")
    MODELS = (
        ("gpt2", "causal", "观察者模型 observer"),
        ("gpt2-medium", "causal", "表演者模型 performer"),
    )

    def predict_paragraphs(
        self,
        paragraphs,
        device,
        # ⚠️ 缺省值只是**兜底**，正常路径由清单参数覆盖（见 engines_catalog.json）。
        # 注意 0.9015 是**论文给 Falcon-7B + Falcon-7B-Instruct 的全局阈值**
        # （arXiv:2401.12070v3 Table 1），本机用 gpt2 + gpt2-medium，
        # **量纲/分布都不同，不可移植**。若调用方忘了传 threshold，
        # 拿到的是这个不可用的值 —— 所以清单里必须显式给。
        threshold=0.9015,
        scale=0.12,
        max_tokens=512,
        progress_cb=None,
        **kwargs
    ):
        tok = self.tok(0)
        observer = self.mdl(0, device)
        performer = self.mdl(1, device)
        out = []
        total = len(paragraphs)
        for i, p in enumerate(paragraphs):
            # 分子：observer 的 logPPL（论文式 2），留在 log 域
            log_ppl = self.avg_logprob(
                p, observer, tok, device, max_tokens=max_tokens
            )
            # 分母：observer 与 performer 的 log-xPPL（论文式 3，逐 token 点积）
            log_xppl = self.cross_perplexity(
                p, observer, performer, tok, device, max_tokens=max_tokens
            )
            if log_ppl == float("-inf") or log_xppl == float("-inf"):
                out.append(0.5)
            elif abs(log_xppl) < 1e-9:
                out.append(0.5)
            else:
                # B 越小越像 AI -> 用 “阈值 - B” 作为“越大越像 AI”的判别分数
                score = log_ppl / log_xppl
                out.append(squash(threshold - score, 0.0, scale))
            if progress_cb:
                progress_cb(i + 1, total)
        return out
