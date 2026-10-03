# -*- coding: utf-8 -*-
"""引擎清单（11 项，零依赖，UI 与安装器都可安全导入）。

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
        "tags": ["中文", "中文可用", "CPU 可跑", "推荐"],
        "params": {"max_len": 500},
        "update_channel": "models",
    },
    {
        "id": "aigc_zh_v3",
        "name": "AIGC 中文检测 v3",
        "name_en": "AIGC Chinese detector v3",
        "category": CAT_DETECT,
        "impl": "classifier",
        "model_id": "yuchuantian/AIGC_detector_zhv3",
        "models": [
            {
                "repo": "yuchuantian/AIGC_detector_zhv3",
                "size": "约 400MB",
                "role": "中文判别模型（BERT）",
                "role_en": "Chinese classifier (BERT)",
            }
        ],
        "size_hint": "约 400MB",
        "paper": "HC3-Chinese / AIGC_text_detector",
        "venue": "中文 AIGC 检测公开实现 · Apache-2.0",
        "desc": "在 HC3 中文语料升级版上训练的判别模型，对中文改写、润色后的 AI 文本比旧版更敏感，逐段输出 AI 概率。CPU 可跑。",
        "desc_en": "A classifier trained on the upgraded Chinese HC3 corpus; more sensitive to paraphrased or polished Chinese AI text than the older detector. Outputs a per-paragraph AI probability. Runs on CPU.",
        "tags": ["中文", "CPU 可跑"],
        "params": {"max_len": 500},
        "update_channel": "models",
    },
    {
        "id": "pan_modernbert",
        "name": "PAN 2026 ModernBERT（英文）",
        "name_en": "PAN 2026 ModernBERT (English)",
        "category": CAT_DETECT,
        "impl": "classifier",
        "model_id": "ShantanuT01/vanguard-ai-text-detector",
        "models": [
            {
                "repo": "ShantanuT01/vanguard-ai-text-detector",
                "size": "约 1.6GB",
                "role": "英文判别模型（ModernBERT-large）",
                "role_en": "English classifier (ModernBERT-large)",
            }
        ],
        "size_hint": "约 1.6GB",
        "paper": "arXiv:2607.17382",
        "venue": "PAN@CLEF 2026 检测赛道 · MIT",
        "desc": "PAN 2026 检测赛道的高分分类器（均分 0.96），主打抗跨域过拟合，长英文文档表现最稳。模型较大，建议独立显卡。",
        "desc_en": "A top-scoring classifier from the PAN 2026 detection track (mean score 0.96), built for out-of-distribution robustness. Strongest on long English texts. Large model, GPU recommended.",
        "tags": ["英文", "需显卡"],
        "params": {"max_len": 1000},
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
        "desc": "统计派方法：语言模型算困惑度，越低越像机器写的。英文实测准确率约 94%（误报 5%）；中文仅 77% 且误报高达 28%，不建议用于中文。",
        "desc_en": "Statistical method: a language model scores perplexity; lower perplexity means more machine-like. Measured ~94% accuracy / 5% false positives on English; only ~77% with 28% false positives on Chinese, so it is not recommended there.",
        "tags": ["轻量", "英文更佳", "双语", "中文极弱"],
        # 阈值按语言分开，均为**实测标定值**（各 300 条 1:1 平衡样本）：
        #   英文 (12, 25)        -> acc 93.67%  FPR 5.19%
        #   中文 (11.35, 18.72)  -> acc 74.67%  FPR 29.58%
        # 数据：Ghostbuster Student Essay / HC3-Chinese
        # 详见 docs/FIXES.md §3
        # 为什么要分：英文 human 的 PPL 中位 29.50、中文只有 17.18 ——
        # 同一组阈值对中文会把大段人写文本判进插值区间。
        #
        # 中文可用性（2026-09-23 AUC 复测）：AUC 0.7816，但**在 FPR<=5%
        # 约束下中文不存在可行阈值**（英文有：thr=0.4998 acc=0.9400）。
        # 查重工具误报比漏报严重，故中文侧实际不可交付。
        # 详见 docs/FIXES.md §3.1
        #
        # method 可切到论文 §3 的 Test-2（逐 token rank 四档）：
        # "rank" 路线实测与 PPL 打平（中文还略差），故默认仍是 "ppl"。
        # 详见 docs/FIXES.md §2.2（Test-2 已实现为 method="rank" 可选路线）
        "params": {
            "method": "ppl",
            "ppl_high": 25.0,
            "ppl_low": 12.0,
            "ppl_high_zh": 18.72,
            "ppl_low_zh": 11.35,
        },
        "update_channel": "models",
    },
    {
        # 中文困惑度：原作者在 engines_manifest.json 里备好了这条（含阈值），
        # 但没接进内置清单 —— 中文侧原本只有 simpleai 一个可用选项。
        # 本次（TODO-8 方案 A）把它落到内置清单，用户开箱即可用。
        #
        # 实测（HC3-Chinese 200 条 1:1，见 docs/FIXES.md §3.1）：
        #   AI    PPL 中位  6.27
        #   human PPL 中位 13.64        <- 英文 human 中位是 29.50
        #   阈值原来填的 (20, 45) -> acc 0.5200 / FPR 0.9500（95% 人写被判 AI）
        #   改为 FPR<=5% 版 (2.88, 7.68) -> acc 0.6300 / FPR 0.0400
        # 中文 PPL 远低于英文，所以阈值与 gltr 那组**完全不通用**。
        "id": "zh_perplexity",
        "name": "中文困惑度检测（GPT2-Chinese）",
        "name_en": "Chinese perplexity (GPT2-Chinese)",
        "category": CAT_DETECT,
        "impl": "perplexity",
        "model_id": "uer/gpt2-chinese-cluecorpussmall",
        "models": [
            {
                "repo": "uer/gpt2-chinese-cluecorpussmall",
                "size": "约 400MB",
                "role": "中文困惑度打分模型",
                "role_en": "Chinese perplexity scoring LM",
            }
        ],
        "size_hint": "约 400MB",
        "paper": "arXiv:1906.04043",
        "venue": "中文 GPT-2（CLUECorpusSmall 训练）",
        "desc": "把 GLTR 的困惑度方法换到中文语料模型上。比英文底座强不少（准确率 0.4950 → 0.6300），但中文侧整体仍弱于默认的 SimpleAI，适合当交叉参考。",
        "desc_en": "GLTR's perplexity method on a Chinese LM. Clearly better than the English backbone (accuracy 0.4950 -> 0.6300), but still weaker than the default SimpleAI; use it as a cross-check.",
        "tags": ["中文", "统计派", "中文弱", "需下载"],
        "params": {"ppl_low": 2.88, "ppl_high": 7.68},
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
        # ⚠️ 本引擎**中英两侧都还没标定**（docs/FIXES.md §3.1 与 §3.2 均记
        # 「未标定」）。原标签写「中文不可用」是**推测**（因底座是英文模型、
        # 且 detectgpt 中文反向），不是实测 —— 2026-09-23 撤掉，改为「未标定」，
        # 避免让用户以为已有依据。
        #
        # 跑不了的原因：需可用显存 >=7GB，本机常被其他进程占 7.8GB，余量不足
        # 时会慢 10 倍（139.9 秒/条 vs 干净环境 13.6 秒）—— 见 docs/FIXES.md §5。
        "tags": ["零样本", "需显卡", "英文", "未标定"],
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
        "desc": "论文的掩码扰动实现：用 T5 对原文做局部改写生成扰动样本，比较对数概率曲率。比 Fast 版更忠实原文，也更慢。英文实测 AUC 0.71（论文 0.9554，差 0.245）；中文排序反向，勿用。",
        "desc_en": "Masked-perturbation implementation: T5 rewrites short spans to build perturbed samples, then compares log-probability curvature. Slower but closer to the paper. Measured AUC 0.71 on English (the paper reports 0.9554); its Chinese ranking is inverted, so it must not be used there.",
        "tags": ["零样本", "CPU 勉强可跑", "英文", "中文不可用"],
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
        "desc": "一对同词表模型交叉打分（对数困惑度 / 对数交叉困惑度），只看比值不看绝对困惑度。轻量组合 CPU 也可跑。英文实测约 94%（误报 5%）；中文两个分布高度重叠，用默认阈值时一条 AI 都抓不出来。",
        "desc_en": "Two same-tokenizer models score the text cross-wise (logPPL / log-xPPL); the ratio is used instead of raw perplexity. CPU-capable in the light configuration. Measured ~94% / 5% false positives on English; on Chinese the two distributions overlap heavily and the default threshold catches no AI text at all.",
        "tags": ["零样本", "双模型", "英文", "中文弱"],
        # threshold/scale 是**实测标定值**，不是论文原值。
        # 论文的 0.901 绑定 Falcon-7B-Instruct + Falcon-7B；本项目用 gpt2 组合，
        # 论文附录 A.1.2 要求换模型后重标（"optimize using accuracy"）。
        # 标定数据：Ghostbuster Student Essay 1:1 平衡样本 120 条，
        #           最优阈值 0.615，准确率 94.17%，FPR 4.84%。
        # 详见 docs/FIXES.md §3.2
        "params": {"threshold": 0.615, "scale": 0.12},
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
