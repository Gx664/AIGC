# -*- coding: utf-8 -*-
"""SimpleAI / HC3 中文检测引擎：基于 HF 序列分类模型逐段判定。"""
from .base import BaseEngine
from .registry import register


@register("classifier")
class SimpleAIEngine(BaseEngine):
    """RoBERTa 序列分类：取 "AI" 那一类的 softmax 概率。"""

    type = "classifier"
    MODEL_KINDS = ("seq",)
    MODELS = (
        ("Hello-SimpleAI/chatgpt-detector-roberta-chinese", "seq", "中文判别模型（RoBERTa）"),
    )

    @staticmethod
    def _ai_index(model):
        labels = getattr(model.config, "id2label", None)
        if labels:
            for k, v in labels.items():
                low = str(v).lower()
                if any(x in low for x in ("ai", "chatgpt", "gpt", "machine")):
                    return int(k)
        return 1

    def predict_paragraphs(
        self, paragraphs, device, max_len=500, progress_cb=None, **kwargs
    ):
        import torch

        tok = self.tok(0)
        model = self.mdl(0, device)
        idx = self._ai_index(model)
        out = []
        total = len(paragraphs)
        for i, p in enumerate(paragraphs):
            enc = tok(p[:max_len], truncation=True, max_length=512, return_tensors="pt")
            enc = {k: v.to(device) for k, v in enc.items()}
            with torch.no_grad():
                logits = model(**enc).logits
            out.append(torch.softmax(logits, dim=1)[0, idx].item())
            if progress_cb:
                progress_cb(i + 1, total)
        return out
