import math
import os
import threading

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


class PerplexityEngine:
    """困惑度检测引擎：语言模型算困惑度，越低越像 AI（实验性）。"""

    type = "perplexity"

    def __init__(self, cfg, base_dir):
        self.cfg = cfg
        self.model_id = cfg["model_id"]
        self.model_dir = os.path.join(base_dir, "models", cfg["id"])
        self._tok = None
        self._models = {}
        self._lock = threading.Lock()

    def install(self, progress_cb=None):
        os.makedirs(self.model_dir, exist_ok=True)
        if progress_cb:
            progress_cb(10, "下载分词器...")
        self._get_tokenizer()
        if progress_cb:
            progress_cb(50, "下载模型参数（较大，请耐心等待）...")
        self._get_model("cpu")
        if progress_cb:
            progress_cb(100, "模型就绪")

    def _get_tokenizer(self):
        if self._tok is None:
            with self._lock:
                if self._tok is None:
                    self._tok = AutoTokenizer.from_pretrained(
                        self.model_id, cache_dir=self.model_dir
                    )
                    if self._tok.pad_token is None:
                        self._tok.pad_token = self._tok.eos_token
        return self._tok

    def _get_model(self, device):
        if device in self._models:
            return self._models[device]
        with self._lock:
            if device not in self._models:
                m = AutoModelForCausalLM.from_pretrained(
                    self.model_id, cache_dir=self.model_dir
                )
                m.to(device)
                m.eval()
                self._models[device] = m
        return self._models[device]

    def _ppl(self, text, model, tok, device, max_length=256):
        enc = tok(text, return_tensors="pt", truncation=False)
        ids = enc.input_ids.to(device)
        seq_len = ids.size(1)
        if seq_len < 2:
            return 100.0
        total_nll = 0.0
        n = 0
        with torch.no_grad():
            for begin in range(0, seq_len, max_length):
                end = min(begin + max_length, seq_len)
                chunk = ids[:, begin:end]
                if chunk.size(1) < 2:
                    break
                out = model(chunk, labels=chunk)
                total_nll += out.loss.item() * (end - begin)
                n += end - begin
                if end == seq_len:
                    break
        if n == 0:
            return 100.0
        return math.exp(min(total_nll / n, 700.0))

    def predict_paragraphs(
        self,
        paragraphs,
        device,
        ppl_high=25.0,
        ppl_low=12.0,
        progress_cb=None,
        **kwargs
    ):
        tok = self._get_tokenizer()
        model = self._get_model(device)
        out = []
        total = len(paragraphs)
        for i, p in enumerate(paragraphs):
            ppl = self._ppl(p, model, tok, device)
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
