# -*- coding: utf-8 -*-
"""本地改写模型仓库：**只负责把模型拉到本地，不做任何改写**。

为什么要有这个引擎
------------------
规则降重引擎（``rule_engine.RuleRewriteEngine``）本身不需要模型，是本项目的
默认降重方案。而用户常备着几个「以后可能接上」的本地改写模型 —— 清单里给出
条目、能在「模型下载管理」里提前下好，但**当前版本不参与降重流程**。

如果这些条目没有对应的 ``impl``，点下载会直接报「引擎实现未加载」
（``engines.create_engine`` 找不到实现就抛异常）。所以这里补一个最小实现：
它只复用基类的下载 / 落盘机制，``rewrite()`` 系列方法一律明确拒绝调用。

⚠️ **不要把它当成降重引擎用** —— 调 ``rewrite()`` 会抛 RuntimeError，
这是有意为之：本引擎不含任何改写逻辑，规则引擎的地位不受任何影响。

为什么不用 seq2seq 微调模型
--------------------------
``google/mt5-small`` 和 ``uer/t5-v1_1-small-chinese`` 这类**只有预训练、
没有做过下游微调**的模型，官方模型卡明确写了必须微调才能用于改写任务。
直接拿去「降重」只会得到无意义输出（不是效果差，是不能用），所以清单里
不收它们 —— 详见 ``catalog.py`` 里对应位置的注释。

下载分两条路
------------
清单里每个模型条目可声明 ``files``（要取的原始文件名列表）：

* **声明了** → 走 ``BaseEngine.download_raw()``，用 ``huggingface_hub``
  按文件名精确取。用于**两种 transformers 读不了的布局**：
  ① GGUF 格式（llama.cpp 的权重）；② 仓库子目录里的完整权重（如 ``merged/``）。
* **没声明** → 走基类 ``from_pretrained``，用于标准 transformers 仓库。

两条路都只落盘，不在本进程加载权重。
"""
import os

from .base import BaseEngine
from .registry import register


@register("model_warehouse")
class ModelWarehouseEngine(BaseEngine):
    """本地模型仓库：可下载、可查看占用，但不执行任何推理改写。"""

    type = "repair"
    needs_torch = True
    # 只装权重不跑推理，因此不需要"打分模型"那套 kind 语义；
    # 但仍要真 torch（transformers 加载权重依赖它）。
    MODELS = ()
    MODEL_KINDS = ("causal", "seq2seq")

    # ------------------------------------------------------------- 明确拒绝
    def rewrite(self, paragraphs, indices=None, options=None):
        raise RuntimeError(
            "本条目只是本地模型仓库，不含改写能力。请使用默认的规则降重引擎。"
        )

    def rewrite_one(self, paragraph, options=None):
        raise RuntimeError(
            "本条目只是本地模型仓库，不含改写能力。请使用默认的规则降重引擎。"
        )

    def predict_paragraphs(self, paragraphs, device=None, progress_cb=None, **params):
        raise RuntimeError(
            "本条目只是本地模型仓库，不产出 AI 概率。请使用检测类引擎。"
        )

    # 审计 / 导出沿用基类的空实现即可 —— 这两个方法本来只服务于降重流程，
    # 而本引擎根本进不了那条流程。

    # --------------------------------------------------------------- 安装态
    def install_state(self):
        """给 UI 用的安装状态说明（已下载占用多大 / 未下载）。"""
        if not self.repos():
            return "no_models"
        return "installed" if self.is_installed() else "missing"

    # --------------------------------------------------------------- 下载
    def install(self, progress_cb=None):
        """下载模型。

        **按清单声明分两条路**（这是本引擎唯一需要区别对待的地方）：

        * 声明了 ``files`` —— 走 ``download_raw()`` 原样取文件。
          用于 **GGUF 格式**（llama.cpp 的权重，transformers 读不了）
          和**子目录权重**（如 ``merged/`` 下的完整模型）。
        * 没声明 ``files`` —— 走基类的 ``from_pretrained`` 路径，
          用于标准 transformers 仓库（Qwen3 系列、Paraphraser 等）。

        两条路都只**落盘**，不在本进程里加载权重。
        """
        declared = self.cfg.get("models") or []
        raw = [m for m in declared if isinstance(m, dict) and m.get("files")]
        if not raw:
            # 全是标准格式：交给基类（它会连分词器一起备好）
            return super().install(progress_cb)

        # 有需要原样取文件的条目：逐个处理
        os.makedirs(self.model_dir, exist_ok=True)
        n = len(raw)
        for i, m in enumerate(raw):
            repo = m.get("repo") or ""
            role = m.get("role") or repo
            files = m.get("files") or []
            if progress_cb:
                progress_cb(int(i * 100.0 / n), "下载 %s（%d/%d）..."
                            % (role, i + 1, n))
            self.download_raw(repo, files, progress_cb)
            if progress_cb:
                progress_cb(int((i + 1) * 100.0 / n), "%s 就绪" % role)

    def is_installed(self):
        """已下载判定。

        基类只认 ``.bin/.safetensors/.h5/.msgpack/.onnx``，**不认 ``.gguf``** ——
        而 GGUF 恰恰是本引擎最常见的落盘格式。所以这里补上，
        并额外识别「子目录权重」这种布局（``merged/model.safetensors``）。
        """
        if not self.repos():
            return True
        if not os.path.isdir(self.model_dir):
            return False
        for root, _dirs, files in os.walk(self.model_dir):
            for f in files:
                if f.endswith((".bin", ".safetensors", ".h5", ".msgpack",
                                ".onnx", ".gguf")):
                    return True
        return False
