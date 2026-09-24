# -*- coding: utf-8 -*-
"""概率曲率类检测引擎：Fast-DetectGPT（采样近似）与 DetectGPT（掩码扰动）。

两篇论文共用的骨架
------------------
    曲率 d = logP(x) − E[ logP(x̃) ]
    x̃ 是 x 的"轻微改写"。机器生成的文本站在语言模型概率的高地上，
    所以 d 偏正；人写的文本更平缓，d 接近 0 或为负。

两种扰动方式对应清单里的两个条目（用 params.mode 切换）
--------------------------------------------------------
* ``mode="fast"``   Fast-DetectGPT：直接用打分模型自己采样构造 x̃。
                    只要一个模型，快；是原论文采样近似（arXiv:2310.05130）。
* ``mode="detect"`` DetectGPT：用 T5 对随机片段做掩码补全构造 x̃。
                    更贴近论文（arXiv:2301.11305），但要多下一个模型、也更慢。

换模型不用改这里的代码：清单里 ``models`` 写什么就用什么。
"""
import random
import re

from .base import BaseEngine, squash
from .registry import register

_EXTRA_RE = re.compile(r"<extra_id_\d+\s*>(.*?)(?=<extra_id_\d+\s*>|</s>|$)", re.S)
_SPECIAL_RE = re.compile(r"</?s>|<pad>|<extra_id_\d+\s*>")


@register("curvature")
class CurvatureEngine(BaseEngine):
    """条件概率曲率检测。"""

    type = "curvature"
    MODEL_KINDS = ("causal", "seq2seq")
    MODELS = (
        ("gpt2", "causal", "对数概率打分模型"),
        ("t5-base", "seq2seq", "掩码扰动生成模型"),
    )

    # ---------------------------------------------------------------- 入口
    def predict_paragraphs(
        self,
        paragraphs,
        device,
        mode="fast",
        samples=5,
        mask_ratio=0.15,
        span_max=5,
        threshold=0.0,
        scale=0.6,
        max_tokens=512,
        prompt_ratio=0.5,
        progress_cb=None,
        **kwargs
    ):
        mode = (mode or "fast").lower()
        if mode == "detect":
            return self._run_detect(
                paragraphs, device, samples, mask_ratio, span_max,
                threshold, scale, max_tokens, progress_cb,
            )
        return self._run_fast(
            paragraphs, device, samples, threshold, scale,
            max_tokens, prompt_ratio, progress_cb,
        )

    @staticmethod
    def _tick(progress_cb, i, total):
        if progress_cb:
            progress_cb(i + 1, total)

    # ------------------------------------------------------ Fast-DetectGPT
    def _run_fast(
        self, paragraphs, device, samples, threshold, scale,
        max_tokens, prompt_ratio, progress_cb,
    ):
        tok = self.tok(0)
        model = self.mdl(0, device)
        out = []
        total = len(paragraphs)
        for i, p in enumerate(paragraphs):
            base = self.avg_logprob(p, model, tok, device, max_tokens=max_tokens)
            if base == float("-inf"):
                out.append(0.5)
                self._tick(progress_cb, i, total)
                continue
            perturbed = []
            for _ in range(max(1, int(samples))):
                fake = self._self_sample(p, model, tok, device, max_tokens, prompt_ratio)
                if not fake:
                    continue
                lp = self.avg_logprob(fake, model, tok, device, max_tokens=max_tokens)
                if lp != float("-inf"):
                    perturbed.append(lp)
            if perturbed:
                mean_pert = sum(perturbed) / len(perturbed)
                out.append(squash(base - mean_pert, threshold, scale))
            else:
                out.append(0.5)
            self._tick(progress_cb, i, total)
        return out

    @staticmethod
    def _self_sample(text, model, tok, device, max_tokens, prompt_ratio):
        """以原文前半为前缀让模型自己续写，得到扰动样本 x̃。"""
        import torch

        enc = tok(text, return_tensors="pt", truncation=True, max_length=max_tokens)
        ids = enc.input_ids.to(device)
        n = ids.size(1)
        if n < 4:
            return None
        plen = max(1, min(n - 1, int(n * prompt_ratio)))
        pad = getattr(tok, "pad_token_id", None)
        if pad is None:
            pad = getattr(tok, "eos_token_id", 0) or 0
        with torch.no_grad():
            seq = model.generate(
                ids[:, :plen],
                do_sample=True,
                top_p=0.96,
                temperature=1.0,
                max_new_tokens=n - plen,
                pad_token_id=pad,
            )
        return tok.decode(seq[0], skip_special_tokens=True)

    # ---------------------------------------------------------- DetectGPT
    def _run_detect(
        self, paragraphs, device, samples, mask_ratio, span_max,
        threshold, scale, max_tokens, progress_cb,
    ):
        tok = self.tok(0)
        model = self.mdl(0, device)
        t5tok = self.tok(1)
        t5 = self.mdl(1, device)
        out = []
        total = len(paragraphs)
        for i, p in enumerate(paragraphs):
            base = self.avg_logprob(p, model, tok, device, max_tokens=max_tokens)
            if base == float("-inf"):
                out.append(0.5)
                self._tick(progress_cb, i, total)
                continue
            perturbed = []
            for _ in range(max(1, int(samples))):
                fake = self._mask_perturb(
                    p, t5, t5tok, device, mask_ratio, span_max, max_tokens
                )
                if not fake:
                    continue
                lp = self.avg_logprob(fake, model, tok, device, max_tokens=max_tokens)
                if lp != float("-inf"):
                    perturbed.append(lp)
            if perturbed:
                mean_pert = sum(perturbed) / len(perturbed)
                out.append(squash(base - mean_pert, threshold, scale))
            else:
                out.append(0.5)
            self._tick(progress_cb, i, total)
        return out

    def _mask_perturb(self, text, t5, t5tok, device, mask_ratio, span_max, max_tokens):
        """随机挖掉一小段，用 T5 补全后拼回原文 —— 这就是 x̃。"""
        ids = t5tok.encode(text, add_special_tokens=False)[:max_tokens]
        n = len(ids)
        if n < 6:
            return None
        cap = max(1, min(int(span_max), max(1, int(round(n * mask_ratio)))))
        span = random.randint(1, cap)
        s = random.randrange(1, max(2, n - span))
        e = min(s + span, n - 1)
        if e <= s:
            return None
        left = t5tok.decode(ids[:s], skip_special_tokens=True)
        right = t5tok.decode(ids[e:], skip_special_tokens=True)
        prompt = "<extra_id_0> %s <extra_id_1> %s" % (left, right)
        enc = t5tok(prompt, return_tensors="pt", truncation=True, max_length=512)
        enc = {k: v.to(device) for k, v in enc.items()}
        import torch

        with torch.no_grad():
            gen = t5.generate(**enc, max_new_tokens=48, do_sample=False)
        filled = self._extract_fill(t5tok.decode(gen[0], skip_special_tokens=False))
        if not filled:
            return None
        return "%s%s%s" % (left, filled, right)

    @staticmethod
    def _extract_fill(decoded):
        """从 T5 的 '<extra_id_0> 填的内容 <extra_id_1> ...' 里取中间那段。"""
        m = _EXTRA_RE.search(decoded or "")
        if not m:
            return ""
        return _SPECIAL_RE.sub("", m.group(1)).strip()

# aigc-toolkit: file purpose marker
