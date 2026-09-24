# -*- coding: utf-8 -*-
"""GLTR 困惑度检测引擎：语言模型困惑度越低越像机器写的。"""
from .base import BaseEngine
from .registry import register


@register("perplexity")
class PerplexityEngine(BaseEngine):
    """统计派方法：PPL ≤ ppl_low 判 0.85，≥ ppl_high 判 0.15，中间线性插值。"""

    type = "perplexity"
    MODEL_KINDS = ("causal",)
    MODELS = (("gpt2", "causal", "困惑度打分模型"),)

    def predict_paragraphs(
        self,
        paragraphs,
        device,
        ppl_high=25.0,
        ppl_low=12.0,
        progress_cb=None,
        **kwargs
    ):
        tok = self.tok(0)
        model = self.mdl(0, device)
        out = []
        total = len(paragraphs)
        for i, p in enumerate(paragraphs):
            ppl = self.perplexity(p, model, tok, device)
            if ppl <= ppl_low:
                prob = 0.85
            elif ppl >= ppl_high:
                prob = 0.15
            else:
                t = (ppl - ppl_low) / max(ppl_high - ppl_low, 1e-6)
                prob = 0.85 - 0.7 * t
            out.append(prob)
            if progress_cb:
                progress_cb(i + 1, total)
        return out

# aigc-toolkit: file purpose marker
