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
"""
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
