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
    EN_SENTENCE_REWRITES,
    EN_WORD_REPLACEMENTS,
    NUMBERED_MARKERS,
    PROTECTED_SPAN_PATTERNS,
    SENTENCE_REWRITES,
    SEQ_MARKERS,
    WORD_REPLACEMENTS,
    WORD_SKIP,
    find_colloquial,
    is_english_text,
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


# ─────────────────────────────────────────────────────────────
# 英文路径（SCI / 学术论文）
# ─────────────────────────────────────────────────────────────
def _build_en_master_pattern():
    """把全部英文词级规则合成一条正则：长词优先 + 整词边界，单遍扫描。"""
    alts = []
    for word, _ in EN_WORD_REPLACEMENTS:
        # 前后不能紧贴 ASCII 字母数字，否则 "utilize" 会命中 "utilizationized" 这类
        alts.append(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(word))
    pattern = re.compile("|".join("(?:%s)" % a for a in alts), re.I)
    mapping = {word.lower(): variants for word, variants in EN_WORD_REPLACEMENTS}
    return pattern, mapping


_EN_MASTER, _EN_VARIANTS = _build_en_master_pattern()
# 每条规则已用掉的次数（决定取第几个变体）。每次 treat_paragraph 开头重置。
_EN_USED = {}

# 「量词 + 量词」相邻即病句（multiple many / many several / several many）。
# 这些词单独看都是合法的量词/不定代词，两个量词叠用必然不合语法。
_EN_QUANTIFIER_ALT = re.compile(
    r"(?:multiple|many|several|numerous|a\s+range\s+of|a\s+variety\s+of|"
    r"a\s+number\s+of|both|either|neither)"
    r"\s+(?:multiple|many|several|numerous|a\s+range\s+of|a\s+variety\s+of|"
    r"a\s+number\s+of|both|either|neither)(?![A-Za-z])"
)


def _en_keep_case(src, repl):
    """按原词大小写形态套用替换词：Title / UPPER / 原样。"""
    if src.isupper() and len(src) > 1:
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def _en_sentence_rewrite(text, changes):
    """删元话语壳 + 换冗余连接词。每条规则单遍扫，命中即记录。"""
    counters = {}
    for pattern, repl in EN_SENTENCE_REWRITES:
        while True:
            m = pattern.search(text)
            if not m:
                break
            old = m.group(0)
            # 整句被删空会造成语法断裂，跳过（原文本身也不该只有这个壳）
            if not old.strip() or not repl.strip():
                if len(text.strip()) <= len(old.strip()) + 10:
                    break
            new_text = text[:m.start()] + repl + text[m.end():]
            if new_text == text:
                break
            text = new_text
            key = pattern.pattern
            counters[key] = counters.get(key, 0) + 1
            changes.append({"level": "sentence", "from": old.strip(), "to": repl.strip() or "（删除元话语壳）"})
    return text


def _en_word_replace(text, changes):
    """英文词级替换：**合成一条 master 正则、单遍扫描**，长词优先 + 从后往前应用。

    写法必须与中文 ``_word_replace`` 同构，原因有二：
    1. **单遍扫描**。若按规则逐条扫（每条规则都重新 finditer 一次），前面规则改写
       后文本长度已变，后面规则拿到的区间就错位——会产出 ``signnotabletors``
       这种把词劈成两半的垃圾（``significant``→``notable`` 后长度变了，
       ``factors`` 的区间仍按旧偏移量切片）。
    2. **从后往前应用**。保持前面所有区间有效。

    另有一道病句防护：``a variety of numerous factors`` 两条规则各自命中会拼出
    "multiple many"。所以**收集完全部命中后统一校验**，若相邻两条替换的结果
    叠成「量词 + 量词」就成对丢弃。

    ⚠️ 两条纪律（都是 2026-10-07 自查踩出来的）：
    - 必须**事后**判定，不能边收集边判：命中顺序不一定相邻
      （"a variety of numerous" 里 numerous 先被收集），边收集边判会漏。
    - 只管「两处都是本次替换的结果」，不管「替换结果 + 邻近原文」：
      曾把 ``a variety of → multiple`` 这种本来正确的替换一起误杀。
      **宁可漏杀不可错杀**。
    """
    replacements = []  # (start, end, old, variant)
    for m in _EN_MASTER.finditer(text):
        word = m.group(0)
        variants = _EN_VARIANTS.get(word.lower())
        if not variants:
            continue
        lw = word.lower()
        # 变体等于原词 → 空转，跳过
        usable = [v for v in variants if v.lower() != lw]
        if not usable:
            continue
        used = _EN_USED.get(lw, 0)
        _EN_USED[lw] = used + 1
        replacements.append((m.start(), m.end(), word,
                             _en_keep_case(word, usable[used % len(usable)])))

    # 病句防护：相邻两条替换拼成「量词 + 量词」→ 成对丢弃
    ordered = sorted(replacements, key=lambda x: x[0])
    drop = set()
    for i in range(len(ordered) - 1):
        s1, e1, _o1, v1 = ordered[i]
        s2, e2, _o2, v2 = ordered[i + 1]
        if any(e < s2 for _s, e, _o, _v in ordered[i + 2:]):
            break  # 中间还夹着别的替换 → 不是紧邻的一对
        if _EN_QUANTIFIER_ALT.match(v1.lower() + " " + v2.lower()):
            drop.add((s1, e1))
            drop.add((s2, e2))
    ordered = [r for r in ordered if (r[0], r[1]) not in drop]

    for start, end, old, variant in reversed(ordered):
        text = text[:start] + variant + text[end:]
        changes.append({"level": "word", "from": old, "to": variant})
    return text


def _treat_english(para, masked, options, changes):
    """英文段落的完整降重流程。

    与中文流程的差异：① 不跑 ``_break_parallel``——``(1)/(2)`` 在英文里是
    参考文献编号，换成"其一，"是纯粹的破坏；② 不跑 ``_fix_dashes``——中文
    破折号规则针对"——"，英文 ``--`` 语义不同，误伤风险大于收益。
    """
    if options.get("sentence_level", True):
        masked = _en_sentence_rewrite(masked, changes)
    if options.get("word_level", True):
        masked = _en_word_replace(masked, changes)
    masked = _en_recap_sentences(masked, changes)
    masked = _en_fix_articles(masked, changes)
    return masked


def _en_recap_sentences(text, changes):
    """删掉元话语壳后把句首字母补回大写。

    "It is worth noting that these findings are preliminary." 去掉壳后剩下
    "these findings are preliminary."——英文句首小写是语法错误。删壳类规则
    必然制造这种情况，所以收尾统一修一次。

    **句首位置无条件大写**，白名单只管非句首：冠词/介词/连词（a/an/the/in/on/at/
    of/to/for…）在句中不该大写（"the solution" 不能改成 "The solution"），
    但出现在**句首就必须大写**（"the use of resources…" → "The use of…"）。
    早期版本把 the 放进白名单一刀切，结果句首的 the 永远补不上——
    这类位置判断必须区分"句首"与"句中"，不能只看词性。
    """
    out = []
    for m in re.finditer(r"(^|[.!?]\s+)([a-z])([a-zA-Z'-]*)", text):
        out.append((m.start(2), m.start(3)))
    if not out:
        return text
    for start, end in reversed(out):
        text = text[:start] + text[start].upper() + text[end:]
    changes.append({"level": "sentence", "from": "（句首小写）", "to": "（补大写）"})
    return text


# ── a / an 协调 ──────────────────────────────────────────────
# 词级替换会把元音开头的词换进来，"a crucial role" → "a essential role"，
# a/an 不协调是明确的语法错误。英文没有独立的元音音标表，用拼写启发式：
# 词首是元音字母、但以"辅音音素"开头（u→/ju/、eu/one…）的仍用 an。
_EN_A_AN_FIX = (
    re.compile(r"\ban\s+(?=[bcdfgjklmnpqrstvwxyz][a-z])", re.I),   # a + 辅音
    re.compile(r"\ba\s+(?=[aeiou][a-z])", re.I),                  # an + 元音
)
# 例外：hour / honest / university 这类 u 开头但读 /ju/ 或辅音的词
_AN_EXCEPT = re.compile(
    r"\ba\s+(?=(?:hour|honest|honor|honour|heir|university|universal|unique|"
    r"unit|user|usual|useful|utility|european|euro|one[- ]|once)[a-z])", re.I)


def _en_fix_articles(text, changes):
    """修 a/an 不协调（``a essential`` → ``an essential``）。"""
    fixed = _AN_EXCEPT.sub("an ", text)
    fixed = _EN_A_AN_FIX[0].sub("a ", fixed)
    fixed = _EN_A_AN_FIX[1].sub("an ", fixed)
    if fixed != text:
        changes.append({"level": "word", "from": "a/an 不协调", "to": "已修正"})
    return fixed


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
    hits = find_colloquial(text)
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
    # 英文段落走独立规则库。中文规则全是汉字模式，硬套英文只会把"(1)"换成
    # "其一，"——句子改坏、改动率还只有 1%（早期版本对英文 SCI 的实际表现）。
    english = is_english_text(masked)

    if english:
        _EN_USED.clear()  # 词级轮换计数按段落重置，否则整篇只用第一个变体
        masked = _treat_english(para, masked, options, changes)
    else:
        # 第一轮：减法（句子级先于词级，避免"归因于两方面，首先"这类整句规则被拆散）
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
