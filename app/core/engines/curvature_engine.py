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
import math
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
        """Fast-DetectGPT（arXiv:2310.05130v3 §2.3 式 3）。

        ::

            d = ( log p_theta(x|x) - mu_tilde ) / sigma_tilde

        其中 mu_tilde / sigma_tilde 是采样样本分数的均值与**标准差**
        （式 4：``sigma_tilde^2`` 是方差，故式 3 的分母取 sqrt）。
        论文 §3.2 的消融明确：这个归一化是有效性的关键，不能省。

        归一化后 d 是无量纲量，阈值才具备跨文本长度/领域的可比性。
        """
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
            if len(perturbed) >= 2:
                mean_pert = sum(perturbed) / len(perturbed)
                # 样本标准差（分母 n-1，与论文 Algorithm 1 第 4 步一致）
                var = sum((x - mean_pert) ** 2 for x in perturbed) / (
                    len(perturbed) - 1
                )
                sigma = math.sqrt(var)
                curvature = (base - mean_pert) / sigma if sigma > 1e-9 else 0.0
                out.append(squash(curvature, threshold, scale))
            elif perturbed:
                # 只有 1 个样本时估不出方差，退化为未归一化的旧行为
                out.append(squash(base - perturbed[0], threshold, scale))
            else:
                out.append(0.5)
            self._tick(progress_cb, i, total)
        return out

    @staticmethod
    def _self_sample(text, model, tok, device, max_tokens, prompt_ratio):
        """构造扰动样本 x̃ —— 论文 §2.3 的 **Conditional Independent Sampling**。

        为什么不能用 ``model.generate()``
        ----------------------------------
        论文（arXiv:2310.05130v3 §2.3）原文：

        > This sampling strategy is named **Conditional Independent Sampling**
        > ... we sample each token x̃_j **independently** from
        > q_phi(x̃_j | x_<j), where the conditioning is **only on the original
        > prefix** x_<j and **not on the previously sampled tokens**.

        即：每个 x̃_j 都只依赖**原文前缀**，彼此之间**不依赖**。
        而 `model.generate()` 是自回归的 —— 后一个 token 依赖前一个**已生成的**
        token，产出的分布不是论文要的 q_φ，样本多样性也偏低。

        做法：一次前向拿到整段 logits，再对每个位置**从各自的条件分布里
        独立抽样**。N 次采样因此可压成「1 次前向 + N 次抽样」，
        比 N 次串行 generate 快得多 —— 这也是论文叫 Fast 的原因之一。

        :param prompt_ratio: 原文保留作前缀的比例（其余位置待采样）
        """
        import torch

        enc = tok(text, return_tensors="pt", truncation=True, max_length=max_tokens)
        ids = enc.input_ids.to(device)
        n = ids.size(1)
        if n < 4:
            return None
        plen = max(1, min(n - 1, int(n * prompt_ratio)))
        with torch.no_grad():
            logits = model(ids).logits[0]          # (n, vocab)
        # 位置 j 的条件分布来自前一位 j-1 的 logits（因果 LM 的 shift）
        # 逐位独立采样：每个位置各抽一次，互不影响
        gen = []
        for j in range(plen, n):
            probs = torch.softmax(logits[j - 1].float(), dim=-1)
            gen.append(int(torch.multinomial(probs, 1).item()))
        if not gen:
            return None
        new_ids = torch.cat([ids[0, :plen], torch.tensor(gen, device=device)])
        return tok.decode(new_ids.tolist(), skip_special_tokens=True)

    # ---------------------------------------------------------- DetectGPT
    def _run_detect(
        self, paragraphs, device, samples, mask_ratio, span_max,
        threshold, scale, max_tokens, progress_cb,
    ):
        """DetectGPT（arXiv:2301.11305v2 §4 Algorithm 1）。

        ::

            d_hat_x = ( log p_theta(x) - mu_tilde ) / sqrt( sigma_tilde )

        论文 Algorithm 1 第 3~5 步：
            3: mu_tilde  <- (1/k) * sum_i log p_theta(x_tilde_i)
            4: sigma_tilde^2 <- (1/(k-1)) * sum_i (log p_theta(x_tilde_i) - mu_tilde)^2
            5: d_hat_x <- ( log p_theta(x) - mu_tilde ) / sqrt(sigma_tilde)

        注意第 4 步算的是**方差**，第 5 步取 sqrt 才是标准差 —— 与
        Fast-DetectGPT 式 (3) 的记号不同，这里以各论文自身的写法为准。
        论文 §5.3 指出：正因为有了这个归一化，阈值（"slightly below 0.1"）
        才能跨数据分布通用。
        """
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
            if len(perturbed) >= 2:
                mean_pert = sum(perturbed) / len(perturbed)
                var = sum((x - mean_pert) ** 2 for x in perturbed) / (
                    len(perturbed) - 1
                )
                # Algorithm 1 第 5 步：除以 sqrt(sigma_tilde^2)
                curvature = (base - mean_pert) / math.sqrt(var) if var > 1e-18 else 0.0
                out.append(squash(curvature, threshold, scale))
            elif perturbed:
                out.append(squash(base - perturbed[0], threshold, scale))
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
        # T5 输入上限 512，拼接后可能超限 -> 两侧各自截断，保证总量可控
        budget = 380
        half = budget // 2
        if len(left) > half:
            left = left[-half:]
        if len(right) > half:
            right = right[:half]
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
