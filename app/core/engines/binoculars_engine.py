# -*- coding: utf-8 -*-
"""Binoculars 双模型零样本检测引擎。

原理（arXiv:2401.12070）
------------------------
用一对**同词表**的模型给同一段文本打分：

    B(x) = logPPL_observer(x) / crossPPL_performer(x)

两个模型"看到"的都是同一段文字，但困惑度差异在机器生成的文本上会塌缩，
所以 B 越小越像 AI。因为看的是比值而不是绝对值，它不需要按领域重调阈值。

默认的轻量组合是 gpt2 + gpt2-medium（同词表、合计约 1.9GB、CPU 可跑）；
要换成论文里的 Falcon 组合，改清单里的 ``models`` 即可，不必动代码。
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
            lp_obs = self.avg_logprob(p, observer, tok, device, max_tokens=max_tokens)
            lp_perf = self.avg_logprob(p, performer, tok, device, max_tokens=max_tokens)
            if lp_obs == float("-inf") or lp_perf == float("-inf"):
                out.append(0.5)
            else:
                import math

                log_ppl = -lp_obs                       # 对数困惑度（越小越像 AI）
                cross_ppl = math.exp(min(-lp_perf, 700.0))
                score = log_ppl / max(cross_ppl, 1e-6)
                # B 越小越像 AI，所以用 阈值 − B 作为"越大越像 AI"的判别分数
                out.append(squash(threshold - score, 0.0, scale))
            if progress_cb:
                progress_cb(i + 1, total)
        return out

# aigc-toolkit: file purpose marker
