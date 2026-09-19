# -*- coding: utf-8 -*-
"""修复类引擎：aigc-reduce 三轮降重协议 与 知网 5 种语言模式诊断。

这两个是**内置规则引擎**，不需要下载任何模型 —— 所以它们在线上的清单里
标的是「内置（无需下载）」。它们同样是可插拔的：注册表里换一个 impl，
就能用完全不同的降重 / 诊断策略把其中一个替换掉，而不必改主程序。

约定（和检测引擎一致）：类里声明 ``impl`` / ``MODELS``，框架负责创建与调度。
"""
from .base import BaseEngine
from .registry import register


@register("rule_rewrite")
class RuleRewriteEngine(BaseEngine):
    """aigc-reduce 三轮降重协议：受保护片段 + 确定性改写 + 语体守门。"""

    type = "repair"
    needs_torch = False
    MODELS = ()

    def rewrite(self, paragraphs, indices=None, options=None):
        """批量降重。indices 为 1 起始段落序号；None = 全部。"""
        from ..therapy import treat

        return treat(paragraphs, indices=indices, options=options or {})

    def rewrite_one(self, paragraph, options=None):
        from ..therapy import treat_paragraph

        return treat_paragraph(paragraph, options or {})

    def audit(self, text):
        """第三轮自检：返回改写后仍残留的 AI 信号。"""
        from ..therapy import audit_paragraph

        return audit_paragraph(text)

    def export_text(self, result, separator="\n\n"):
        from ..therapy import export_text

        return export_text(result, separator)

    def predict_paragraphs(self, paragraphs, device=None, progress_cb=None, **params):
        """修复引擎不产出 AI 概率；这里给出"可改写幅度"占位，便于统一接口调用。"""
        out = []
        for i, p in enumerate(paragraphs):
            r = self.rewrite_one(p, params.get("options") or {})
            out.append(float(r.get("mod_ratio", 0.0)))
            if progress_cb:
                progress_cb(i + 1, len(paragraphs))
        return out


@register("cnki_diagnose")
class CnkiDiagnoseEngine(BaseEngine):
    """知网 5 种语言模式 + 9 维扫描 + 11 种深度 AI 痕迹的段落级诊断。"""

    type = "repair"
    needs_torch = False
    MODELS = ()

    def diagnose(self, paragraphs, probs=None, threshold=0.5):
        from ..diagnosis import diagnose

        return diagnose(paragraphs, probs=probs, threshold=threshold)

    def scan(self, paragraphs):
        """只要 9 维全文扫描结果。"""
        from ..diagnosis import scan_9dim

        return scan_9dim(paragraphs)

    def pattern_name(self, pid, lang="zh"):
        from ..diagnosis import pattern_name

        return pattern_name(pid, lang)

    def predict_paragraphs(self, paragraphs, device=None, progress_cb=None, **params):
        """把段落风险等级映射成 0/0.5/1 的粗粒度分数，便于统一接口调用。"""
        risk_score = {"low": 0.1, "medium": 0.5, "high": 0.9}
        result = self.diagnose(
            paragraphs, params.get("probs"), params.get("threshold", 0.5)
        )
        para_map = {p.get("index"): p for p in result.get("paragraphs", [])}
        out = []
        for i, _p in enumerate(paragraphs, 1):
            item = para_map.get(i) or {}
            out.append(risk_score.get(item.get("risk", "low"), 0.1))
            if progress_cb:
                progress_cb(i, len(paragraphs))
        return out
