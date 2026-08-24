ABOUT_TEXT = """AI 检测工具箱（AIGC Detector Toolkit）
====================================

【简介】
一款本地运行的 AIGC 检测桌面工具：拖入论文（PDF/DOCX/TXT），
选择检测引擎，得到整篇 AI 生成占比与段落级报告。
- 全程离线推理：论文内容不上传任何平台，保护隐私
- 多引擎：SimpleAI 中文检测（默认）、GLTR 困惑度、Fast-DetectGPT 参考实现、可自定义模型
- 参数可自定义并存档
- 同机多卡自动并行；局域网可把室友电脑、Pad、手机加入并行计算
- 检测 → 诊断 → 治疗闭环：检测出 AI 率后，本地规则引擎诊断 AI 痕迹（段落级 JSON），
  再按“三轮降重协议”做保学术语体的确定性降重

【检测 → 诊断 → 治疗（v1.1 新增）】
检测只是第一步。本工具内置完全离线的 AI 痕迹诊断与降重（治疗）引擎：
- 诊断：不调用任何外部 AI。扫描 9 维特征（模板句式、突发性、段落对称性、被动语态、
  嵌套编号、冒号并列、标点规律、口语化预警、破折号密度）+ 知网 5 种语言模式
  （句法节奏、信息密度、术语句法位置、连接词功能、模板段功能）+ 11 种深度 AI 痕迹
  （重要性膨胀、同义词轮换、三板斧、系词回避、模糊归因、公式化挑战段、悬浮式分析、
  空洞结论、破折号过度、虚假范围、成对转折收束），输出结构化 JSON 诊断报告。
- 治疗：按三轮协议做确定性改写——去除 AI 痕迹（词级替换/句级重构/拆排比）、
  注入书面学术特征（确定性长句拆分，绝不编造）、Anti-AI 审计与语体守门。
  数字、术语、引用、图表编号、公式原样保留；不口语化，不编造事实；语体优先于修改率。
- 检测到 AI 率高于阈值会自动建议进入降重；降重参数可自定义并存档。

【灵感故事】
灵感来自我的一位大学生朋友。他的毕业论文需要反复查 AI 率，
每改一版都要查，学校官方检测入口次数有限而且费钱。
我想到：宿舍里打游戏的同学电脑基本都有独立显卡，跑得动本地检测；
一张卡不够还能用数据线/局域网连室友的电脑，甚至 Pad、手机也能加入算力。
于是就有了这个免费、本地、可控的项目。

【权威性依据（为什么可信）】
本项目不是自创算法，而是落地集成了经过学术评审的开源方法与论文：
1) SimpleAI / HC3（默认中文引擎）
   论文：How Close is ChatGPT to Human Experts?（arXiv:2301.07597）
   数据集、代码、模型全部公开，被大量研究引用。
2) Fast-DetectGPT（参考实现）
   论文：arXiv:2310.05130，发表于 ICLR 2024（AI 顶级会议）。
3) GLTR（统计检测方法）
   论文：arXiv:1906.04043，来自 MIT，发表于 NeurIPS 2019（顶级会议）。
4) DetectGPT（零样本检测）
   论文：arXiv:2301.11305，发表于 ICML 2023（顶级会议，Oral），来自斯坦福大学；
   无需训练数据即可零样本检测。
5) Binoculars（零样本检测）
   论文：arXiv:2401.12070，发表于 ICML 2024（顶级会议），检测准确率领先，代码开源。
6) RAID（评测基准）
   论文：arXiv:2401.09985，发表于 ACL 2024（计算语言学顶级会议）；
   目前最大、最全面的 AI 文本检测评测基准（600 万+ 条文本）。
7) MGTBench（评测基准）
   论文：arXiv:2303.14822；首个面向大语言模型（LLM）的机器生成文本检测基准框架。
8) 知网 3.0 检测原理（诊断/降重规则参考）
   数据来源：aigc-reduce 引用的《论文AIGC查重检测方法与原理深度研究报告》，
   知网 3.0 综合准确率 98.6%、假阳性率 1.2%；降重规则按知网/万方/PaperPass/PaperPure
   的检测原理实现。
9) Wikipedia “Signs of AI writing” + Humanizer skill
   深度 AI 痕迹模式清单源自 Wikipedia WikiProject AI Cleanup 维护的指南，
   经 aigc-reduce 本地化适配。
声明：检测结果受模型与文本类型影响，仅供自测参考，
请以学校/期刊官方认定为准。

【特别感谢（算力合并）】
- exo（exo-explore/exo，GitHub 约 4.6 万 star）：
  把手机、Pad、笔记本、游戏主机组成 P2P 分布式 AI 集群，
  自动发现设备、动态切分模型。本项目借鉴其 P2P 组网思路。
- llama.cpp（ggml-org/llama.cpp）：
  最受欢迎的本地 LLM 推理框架之一，其 RPC 分布式推理可在
  异构设备间切分模型层，是本项目跨设备计算的参考方案。
感谢以上项目及其社区。

【特别感谢（诊断与治疗）】
- aigc-reduce（xiaofenggan01/aigc-reduce，MIT）：
  提供三轮降重协议、替换表、中文 AI 高频词、口语化负面清单与 9 维扫描方法论，
  本项目降重引擎按其规则实现。
- cnki-aigc---skill（qingshanliuci/cnki-aigc---skill，MIT）：
  基于知网 AIGC 检测器“5 种语言模式”的实战方法（实测 20.6% → 10.1%，
  红色显著片段全部降为疑似），本项目诊断引擎按其模式实现。

【技术架构】
界面：Python + PySide6（玻璃拟态 UI）
检测：transformers（SimpleAI 中文分类 / 困惑度）
多设备：同机多卡自动并行 + 局域网主从节点（UDP 发现 + TCP 分发）
统计：匿名遥测（可关闭）+ 本地运行日志（可导出）
打包：小体积安装器，环境按需下载（先检查、缺什么装什么、带进度条）

【开发声明】
本项目由作者独立开发，部分代码由 DeepSeek V4 Flash + Codex 辅助编写与调试。

【支持与赞赏 · Support】
如果这个项目对你有一点帮助，可以请作者喝杯奶茶，支持继续开发：
- 支付宝（Alipay） / 微信支付（WeChat Pay）：扫描软件内或项目主页的赞赏码即可
- 想给就给，不想给就不给，绝非道德绑架；作者还是一名学生，
  零花钱不多，但做这个项目本身已经很有意义，你的支持只是额外的鼓励。

For international users:
If you don't use Alipay or WeChat Pay, you can also gift any AI API key
(any provider is welcome) to gxgx3456@qq.com.
Please include: model name, API/model URL and port.
If you'd like to be credited, mark it as "特别感谢 / Special Thanks".
Recommended: DeepSeek (great value) - https://platform.deepseek.com/api_keys
If you really want to gift one, DeepSeek V4 Flash is the most cost-effective.

【Bug 反馈】
点击「导出日志」打包日志后，发送至：gxgx3456@qq.com

【免责声明】
本人还是一名学生，代码可能存在不足，不好勿喷，
欢迎友善的建议与改进。本项目免费开源，仅供学习交流。

【开源协议】MIT
"""

ABOUT_TEXT_EN = """AIGC Detector Toolkit
====================================

[Introduction]
A local AIGC detection desktop tool: drop in a paper (PDF/DOCX/TXT),
choose a detection engine, and get the overall AI-written ratio plus
a paragraph-level report.
- Fully offline inference: your paper never leaves your computer
- Multiple engines: SimpleAI Chinese detection (default), GLTR perplexity,
  Fast-DetectGPT reference implementation, and custom models
- Highly customizable parameters, with savable presets
- Automatic multi-GPU parallelism on one machine; LAN cluster lets you add
  roommates' PCs, Pads and phones to the compute pool
- Detect → Diagnose → Treat: after detecting the AI ratio, a fully local rule
  engine diagnoses AI traces (paragraph-level JSON), then applies deterministic
  rewriting that keeps the academic register

[Detect → Diagnose → Treat (new in v1.1)]
Detection is only the first step. This tool ships with fully offline diagnosis
and rewriting (treatment):
- Diagnosis: no external AI calls. Scans 9 feature dimensions (template phrases,
  burstiness, paragraph symmetry, passive voice, nested numbers, colon lists,
  punctuation, colloquial warning, em-dash density) + CNKI's 5 language patterns
  (rhythm, density, term position, connective function, template paragraphs)
  + 11 deep AI patterns (significance inflation, synonym cycling, rule of three,
  copula avoidance, vague attribution, formulaic challenges, suspended analysis,
  generic conclusions, em-dash overuse, false ranges, paired contrast closures).
  Output: structured JSON diagnosis report.
- Treatment: three-round protocol with deterministic rewriting - remove AI
  traces (word/sentence/parallel), inject written academic features (deterministic
  sentence splitting, never fabricating), then Anti-AI audit + register guard.
  Numbers, terms, citations, figure/table refs and formulas stay untouched;
  no colloquialisms, no invented facts; register comes before change ratio.
- When the AI ratio exceeds the threshold you set, the app suggests entering
  the rewrite flow. Rewrite parameters are customizable and savable.
[Inspiration]
This project was inspired by my college-student friend. His graduation
thesis had to be re-checked for AI-written ratio again and again - once for
every revision - while the official school service is limited and expensive.
Then it hit me: dorm PCs with gaming graphics cards can easily run local
detection; if one GPU is not enough, you can link roommates' computers over
Ethernet/LAN, or even add Pads and phones. So this free, local, controllable
project was born.

[Why you can trust it]
This project does not invent algorithms; it integrates open-source methods
and papers that have been peer reviewed:
1) SimpleAI / HC3 (default Chinese engine)
   Paper: "How Close is ChatGPT to Human Experts?" (arXiv:2301.07597).
   Dataset, code and models are fully public and widely cited.
2) Fast-DetectGPT (reference implementation)
   Paper: arXiv:2310.05130, published at ICLR 2024 (top AI conference).
3) GLTR (statistical detection method)
   Paper: arXiv:1906.04043, from MIT, published at NeurIPS 2019 (top conference).
4) DetectGPT (zero-shot detection)
   Paper: arXiv:2301.11305, published at ICML 2023 (top conference, Oral),
   from Stanford; zero-shot detection without any training data.
5) Binoculars (zero-shot detection)
   Paper: arXiv:2401.12070, published at ICML 2024 (top conference);
   state-of-the-art accuracy, open source.
6) RAID (benchmark)
   Paper: arXiv:2401.09985, published at ACL 2024 (top NLP conference);
   the largest and most comprehensive benchmark for AI-text detectors (6M+ texts).
7) MGTBench (benchmark)
   Paper: arXiv:2303.14822; the first benchmarking framework for machine-generated
   text detection against large language models.
8) CNKI 3.0 detection principles (reference for diagnosis/rewrite rules)
   Source: "In-depth Research Report on AIGC Detection Methods and Principles"
   cited by aigc-reduce; CNKI 3.0 reports 98.6% accuracy and 1.2% false-positive
   rate. The rewrite rules follow the detection principles of CNKI/Wanfang/
   PaperPass/PaperPure.
9) Wikipedia "Signs of AI writing" + Humanizer skill
   The deep AI-pattern list (significance inflation, synonym cycling, rule of
   three, etc.) originates from Wikipedia's WikiProject AI Cleanup guide,
   localized by aigc-reduce.
Disclaimer: results depend on the model and text type. Use them for
self-checking only - the official verdict of your school/journal always wins.

[Special Thanks (compute pooling)]
- exo (exo-explore/exo, ~46k stars on GitHub): turns phones, Pads, laptops
  and gaming PCs into a P2P distributed AI cluster with auto-discovery and
  dynamic model splitting. We borrowed its P2P networking idea.
- llama.cpp (ggml-org/llama.cpp): one of the most popular local LLM inference
  frameworks; its RPC distributed inference splits model layers across
  heterogeneous devices - our reference for cross-device computing.
Thanks to those projects and their communities.

[Special Thanks (diagnosis & treatment)]
- aigc-reduce (xiaofenggan01/aigc-reduce, MIT): provides the three-round
  protocol, replacement tables, Chinese AI high-frequency words, colloquial
  blacklist and 9-dimension scanning methodology; our rewrite engine follows
  its rules.
- cnki-aigc---skill (qingshanliuci/cnki-aigc---skill, MIT): a real-world method
  based on CNKI's "5 language patterns" (measured 20.6% -> 10.1%, all red
  segments dropped to suspicious); our diagnosis engine follows its patterns.

[Tech Stack]
UI: Python + PySide6 (glassmorphism)
Detection: transformers (SimpleAI Chinese classifier / perplexity)
Multi-device: multi-GPU parallelism + LAN master/worker (UDP discovery + TCP dispatch)
Logs: local run logs (exportable; never contains paper content)
Packing: small installer; the runtime downloads on demand
(checks first, installs what's missing, with a progress bar)

[Development Note]
Developed independently by the author; part of the code was written and
debugged with the help of DeepSeek V4 Flash + Codex.

[Support]
If this project helped you a little, you are welcome to buy the author a
milk tea to support further development:
- Alipay / WeChat Pay: scan the QR codes shown in the app or on the project page
- No pressure at all - give only if you want to. It is not moral coercion.
  The author is still a student with a tiny allowance, but
  building this project is already meaningful on its own; your support is
  just extra encouragement.
For international users: if you don't use Alipay or WeChat Pay, you can also
gift any AI API key (any provider is welcome) to gxgx3456@qq.com. Please
include: model name, API/model URL and port. If you'd like to be credited,
mark it as "Special Thanks". Recommended: DeepSeek (great value) -
https://platform.deepseek.com/api_keys . If you really want to gift one,
DeepSeek V4 Flash is the most cost-effective choice.

[Bug Reports]
Click "Export Logs" in the app and send the package to: gxgx3456@qq.com

[Disclaimer]
The author is still a student;
the code may have flaws. Please be kind - friendly suggestions and
improvements are always welcome. This project is free and open source,
for learning and exchange only.

[License] MIT
"""
