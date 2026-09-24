# -*- coding: utf-8 -*-
"""本地 AIGC 诊断引擎（纯标准库，完全离线）。

融合两个开源项目的方法论：
- aigc-reduce：9 维特征扫描 + 11 种深度 AI 痕迹模式 + 口语化/破折号语体门禁
- cnki-aigc---skill：知网检测器“5 种语言模式”

输出：结构化 JSON 诊断报告，段落级（可精确到句）。
"""

import math
import re

from .aigc_rules import (
    ABSTRACT_NOUN_CHAIN,
    COLLOQUIAL_TERMS,
    DEEP_PATTERNS,
    OVERLAP_CONNECTIVES,
    PARA_END_META,
    PARALLEL_PATTERNS,
    PASSIVE_MARKERS,
    REPORT_TEMPLATES,
    SUGGESTIONS,
    TEMPLATE_PATTERNS,
)


EM_DASH = "——"
FULLWIDTH_PUNCT = set("，。！？；：、""''（）【】《》")


# ─────────────────────────────────────────────────────────────
# 基础切分
# ─────────────────────────────────────────────────────────────
def split_sentences(text):
    """按句切分（避开小数点和引用编号）。"""
    parts = re.split(r"[。！？!?\n]|(?<!\d)\.|\.(?!\d)", text)
    return [s.strip() for s in parts if s.strip() and len(s.strip()) > 5]


def _para_len_stats(paragraphs):
    lens = [len(p) for p in paragraphs]
    avg = sum(lens) / len(lens) if lens else 0
    var = sum((x - avg) ** 2 for x in lens) / len(lens) if lens else 0
    return avg, math.sqrt(var)


def _template_hits(text):
    hits = []
    for pattern in TEMPLATE_PATTERNS:
        for m in re.finditer(pattern, text, re.MULTILINE):
            hits.append(m.group(0))
    return hits


def _passive_count(text):
    total = 0
    for pattern in PASSIVE_MARKERS:
        total += len(re.findall(pattern, text))
    return total


def _cv(sent_lengths):
    if len(sent_lengths) < 3:
        return 0.0
    avg = sum(sent_lengths) / len(sent_lengths)
    var = sum((x - avg) ** 2 for x in sent_lengths) / len(sent_lengths)
    return (var ** 0.5) / max(avg, 1)


# ─────────────────────────────────────────────────────────────
# 9 维扫描（对齐 aigc_scan.py）
# ─────────────────────────────────────────────────────────────
def scan_9dim(paragraphs):
    text = "\n".join(paragraphs)
    sentences = split_sentences(text)

    template = _template_hits(text)
    passive = _passive_count(text)
    sent_lens = [len(s) for s in sentences]
    cv = _cv(sent_lens)
    if cv < 0.25:
        burst_risk = "high"
    elif cv < 0.35:
        burst_risk = "medium"
    elif cv < 0.5:
        burst_risk = "low"
    else:
        burst_risk = "ok"

    para_lens = [len(p) for p in paragraphs]
    symmetric_runs = 0
    run = 0
    for i in range(1, len(para_lens)):
        dev = abs(para_lens[i] - para_lens[i - 1]) / max(para_lens[i - 1], 1)
        if dev < 0.2:
            run += 1
        else:
            if run >= 2:
                symmetric_runs += 1
            run = 0
    if run >= 2:
        symmetric_runs += 1

    nested = len(re.findall(r"[（(]\d+[）)]", text))
    colon_lists = len(re.findall(r"[：:]\s*.+?[；;]\s*.+?[；;]", text))
    comma_count = text.count("，") + text.count(",")
    commas_per_sent = round(comma_count / max(len(sentences), 1), 2)
    colloquial_hits = []
    for term in COLLOQUIAL_TERMS:
        c = text.count(term)
        if c:
            colloquial_hits.extend([term] * c)
    dash_over_paras = sum(1 for p in paragraphs if p.count(EM_DASH) >= 2)

    risk_count = 0
    if len(template) > 3:
        risk_count += 1
    if passive / max(len(sentences), 1) > 0.3:
        risk_count += 1
    if cv < 0.35:
        risk_count += 1
    if symmetric_runs:
        risk_count += 1
    if nested > 3:
        risk_count += 1
    if commas_per_sent > 2.5:
        risk_count += 1
    if colloquial_hits:
        risk_count += 1
    if dash_over_paras:
        risk_count += 1

    if risk_count >= 4:
        overall = "high"
    elif risk_count >= 2:
        overall = "medium"
    else:
        overall = "low"

    return {
        "template": {
            "count": len(template),
            "density_per_1000": round(len(template) / max(len(text), 1) * 1000, 2),
            "matches": template[:12],
        },
        "passive": {
            "count": passive,
            "per_sentence": round(passive / max(len(sentences), 1), 3),
        },
        "burstiness": {
            "avg_len": round(sum(sent_lens) / max(len(sent_lens), 1), 1),
            "cv": round(cv, 3),
            "risk": burst_risk,
        },
        "para_symmetry": {
            "avg_len": round(sum(para_lens) / max(len(para_lens), 1), 1),
            "symmetrical_runs": symmetric_runs,
        },
        "nested_numbers": {"count": nested},
        "colon_lists": {"count": colon_lists},
        "punctuation": {"commas_per_sentence": commas_per_sent},
        "colloquial": {"count": len(colloquial_hits), "terms": sorted(set(colloquial_hits))},
        "dash_density": {"total": text.count(EM_DASH), "over_limit_paras": dash_over_paras},
        "overall": overall,
        "risk_count": risk_count,
    }


# ─────────────────────────────────────────────────────────────
# 知网“5 种语言模式”（cnki-aigc---skill）
# ─────────────────────────────────────────────────────────────
_TERM_STOP = set("研究分析结果表明本文论文问题方法数据模型实验发现证明认为显示体现呈现影响改变促进推动提升增强降低减少增加过程阶段方面因素情况问题现象结果结论作用意义价值水平程度范围内容形式方式手段途径渠道环节机制路径框架体系结构特征特点性质属性功能效果效率性能质量数量规模速度频率强度浓度温度压力条件环境背景领域方向趋势变化发展进步深入广泛全面系统整体综合重要关键核心主要基本显著明显大幅较高较低相对更加更为较为十分非常尤其特别是即以及和与或而并且因此从而进而由此")


def _candidate_terms(text):
    """提取段内重复出现 2 次以上、长度 2-6 的候选术语。"""
    counts = {}
    for m in re.finditer(r"[\u4e00-\u9fff]{2,6}", text):
        w = m.group(0)
        if w[0] in "的了着在是这与及和或把被对于从向以" or w[-1] in "的了着吗呢吧啊":
            continue
        counts[w] = counts.get(w, 0) + 1
    terms = [w for w, c in counts.items() if c >= 2]
    terms.sort(key=len, reverse=True)
    out = []
    for w in terms:
        if any(w in t for t in out):
            continue
        out.append(w)
    return out[:8]


def _term_at_subject(sentences, terms):
    """术语出现在句首主语位置（后接系词/使役/影响类动词）。"""
    evidence = []
    for s in sentences:
        for t in terms:
            m = re.match(
                r"^(?:该|其|本研究中)?%s(?:是|在|对|为|使|将|作为|体现|促进|影响|增强|削弱|提升|降低|表明|反映|决定|作用于)"
                % re.escape(t),
                s,
            )
            if m:
                evidence.append("术语“%s”位于句首主语位置：%s…" % (t, s[:40]))
                break
    return evidence


def _analyze_cnki_5(para, doc_stats, para_index, doc_para_count):
    sentences = split_sentences(para)
    sent_lens = [len(s) for s in sentences]
    cv = _cv(sent_lens)
    patterns = []

    # 模式 1：句法节奏可预测性
    if cv < 0.25 and len(sentences) >= 3:
        patterns.append({
            "id": "burstiness",
            "zh": "句法节奏可预测",
            "en": "Predictable rhythm",
            "severity": "high",
            "evidence": ["句长变异系数 CV=%.3f（<0.25 为高风险），句子长度过于均匀" % cv],
        })
    elif cv < 0.35 and len(sentences) >= 3:
        patterns.append({
            "id": "burstiness",
            "zh": "句法节奏可预测",
            "en": "Predictable rhythm",
            "severity": "medium",
            "evidence": ["句长变异系数 CV=%.3f（0.25-0.35 为中风险），句子变化度偏低" % cv],
        })

    # 模式 2：信息密度均匀性（段落长度贴近全文平均 + 模板句偏多）
    avg_para_len, _ = doc_stats["para_len"]
    density = abs(len(para) - avg_para_len) / max(avg_para_len, 1)
    template_n = len(_template_hits(para))
    if density < 0.15 and template_n >= 2:
        patterns.append({
            "id": "density",
            "zh": "信息密度均匀",
            "en": "Uniform density",
            "severity": "medium",
            "evidence": [
                "段落长度 %d 字与全文平均 %d 字偏差 <15%%，且含 %d 处模板句，信息密度过于均匀"
                % (len(para), int(avg_para_len), template_n)
            ],
        })

    # 模式 3：术语的句法位置固定
    terms = _candidate_terms(para)
    ev = _term_at_subject(sentences, terms)
    if len(ev) >= 2:
        patterns.append({
            "id": "term_position",
            "zh": "术语句法位置固定",
            "en": "Fixed term position",
            "severity": "medium",
            "evidence": ev[:3],
        })

    # 模式 4：连接词功能重叠
    conn = []
    for c in OVERLAP_CONNECTIVES:
        n = para.count(c)
        if n:
            conn.append("%s×%d" % (c, n))
    if len(conn) >= 2:
        patterns.append({
            "id": "connective",
            "zh": "连接词功能重叠",
            "en": "Overlapping connectives",
            "severity": "medium",
            "evidence": ["因果推进连接词集中出现：%s（功能高度重叠）" % "、".join(conn)],
        })

    # 模式 5：模板段功能全等性
    # 5.1 三/四项工整排比
    para_evidence = []
    for pat in PARALLEL_PATTERNS:
        for m in re.finditer(pat, para):
            para_evidence.append("工整排比：%s…" % m.group(0)[:45])
    # 5.2 抽象名词链
    for m in re.finditer(ABSTRACT_NOUN_CHAIN, para):
        para_evidence.append("抽象名词链：%s" % m.group(0))
    # 5.3 段尾元话语
    tail = para[-60:]
    if PARA_END_META.search(tail):
        para_evidence.append("段尾元话语收束：…%s" % tail.strip()[-25:])
    # 5.4 模板化报告句
    for pat in REPORT_TEMPLATES:
        for m in re.finditer(pat, para):
            para_evidence.append("模板化报告句：%s" % m.group(0))
            break
    # 5.5 平行铺陈 + 末尾收束
    start_parallel = len(re.findall(r"在[^，。；]{2,12}(?:方面|角度)[，,]", para[:120]))
    if start_parallel >= 3 and PARA_END_META.search(tail):
        para_evidence.append("平行铺陈开头 + 段尾收束（%d 处“在…方面”）" % start_parallel)
    if para_evidence:
        patterns.append({
            "id": "parallel",
            "zh": "模板段功能全等",
            "en": "Template-functional paragraphs",
            "severity": "high",
            "evidence": para_evidence[:5],
        })

    return patterns


# ─────────────────────────────────────────────────────────────
# 11 种深度 AI 痕迹模式
# ─────────────────────────────────────────────────────────────
def _analyze_deep_11(para, doc_paired_contrast_count):
    sentences = split_sentences(para)
    patterns = []

    def add(pid, severity, evidence):
        meta = DEEP_PATTERNS[pid]
        patterns.append({
            "id": pid,
            "zh": meta["zh"],
            "en": meta["en"],
            "severity": severity,
            "evidence": evidence[:3],
        })

    for pid in ("significance", "rule_of_three", "copula_avoidance",
                "vague_attribution", "formulaic_challenge",
                "suspended_analysis", "generic_conclusion", "false_range",
                "paired_contrast"):
        meta = DEEP_PATTERNS[pid]
        evidence = []
        for pat in meta.get("regex", []):
            for m in re.finditer(pat, para):
                evidence.append(m.group(0)[:60])
        if evidence:
            sev = "high" if len(evidence) >= 2 or pid in (
                "vague_attribution", "suspended_analysis", "generic_conclusion"
            ) else "medium"
            add(pid, sev, evidence)

    # 同义词轮换：同一语义组内 ≥3 个不同词交替出现
    for group in DEEP_PATTERNS["synonym_cycling"]["groups"]:
        present = [w for w in group if w in para]
        if len(present) >= 3:
            add("synonym_cycling", "medium", ["疑似同义词轮换：%s 交替出现" % " / ".join(present)])
            break

    # 破折号过度
    n_dash = para.count(EM_DASH)
    if n_dash >= 2:
        add("em_dash", "high", ["本段含 %d 个破折号（阈值：每段 ≤1 个）" % n_dash])

    # 成对转折：段内 ≥2 处，或全文多处段落以转折收束
    pc = len(re.findall(r"不是[^。！？]{2,35}而是|但至少|不代表|不等于|即使[^。！？]{2,35}也", para))
    if pc >= 2 or (pc >= 1 and doc_paired_contrast_count >= 3):
        # 已经由正则循环加入，避免重复
        if not any(p["id"] == "paired_contrast" for p in patterns):
            add("paired_contrast", "medium", ["成对转折收束 %d 处，全文多处段落采用同构收束" % pc])

    return patterns


# ─────────────────────────────────────────────────────────────
# 语体守门（降重过度预警）
# ─────────────────────────────────────────────────────────────
def _style_guard(para):
    issues = []
    hits = [t for t in COLLOQUIAL_TERMS if t in para]
    if hits:
        issues.append("口语化/网络用语：%s" % "、".join(hits))
    if para.count(EM_DASH) >= 2:
        issues.append("破折号 %d 个（每段应 ≤1 个）" % para.count(EM_DASH))
    return issues


# ─────────────────────────────────────────────────────────────
# 汇总建议（按模式 id 去重排序）
# ─────────────────────────────────────────────────────────────
def _suggestions_for(patterns):
    seen = []
    out = []
    for p in patterns:
        pid = p["id"]
        if pid in seen:
            continue
        seen.append(pid)
        s = SUGGESTIONS.get(pid)
        if s:
            out.append({"zh": s["zh"], "en": s["en"]})
    return out


# ─────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────
def diagnose(paragraphs, probs=None, threshold=0.5):
    """诊断整篇文本。

    paragraphs: 段落列表（与检测引擎输出一致）
    probs:      可选，检测引擎给出的逐段 AI 概率（None = 未检测）
    threshold:  检测阈值（用于标记疑似段落）
    """
    paragraphs = [p for p in paragraphs if p and p.strip()]
    if not paragraphs:
        return {
            "summary": {"overall_risk": "low", "total_paragraphs": 0},
            "scan9": {},
            "paragraphs": [],
        }

    text = "\n".join(paragraphs)
    sentences_all = split_sentences(text)
    scan9 = scan_9dim(paragraphs)
    avg_para_len, _ = _para_len_stats(paragraphs)
    doc_stats = {"para_len": (avg_para_len, 0)}

    # 全文成对转折计数（供段落级判断“多处同构收束”）
    doc_paired = 0
    for p in paragraphs:
        doc_paired += len(re.findall(r"不是[^。！？]{2,35}而是|但至少|不代表|不等于|即使[^。！？]{2,35}也", p))

    para_results = []
    top_counts = {}
    high = medium = 0
    style_warnings = []

    for i, para in enumerate(paragraphs, 1):
        pats = _analyze_cnki_5(para, doc_stats, i, len(paragraphs))
        pats += _analyze_deep_11(para, doc_paired)

        # 风险评分
        score = 0.0
        for p in pats:
            w = 2.0 if p["severity"] == "high" else 1.2
            score += w * min(len(p["evidence"]), 3)
        # 9 维中的段落级信号也计入
        template_n = len(_template_hits(para))
        score += min(template_n, 4) * 0.8
        passive_n = _passive_count(para)
        sents = split_sentences(para)
        if sents and passive_n / len(sents) > 0.3:
            score += 1.0
        if para.count("，") > 2.5 * max(len(sents), 1):
            score += 0.5

        risk_score = round(min(1.0, score / 10.0), 3)
        if risk_score >= 0.5:
            level = "high"
            high += 1
        elif risk_score >= 0.28:
            level = "medium"
            medium += 1
        else:
            level = "low"

        guard = _style_guard(para)
        if guard:
            style_warnings.extend(guard)

        sentences_out = []
        for s in sents:
            markers = []
            if any(c in s for c in OVERLAP_CONNECTIVES):
                markers.append("因果连接词")
            if len(s) >= 50:
                markers.append("长句(%d字)" % len(s))
            if s.count(EM_DASH) >= 1:
                markers.append("破折号×%d" % s.count(EM_DASH))
            if _template_hits(s):
                markers.append("模板句")
            sentences_out.append({
                "text": s,
                "length": len(s),
                "band": "20-35" if 20 <= len(s) <= 35 else ("long" if len(s) > 35 else "short"),
                "markers": markers,
            })

        for p in pats:
            top_counts[p["id"]] = top_counts.get(p["id"], 0) + 1

        para_results.append({
            "index": i,
            "text": para,
            "ai_prob": round(probs[i - 1], 3) if probs and i - 1 < len(probs) and probs[i - 1] is not None else None,
            "suspicious": bool(probs and i - 1 < len(probs) and probs[i - 1] is not None and probs[i - 1] >= threshold),
            "risk_score": round(risk_score, 3),
            "risk_level": level,
            "patterns": pats,
            "sentences": sentences_out,
            "suggested_actions": _suggestions_for(pats),
        })

    top_patterns = [
        {
            "id": pid,
            "zh": DEEP_PATTERNS.get(pid, {"zh": pid})["zh"]
            if pid in DEEP_PATTERNS else _PATTERN_ZH.get(pid, pid),
            "en": DEEP_PATTERNS.get(pid, {"en": pid})["en"]
            if pid in DEEP_PATTERNS else _PATTERN_EN.get(pid, pid),
            "count": c,
        }
        for pid, c in sorted(top_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return {
        "summary": {
            "total_chars": len(text),
            "total_paragraphs": len(paragraphs),
            "total_sentences": len(sentences_all),
            "high_risk_paras": high,
            "medium_risk_paras": medium,
            "overall_risk": scan9["overall"],
            "risk_count_9dim": scan9["risk_count"],
            "style_warnings": style_warnings[:8],
            "top_patterns": top_patterns[:10],
        },
        "scan9": scan9,
        "paragraphs": para_results,
    }


_PATTERN_ZH = {
    "burstiness": "句法节奏可预测",
    "density": "信息密度均匀",
    "term_position": "术语句法位置固定",
    "connective": "连接词功能重叠",
    "parallel": "模板段功能全等",
    "significance": "重要性膨胀",
    "synonym_cycling": "同义词轮换",
    "rule_of_three": "三板斧强迫症",
    "copula_avoidance": "系词回避",
    "vague_attribution": "模糊归因",
    "formulaic_challenge": "公式化挑战段",
    "suspended_analysis": "悬浮式分析",
    "generic_conclusion": "空洞结论",
    "em_dash": "破折号过度使用",
    "false_range": "虚假范围",
    "paired_contrast": "成对转折收束",
    "colloquial": "口语化/网络用语",
    "dash_guard": "破折号密度",
    "template": "模板句式",
    "passive": "被动语态",
    "para_symmetry": "段落对称性",
    "nested_numbers": "嵌套编号",
    "colon_list": "冒号并列",
    "punctuation": "标点规律",
}

_PATTERN_EN = {
    "burstiness": "Predictable rhythm",
    "density": "Uniform density",
    "term_position": "Fixed term position",
    "connective": "Overlapping connectives",
    "parallel": "Template-functional paragraphs",
    "significance": "Significance inflation",
    "synonym_cycling": "Synonym cycling",
    "rule_of_three": "Rule of three",
    "copula_avoidance": "Copula avoidance",
    "vague_attribution": "Vague attribution",
    "formulaic_challenge": "Formulaic challenges",
    "suspended_analysis": "Suspended analysis",
    "generic_conclusion": "Generic conclusions",
    "em_dash": "Em-dash overuse",
    "false_range": "False ranges",
    "paired_contrast": "Paired contrast closures",
    "colloquial": "Colloquial/online slang",
    "dash_guard": "Em-dash density",
    "template": "Template phrases",
    "passive": "Passive voice",
    "para_symmetry": "Paragraph symmetry",
    "nested_numbers": "Nested numbers",
    "colon_list": "Colon lists",
    "punctuation": "Punctuation patterns",
}


def pattern_name(pid, lang="zh"):
    if pid in DEEP_PATTERNS:
        return DEEP_PATTERNS[pid]["zh" if lang == "zh" else "en"]
    return (_PATTERN_ZH if lang == "zh" else _PATTERN_EN).get(pid, pid)


def risk_label(level, lang="zh"):
    if lang == "zh":
        return {"high": "高风险", "medium": "中风险", "low": "低风险"}.get(level, level)
    return {"high": "High", "medium": "Medium", "low": "Low"}.get(level, level)
