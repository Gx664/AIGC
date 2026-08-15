# -*- coding: utf-8 -*-
"""本地 AIGC 治疗引擎（确定性改写，完全离线，不调用任何 LLM）。

对齐 aigc-reduce 的“三轮降重协议”：
  第一轮（减法）：受保护片段预检 → 词级替换 → 句级重构 → 段落调整
  第二轮（加法）：节奏工程（确定性长句拆分，绝不编造事实）
  第三轮（自检）：Anti-AI 审计 + 语体守门（口语化/破折号/事实保真）

四条铁律在此落地：
  1. 禁止全量重写 —— 只做局部确定性替换
  2. 修改率 >40% 为目标，但语体优先
  3. 确定性替换 —— 不经过 token 采样
  4. 保持学术语体 —— 口语化黑名单门禁 + 受保护片段原样保留
"""

import difflib
import re

from .aigc_rules import (
    COLLOQUIAL_FIXES,
    COLLOQUIAL_TERMS,
    NUMBERED_MARKERS,
    PROTECTED_SPAN_PATTERNS,
    SENTENCE_REWRITES,
    SEQ_MARKERS,
    WORD_REPLACEMENTS,
    WORD_SKIP,
)

EM_DASH = "——"
TOKEN_PREFIX = "⟦AIGC"
TOKEN_SUFFIX = "⟧"


# ─────────────────────────────────────────────────────────────
# 受保护片段
# ─────────────────────────────────────────────────────────────
def protect_spans(text):
    """把引用/编号/数据/公式/术语/引语替换成占位符，返回 (掩码文本, 片段列表)。"""
    spans = []
    for pattern, kind in PROTECTED_SPAN_PATTERNS:
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end(), m.group(0), kind))
    spans.sort(key=lambda x: (x[0], x[1]))
    # 合并重叠
    merged = []
    for s in spans:
        if merged and s[0] < merged[-1][1]:
            if s[1] > merged[-1][1]:
                merged[-1] = (merged[-1][0], s[1], text[merged[-1][0]:s[1]], merged[-1][3])
            continue
        merged.append(s)
    # 生成掩码文本
    masked = []
    last = 0
    spans_out = []
    for i, (start, end, orig, kind) in enumerate(merged):
        masked.append(text[last:start])
        token = "%s%d%s" % (TOKEN_PREFIX, i, TOKEN_SUFFIX)
        masked.append(token)
        spans_out.append({"token": token, "start": start, "end": end, "text": orig, "kind": kind})
        last = end
    masked.append(text[last:])
    return "".join(masked), spans_out


def restore_spans(masked, spans):
    out = masked
    for s in sorted(spans, key=lambda x: len(x["token"]), reverse=True):
        out = out.replace(s["token"], s["text"])
    return out


# ─────────────────────────────────────────────────────────────
# 第一轮：去除 AI 痕迹（减法）
# ─────────────────────────────────────────────────────────────
def _build_master_pattern():
    """把全部词级规则合成一条正则：最长优先 + 语境保护，单遍扫描避免链式二次替换。"""
    alts = []
    words = []
    for word, _ in WORD_REPLACEMENTS:
        skip = WORD_SKIP.get(word)
        alts.append(skip.pattern if skip else re.escape(word))
        words.append(word)
    return words, re.compile("|".join("(?:%s)" % a for a in alts))


_WORDS, _MASTER = _build_master_pattern()


def _word_replace(text, changes):
    counters = {}
    replacements = []  # (start, end, word, variant)
    for m in _MASTER.finditer(text):
        word = m.group(0)
        if word not in counters:
            counters[word] = 0
        i = counters[word]
        counters[word] = i + 1
        # 找到该词对应的变体列表
        variants = None
        for w, v in WORD_REPLACEMENTS:
            if w == word:
                variants = v
                break
        if not variants:
            continue
        variant = variants[i % len(variants)]
        if variant == word:
            continue
        replacements.append((m.start(), m.end(), word, variant))
    # 从后往前应用，保持索引有效
    for start, end, old, variant in reversed(replacements):
        text = text[:start] + variant + text[end:]
        changes.append({"level": "word", "from": old, "to": variant})
    return text


def _sentence_rewrite(text, changes):
    counters = {}
    for pattern, variant in SENTENCE_REWRITES:
        if not pattern.search(text):
            continue
        key = pattern.pattern
        i = counters.get(key, 0)
        counters[key] = i + 1
        m = pattern.search(text)
        if not m:
            continue
        old = m.group(0)
        if old == variant:
            continue
        text = text[:m.start()] + variant + text[m.end():]
        changes.append({"level": "sentence", "from": old, "to": variant})
    return text


_GENERIC_OPENER = re.compile(r"随着(.{2,18}?)的(?:不断发展|发展|进步|深入)[，,]")


def _generic_openers(text, changes):
    """“随着X的不断发展/深入”类万能开头 → “在X持续发展的背景下”。"""
    for m in list(_GENERIC_OPENER.finditer(text)):
        subject = m.group(1)
        repl = "在%s持续发展的背景下，" % subject
        old = m.group(0)
        text = text.replace(old, repl, 1)
        changes.append({"level": "sentence", "from": old, "to": repl})
    return text


def _break_parallel(text, changes):
    for pattern, repl in NUMBERED_MARKERS:
        while True:
            m = pattern.search(text)
            if not m:
                break
            old = m.group(0)
            text = text[:m.start()] + repl + text[m.end():]
            changes.append({"level": "parallel", "from": old, "to": repl})
    for pattern, repl in SEQ_MARKERS:
        while True:
            m = pattern.search(text)
            if not m:
                break
            old = m.group(0)
            text = text[:m.start()] + repl + text[m.end():]
            changes.append({"level": "parallel", "from": old, "to": repl})
    # “一方面…另一方面…总的来说/综上所述” 删总结句开头
    m = re.search(r"(一方面[^。]{2,40}另一方面[^。]{2,80}(?:总的来说|综上所述|综合来看)[，,])", text)
    if m:
        old = m.group(1)
        repl = old.replace("总的来说，", "").replace("综上所述，", "").replace("综合来看，", "")
        text = text.replace(old, repl, 1)
        changes.append({"level": "parallel", "from": old, "to": repl})
    return text


def _fix_dashes(text, changes):
    if text.count(EM_DASH) <= 1:
        return text
    parts = text.split(EM_DASH)
    # 保留第一个，其余替换
    fixed = parts[0]
    for i, part in enumerate(parts[1:]):
        if i == 0:
            fixed += EM_DASH + part
        else:
            repl = "，" if part else "。"
            fixed += repl + part
            changes.append({"level": "dash", "from": EM_DASH, "to": repl})
    return fixed


# ─────────────────────────────────────────────────────────────
# 第二轮：注入书面学术特征（加法，仅结构层面，不编造事实）
# ─────────────────────────────────────────────────────────────
_SPLIT_CONNECTIVES = ("，但是", "，但", "，而", "，因此", "，从而", "，进而", "，其中", "，同时", "，此外", "，而且")


def _split_long_sentences(text, changes):
    """节奏工程：把 50 字以上的长句在自然连接处拆成两句（书面完整句）。"""
    sentences = re.split(r"(?<=[。！？])", text)
    out = []
    for s in sentences:
        if len(s) < 50:
            out.append(s)
            continue
        best = -1
        best_len = 0
        for conn in _SPLIT_CONNECTIVES:
            pos = s.rfind(conn)
            if pos >= 0:
                # 选靠近中后部（40%-75%）的切分点
                if 0.4 * len(s) <= pos <= 0.8 * len(s):
                    best = pos
                    best_len = len(conn)
                    break
                if pos > best:
                    best = pos
                    best_len = len(conn)
        if best < 0:
            out.append(s)
            continue
        tail = s[best + best_len:]
        if len(tail) < 12:
            out.append(s)
            continue
        conn = s[best:best + best_len]
        before = s[:best] + "。" + s[best + best_len:]
        changes.append({
            "level": "split",
            "from": s.strip()[:50] + "…",
            "to": before.strip()[:50] + "…",
        })
        out.append(before)
    return "".join(out)


# ─────────────────────────────────────────────────────────────
# 第三轮：语体守门 + Anti-AI 审计
# ─────────────────────────────────────────────────────────────
def _style_fix(text, changes):
    for word, repl in COLLOQUIAL_FIXES.items():
        while word in text:
            text = text.replace(word, repl, 1)
            changes.append({"level": "style", "from": word, "to": repl})
    return text


def audit_paragraph(text):
    """对改写结果做第三轮自检，返回剩余信号（供 UI 展示）。"""
    from .diagnosis import _analyze_deep_11, _template_hits

    remaining = []
    template_n = len(_template_hits(text))
    if template_n:
        remaining.append("模板句 %d 处" % template_n)
    hits = [t for t in COLLOQUIAL_TERMS if t in text]
    if hits:
        remaining.append("口语化/网络用语：%s" % "、".join(hits))
    n_dash = text.count(EM_DASH)
    if n_dash >= 2:
        remaining.append("破折号 %d 个（应 ≤1）" % n_dash)
    pats = _analyze_deep_11(text, 0)
    for p in pats:
        remaining.append("%s ×%d" % (p["zh"], len(p["evidence"])))
    return remaining


def _mod_ratio(orig, rev):
    ratio = difflib.SequenceMatcher(None, orig, rev).ratio()
    return round(1 - ratio, 3)


# ─────────────────────────────────────────────────────────────
# 段落级治疗
# ─────────────────────────────────────────────────────────────
def treat_paragraph(para, options=None):
    options = options or {}
    orig = para
    masked, spans = protect_spans(para)
    changes = []

    # 第一轮：减法（句子级先于词级，避免“归因于两方面，首先”这类整句规则被拆散）
    if options.get("sentence_level", True):
        masked = _sentence_rewrite(masked, changes)
        masked = _generic_openers(masked, changes)
    if options.get("word_level", True):
        masked = _word_replace(masked, changes)
    if options.get("parallel", True):
        masked = _break_parallel(masked, changes)
    if options.get("dash_fix", True):
        masked = _fix_dashes(masked, changes)

    # 第二轮：加法（节奏工程，确定性长句拆分）
    if options.get("split_long", True):
        masked = _split_long_sentences(masked, changes)

    # 第三轮：语体守门
    if options.get("style_guard", True):
        masked = _style_fix(masked, changes)

    revised = restore_spans(masked, spans)
    changed = revised != orig
    ratio = _mod_ratio(orig, revised)
    remaining = audit_paragraph(revised) if changed else []

    notes = []
    target = options.get("target_ratio", 0.40)
    if changed and ratio < target:
        notes.append("修改率 %.0f%% 未达目标 %.0f%%，可在剩余模板句上继续结构性改写；语体优先，不要口语化凑数。"
                     % (ratio * 100, target * 100))
    if not changed:
        notes.append("未发现可确定性替换的 AI 痕迹；如需进一步降低，请人工按诊断建议逐句调整。")
    if any("口语化" in r for r in remaining):
        notes.append("仍检测到口语化/网络用语，必须改回书面学术表达（语体优先于修改率）。")

    return {
        "index": None,
        "original": orig,
        "revised": revised,
        "changed": changed,
        "mod_ratio": ratio,
        "changes": changes,
        "remaining": remaining,
        "notes": notes,
        "protected_spans": [s["text"] for s in spans],
    }


def treat(paragraphs, indices=None, options=None):
    """批量治疗。indices 为 1 起始段落序号；None = 全部。"""
    options = options or {}
    if indices is None:
        indices = list(range(1, len(paragraphs) + 1))
    results = []
    rewritten = 0
    ratios = []
    all_warnings = []
    for i, para in enumerate(paragraphs, 1):
        if i not in indices:
            results.append({
                "index": i,
                "original": para,
                "revised": para,
                "changed": False,
                "mod_ratio": 0.0,
                "changes": [],
                "remaining": [],
                "notes": ["未选中，跳过"],
                "protected_spans": [],
            })
            continue
        r = treat_paragraph(para, options)
        r["index"] = i
        results.append(r)
        if r["changed"]:
            rewritten += 1
            ratios.append(r["mod_ratio"])
        all_warnings.extend(r["remaining"])
    return {
        "summary": {
            "total": len(paragraphs),
            "selected": len(indices),
            "rewritten": rewritten,
            "avg_mod_ratio": round(sum(ratios) / len(ratios), 3) if ratios else 0.0,
            "style_warnings": sorted(set(all_warnings))[:10],
        },
        "paragraphs": results,
    }


def export_text(result, separator="\n\n"):
    """把治疗结果导出为纯文本（只导出有改动的段落）。"""
    parts = []
    for r in result["paragraphs"]:
        if not r["changed"]:
            continue
        head = "=== 第 %d 段（修改率 %d%%）===" % (r["index"], r["mod_ratio"] * 100)
        parts.append(head + "\n" + r["revised"])
    return separator.join(parts)
