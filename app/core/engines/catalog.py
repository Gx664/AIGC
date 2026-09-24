# -*- coding: utf-8 -*-
"""引擎清单（9 项，零依赖，UI 与安装器都可安全导入）。

设计要点
--------
* **不预置模型**：这里只声明"用哪个模型、多大、去哪下"，模型一律由用户在
  「模型下载管理」里按需下载，和以前的做法一致。
* **分三类**：``category`` 取 ``detect``（检查）/ ``repair``（修复）/
  ``benchmark``（评测基准），界面按这三类分组展示。
* **预留接口**：新增 / 更新条目不一定要改本文件 ——
  ``<base_dir>/engines_catalog.json``（本地覆盖）和远端 manifest 都会与
  本清单合并，见 ``manager.EngineManager``。
"""

CAT_DETECT = "detect"
CAT_REPAIR = "repair"
CAT_BENCH = "benchmark"

CATEGORY_ORDER = (CAT_DETECT, CAT_REPAIR, CAT_BENCH)

# 主模型大小（含分词器）为作者实测 / 官方体积的粗略值，仅用于界面提示
BUILTIN_ENGINES = [
    # ------------------------------------------------------------ 检查 / 检测
    {
        "id": "simpleai",
        "name": "SimpleAI 中文检测（默认）",
        "name_en": "SimpleAI Chinese detector (default)",
        "category": CAT_DETECT,
        "impl": "classifier",
        "model_id": "Hello-SimpleAI/chatgpt-detector-roberta-chinese",
        "models": [
            {
                "repo": "Hello-SimpleAI/chatgpt-detector-roberta-chinese",
                "size": "约 400MB",
                "role": "中文判别模型（RoBERTa）",
                "role_en": "Chinese classifier (RoBERTa)",
            }
        ],
        "size_hint": "约 400MB",
        "paper": "arXiv:2301.07597",
        "venue": "HC3 数据集 · ICLR/公开评测广泛引用",
        "desc": "用中文问答对比语料训练的分类器，逐段输出 AI 概率。CPU 可跑，是中文论文的默认选择。",
        "desc_en": "A classifier trained on Chinese human-vs-ChatGPT corpora; outputs a per-paragraph AI probability. Runs on CPU.",
        "tags": ["中文", "CPU 可跑", "推荐"],
        "params": {"max_len": 500},
        "update_channel": "models",
    },
    {
        "id": "gltr",
        "name": "GLTR 困惑度检测",
        "name_en": "GLTR perplexity detector",
        "category": CAT_DETECT,
        "impl": "perplexity",
        "model_id": "gpt2",
        "models": [
            {"repo": "gpt2", "size": "约 500MB", "role": "困惑度打分模型", "role_en": "Perplexity scoring LM"}
        ],
        "size_hint": "约 500MB",
        "paper": "arXiv:1906.04043",
        "venue": "MIT · NeurIPS 2019",
        "desc": "统计派方法：语言模型算困惑度，越低越像机器写的。英文文档表现更稳，中文可作参考。",
        "desc_en": "Statistical method: a language model scores perplexity; lower perplexity means more machine-like. Stronger on English.",
        "tags": ["轻量", "英文更佳"],
        "params": {"ppl_high": 25.0, "ppl_low": 12.0},
        "update_channel": "models",
    },
    {
        "id": "fastdetectgpt",
        "name": "Fast-DetectGPT（零样本）",
        "name_en": "Fast-DetectGPT (zero-shot)",
        "category": CAT_DETECT,
        "impl": "curvature",
        "model_id": "EleutherAI/gpt-neo-2.7B",
        "models": [
            {
                "repo": "EleutherAI/gpt-neo-2.7B",
                "size": "约 5.4GB",
                "role": "条件概率曲率打分模型",
                "role_en": "Conditional-probability scoring LM",
            }
        ],
        "size_hint": "约 5.4GB",
        "paper": "arXiv:2310.05130",
        "venue": "ICLR 2024",
        "desc": "原论文的采样近似实现：用模型自身采样近似曲率，无需训练数据。模型大，建议独立显卡。",
        "desc_en": "Sampling-based approximation of the original method: conditional probability curvature via self-sampling, no training data needed. Large model, GPU recommended.",
        "tags": ["零样本", "需显卡"],
        "params": {"mode": "fast", "samples": 5, "threshold": 0.0, "scale": 0.6},
        "update_channel": "models",
    },
    {
        "id": "detectgpt",
        "name": "DetectGPT（零样本·掩码扰动）",
        "name_en": "DetectGPT (zero-shot, masked perturbation)",
        "category": CAT_DETECT,
        "impl": "curvature",
        "model_id": "gpt2",
        "models": [
            {"repo": "gpt2", "size": "约 500MB", "role": "对数概率打分模型", "role_en": "Log-probability scoring LM"},
            {"repo": "t5-base", "size": "约 890MB", "role": "掩码扰动生成模型", "role_en": "Masked-perturbation generator"},
        ],
        "size_hint": "约 1.4GB",
        "paper": "arXiv:2301.11305",
        "venue": "斯坦福 · ICML 2023 (Oral)",
        "desc": "论文的掩码扰动实现：用 T5 对原文做局部改写生成扰动样本，比较对数概率曲率。比 Fast 版更忠实原文，也更慢。",
        "desc_en": "Masked-perturbation implementation: T5 rewrites short spans to build perturbed samples, then compares log-probability curvature. Slower but closer to the paper.",
        "tags": ["零样本", "CPU 勉强可跑"],
        "params": {"mode": "detect", "samples": 10, "mask_ratio": 0.15, "threshold": 0.0, "scale": 0.6},
        "update_channel": "models",
    },
    {
        "id": "binoculars",
        "name": "Binoculars（零样本·双模型）",
        "name_en": "Binoculars (zero-shot, dual model)",
        "category": CAT_DETECT,
        "impl": "binoculars",
        "model_id": "gpt2",
        "models": [
            {"repo": "gpt2", "size": "约 500MB", "role": "观察者模型 observer", "role_en": "Observer model"},
            {"repo": "gpt2-medium", "size": "约 1.4GB", "role": "表演者模型 performer", "role_en": "Performer model"},
        ],
        "size_hint": "约 1.9GB",
        "paper": "arXiv:2401.12070",
        "venue": "ICML 2024",
        "desc": "一对同词表模型交叉打分，只看比值不看绝对困惑度，不用调阈值就跨领域通用。轻量组合 CPU 也可跑。",
        "desc_en": "Two same-tokenizer models score the text cross-wise; the ratio is threshold-free and transfers across domains. CPU-capable in the light configuration.",
        "tags": ["零样本", "免调阈值"],
        "params": {"threshold": 0.9015, "scale": 0.12},
        "update_channel": "models",
    },
    # ------------------------------------------------------------ 修复 / 降重
    {
        "id": "aigc_reduce",
        "name": "aigc-reduce 三轮降重协议",
        "name_en": "aigc-reduce three-round rewrite",
        "category": CAT_REPAIR,
        "impl": "rule_rewrite",
        "model_id": "",
        "models": [],
        "size_hint": "内置（无需下载）",
        "paper": "MIT 开源项目 aigc-reduce",
        "venue": "知网/万方/PaperPass 检测原理",
        "desc": "内置规则引擎：9 维模板扫描 + AI 高频词替换表 + 口语化负面清单 + 受保护片段，三轮确定性改写。坚持「降重 ≠ 口语化」。",
        "desc_en": "Built-in rule engine: 9-dimension template scan, AI-frequent word table, colloquial blacklist, protected spans, three deterministic rewrite rounds.",
        "tags": ["内置", "无需模型"],
        "params": {},
        "update_channel": "rules",
    },
    {
        "id": "cnki_skill",
        "name": "知网 5 种语言模式诊断",
        "name_en": "CNKI 5-pattern diagnosis",
        "category": CAT_REPAIR,
        "impl": "cnki_diagnose",
        "model_id": "",
        "models": [],
        "size_hint": "内置（无需下载）",
        "paper": "MIT 开源项目 cnki-aigc---skill",
        "venue": "知网 AIGC 检测器实战方法",
        "desc": "按知网检测器的 5 种语言模式（节奏/密度/位置/连接词/模板段）给段落定风险等级，输出段落级 JSON 诊断。",
        "desc_en": "Scores each paragraph against CNKI's five language patterns (rhythm/density/position/connectives/template blocks) and emits a paragraph-level JSON diagnosis.",
        "tags": ["内置", "无需模型"],
        "params": {},
        "update_channel": "rules",
    },
    # ------------------------------------------------------------ 评测基准
    {
        "id": "raid",
        "name": "RAID 评测基准",
        "name_en": "RAID benchmark",
        "category": CAT_BENCH,
        "impl": "benchmark_raid",
        "model_id": "",
        "models": [],
        "size_hint": "内置快检 / 可导入官方集",
        "paper": "arXiv:2401.09985",
        "venue": "ACL 2024 · 600 万+ 条文本",
        "desc": "拿当前检测器跑一批带标注的样本文本，给出准确率、假阳性率、假阴性率，并按生成模型分项。支持导入 RAID 官方数据集子集。",
        "desc_en": "Runs the selected detector over labelled samples and reports accuracy, false-positive/false-negative rates, broken down per generator. Supports importing a RAID subset.",
        "tags": ["评测", "无模型"],
        "params": {"threshold": 0.5, "max_samples": 200},
        "update_channel": "samples",
    },
    {
        "id": "mgtbench",
        "name": "MGTBench 评测基准",
        "name_en": "MGTBench benchmark",
        "category": CAT_BENCH,
        "impl": "benchmark_mgt",
        "model_id": "",
        "models": [],
        "size_hint": "内置快检 / 可导入官方集",
        "paper": "arXiv:2303.14822",
        "venue": "首个 LLM 生成文本检测基准框架",
        "desc": "同一套样本文本上做精确率 / 召回率 / F1 的分类指标评测，用来横向比较不同检测器在同一批文本上的表现。",
        "desc_en": "Precision / recall / F1 over the same labelled set, used to compare detectors fairly on identical inputs.",
        "tags": ["评测", "无模型"],
        "params": {"threshold": 0.5, "max_samples": 200},
        "update_channel": "samples",
    },
]


def by_id(engine_id):
    for e in BUILTIN_ENGINES:
        if e["id"] == engine_id:
            return e
    return None


def by_category(category):
    return [e for e in BUILTIN_ENGINES if e.get("category") == category]

# aigc-toolkit: file purpose marker
