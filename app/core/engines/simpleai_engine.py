import os
import threading

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


class SimpleAIEngine:
    """基于 HF 序列分类模型的中文/通用检测引擎。"""

    type = "classifier"

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
            progress_cb(55, "下载模型参数...")
        self._get_model("cpu")
        if progress_cb:
            progress_cb(100, "模型就绪")

    def _get_tokenizer(self):
        if self._tok is None:
            with self._lock:
                if self._tok is None:
                    # Try local cache first (offline mode)
                    try:
                        self._tok = AutoTokenizer.from_pretrained(
                            self.model_id, cache_dir=self.model_dir, local_files_only=True
                        )
                    except Exception:
                        self._tok = AutoTokenizer.from_pretrained(
                            self.model_id, cache_dir=self.model_dir
                        )
        return self._tok

    def _get_model(self, device):
        if device in self._models:
            return self._models[device]
        with self._lock:
            if device not in self._models:
                # Try local cache first (offline mode)
                try:
                    m = AutoModelForSequenceClassification.from_pretrained(
                        self.model_id, cache_dir=self.model_dir, local_files_only=True
                    )
                except Exception:
                    m = AutoModelForSequenceClassification.from_pretrained(
                        self.model_id, cache_dir=self.model_dir
                    )
                m.to(device)
                m.eval()
                self._models[device] = m
        return self._models[device]

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
        tok = self._get_tokenizer()
        model = self._get_model(device)
        idx = self._ai_index(model)
        out = []
        total = len(paragraphs)
        for i, p in enumerate(paragraphs):
            enc = tok(p[:max_len], truncation=True, max_length=512, return_tensors="pt")
            enc = {k: v.to(device) for k, v in enc.items()}
            with torch.no_grad():
                logits = model(**enc).logits
            prob = torch.softmax(logits, dim=1)[0, idx].item()
            out.append(prob)
            if progress_cb:
                progress_cb(i + 1, total)
        return out
