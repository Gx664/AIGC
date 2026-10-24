# -*- coding: utf-8 -*-
"""引擎清单（零依赖，UI 与安装器都可安全导入）。

设计要点
--------
* **不预置模型**：这里只声明"用哪个模型、多大、去哪下"，模型一律由用户在
  「模型下载管理」里按需下载，和以前的做法一致。
* **分三类**：``category`` 取 ``detect``（检查）/ ``repair``（修复）/
  ``benchmark``（评测基准），界面按这三类分组展示。
* **预留接口**：新增 / 更新条目不一定要改本文件 ——
  ``<base_dir>/engines_catalog.json``（本地覆盖）和远端 manifest 都会与
  本清单合并，见 ``manager.EngineManager``。

条目数量
--------
**不要在本文档里写死条目数** —— 加一条就过期一次。
需要断言时用 ``len(BUILTIN_ENGINES)`` 动态读（``tools/test_engines.py``
已按此写），别硬编码数字。
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
    # ------------------------------------------------------------ 本地改写模型仓库
    # 以下四条**只用于提前把模型下到本地**，当前版本不参与降重流程 ——
    # 真正的降重仍然走上面的内置规则引擎（默认选中，且是 LLM 失败时的兜底）。
    # 它们能出现在「模型下载管理」里，是因为有 model_warehouse 这个最小实现
    # 负责落盘；该实现的 rewrite() 会明确抛异常，不会误用。
    #
    # 🔴 为什么不收 mt5-small / uer/t5-v1_1-small-chinese：
    # 这类模型**只做过预训练，没有做过任何改写微调**，官方模型卡写明
    # "has to be fine-tuned before it is useable on a downstream task"。
    # 直接拿来降重得到的是无意义输出（不是效果差，是根本不能用），
    # 收录只会浪费用户 1.4GB 磁盘和一次下载等待，故不收。
    {
        "id": "qwen3_06b_rewrite",
        "name": "本地改写模型 Qwen3-0.6B（仓库 · 最小）",
        "name_en": "Qwen3-0.6B rewrite model (warehouse, smallest)",
        "category": CAT_REPAIR,
        "impl": "model_warehouse",
        "model_id": "Qwen/Qwen3-0.6B",
        "models": [
            {
                "repo": "Qwen/Qwen3-0.6B",
                "kind": "causal",
                "size": "约 1.2GB",
                "role": "因果改写模型（入门档，Q4 量化约 0.4GB 显存）",
                "role_en": "Causal rewrite model (entry tier, ~0.4GB VRAM at Q4)",
            }
        ],
        "size_hint": "约 1.2GB",
        "paper": "arXiv:2505.09388 · Apache-2.0",
        "venue": "中文 / 英文均可，Qwen3 家族最小号",
        "desc": "⚠️ 仅预下载，当前版本**不参与降重**。Qwen3 最小号，中英文都能跑，体积和磁盘占用最低；但 0.6B 的改写质量在三者中最弱，长句容易丢信息，适合先试用确定是否合口味。",
        "desc_en": "⚠️ Download-only; NOT used for rewriting in this release. The smallest Qwen3 tier handles both Chinese and English with the lowest disk footprint, but 0.6B is the weakest of the three at rewriting and may drop information in long sentences.",
        "tags": ["中文", "英文", "需 1.2GB", "仅预下载", "入门档", "Apache-2.0"],
        "params": {},
        "update_channel": "models",
    },
    {
        "id": "qwen3_17b_rewrite",
        "name": "本地改写模型 Qwen3-1.7B（仓库 · 推荐）",
        "name_en": "Qwen3-1.7B rewrite model (warehouse, recommended)",
        "category": CAT_REPAIR,
        "impl": "model_warehouse",
        "model_id": "Qwen/Qwen3-1.7B",
        "models": [
            {
                "repo": "Qwen/Qwen3-1.7B",
                "kind": "causal",
                "size": "约 3.4GB",
                "role": "因果改写模型（推荐档，Q4 量化约 1.1GB 显存）",
                "role_en": "Causal rewrite model (recommended tier, ~1.1GB VRAM at Q4)",
            }
        ],
        "size_hint": "约 3.4GB",
        "paper": "arXiv:2505.09388 · Apache-2.0",
        "venue": "中文 / 英文均可，质量与体积的最佳平衡",
        "desc": "⚠️ 仅预下载，当前版本**不参与降重**。四个仓库条目里质量与体积平衡最好的一档：比 0.6B 稳（长句不易丢信息），比 4B 省一半磁盘。纯 CPU 机器上改写一段约需 30~60 秒。",
        "desc_en": "⚠️ Download-only; NOT used for rewriting in this release. The best quality-to-size balance among the four warehouse entries: steadier than 0.6B on long sentences, half the disk of 4B. Roughly 30-60s per paragraph on a CPU-only machine.",
        "tags": ["中文", "英文", "需 3.4GB", "仅预下载", "推荐", "Apache-2.0"],
        "params": {},
        "update_channel": "models",
    },
    {
        "id": "qwen3_4b_rewrite",
        "name": "本地改写模型 Qwen3-4B（仓库 · 最强）",
        "name_en": "Qwen3-4B rewrite model (warehouse, strongest)",
        "category": CAT_REPAIR,
        "impl": "model_warehouse",
        "model_id": "Qwen/Qwen3-4B",
        "models": [
            {
                "repo": "Qwen/Qwen3-4B",
                "kind": "causal",
                "size": "约 8.0GB",
                "role": "因果改写模型（最强档，Q4 量化约 2.5GB 显存）",
                "role_en": "Causal rewrite model (strongest tier, ~2.5GB VRAM at Q4)",
            }
        ],
        "size_hint": "约 8.0GB",
        "paper": "arXiv:2505.09388 · Apache-2.0",
        "venue": "中文 / 英文均可，长句重构能力最强",
        "desc": "⚠️ 仅预下载，当前版本**不参与降重**。四个仓库条目里改写质量最高的一档，长句和多小句的段落重构明显更强；代价是 8GB 下载 + 8GB 磁盘，纯 CPU 机器上推理较慢，建议有独显再用。",
        "desc_en": "⚠️ Download-only; NOT used for rewriting in this release. The highest rewrite quality of the four warehouse entries, noticeably stronger on long multi-clause sentences; costs 8GB download plus 8GB on disk and is slow on CPU-only machines, so a dedicated GPU is advised.",
        "tags": ["中文", "英文", "需 8GB", "仅预下载", "最强", "Apache-2.0"],
        "params": {},
        "update_channel": "models",
    },
    {
        "id": "ateeqq_paraphraser",
        "name": "本地改写模型 Paraphraser（仓库 · 仅英文）",
        "name_en": "Text-Rewriter-Paraphraser English rewriter (warehouse, English only)",
        "category": CAT_REPAIR,
        "impl": "model_warehouse",
        "model_id": "Ateeqq/Text-Rewriter-Paraphraser",
        "models": [
            {
                "repo": "Ateeqq/Text-Rewriter-Paraphraser",
                "kind": "seq2seq",
                "size": "约 900MB",
                "role": "英文释义改写模型（T5-base，43 万条改写语料微调）",
                "role_en": "English paraphrase model (T5-base, fine-tuned on 430k pairs)",
            }
        ],
        "size_hint": "约 900MB",
        "paper": "T5-base · 43 万条改写数据 · 许可证未标注",
        "venue": "仅英文；中文无效",
        "desc": "⚠️ 仅预下载，当前版本**不参与降重**。🔴 **只支持英文**，中文段落用它无效。这是唯一一个开箱即用的改写微调模型（其余几个只有预训练），但训练目标是「一句话换说法」，输出长度接近输入，长段落会被 512 token 上限截断；且仓库未标注许可证，**非商业用途需自行确认授权**。",
        "desc_en": "⚠️ Download-only; NOT used for rewriting in this release. 🔴 **English only** - useless on Chinese text. The only ready-to-use rewrite fine-tune here (the others are pretrained-only), but its training target is sentence-level rephrasing with output length close to input, so long paragraphs get truncated at the 512-token limit; the repo carries no license tag, so confirm authorization yourself before any use.",
        # 🔴 tags 里**不能出现「中文」或「英文」以外含这两个字的词**：
        # engine_dialog.engine_lang_mark 用 `"中文" in tag` 做**子串**判断
        # （engine_dialog.py:123-124），任何含「中文」二字的标签都会让这条
        # 仅英文的模型被错标成中英双语。正文说明放 desc 里，tags 只留纯语言标记。
        "tags": ["英文", "仅英文", "需 900MB", "仅预下载", "许可证未标注"],
        "params": {},
        "update_channel": "models",
    },
    # ------------------------------------------------------------ 改写模型 · 2026-10 新增
    # 这一组是**真正做过改写微调**的模型（v1.3.9 那四条只有预训练，
    # 官方卡写明「必须微调后才能用于下游任务」）。
    #
    # 🔴 仍然**只预下载、不参与降重**：本项目的降重默认走内置规则引擎，
    # 本版一行都没碰它。模型条目只是把权重提前备到本地。
    {
        "id": "humanizer_12b_gguf",
        "name": "本地改写模型 Humanizer 12B（仓库 · 中英双语）",
        "name_en": "Humanizer 12B rewriter (warehouse, EN+ZH bilingual)",
        "category": CAT_REPAIR,
        "impl": "model_warehouse",
        "model_id": "jialinyyzz/humanizer-GGUF",
        "models": [
            {
                "repo": "jialinyyzz/humanizer-GGUF",
                "kind": "gguf",
                # 🔴 必须声明 files：GGUF 是 llama.cpp 的格式，
                # transformers 的 from_pretrained 读不了 —— 只能原样落盘。
                # 见 model_warehouse_engine.install() 的「下载分两条路」。
                "files": [
                    "humanizer-12b-Q4_K_M.gguf",
                    "prompt_format.json",
                ],
                "size": "约 7.6GB",
                "role": "中英双语改写模型（GGUF 量化 Q4_K_M，Gemma-4-12B 微调）",
                "role_en": "EN+ZH rewriting model (GGUF Q4_K_M, fine-tuned from Gemma-4-12B)",
            }
        ],
        "size_hint": "约 7.6GB",
        "paper": "Gemma-4-12B 微调 · Apache-2.0",
        "venue": "中英双语 · 2026-10 HF trending #2 · 12.9 万次下载",
        "desc": "⚠️ 仅预下载，当前版本**不参与降重**。🔴 **唯一中英双语的成品改写模型**——它做了真正的改写微调（合成 AI 稿 → 真人原文），不是只有预训练。官方实测：英文严格检测下 210 篇仅 11 篇被误判为 AI（上一版是 26 篇），且**训练全程没用任何 AI 检测器**。三档量化任选：IQ2_XS 3.9GB / Q3 5.6GB / Q4_K_M 7.6GB（推荐，峰值内存约 10GB）。🔴 官方强调它是 **text-completion 模型而非对话模型**，prompt 必须逐字节匹配官方模板，且采样参数须为 temperature=1.0 / top_p=0.95（top_k、min_p 关闭、repetition_penalty=1.0）—— 自行改写提示词会明显变差。",
        "desc_en": "⚠️ Download-only; NOT used for rewriting in this release. 🔴 **The only ready-made EN+ZH bilingual rewriter** - genuinely fine-tuned for rewriting (synthetic AI drafts → authentic human text), not merely pretrained. Official measurement: on strict English detection, 11 of 210 rewrites were flagged as AI (down from 26 in the prior release), and no AI detector was used anywhere in training. Three quantizations available: IQ2_XS 3.9GB / Q3 5.6GB / Q4_K_M 7.6GB (recommended, ~10GB peak memory). 🔴 The official docs stress this is a **text-completion model, not a chat model**: the prompt must match the published template byte for byte, and sampling must be temperature=1.0 / top_p=0.95 with top-k and min-p off and repetition_penalty=1.0 - paraphrasing the prompt makes the output noticeably worse.",
        "tags": ["中文", "英文", "需 7.6GB", "仅预下载", "真微调", "Apache-2.0"],
        "params": {},
        "update_channel": "models",
    },
    {
        "id": "humanize_zh_9b",
        "name": "本地改写模型 Humanize-ZH 9B（仓库 · 中文专用）",
        "name_en": "Humanize-ZH 9B rewriter (warehouse, Chinese only)",
        "category": CAT_REPAIR,
        "impl": "model_warehouse",
        "model_id": "XiangJinYu/Qwen3.5-9B-Humanize-DPO-Round2",
        "models": [
            {
                "repo": "XiangJinYu/Qwen3.5-9B-Humanize-DPO-Round2",
                "kind": "adapter",
                # 🔴 仓库里只有 adapter_model.safetensors（LoRA 增量权重，
                # 116MB），**没有合并后的完整权重**。要真跑起来必须另外
                # 准备底座 Qwen3.5-9B（19.3GB）并用 peft 合并 ——
                # 本项目当前不含 peft，所以这条**只是把 adapter 备到本地**。
                "files": [
                    "adapter_model.safetensors",
                    "adapter_config.json",
                ],
                "size": "约 116MB（另需 19.3GB 底座）",
                "role": "中文改写模型（LoRA 增量权重，基于 Qwen3.5-9B）",
                "role_en": "Chinese rewriting model (LoRA adapter on Qwen3.5-9B)",
            },
            {
                "repo": "unsloth/Qwen3.5-9B",
                "kind": "causal",
                "size": "约 19.3GB",
                "role": "配套底座（adapter 需要它才能生效）",
                "role_en": "Required base model (the adapter needs it to take effect)",
            },
        ],
        "size_hint": "约 116MB + 19.3GB",
        "paper": "Qwen3.5-9B · SFT + 两轮 DPO · Apache-2.0",
        "venue": "中文专用 · 1.8 万条 SFT 数据 · 作者实测 AI 率 30% → 10% 以下",
        "desc": "⚠️ 仅预下载，当前版本**不参与降重**。🔴 **中文场景最对口的一个** —— 训练数据全部来自中文学术论文摘要，三阶段训练：SFT（1.8 万条「AI 改写稿 → 真人原文」对）→ DPO 第一轮（正反双向负样本，让模型学「真人分布」而不是简单往口语化偏）→ DPO 第二轮（自博弈数据，进一步提多样性）。作者实测两篇论文 AI 率分别从 50% 降到 24%、从 30% 降到 8.9%。🔴 注意体积：仓库只发布了 **116MB 的 LoRA 增量权重**，要真正跑起来还需 **19.3GB 底座**（本清单里已一并列出）；且合并需要 peft 库，本项目当前未安装。",
        "desc_en": "⚠️ Download-only; NOT used for rewriting in this release. 🔴 **The best fit for Chinese academic text** - all training data comes from Chinese academic abstracts, trained in three stages: SFT (18k pairs of AI-rewritten → authentic human abstracts) → DPO round 1 (bidirectional negative samples, so it learns the human distribution rather than merely drifting toward colloquial style) → DPO round 2 (self-play data for extra diversity). The author's measurement: AI ratio dropped from 50% to 24% and from 30% to 8.9% on two papers. 🔴 Mind the size: the repo publishes only a **116MB LoRA adapter**, so actually running it also needs the **19.3GB base model** (listed in this entry too); merging additionally requires the peft library, which this release does not ship.",
        "tags": ["中文", "仅中文", "需 19.3GB", "仅预下载", "真微调", "Apache-2.0"],
        "params": {},
        "update_channel": "models",
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
