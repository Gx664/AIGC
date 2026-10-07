# -*- coding: utf-8 -*-
"""共享规则库：诊断与治疗引擎共用的静态数据。

数据来源（均在 README / 软件“关于”中致谢）：
- aigc-reduce（xiaofenggan01/aigc-reduce）：
  模板句式、中文 AI 高频词、口语化负面清单、替换表、深度 AI 痕迹模式
- cnki-aigc---skill（qingshanliuci/cnki-aigc---skill）：
  知网检测器“5 种语言模式”判定依据

本文件只含数据与正则，不含执行逻辑。
"""

import re


# ─────────────────────────────────────────────────────────────
# 1. 受保护片段（治疗改写时绝不改动，也不为降重编造）
# ─────────────────────────────────────────────────────────────
PROTECTED_SPAN_PATTERNS = [
    # 参考文献编号 [1] [3-5] [1,2]
    (re.compile(r"\[\s*\d+(?:\s*[,，\-–—]\s*\d+)*\s*\]"), "citation"),
    # 英文引用 (Zhang et al., 2021) / (Zhang et al., 2021, p. 3)
    (re.compile(r"\([^()]{0,60}?(?:et al\.?|20\d{2}|19\d{2})[^()]{0,40}?\)"), "citation"),
    # 中文引用 （张三, 2020） / （张三等，2021）
    (re.compile(r"（[^（）]{1,60}?(?:19|20)\d{2}[^（）]{0,30}?）"), "citation"),
    # 图表公式编号：图3、表2、式(5)、Fig. 4、Table 2、Eq. (2)
    (re.compile(r"(?:图|表|式|Fig\.?|Figure|Table|Eq\.?|Equation|公式)\s*\.?\s*[（(]?\d+(?:[-–]\d+)?[）)]?"), "ref"),
    # 变量、统计量、公式符号
    (re.compile(r"R\s*[²2]|β\s*\d*|α\s*\d*|γ\s*\d*|σ\s*\d*|μ\s*\d*|ln_?[A-Za-z0-9_]+"), "variable"),
    # 数字 + 单位 / 百分比 / 置信区间 / P 值
    (re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|mm|cm|m|km|kg|g|mg|mL|ml|L|h|min|s|℃|°C|°|mol/L|mmol/L|MPa|kPa|Pa|Hz|kHz|MHz|GHz|nm|μm|µm|V|mV|A|mA|W|kW)" ), "number"),
    (re.compile(r"\d+(?:\.\d+)?\s*[-–—±~至~]\s*\d+(?:\.\d+)?\s*(?:%|％|mm|cm|m|km|kg|g|mg|mL|ml|L|h|min|s|℃|°C|°|mol/L|mmol/L|MPa|kPa|Pa|Hz|kHz|MHz|GHz|nm|μm|µm|V|mV|A|mA|W|kW)?"), "number"),
    (re.compile(r"P\s*[<>=≤≥]\s*\d*\.?\d+"), "number"),
    (re.compile(r"p\s*[<>=≤≥]\s*\d*\.?\d+"), "number"),
    (re.compile(r"±\s*\d+(?:\.\d+)?(?:\s*[A-Za-zµμ°%]+)?"), "number"),
    (re.compile(r"\d{4}\s*年"), "number"),
    # 引号内原文
    (re.compile('["“”][^"“”]{1,160}["“”]'), "quote"),
]


# ─────────────────────────────────────────────────────────────
# 2. 模板句式库（来自 aigc_scan.py，9 维扫描维度 1）
# ─────────────────────────────────────────────────────────────
TEMPLATE_PATTERNS = [
    r"^(综上所述[，,])",
    r"^(基于.{2,10}(分析|研究|探讨))",
    r"^(通过.{2,15}(验证|实验|研究|测定))",
    r"^(随着.{2,20}(发展|进步|深入))",
    r"^(近年来[，,])",
    r"^(在.{2,20}(背景下|条件下|过程中))",
    r"^(本研究[旨在对通过])",
    r"^(目前[，,])",
    r"^(当前[，,])",
    r"^(因此[，,])",
    r"^(由此可见[，,])",
    r"^(总而言之[，,])",
    r"(此外[，,])",
    r"(另外[，,])",
    r"(与此同时[，,])",
    r"(值得注意的是[，,])",
    r"(需要指出的是[，,])",
    r"(据统计[，,])",
    r"(相关研究表明[，,])",
    r"(一般认为[，,])",
    r"(具有重要的.{2,10}(意义|价值|作用))",
    r"(具有广阔的应用前景)",
    r"(为.{2,20}(提供了|奠定了).{2,10}(基础|依据|参考))",
    r"(不是[^\n。！？!?.]{1,40}而是)",
    r"(但至少)",
    r"(不代表)",
    r"(不等于)",
    r"(不一定[^\n。！？!?.]{1,40}(?:但是|但|却))",
    r"(即使[^\n。！？!?.]{1,40}也)",
]


# 被动语态标记（9 维扫描维度 2）
PASSIVE_MARKERS = [
    r"被.{1,15}(测定|检测|验证|确认|证明|发现|计算)",
    r"由.{1,15}(进行|完成|测定|检测|计算)",
    r"经.{1,15}(测定|检测|计算|分析)",
    r"通过.{1,15}(测定|检测|验证|实验|计算)",
    r"采用.{1,15}(进行|测定|检测)",
]


# ─────────────────────────────────────────────────────────────
# 3. 口语化 / 网络用语负面清单（降重过度预警，语体守门）
# ─────────────────────────────────────────────────────────────
COLLOQUIAL_TERMS = [
    "yyds", "绝绝子", "破防", "emo", "拿捏", "整活", "有梗", "无语",
    "离谱", "逆天", "炸裂", "社死", "摆烂", "搞定", "踩坑", "翻车",
    "封神", "硬核", "谁懂啊", "手感", "cpu", "崩了",
    "气死", "乐死", "笑死", "烦躁", "郁闷", "兴奋", "爽", "恶心",
    "说实话", "坦白讲", "老实说", "不瞒你说", "说白了", "讲真", "反正",
    "大概齐", "差不多就是", "这事的难度", "这事儿", "不得不考虑的一环",
    "一点一点磨出来", "撑起来", "比表面看起来大得多", "说到底", "归根结底就是",
    "真的强", "真的行", "拉满", "没跑偏", "谁懂",
]

# 清单里的 ASCII 项（emo / cpu / yyds…）必须按**词边界**匹配，不能用 `in`。
# 否则英文论文会被整片误判：haemorrhagic 里含 "emo"、occupied 里含 "cpu"、
# remove 里含 "emo"，全是子串巧合，与语体无关。中文项没有词边界概念，保持子串。
#
# 边界不能用 ``\b``：Python 的 \w 把中文也算单词字符，于是"emo了""cpu崩了"
# 这种 ASCII 词紧贴中文的写法会漏检（o 与 了 之间没有 \b）。改用显式的
# ASCII 字母/数字/下划线否定环视——只要左右不是 ASCII 单词字符就算独立成词，
# 紧贴中文照样命中，而 remove / occupied 里的内嵌子串不会。
_COLLOQUIAL_ASCII = re.compile(
    r"(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9_])"
    % "|".join(re.escape(t) for t in COLLOQUIAL_TERMS if t.isascii()),
    re.IGNORECASE,
)
# 中文文本判定：只有含中日韩字符的文本才去查ASCII 口语词——
# 纯英文文本里的 "cpu"/"emo" 是正常词汇，不是网络用语。
_HAS_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def count_colloquial(text):
    """统计口语化命中，**按词边界匹配 ASCII 项**，返回 ``[(词, 次数), ...]``。

    为什么不能直接 ``term in text``：``in`` 是子串匹配，英文论文会被误伤成一片
    红——``haemorrhagic``（出血性的）含 ``emo``、``occupied`` 含 ``cpu``、
    ``remove`` 含 ``emo``。这类假阳性会让降重引擎以为碰到网络用语而放弃改写。

    :param text: 待检查文本
    :return: ``[(命中词, 次数), ...]``，无命中返回 ``[]``
    """
    hits = []
    for term in COLLOQUIAL_TERMS:
        if term.isascii():
            continue
        c = text.count(term)
        if c:
            hits.append((term, c))
    if _HAS_CJK.search(text):
        for m in _COLLOQUIAL_ASCII.finditer(text):
            hits.append((m.group(0).lower(), 1))
    return hits


def find_colloquial(text):
    """命中词去重列表（按在文中首次出现的位置排序），供诊断/审计展示。"""
    seen = {}
    for term, _ in count_colloquial(text):
        pos = text.find(term)
        if pos < 0:  # ASCII 大小写与原文不同的情况
            pos = text.lower().find(term)
        seen.setdefault(pos, term)
    return [seen[k] for k in sorted(seen)]

# 口语词 → 书面学术替代（语体守门用，只替换黑名单里可安全映射的）
COLLOQUIAL_FIXES = {
    "说白了": "具体而言",
    "说实话": "事实上",
    "坦白讲": "坦率地说",
    "老实说": "客观而言",
    "不瞒你说": "值得注意的是",
    "讲真": "事实上",
    "反正": "无论如何",
    "这事儿": "该事项",
    "搞定": "完成",
    "踩坑": "遇到问题",
    "离谱": "异常",
    "逆天": "超出预期",
    "无语": "难以理解",
    "炸裂": "剧烈",
    "崩了": "失效",
    "爽": "顺利",
    "恶心": "令人不适",
    "兴奋": "显著",
    "拉满": "达到上限",
    "没跑偏": "保持稳定",
    "真的强": "表现突出",
    "真的行": "切实可行",
    "撑起来": "得以维持",
    "说到底": "归根结底",
}


# ─────────────────────────────────────────────────────────────
# 4. 中文 AI 高频词与替换（词级替换，每个词多个变体轮换使用）
# ─────────────────────────────────────────────────────────────
WORD_REPLACEMENTS = [
    # 模板连接词
    ("此外", ["另一方面", "从另一角度看"]),
    ("与此同时", ["同时", "结合前文来看"]),
    ("综上所述", ["把以上结论放在一起看", "综合上述结果"]),
    ("需要指出的是", ["值得说明的是"]),
    ("值得注意的是", ["特别之处在于", "一个细节是"]),
    ("研究表明", ["实验表明", "数据呈现", "从结果来看"]),
    ("分析认为", ["推测", "据此推断", "可能的原因是"]),
    ("具体而言", ["从数据来看", "进一步分析发现"]),
    ("具体来说", ["细看各组数据", "从细节来看"]),
    # “XX了”高危句式
    ("揭示了", ["指向了", "显示出"]),
    ("探讨了", ["考察了", "梳理了"]),
    ("验证了", ["确认了", "实测结果表明"]),
    ("构建了", ["建立了", "设计出"]),
    ("展示了", ["呈现了", "反映了"]),
    ("展现出", ["表现出", "显示出"]),
    ("展现了", ["表现出", "显示出"]),
    ("呈现出", ["表现出", "显示出"]),
    ("证实了", ["确认了", "实测支持了"]),
    ("导致了", ["造成了", "使得"]),
    ("表明了", ["显示出", "意味着"]),
    # 动词 / 形容词 / 副词
    ("显著提升", ["明显增强", "大幅改善"]),
    ("显著", ["明显", "大幅"]),
    ("深入探讨", ["仔细考察", "详细分析"]),
    ("至关重要", ["关键", "必要"]),
    ("不可或缺", ["不可缺少", "必需"]),
    ("系统性", ["全面", "整体"]),
    ("全方位", ["各方面", "多角度"]),
    ("多维度", ["多个方面", "从不同角度看"]),
    ("深度剖析", ["仔细分析", "拆解"]),
    ("高度契合", ["吻合", "相符"]),
    ("紧密结合", ["结合", "联系"]),
    ("有机融合", ["结合", "整合"]),
    ("无缝衔接", ["衔接", "过渡"]),
    ("稳步提升", ["逐步提高"]),
    ("持续优化", ["改进", "调整"]),
    ("全面提升", ["整体提高", "改善"]),
    ("举足轻重", ["重要", "关键"]),
    ("深远影响", ["长期影响", "重要影响"]),
    ("广泛关注", ["关注", "重视"]),
    ("进一步", ["更深入地"]),
    ("有效", ["切实", "确实"]),
    ("确保", ["保证"]),
    ("旨在", ["目的是"]),
    ("赋予", ["带来"]),
    ("阐述", ["说明", "解释"]),
    ("阐明", ["说明", "解释清楚"]),
    ("揭示", ["显示", "指向"]),
    ("凸显", ["突出", "显示出"]),
    ("彰显", ["显示", "体现"]),
    ("展现", ["表现", "呈现"]),
    ("助力", ["有利于", "帮助"]),
    ("赋能", ["支持", "帮助"]),
    ("协同", ["配合", "共同"]),
    ("探索", ["尝试", "考察"]),
    ("梳理", ["整理", "回顾"]),
    ("聚焦", ["关注", "集中于"]),
    ("呈现", ["表现出", "显示出"]),
    ("反映", ["体现", "折射"]),
    ("促进", ["推动", "有利于"]),
    ("抑制", ["限制", "阻碍"]),
    ("导致", ["造成", "引发"]),
    ("证实", ["确认", "验证"]),
    ("具备", ["具有"]),
    ("体现", ["表现", "反映"]),
    ("涵盖", ["包括", "覆盖"]),
    ("归因于", ["来源于", "主要在于"]),
    ("提升", ["提高", "增强", "改善"]),
    ("优化", ["改进", "调整"]),
    ("融合", ["结合"]),
    ("整体", ["总体上"]),
    ("整体上", ["总体上"]),
    ("本研究旨在", ["本研究聚焦于", "本文着重"]),
    ("进一步地", ["更深入地"]),
    ("聚焦于", ["关注"]),
    ("具有重要的理论意义和实践价值", ["在学理与应用两个层面均有所推进"]),
    ("进行了深入分析", ["作了较为细致的考察", "做了逐层剖析"]),
    ("具有广阔的应用前景", ["在应用层面仍有可拓展的空间"]),
    ("奠定了坚实的基础", ["打下了相应基础", "在基础层面做了铺垫"]),
    ("提供了重要的参考价值", ["提供了启发", "对相关研究有所启发"]),
    ("引起了广泛关注", ["逐渐进入研究者的视野"]),
    ("发挥着重要作用", ["起到了关键作用", "在其中起到了关键的支撑"]),
    ("取得了显著的成效", ["收到了一定的效果"]),
    ("有待进一步研究", ["仍有继续追问的空间"]),
    ("鉴于此", ["基于上述考虑"]),
    ("开辟了新的途径", ["探索出一条可能的路径"]),
    ("做出了重要贡献", ["在该领域有所推进"]),
    ("成为学术界研究的热点", ["在学界引发了持续的讨论"]),
    ("有着不可忽视的作用", ["其作用不宜低估"]),
    ("前景广阔", ["后续仍有拓展余地"]),
    ("数据显示", ["从数据来看", "数据层面反映出"]),
    ("数据表明", ["数据所呈现的趋势是"]),
    ("从表中可以看出", ["梳理表中数据后发现", "观察该表"]),
    ("从图中可以看出", ["对照该图", "图中曲线显示"]),
    ("如图所示", ["参见下图", "图中呈现的规律是"]),
    ("由表可知", ["梳理表中数据后发现"]),
    ("实验结果表明", ["实验所得结果指向", "从实验结果来看"]),
    ("统计结果表明", ["统计分析给出的结论是"]),
    ("分析结果显示", ["分析结果提示"]),
    # 过度确定性语气（学术留白）
    ("毫无疑问", ["应当承认", "较为确定的是"]),
    ("毋庸置疑", ["可以说", "较为明确的是"]),
    ("势必", ["很可能", "有较大概率"]),
    ("必将", ["预计将", "有望"]),
    ("无一例外", ["在绝大多数情况下"]),
    ("绝对", ["在很大程度上"]),
]

# 排序：长词优先，避免“显著提升”先被“显著”拆掉
WORD_REPLACEMENTS.sort(key=lambda x: len(x[0]), reverse=True)

# 语境保护：这些词在特定后缀/搭配中属于规范学术表达，不替换
WORD_SKIP = {
    "显著": re.compile(r"显著(?!性)"),
    "有效": re.compile(r"有效(?!性)"),
    "整体": re.compile(r"整体(?!上)"),
    "进一步": re.compile(r"进一步(?!地)"),
    "聚焦": re.compile(r"聚焦(?!于)"),
    "协同": re.compile(r"协同(?!作用|效应|发展)"),
    "绝对": re.compile(r"绝对(?!值)"),
    "融合": re.compile(r"融合(?!特征|深度|多模态|数据|图像|模型)"),
    "呈现": re.compile(r"呈现(?!出)"),
    "展现": re.compile(r"展现(?!出)"),
}


# ─────────────────────────────────────────────────────────────
# 5. 句级 / 结构级确定性改写规则（治疗第一轮“减法”）
# ─────────────────────────────────────────────────────────────
SENTENCE_REWRITES = [
    (re.compile(r"归因于两方面，首先"), "主要有两方面原因：一是"),
    (re.compile(r"归因于两方面，首先"), "主要原因有两方面：其一"),
    (re.compile(r"归因于(?:多种因素|多方面因素)的综合作用"), "可能受到多种因素的综合影响"),
    (re.compile(r"上述结果一致表明"), "综合这几组数据可以看到"),
    (re.compile(r"上述结果一致表明"), "把以上结果放在一起看"),
    (re.compile(r"这一现象归因于"), "这一现象可能源于"),
    (re.compile(r"与预期方向一致"), "与预期方向相符"),
    (re.compile(r"在统计推断意义上获得支持"), "得到了样本数据较为充分的支持"),
    (re.compile(r"结果表明"), "结果显示"),
    (re.compile(r"结果表明"), "所得结果指向"),
    (re.compile(r"随着人工智能技术的不断发展"), "在人工智能技术持续发展的背景下"),
    (re.compile(r"随着科学技术的不断发展"), "在科学技术持续发展的背景下"),
    (re.compile(r"从宏观到微观"), "在多个层面"),
    (re.compile(r"从理论到实践"), "在理论与应用层面"),
    (re.compile(r"从基础研究到工程应用"), "在研究与应用两个层面"),
]

# 平行编号：确定性拆解
NUMBERED_MARKERS = [
    (re.compile(r"[（(]\s*1\s*[）)]"), "其一，"),
    (re.compile(r"[（(]\s*2\s*[）)]"), "其二，"),
    (re.compile(r"[（(]\s*3\s*[）)]"), "其三，"),
    (re.compile(r"[（(]\s*4\s*[）)]"), "其四，"),
    (re.compile(r"[（(]\s*5\s*[）)]"), "其五，"),
]

# “首先…其次…最后…” 序列化标记处理
SEQ_MARKERS = [
    (re.compile(r"首先[，,]"), "其一，"),
    (re.compile(r"其次[，,]"), "其二，"),
    (re.compile(r"再次[，,]"), "其三，"),
]


# ─────────────────────────────────────────────────────────────
# 6. 知网“5 种语言模式”判定数据（cnki-aigc---skill）
# ─────────────────────────────────────────────────────────────
# 模式 4：功能重叠的连接词
OVERLAP_CONNECTIVES = ["因此", "从而", "进而", "由此", "因而", "故"]

# 模式 5 子特征
PARALLEL_PATTERNS = [
    re.compile(r"从[^，。；]{2,12}看[，,]从[^，。；]{2,12}看[，,]从[^，。；]{2,12}看"),
    re.compile(r"对[^，。；]{2,12}[，,]对[^，。；]{2,12}[，,]对[^，。；]{2,12}"),
    re.compile(r"一方面[^。]{2,40}另一方面[^。]{2,40}"),
    re.compile(r"既[^，。]{2,18}又[^，。]{2,18}更[^，。]{2,18}"),
    re.compile(r"不仅[^，。]{2,20}而且[^，。]{2,20}更[^，。]{2,20}"),
    re.compile(r"[^，。]{2,10}以[^，。]{2,10}为主；[^，。]{2,10}以[^，。]{2,10}为主"),
    re.compile(r"首先[^。；]{2,40}(?:其次|此外|再者)[^。；]{2,40}"),
]

ABSTRACT_NOUN_CHAIN = re.compile(
    r"(?:传导机制|调控机制|调控变量|动态监测|监测体系|检验路径|重要环节|"
    r"体系|机制|路径|环节|效应|框架|范式)(?:的(?:传导|调控|监测|检验|重要|关键|核心)){1,3}"
)

PARA_END_META = re.compile(
    r"(这一结论|上述发现|上述结果表明|综上所述|为(?:后续|今后).{0,12}(?:提供了|奠定)|"
    r"具有(?:重要的)?(?:理论|实践|现实)意义|意义重大)$"
)

REPORT_TEMPLATES = [
    r"(?:实验|统计|分析)?结果表明",
    r"一致表明",
    r"数据显示",
    r"数据表明",
    r"研究表明",
    r"与预期(?:方向)?一致",
    r"(?:下降|上升|降至|升至)",
    r"在统计推断意义上获得支持",
]

# 模式 3：术语（用于检查“术语放主语位置”）——由程序统计重复词后判断


# ─────────────────────────────────────────────────────────────
# 7. 11 种深度 AI 痕迹模式（Wikipedia “Signs of AI writing” 本地化）
# ─────────────────────────────────────────────────────────────
DEEP_PATTERNS = {
    "significance": {
        "zh": "重要性膨胀",
        "en": "Significance inflation",
        "regex": [
            re.compile(r"至关重要|不可忽视|深远影响|具有重要价值|标志着|开启了新篇章|"
                       r"具有重要的.{2,10}(?:意义|价值|作用)|值得关注"),
        ],
    },
    "synonym_cycling": {
        "zh": "同义词轮换",
        "en": "Synonym cycling",
        "groups": [
            ["表明", "显示", "呈现", "体现", "反映"],
            ["显著", "明显", "大幅", "可观"],
            ["研究", "考察", "探讨", "分析", "梳理", "调查"],
            ["影响", "改变", "调控", "左右", "作用"],
            ["促进", "推动", "驱动", "有利于"],
            ["提升", "增强", "改善", "优化"],
            ["导致", "造成", "引发", "使得"],
        ],
    },
    "rule_of_three": {
        "zh": "三板斧强迫症",
        "en": "Rule of three",
        "regex": [
            re.compile(r"[^，。；]{2,10}[、][^，。；]{2,10}[、][^，。；]{2,10}(?:和|与|及)[^，。；]{2,10}"),
            re.compile(r"不仅[^，。]{2,18}而且[^，。]{2,18}甚至[^，。]{2,18}"),
        ],
    },
    "copula_avoidance": {
        "zh": "系词回避",
        "en": "Copula avoidance",
        "regex": [
            re.compile(r"作为[^，。]{1,20}的代表"),
            re.compile(r"扮演着[^，。]{1,20}的角色"),
            re.compile(r"发挥着[^，。]{1,20}的作用"),
            re.compile(r"体现了[^，。]{1,20}的特征"),
        ],
    },
    "vague_attribution": {
        "zh": "模糊归因",
        "en": "Vague attribution",
        "regex": [
            re.compile(r"(?:有研究表明|相关研究指出|学界普遍认为|众所周知|一般认为|据统计)(?![^。]{0,15}\[\d+\])"),
        ],
    },
    "formulaic_challenge": {
        "zh": "公式化挑战段",
        "en": "Formulaic challenges",
        "regex": [
            re.compile(r"尽管[^。]{2,30}(?:取得|获得)[^。]{0,25}(?:成果|进展)，但(?:本研究)?仍(?:存在|有)"),
            re.compile(r"未来的研究可以进一步"),
            re.compile(r"有待进一步研究"),
            re.compile(r"尚需(?:深入|进一步)(?:研究|探讨|验证)"),
        ],
    },
    "suspended_analysis": {
        "zh": "悬浮式分析",
        "en": "Suspended analysis",
        "regex": [
            re.compile(r"[^。！？]{0,60}从而[^。！？]{0,50}进而[^。！？]{0,50}"),
            re.compile(r"[^。！？]{0,60}从而[^。！？]{0,50}(?:由此|因而)"),
            re.compile(r"[^。！？]{0,60}进而[^。！？]{0,50}(?:从而|由此|因而)"),
        ],
    },
    "generic_conclusion": {
        "zh": "空洞结论",
        "en": "Generic conclusions",
        "regex": [
            re.compile(r"具有良好的应用前景|为[^。]{0,20}提供了(?:理论和)?实验依据|"
                       r"具有重要的理论价值与现实意义|意义重大|前景广阔"),
        ],
    },
    "em_dash": {
        "zh": "破折号过度使用",
        "en": "Em-dash overuse",
        "threshold": 2,
    },
    "false_range": {
        "zh": "虚假范围",
        "en": "False ranges",
        "regex": [
            re.compile(r"从(?:宏观|理论|基础研究|整体)(?:到|至)(?:微观|实践|工程应用|局部)"),
            re.compile(r"涵盖了从[^。]{1,15}到[^。]{1,15}的(?:各个方面|全部)"),
        ],
    },
    "paired_contrast": {
        "zh": "成对转折收束",
        "en": "Paired contrast closures",
        "regex": [
            re.compile(r"不是[^。！？]{2,35}而是"),
            re.compile(r"但至少"),
            re.compile(r"不代表|不等于"),
            re.compile(r"即使[^。！？]{2,35}也"),
        ],
    },
}


# ─────────────────────────────────────────────────────────────
# 8. 诊断建议（按模式 id 给出可执行的改写动作，双语）
# ─────────────────────────────────────────────────────────────
SUGGESTIONS = {
    "burstiness": {
        "zh": "句长过于均匀：在语义自然处拆分 50 字以上长句，穿插 15-30 字短句，目标变异系数约 0.45",
        "en": "Sentence lengths are too uniform: split sentences over 50 chars and vary length (target CV ≈ 0.45)",
    },
    "density": {
        "zh": "段落密度过于均匀：把高密度论证段与低密度铺陈段错开，调整段落长度",
        "en": "Paragraph density is too uniform: alternate dense argument paragraphs with lighter ones",
    },
    "term_position": {
        "zh": "术语频繁出现在主语位置：不动术语本身，把它挪到话题或宾语位置",
        "en": "Terms often sit in subject position: keep the term, move it to topic/object position",
    },
    "connective": {
        "zh": "连接词功能重叠（因此/从而/进而/由此）：换成补充、转述、对照等不同功能的连接词",
        "en": "Overlapping connectives (therefore/thus/furthermore): diversify their functions",
    },
    "parallel": {
        "zh": "工整排比：每一项换不同句式起头（描述句/判断句/动宾句/转折句各一）",
        "en": "Parallel triads: start each item with a different sentence pattern",
    },
    "abstract_chain": {
        "zh": "抽象名词链：把名词堆叠改为动词短语或具体表述",
        "en": "Abstract noun chains: replace with verb phrases or concrete wording",
    },
    "para_end_meta": {
        "zh": "段尾元话语：删掉“这一结论/上述发现表明”式收束，让段落自然结束",
        "en": "End-of-paragraph metadiscourse: remove formulaic closures",
    },
    "report_template": {
        "zh": "模板化报告句（研究表明/结果显示）：换成“从结果来看/数据所呈现的趋势是”等具体表述",
        "en": "Template report phrases: replace with concrete result-oriented wording",
    },
    "significance": {
        "zh": "重要性膨胀：删掉“至关重要/不可忽视”等修饰，或替换为具体数据",
        "en": "Significance inflation: drop inflated modifiers or replace with concrete data",
    },
    "synonym_cycling": {
        "zh": "同义词轮换：核心术语全文统一，不要人为制造轮换",
        "en": "Synonym cycling: keep core terms consistent throughout",
    },
    "rule_of_three": {
        "zh": "三板斧强迫症：把三件套拆为两件或四件，避免每段恰好三个要点",
        "en": "Rule of three: break triads into two or four items",
    },
    "copula_avoidance": {
        "zh": "系词回避：该用“是”的地方直接用“是”",
        "en": "Copula avoidance: use plain “is/are” where natural",
    },
    "vague_attribution": {
        "zh": "模糊归因：删除无出处的“有研究表明”，或补上具体引用编号",
        "en": "Vague attribution: remove unsourced claims or add a specific citation",
    },
    "formulaic_challenge": {
        "zh": "公式化挑战段：用具体、自然的叙述替代“尽管…但仍存在局限性”模板",
        "en": "Formulaic challenges: replace with specific, natural limitations",
    },
    "suspended_analysis": {
        "zh": "悬浮式分析：一句话挂 2+ 个“从而/进而”时，拆成独立句子",
        "en": "Suspended analysis: split chains of “thus/furthermore” into separate sentences",
    },
    "generic_conclusion": {
        "zh": "空洞结论：替换为具体判断（如“该配比下硬度接近实测值，可作为原型材料”）",
        "en": "Generic conclusions: replace with a concrete judgment",
    },
    "em_dash": {
        "zh": "破折号过密：每段最多保留 1 个，其余换成逗号、句号或括号",
        "en": "Em-dash overuse: keep at most one per paragraph, replace the rest",
    },
    "false_range": {
        "zh": "虚假范围（从宏观到微观）：直接列举实际覆盖的范围，或删掉",
        "en": "False ranges: list the actual scope or delete it",
    },
    "paired_contrast": {
        "zh": "成对转折收束（不是…而是…/但至少…）：删除转折外壳，保留具体事实",
        "en": "Paired contrast closures: remove the contrast shell, keep the facts",
    },
    "colloquial": {
        "zh": "检测到口语化/网络用语：改回书面学术表达，语体优先于修改率",
        "en": "Colloquial/online slang detected: restore formal academic register",
    },
    "dash_guard": {
        "zh": "破折号密度超标（每段 ≤1 个）：替换为逗号、句号或括号",
        "en": "Em-dash density exceeds 1 per paragraph: replace with commas or periods",
    },
    "template": {
        "zh": "模板句式密度偏高：删除或替换 AI 高频模板句、套话",
        "en": "High template-phrase density: remove or replace AI clichés",
    },
    "passive": {
        "zh": "被动语态偏多：方法描述中的合规被动保留，其余改为主动",
        "en": "High passive rate: keep compliant method passives, convert the rest",
    },
    "para_symmetry": {
        "zh": "连续 3 段以上长度相近：打破对称段长，扩写或精简其中一段",
        "en": "3+ paragraphs of similar length: break the symmetry",
    },
    "nested_numbers": {
        "zh": "嵌套编号过多：改为自然叙述",
        "en": "Too many nested numbers: convert to natural prose",
    },
    "colon_list": {
        "zh": "冒号并列结构过多：拆成独立叙述",
        "en": "Too many colon lists: break into separate statements",
    },
    "punctuation": {
        "zh": "逗号密度偏高：适当断句，减少超长复合句",
        "en": "High comma density: split long compound sentences",
    },
}


# ─────────────────────────────────────────────────────────────
# 7. 英文降重规则库（SCI/学术论文向）
# ─────────────────────────────────────────────────────────────
# 为什么单列一节：治疗引擎的中文规则全是汉字模式，英文段落一条都匹配不上，
# 结果就是英文论文只能被 ``NUMBERED_MARKERS`` 把"(1)"换成"其一，"——既破坏句子
# 又只拿到 1% 修改率。英文需要的不是词级同义替换，而是**去掉 AI 腔的元话语
# （meta-discourse）**并做句式重构：学术英语里"It is important to note that"
# "Due to the fact that" "In conclusion" 这类壳比用词更像 AI。
#
# 全部为确定性替换，不调用任何 LLM——与本引擎"禁止全量重写、不编造事实"的
# 铁律一致：只删壳、换连接词、调语序，不动事实、不动数字、不动引用。
EN_SENTENCE_REWRITES = [
    # ── 元话语壳（AI 最强特征，删掉不损失信息）
    (re.compile(r"It is (?:important|worth|essential|crucial|necessary) to note that\s*", re.I), ""),
    (re.compile(r"It should be noted that\s*", re.I), ""),
    (re.compile(r"It is worth mentioning that\s*", re.I), ""),
    (re.compile(r"It is worth noting that\s*", re.I), ""),
    (re.compile(r"It is important to (?:emphasize|highlight|stress) that\s*", re.I), ""),
    (re.compile(r"It is (?:clear|evident|apparent) that\s*", re.I), ""),
    (re.compile(r"It (?:can|may) be (?:seen|observed|noted) that\s*", re.I), ""),
    (re.compile(r"There (?:is|are) (?:a number of|several|many|various) \w+ that\s*", re.I), ""),
    (re.compile(r"It (?:is|was) (?:also )?(?:important|necessary) to (?:note|mention|stress)\b", re.I), ""),
    # ── 冗余连接壳 → 学术连词
    (re.compile(r"Due to the fact that\s*", re.I), "Because "),
    (re.compile(r"Due to the reason that\s*", re.I), "Because "),
    (re.compile(r"In order to\s*", re.I), "To "),
    (re.compile(r"In the event that\s*", re.I), "If "),
    (re.compile(r"With regard to\s*", re.I), "For "),
    (re.compile(r"With respect to\s*", re.I), "For "),
    (re.compile(r"Despite the fact that\s*", re.I), "Although "),
    (re.compile(r"Regardless of the fact that\s*", re.I), "Although "),
    (re.compile(r"a (?:large|wide) (?:number|range) of\s*", re.I), "many "),
    (re.compile(r"a great deal of\s*", re.I), "much "),
    (re.compile(r"the utilization of\s*", re.I), "the use of "),
    (re.compile(r"the implementation of\s*", re.I), "the application of "),
    # ── 章末套话（AI 收束签名）。不锚在段首：SCI 长段里"In conclusion,"
    # 常出现在句中甚至句尾，锚 ^ 会整条落空（早期版本因此漏删）。
    (re.compile(r"\bIn conclusion,\s*", re.I), ""),
    (re.compile(r"\bTo sum(?:mary|ing) up,\s*", re.I), ""),
    (re.compile(r"\bIn summary,\s*", re.I), ""),
    (re.compile(r"\bOverall,\s*", re.I), ""),
    (re.compile(r"\bTherefore,\s*", re.I), "Hence, "),
    (re.compile(r"\bThus,\s*", re.I), "Hence, "),
    (re.compile(r"\bMoreover,\s*", re.I), "In addition, "),
    (re.compile(r"\bFurthermore,\s*", re.I), "In addition, "),
    (re.compile(r"\bAdditionally,\s*", re.I), "In addition, "),
    (re.compile(r"\bBesides,\s*", re.I), ""),
    (re.compile(r"\bConsequently,\s*", re.I), "Accordingly, "),
    (re.compile(r"\bHenceforth,\s*", re.I), ""),
    # ── 空壳名词化（AI 偏好 nominalization，拆回动词）
    (re.compile(r"the (?:utilization|employment) of\s*", re.I), "using "),
    (re.compile(r"is able to\s*", re.I), "can "),
    (re.compile(r"are able to\s*", re.I), "can "),
    (re.compile(r"has the ability to\s*", re.I), "can "),
    (re.compile(r"have the ability to\s*", re.I), "can "),
(re.compile(r"there (?:is|are) (?:no|little) (?:doubt|question) (?:that )?\s*", re.I), "Clearly, "),
    # ⚠️ 刻意**不做** "plays a crucial role in → is central to" 这类转换：
    # "numerous factors play a crucial role in X" 会变成 "many factors is central
    # to X"，主谓不一致（factors 是复数）。把 play 拆成 is 就必须同步改主语单复数，
    # 而单复数判定依赖具体名词（factors/data/results…规则表列不全），漏一个就是
    # 语法错误。宁可少改，也不要违反本引擎「不产出病句」的铁律——AI 腔的削弱
    # 由删除元话语壳 + 词级替换承担，不需要动这条。
    (re.compile(r"on the basis of\s*", re.I), "from "),
    (re.compile(r"in the context of\s*", re.I), "within "),
    (re.compile(r"at the same time\s*", re.I), "concurrently "),
]

# 英文词级替换：长词优先 + 大小写保持（句首大写不动）
EN_WORD_REPLACEMENTS = [
    ("numerous", ["many", "several"]),
    ("a variety of", ["multiple", "a range of"]),
    ("a wide range of", ["a broad spectrum of", "many"]),
    ("a variety", ["a range"]),
    ("significant", ["notable", "substantial"]),
    ("significantly", ["notably", "markedly"]),
    ("crucial", ["essential", "pivotal"]),
    ("crucially", ["essentially", "above all"]),
    ("very important", ["critical"]),
    ("extremely", ["highly"]),
    ("in addition", ["furthermore", "also"]),
    ("utilize", ["use", "apply"]),
    ("utilizes", ["uses", "applies"]),
    ("utilized", ["used", "applied"]),
    ("utilization", ["use"]),
    ("approximately", ["about", "roughly"]),
    ("approximately", ["circa"]),
    ("prior to", ["before"]),
    ("subsequent to", ["after"]),
    ("a number of", ["several"]),
    ("the majority of", ["most"]),
    ("conducted a comprehensive", ["ran a full"]),
    ("comprehensive analysis", ["full analysis", "systematic review"]),
    ("detailed analysis", ["close analysis"]),
    ("researchers conducted", ["we carried out", "the study examined"]),
    # ⚠️ 故意**不收**这几条：in order to / due to the fact that / is able to /
    # are able to / has the ability to / it is worth noting / it is important to note
    # ——它们已由 EN_SENTENCE_REWRITES 处理（换连接词或删壳）。同一条内容在两张表里
    # 各写一遍会互相打架：句级删掉 "It is important to note that" 后，词级规则会把
    # 残留的 "it is important to note" 再换成 "notably"，留下悬空的 "that"
    # （"It is important to note that" → "Notably that"，语法崩坏）。
    # 这类壳的清理**只放在句级表**，词级表只留句级表不处理的纯词。
    ("furthermore", ["in addition", "also"]),
    ("moreover", ["in addition", "also"]),
    ("therefore", ["hence", "thus"]),
    ("however", ["yet", "still"]),
    ("very", ["highly", "notably"]),
]

# 排序：长词优先，避免 "significant" 先于 "significantly" 被拆坏
EN_WORD_REPLACEMENTS.sort(key=lambda x: len(x[0]), reverse=True)

# 英文语境判定：ASCII 字母占比够高、且汉字极少，才让治疗引擎走英文路径。
# 阈值放宽到 1.5%：SCI 段落常夹 (1)、n = 30、Fig. 2 这类符号，拉太紧会误判成中文路径。
_EN_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_EN_LATIN = re.compile(r"[A-Za-z]")


def is_english_text(text, min_latin=20):
    """判断文本是否"以英文为主"（治疗引擎据此选中文规则还是英文规则）。

    :param text: 待判定文本
    :param min_latin: 拉丁字母数下限，不足则一律当中文（样本太小判不准）
    :return: True = 英文为主
    """
    if not text:
        return False
    latin = len(_EN_LATIN.findall(text))
    if latin < min_latin:
        return False
    cjk = len(_EN_CJK.findall(text))
    return latin >= cjk * 20
