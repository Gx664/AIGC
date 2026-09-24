# -*- coding: utf-8 -*-
"""检测 / 修复引擎的通用基类。

把「离线优先加载、多模型缓存、下载进度」这些样板代码收敛到一处，
子类只需要声明 MODELS 并实现核心算法。

torch / transformers 一律延迟导入：这样即使本机被安全软件拦住了 torch，
引擎清单、设置界面仍然可以正常打开（只有真正跑检测时才会报错）。
"""
import math
import os
import threading

from ..settings import models_root


def squash(score, center=0.0, scale=1.0):
    """把任意方向的判别分数压到 [0,1]（score 越大越像 AI）。"""
    scale = max(abs(scale), 1e-6)
    return 1.0 / (1.0 + math.exp(-(score - center) / scale))


class BaseEngine:
    """所有引擎的基类（协议见 registry.py）。

    子类需要提供：
        impl          唯一实现名，与 catalog 条目的 "impl" 对应
        MODELS        ((repo, kind, role), ...)  兜底默认模型
        MODEL_KINDS   条目里没写 kind 时，按顺序推断的模型类型
    子类通常只需再实现 predict_paragraphs()。
    """

    impl = "base"
    MODELS = ()
    MODEL_KINDS = ("causal",)
    needs_torch = True

    def __init__(self, cfg, base_dir):
        self.cfg = cfg
        self.base_dir = base_dir
        self.model_id = cfg.get("model_id", "")
        self.model_dir = os.path.join(models_root(base_dir), cfg.get("id", self.impl))
        self._cache = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------- 模型清单
    def repos(self):
        """实际使用的模型清单。

        **条目声明即真相**：``cfg["models"]`` 怎么写，就用什么模型 —— 所以
        以后要换模型 / 加新模型，改清单即可，不必动引擎代码。清单缺省时
        退回类里的 MODELS。
        """
        kinds = tuple(self.MODEL_KINDS) or ("causal",)
        declared = self.cfg.get("models") or []
        out = []
        for i, m in enumerate(declared):
            fallback_kind = kinds[min(i, len(kinds) - 1)]
            if isinstance(m, str):
                repo, role, kind = m, m, fallback_kind
            elif isinstance(m, (list, tuple)) and m:
                repo = m[0]
                kind = m[1] if len(m) > 1 else fallback_kind
                role = m[2] if len(m) > 2 else repo
            elif isinstance(m, dict):
                repo = m.get("repo") or ""
                role = m.get("role") or repo
                kind = m.get("kind") or fallback_kind
            else:
                continue
            if repo:
                out.append((repo, kind, role))
        if out:
            return tuple(out)
        return tuple(self.MODELS)

    def resources(self):
        """本引擎用到的模型清单（供 UI 展示、迁移提示）。"""
        return [
            {"repo": repo, "kind": kind, "role": role}
            for repo, kind, role in self.repos()
        ]

    def is_installed(self):
        """模型是否已下载到本地（无模型的规则引擎恒为 True）。"""
        if not self.repos():
            return True
        if not os.path.isdir(self.model_dir):
            return False
        for root, _dirs, files in os.walk(self.model_dir):
            for f in files:
                if f.endswith((".bin", ".safetensors", ".h5", ".msgpack", ".onnx")):
                    return True
        return False

    # ------------------------------------------------------------- 加载模型
    @staticmethod
    def _is_local(repo):
        return os.path.isdir(repo)

    def _from_pretrained(self, loader, repo, **kw):
        """离线优先：本地缓存命中就直接用，没有再联网下载。"""
        if self._is_local(repo):
            return loader(repo, **kw)
        try:
            return loader(repo, cache_dir=self.model_dir, local_files_only=True, **kw)
        except Exception:
            return loader(repo, cache_dir=self.model_dir, **kw)

    def _load(self, repo, kind, device, **kw):
        from transformers import (
            AutoModelForCausalLM,
            AutoModelForSeq2SeqLM,
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )

        if kind == "tokenizer":
            tok = self._from_pretrained(AutoTokenizer.from_pretrained, repo, **kw)
            if getattr(tok, "pad_token", None) is None and getattr(tok, "eos_token", None):
                tok.pad_token = tok.eos_token
            return tok

        loaders = {
            "seq": AutoModelForSequenceClassification.from_pretrained,
            "causal": AutoModelForCausalLM.from_pretrained,
            "seq2seq": AutoModelForSeq2SeqLM.from_pretrained,
        }
        loader = loaders.get(kind, AutoModelForCausalLM.from_pretrained)
        model = self._from_pretrained(loader, repo, **kw)
        model.to(device or "cpu")
        model.eval()
        return model

    def _get(self, repo, kind, device=None, **kw):
        """带缓存的取模型 / 分词器；同一进程内只加载一次。"""
        key = (repo, kind, device)
        got = self._cache.get(key)
        if got is not None:
            return got
        with self._lock:
            got = self._cache.get(key)
            if got is None:
                got = self._load(repo, kind, device, **kw)
                self._cache[key] = got
        return got

    def tok(self, i=0):
        return self._get(self.repos()[i][0], "tokenizer")

    def mdl(self, i, device):
        kind = self.repos()[i][1]
        return self._get(self.repos()[i][0], kind, device)

    # --------------------------------------------------------------- 下载
    def install(self, progress_cb=None):
        """按模型清单逐个下载 / 准备；无模型的规则引擎直接返回。"""
        repos = self.repos()
        if not repos:
            if progress_cb:
                progress_cb(100, "无需下载（内置规则引擎）")
            return
        os.makedirs(self.model_dir, exist_ok=True)
        n = len(repos)
        for i, (repo, kind, role) in enumerate(repos):
            lo = int(i * 100.0 / n)
            if progress_cb:
                progress_cb(lo, "下载 %s（%d/%d）..." % (role, i + 1, n))
            if kind != "tokenizer":
                self._get(repo, "tokenizer")
            self._get(repo, kind, None if kind == "tokenizer" else "cpu")
            self._cache.pop((repo, kind, "cpu"), None)  # 释放占位，检测时按设备重载
            if progress_cb:
                progress_cb(int((i + 1) * 100.0 / n), "%s 就绪" % role)

    # ----------------------------------------------------------- 通用打分
    def avg_logprob(self, text, model, tok, device, chunk=256, max_tokens=0):
        """每 token 平均对数概率（分块计算，长文不会爆显存）。

        困惑度、条件概率曲率、双模型交叉困惑度都建立在这个量上，
        所以统一放在基类，避免每个引擎各写一遍。
        """
        import torch

        enc = tok(text, return_tensors="pt", truncation=False)
        ids = enc.input_ids.to(device)
        if max_tokens:
            ids = ids[:, :max_tokens]
        if ids.size(1) < 2:
            return float("-inf")
        total, n = 0.0, 0
        with torch.no_grad():
            for begin in range(0, ids.size(1), chunk):
                end = min(begin + chunk, ids.size(1))
                piece = ids[:, begin:end]
                if piece.size(1) < 2:
                    break
                out = model(piece, labels=piece)
                total += out.loss.item() * (end - begin)
                n += end - begin
                if end == ids.size(1):
                    break
        return -(total / n) if n else float("-inf")

    def perplexity(self, text, model, tok, device, chunk=256, max_tokens=0):
        lp = self.avg_logprob(text, model, tok, device, chunk, max_tokens)
        if lp == float("-inf"):
            return 100.0
        return math.exp(min(-lp, 700.0))

    # --------------------------------------------------------------- 推理
    def predict_paragraphs(self, paragraphs, device, progress_cb=None, **params):
        raise NotImplementedError

# aigc-toolkit: file purpose marker
