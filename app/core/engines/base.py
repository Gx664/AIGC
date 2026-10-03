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

    @staticmethod
    def _pick_dtype(device):
        """按设备选模型权重的数据类型。

        为什么必须显式指定（实测踩过的坑）
        ----------------------------------
        不传 ``torch_dtype`` 时 transformers 默认按 **fp32** 加载。对
        gpt-neo-2.7B 这类模型，fp32 权重就要 **10.8GB**，加上推理时的
        激活值和 KV cache 会突破 16GB 显存。

        而 Windows 的 WDDM 在显存不足时**不会报错**，而是把放不下的部分
        换到系统内存（任务管理器里的「共享 GPU 内存」），靠 PCIe 搬运 ——
        带宽比显存低约 30 倍。表现是：GPU 利用率 94%、温度却只有 32℃、
        功耗 117W（正常应 280W+），**跑得极慢但一切"看起来正常"**。
        实测 200 条样本因此耗时数小时仍未完成。

        fp16 把权重压到一半，就能避免溢出；GPU 上精度损失对打分/生成
        的排序无实质影响。
        """
        try:
            import torch

            if device and str(device).startswith("cuda") and torch.cuda.is_available():
                return torch.float16
        except Exception:
            pass
        return None

    def _weight_gb(self, repo):
        """从引擎清单的 ``size`` 字段取该模型的实际占用（GB，fp16）。

        清单里的 ``size`` 是**模型卡上标注的加载大小**，不是下载体积 ——
        实测验证：fastdetectgpt 清单写 ``"约 5.4GB"``，fp16 加载后实测
        **5.33GB**（而磁盘上的 fp32 safetensors 是 10.0GB）。故**不再折算**。

        用途：`_check_vram()` 判断"余量是否紧张"。取不到时返回 0（跳过检查）。
        """
        import re

        for r, _kind, _role, size in self._models_with_size():
            if r != repo:
                continue
            m = re.search(r"([\d.]+)\s*(GB|MB)", size or "", re.I)
            if not m:
                continue
            val = float(m.group(1))
            if m.group(2).upper() == "MB":
                val /= 1024.0
            return val
        return 0.0

    def _models_with_size(self):
        """遍历清单里的 (repo, kind, role, size)（含 size 字段，供显存估算）。"""
        declared = self.cfg.get("models") or []
        kinds = tuple(self.MODEL_KINDS) or ("causal",)
        for i, m in enumerate(declared):
            if not isinstance(m, dict):
                continue
            repo = m.get("repo") or ""
            if not repo:
                continue
            kind = m.get("kind") or kinds[min(i, len(kinds) - 1)]
            yield repo, kind, m.get("role") or repo, m.get("size") or ""

    @staticmethod
    def _check_vram(repo, device, need_gb=0.0):
        """加载前粗估显存是否够用，分三档处理。

        为什么要三档（实测教训，2026-09-23）
        ------------------------------------
        原实现只在可用显存 < 2GB 时硬报错 —— 但**余量紧张比"不足"更常见也更隐蔽**：

        ============  ==============  ===========================  ==========
        可用显存       现象             实测（gpt-neo-2.7B fp16）    处置
        ============  ==============  ===========================  ==========
        >= need+3     正常            13.6 秒/条                   静默
        need~need+3   **静默慢 10 倍** 139.9 秒/条，温度 32℃        **警告**
                                    （GPU 在等，不在算）
        < 2GB         可能溢出到内存   共享显存 +2163MB              **报错**
                      WDDM 不报错
        ============  ==============  ===========================  ==========

        Windows WDDM 在显存不够时不报错，而是把数据换到系统内存走 PCIe
        （慢约 30 倍）。用户只会觉得软件卡死了。所以余量紧张也必须提示。

        :param need_gb: 该模型预计占用（GB，fp16 权重）；0 表示不检查余量
        """
        try:
            import torch

            if not (device and str(device).startswith("cuda")):
                return
            if not torch.cuda.is_available():
                return
            idx = 0
            try:
                idx = int(str(device).split(":")[1])
            except Exception:
                idx = 0
            free, _total = torch.cuda.mem_get_info(idx)
            free_gb = free / 1024 ** 3

            # 硬门槛：低于 2GB 直接报错（原行为，保留）
            if free_gb < 2.0:
                raise RuntimeError(
                    "显存不足：%s 当前可用 %.1fGB，低于 2GB 下限。"
                    "请关闭占用显卡的程序，或在设置里改用 CPU 运行。"
                    % (repo, free_gb)
                )

            # 余量紧张：不报错，但明确提示会变慢（新增）
            if need_gb and free_gb < need_gb + 3.0:
                import warnings

                warnings.warn(
                    "显存余量紧张：%s 预计占用约 %.1fGB，当前可用 %.1fGB。"
                    "推理不会报错，但可能比正常慢 10 倍以上（数据在显存与"
                    "系统内存之间搬运）。建议关闭占用显卡的程序。"
                    % (repo, need_gb, free_gb))
        except RuntimeError:
            raise
        except Exception:
            pass

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

        self._check_vram(repo, device, self._weight_gb(repo))
        loaders = {
            "seq": AutoModelForSequenceClassification.from_pretrained,
            "causal": AutoModelForCausalLM.from_pretrained,
            "seq2seq": AutoModelForSeq2SeqLM.from_pretrained,
        }
        loader = loaders.get(kind, AutoModelForCausalLM.from_pretrained)
        load_kw = dict(kw)
        # 未显式指定时按设备选半精度，避免 fp32 撑爆显存
        if "torch_dtype" not in load_kw and "dtype" not in load_kw:
            dt = self._pick_dtype(device)
            if dt is not None:
                load_kw["torch_dtype"] = dt
        model = self._from_pretrained(loader, repo, **load_kw)
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
    @staticmethod
    def _encode_capped(text, tok, max_tokens, model=None):
        """分词并截断到安全长度。

        为什么要截断（GPU 上会直接崩）
        ------------------------------
        gpt2 这类模型的 ``n_positions`` 固定（gpt2 = 1024）。中文经过
        byte-level BPE 分词后 token 数会暴涨 —— 实测 217 个汉字的段落，
        gpt2 分词后中位 363 token、**最长 1756 token**（一个汉字常占 2~3
        个 token）。一旦超过 n_positions，位置编码越界，CUDA 端会直接
        报 ``device-side assert: vectorized gather kernel index out of
        bounds`` 而崩掉整个进程。

        所以这里按 ``min(max_tokens, n_positions)`` 截断；``max_tokens=0``
        时用模型自身上限兜底。

        为什么不需要显式 ``import torch``：本方法只用 ``tok()`` 的返回值
        （``BatchEncoding``），下面的切片是张量切片，不引用 ``torch`` 里的
        任何名字。历史上这一行是多余的，会被静态检查当成未用导入。
        """
        enc = tok(text, return_tensors="pt", truncation=False)
        ids = enc.input_ids
        cap = int(max_tokens) if max_tokens else 0
        if model is not None:
            n_pos = getattr(getattr(model, "config", None), "n_positions", 0) or 0
            max_pos = getattr(getattr(model, "config", None), "max_position_embeddings", 0) or 0
            hard = n_pos or max_pos
            if hard:
                # 留 1 个位置给"预测下一位"
                hard = max(2, int(hard) - 1)
                cap = min(cap, hard) if cap else hard
        if cap and ids.size(1) > cap:
            ids = ids[:, :cap]
        return ids

    def avg_logprob(self, text, model, tok, device, chunk=256, max_tokens=0):
        """每 token 平均对数概率（`logPPL`，论文式 2）。

        困惑度、条件概率曲率、双模型交叉困惑度都建立在这个量上，
        所以统一放在基类，避免每个引擎各写一遍。

        为什么不按 chunk 分块（历史坑，实测数据）
        -----------------------------------------
        老实现把长文本切成 ``chunk`` 大小逐块前向、再按块长加权平均。这
        **在数学上不等价于整段计算**，三个原因叠加：

        1. **块首缺上下文** —— 从中间截断时，块首 token 丢了全部前文。实测
           某块首位的真值 NLL 是 10.46，而同块平均只有 4.53；
        2. **计数口径** —— causal LM 的 ``out.loss`` 内部已 shift，参与平均
           的是 ``L-1`` 个预测位，用 ``L`` 加权会让块首被重复计入；
        3. **位置编码重置** —— 每块独立喂入时 ``position_ids`` 都从 0 开始。

        实测同一段文本（94 token，gpt2）的改变 chunk 的偏差：

        ===========  ==========  ==========  ==========
        方案          chunk=16    chunk=4     chunk=1
        ===========  ==========  ==========  ==========
        原实现        24.4%       34.4%       67.0%
        仅修计数      15.1%       34.4%       67.0%
        加 1 token 重叠 9.96%     15.4%       16.3%
        ===========  ==========  ==========  ==========

        **无论怎么补，偏差都消不掉** —— 因为切分本身改变了模型看到的输入，
        所以这里直接**整段一次前向**，用 ``max_tokens`` 做长度上限（这也
        正是各引擎清单里 ``max_tokens`` 参数的本意，与论文一致）。

        ``chunk`` 参数保留仅为向后兼容，不再使用。
        """
        import torch
        import torch.nn.functional as F

        ids = self._encode_capped(text, tok, max_tokens, model).to(device)
        L = ids.size(1)
        if L < 2:
            return float("-inf")
        with torch.no_grad():
            logits = model(ids).logits
        # 位置 i 的 logits 预测 token i+1，共 L-1 个预测位
        logp = F.log_softmax(logits[:, :-1, :], dim=-1)
        tgt = ids[:, 1:]
        nll = -logp.gather(-1, tgt.unsqueeze(-1)).squeeze(-1)
        return -nll.mean().item()

    def cross_perplexity(self, text, model_a, model_b, tok, device,
                         chunk=256, max_tokens=0):
        """逐 token 交叉熵（Binoculars 式 (3) 的 ``log-xPPL``）。

        定义（arXiv:2401.12070 §3.1 式 3）::

            log-xPPL_{M1,M2}(s) = -1/L · Σ_i  M1(s)_i · log( M2(s)_i )

        即：对每个位置取 ``M1`` 的**概率分布**与 ``M2`` 的**对数概率分布**
        做点积（等价于以 M1 为权重、对 M2 的对数概率求期望），再对全部
        预测位取平均。要求两个模型共享词表（论文同款约束）。

        ``model_a`` / ``model_b`` 的 logits 必须同 shape（同词表）。
        """
        import torch
        import torch.nn.functional as F

        # 两个模型共享词表 -> 位置上限也要取共同的安全值
        cap_a = getattr(getattr(model_a, "config", None), "n_positions", 0) or 0
        cap_b = getattr(getattr(model_b, "config", None), "n_positions", 0) or 0
        caps = [c for c in (cap_a, cap_b) if c]
        # 借 model_a 走 _encode_capped，再按两者较小的上限二次截断
        ids = self._encode_capped(text, tok, max_tokens, model_a).to(device)
        if caps:
            hard = max(2, min(caps) - 1)
            if ids.size(1) > hard:
                ids = ids[:, :hard]
        L = ids.size(1)
        if L < 2:
            return float("-inf")
        with torch.no_grad():
            logits_a = model_a(ids).logits
            logits_b = model_b(ids).logits
        # 位置 i 的分布用于预测 token i+1 -> 取前 L-1 个位置
        logits_a = logits_a[:, :-1, :]
        logits_b = logits_b[:, :-1, :]
        p_a = F.softmax(logits_a, dim=-1)
        logp_b = F.log_softmax(logits_b, dim=-1)
        # 逐 token 交叉熵，再对预测位求平均
        ce = -(p_a * logp_b).sum(dim=-1)
        return -ce.mean().item()

    def perplexity(self, text, model, tok, device, chunk=256, max_tokens=0):
        lp = self.avg_logprob(text, model, tok, device, chunk, max_tokens)
        if lp == float("-inf"):
            return 100.0
        return math.exp(min(-lp, 700.0))

    # --------------------------------------------------------------- 推理
    def predict_paragraphs(self, paragraphs, device, progress_cb=None, **params):
        raise NotImplementedError
