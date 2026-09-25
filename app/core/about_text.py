ABOUT_TEXT = """AI 检测工具箱（AIGC Detector Toolkit）
====================================

【简介】
一款本地运行的 AIGC 检测桌面工具：拖入论文（PDF/DOCX/TXT），
选择检测引擎，得到整篇 AI 生成占比与段落级报告。
- 全程离线推理：论文内容不上传任何平台，保护隐私
- 5 个可切换检测引擎：SimpleAI 中文检测（默认）、GLTR 困惑度、
  Fast-DetectGPT、DetectGPT、Binoculars，也可接入任意 HuggingFace 模型
- 模型不预置、按需下载：用到哪个下哪个，下载一次之后完全离线可用
- 参数可自定义并存档
- 同机多卡自动并行；局域网可把室友电脑、Pad、手机加入并行计算
- 检测 → 诊断 → 治疗闭环：检测出 AI 率后，本地规则引擎诊断 AI 痕迹（段落级 JSON），
  再按“三轮降重协议”做保学术语体的确定性降重
- 附带 RAID / MGTBench 评测基准：用带标注的样本给自己的检测结果做体检
  （准确率、假阳性率、按生成模型分项），可导入官方数据集子集
- v1.2 新增：轻量安装器（AI 组件改为首次启动时自动下载，CPU/CUDA 自动选择）、
  模型保存路径可自定义、内置国内镜像加速下载
- v1.2.3 新增：自动降重闭环（改写 → 本地模型复检 AI 率 → 超标段落循环再改，
  直到达标或最大轮数）；安装器下载多镜像 + curl 兜底 + 支持手动选择本地安装包
- v1.2.4 新增：支持在 Windows「设置 > 应用 / 控制面板」卸载（含 bug 反馈邮箱）、
  安装时可勾选桌面快捷方式与完成后立即运行、安装器全屏按钮移至右上角
- v1.2.5 修复：打开闪退（torch 被安全软件拦截时改为容错启动并提示）
- v1.2.6 修复：高分屏（缩放 125%/150%）下的文字重影；界面按设计规范重做
- v1.2.7 修复（重点，安装/下载成功率）：
  ① 安装器改用官方 embeddable 便携包（解压即用，不写注册表、不需要管理员权限），
     彻底解决「静默安装退出码 0 却没装上」「卸载/修复报 1603」
  ② 新增网络自愈：VPN 常把系统代理设成 socks://，Python 的 urllib/pip 不支持 →
     自动改直连；下载链路升级为 urllib → 直连 → 系统 curl 三段兜底
- v1.2.8 新增（9 个引擎全部落地 + 插件化）：
  ① 检查引擎补齐到 5 个（SimpleAI / GLTR / Fast-DetectGPT / DetectGPT / Binoculars），
     Fast-DetectGPT 改为按论文的条件概率曲率实现，DetectGPT 按论文的掩码扰动实现；
  ② RAID / MGTBench 变成可运行的评测模块，不再是纸面引用；
  ③ 引擎管理按「检查 / 修复 / 评测」三类分组展示，模型一律按需下载；
  ④ 预留扩展接口：新增算法只要丢一个 .py 进 engines_plugins/，或填写引擎清单
     地址点「检查更新」，都不需要重新打包软件
- v1.3.0 新增 / 修复：
  ① 全新应用图标（程序、任务栏、安装器、桌面快捷方式、卸载列表统一，透明底无白框）；
  ② 修复全屏时按钮文字被裁（小屏 1440×900 上左侧面板被 Qt 等比压扁所致，
     现在改成滚动 + 按钮最小高度锁定，并统一限制窗口不超出屏幕）
- v1.3.1 / v1.3.2 新增 / 修复：
  ① 协议由 MIT 改为 PolyForm Noncommercial 1.0.0 —— 源码公开，**禁止任何商业使用**，
     软件内 3 处可见标注（标题栏版权行、关于窗口横幅、关于窗口协议段）；
  ② 安装器支持覆盖安装：升级不再清空日志与已下载的模型，也不再重置主题 / 阈值 / 预设；
  ③ 修复一类机器装不上：代理软件卸载后残留的畸形系统代理（`http://` 无主机名）
     会让 pip 报 `proxy URL is malformed`，现改为自动识别并转直连；
  ④ 安装包不再夹带作者本机的设备标识与运行日志
- v1.3.3 新增 / 变更：
  ① 新增 Telegram 联系方式 @A9100010：主界面「联系作者」同屏显示邮箱与 Telegram，
     一键复制两者；「关于」窗口、卸载提示、安装器界面、导出日志提示同步更新；
  ② 国际用户赞赏说明改为直接 Telegram 联系打赏（不再需要赠送 API Key）；
  ③ 反馈 / 意见 / 合作统一给出邮箱与 Telegram 两个渠道

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

【集成的方法与落地状态（v1.2.8 起 9 项全部可运行）】
本项目不是自创算法：9 项经过学术评审的方法全部落地成可运行的引擎或评测模块，
分「检查」「修复」「评测」三类。模型不预置，用到哪个下哪个。

■ 检查引擎（5 个 · 判断文本是否 AI 生成）
1) SimpleAI / HC3（默认中文引擎）· arXiv:2301.07597
   数据集、代码、模型全部公开，被大量研究引用。
2) GLTR（统计检测）· arXiv:1906.04043，来自 MIT，NeurIPS 2019
   语言模型困惑度，越低越像机器写的。
3) Fast-DetectGPT · arXiv:2310.05130，ICLR 2024
   按论文的采样近似实现：用打分模型自身采样构造扰动样本，
   比较条件概率曲率。模型较大，建议独立显卡。
4) DetectGPT · arXiv:2301.11305，斯坦福，ICML 2023（Oral）
   按论文的掩码扰动实现：用 T5 补全随机挖掉的片段，比较对数概率曲率。
   零样本，无需训练数据。
5) Binoculars · arXiv:2401.12070，ICML 2024
   同词表双模型交叉困惑度比，只看比值不看绝对值，免调阈值。
   （以上引擎用哪个 HuggingFace 模型由引擎清单声明，换模型不必改代码）

■ 修复引擎（2 个 · 诊断 + 降重 · 内置规则，无需下载模型）
6) aigc-reduce 三轮降重协议（MIT 开源项目）
   9 维扫描 + AI 高频词替换表 + 口语化负面清单 + 受保护片段，
   三轮确定性改写，坚持「降重 ≠ 口语化」。
7) 知网 5 种语言模式诊断（MIT 开源项目 cnki-aigc---skill）
   句法节奏 / 信息密度 / 术语句法位置 / 连接词功能 / 模板段功能，
   该做法实测总 AI 率 20.6% → 10.1%。

■ 评测基准（2 个 · 给检测器做体检）
8) RAID · arXiv:2401.09985，ACL 2024（600 万+ 条文本）
   输出准确率、假阳性率（人类文章被判成 AI 的比例）、假阴性率，
   并按生成模型分项。
9) MGTBench · arXiv:2303.14822（首个面向 LLM 的检测基准框架）
   精确率 / 召回率 / F1，用于横向比较不同检测器。
   两个基准都支持导入官方数据集子集（CSV / JSONL）；
   内置样本是作者手写的快速自检集，不代表官方成绩。

另外，「深度 AI 痕迹」清单源自 Wikipedia “Signs of AI writing”
（WikiProject AI Cleanup 维护），经 aigc-reduce 本地化适配。

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
界面：Python + PySide6（自绘现代工具风 UI）
检测：transformers（5 个可切换引擎，模型按需下载、全程离线推理）
修复：本地规则引擎（9 维扫描 + 知网 5 种语言模式 + 11 种深度 AI 痕迹，段落级 JSON）
评测：RAID / MGTBench 指标（准确率 / 假阳性率 / 假阴性率 / F1，按生成模型分项）
扩展：引擎插件目录（engines_plugins/*.py）+ 可远端更新的引擎清单
多设备：同机多卡自动并行 + 局域网主从节点（UDP 发现 + TCP 分发）
统计：仅本地运行日志（可导出）；不含任何遥测上报
打包：小体积安装器，环境按需下载（先检查、缺什么装什么、带进度条）

【支持与赞赏 · Support】
如果这个项目对你有一点帮助，可以请作者喝杯奶茶，支持继续开发：
- 支付宝（Alipay） / 微信支付（WeChat Pay）：扫描软件内或项目主页的赞赏码即可
- 想给就给，不想给就不给，绝非道德绑架。做这个项目本身已经很有意义，
  你的支持只是额外的鼓励。

For international users:
If you'd like to tip but don't use either of the two payment methods above,
you can contact me on Telegram to send a tip instead - thank you!!!
Telegram: @A9100010  (not my personal account; it is a purchased one)

【Bug 反馈 · 反馈 / 意见 / 合作都欢迎联系】
点击「导出日志」打包日志后，发送至：gxgx3456@qq.com
或 Telegram 私信：@A9100010

【开源协议 · 禁止商业使用】
本项目的代码公开，但**禁止任何形式的商业使用**。
采用 PolyForm Noncommercial License 1.0.0。

✅ 允许：个人学习、研究、实验、测试；个人爱好项目；
        学校 / 非营利组织 / 政府机构等非商业组织内部使用；
        阅读源码、提交反馈、在保留协议与署名的前提下分享。
❌ 禁止：任何商业用途（含公司内部使用、为客户提供服务、SaaS 托管）；
        转售本软件或修改后的版本；
        去除或篡改作者署名、版权声明；
        用本项目代码 / 模型训练商业产品。

如需商业授权 · 反馈 / 意见 / 合作，请联系：
  gxgx3456@qq.com 或 Telegram @A9100010

> 本协议限制的是**他人**的商业使用，不影响作者本人对项目收费或提供商业授权。
"""

ABOUT_TEXT_EN = """AIGC Detector Toolkit
====================================

[Introduction]
A local AIGC detection desktop tool: drop in a paper (PDF/DOCX/TXT),
choose a detection engine, and get the overall AI-written ratio plus
a paragraph-level report.
- Fully offline inference: your paper never leaves your computer
- 5 switchable detectors: SimpleAI Chinese (default), GLTR perplexity,
  Fast-DetectGPT, DetectGPT and Binoculars - or any HuggingFace model you like
- Models are never bundled: download only the ones you use, then work offline
- Highly customizable parameters, with savable presets
- Automatic multi-GPU parallelism on one machine; LAN cluster lets you add
  roommates' PCs, Pads and phones to the compute pool
- Detect → Diagnose → Treat: after detecting the AI ratio, a fully local rule
  engine diagnoses AI traces (paragraph-level JSON), then applies deterministic
  rewriting that keeps the academic register
- RAID / MGTBench benchmarks included: audit your own detection results on
  labelled samples (accuracy, false-positive rate, per-generator breakdown);
  import a subset of the official datasets any time
- New in v1.2: lightweight installer (AI components download on first launch,
  CUDA/CPU auto-selected), customizable model storage path, China mirror for
  faster downloads
- New in v1.2.3: auto-rewrite loop (rewrite → re-check AI ratio with the local
  model → retry over-threshold paragraphs until target or max rounds);
  installer multi-mirror download with curl fallback and local-installer picker
- New in v1.2.4: uninstall entry in Windows Settings > Apps / Control Panel
  (with bug-report email), installer options for desktop shortcut and
  launch-after-install, fullscreen button moved to the top-right corner
- v1.2.5 fix: crash on launch when torch is blocked by security software
  (falls back gracefully with a clear message)
- v1.2.6 fix: garbled/double text on HiDPI scaling (125% / 150%); UI rebuilt
  according to the design spec
- v1.2.7 fix (installation & download reliability):
  1) installer now uses the official embeddable portable package (no registry,
     no admin rights) - fixes the "silent install exits 0 but nothing installed"
     and "uninstall/repair fails with 1603" dead end
  2) network self-heal: VPN clients often set a socks:// system proxy which
     Python's urllib/pip cannot use - now auto-switched to direct connection;
     download chain is urllib -> direct -> system curl
- New in v1.2.8 (all 9 methods live + pluggable engines):
  1) detectors completed to 5 (SimpleAI / GLTR / Fast-DetectGPT / DetectGPT /
     Binoculars). Fast-DetectGPT now follows the paper's conditional probability
     curvature, DetectGPT follows the paper's masked perturbation;
  2) RAID / MGTBench became runnable benchmark modules instead of paper citations;
  3) the engine manager groups everything into Detectors / Rewriters / Benchmarks,
     and every model is downloaded on demand;
  4) extension points: drop a .py into engines_plugins/, or point the engine-list
     URL and hit "Check for updates" - neither needs a rebuild
- New / fixed in v1.3.0:
  1) brand new app icon (window, taskbar, installer, desktop shortcut, uninstall
     entry all share it; transparent background, no white box);
  2) fixed clipped button text in fullscreen on small screens (1440x900): the left
     panel is ~1082px tall so Qt squeezed every widget; it now scrolls instead,
     buttons cannot shrink below their text, and windows are clamped to the screen
- New / fixed in v1.3.1 / v1.3.2:
  1) licence changed from MIT to PolyForm Noncommercial 1.0.0 - the source stays public
     but **all commercial use is prohibited**, with three visible notices in the app
     (copyright line under the title bar, banner in the About window, licence section
     in its body);
  2) the installer overwrites in place: upgrading keeps your logs and downloaded models,
     and no longer resets theme / thresholds / presets;
  3) fixed "cannot install on some machines": a malformed leftover system proxy
     (`http://` with no host) made pip fail with `proxy URL is malformed`; it is now
     detected and switched to a direct connection;
  4) the installer no longer carries the author's local device id or run logs
- New / changed in v1.3.3:
  1) added a Telegram contact, @A9100010: the main window's Contact section now shows the
     email and Telegram on one line and copies both in one click; the About window,
     uninstall prompt, installer window and log-export dialog were updated to match;
  2) the international support note now points straight at Telegram tipping
     (no more "gift an API key");
  3) feedback / suggestions / collaboration now list both channels

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

[Integrated methods & implementation status (all 9 live since v1.2.8)]
This project does not invent algorithms: 9 peer-reviewed methods are all
implemented as runnable engines or benchmark modules, grouped into
Detectors / Rewriters / Benchmarks. No model is bundled; download what you use.

-- Detectors (5) - is this text AI-written? --
1) SimpleAI / HC3 (default Chinese engine) - arXiv:2301.07597
   Dataset, code and models are fully public and widely cited.
2) GLTR (statistical detection) - arXiv:1906.04043, MIT, NeurIPS 2019
   Language-model perplexity: the lower, the more machine-like.
3) Fast-DetectGPT - arXiv:2310.05130, ICLR 2024
   Sampling approximation of the paper: the scoring model samples its own
   perturbations, then we compare conditional probability curvature. Large
   model; a discrete GPU is recommended.
4) DetectGPT - arXiv:2301.11305, Stanford, ICML 2023 (Oral)
   Masked-perturbation implementation: T5 refills randomly removed spans and we
   compare log-probability curvature. Zero-shot, no training data needed.
5) Binoculars - arXiv:2401.12070, ICML 2024
   Two same-tokenizer models scored cross-wise; a ratio, so no threshold
   tuning per domain. (Which HuggingFace model each engine uses is declared in
   the engine list, so swapping models never requires code changes.)

-- Rewriters (2) - diagnose & reduce, built-in rules, no model download --
6) aigc-reduce three-round rewrite protocol (MIT project)
   9-dimension scan + AI-frequent word table + colloquial blacklist +
   protected spans; deterministic rewriting that keeps the academic register.
7) CNKI 5-language-pattern diagnosis (MIT project cnki-aigc---skill)
   Sentence rhythm / information density / term position / connective function /
   template blocks; that method measured 20.6% -> 10.1% in practice.

-- Benchmarks (2) - audit a detector --
8) RAID - arXiv:2401.09985, ACL 2024 (6M+ texts)
   Accuracy, false-positive rate (human text flagged as AI), false-negative
   rate, and a per-generator breakdown.
9) MGTBench - arXiv:2303.14822 (first detection benchmark framework for LLMs)
   Precision / recall / F1 for comparing detectors head to head.
   Both accept a subset of the official datasets (CSV / JSONL); the built-in
   set is a hand-written smoke test, not an official score.

Separately, the "deep AI patterns" list originates from Wikipedia's
"Signs of AI writing" (WikiProject AI Cleanup), localized by aigc-reduce.

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
UI: Python + PySide6 (custom modern-tool UI)
Detection: transformers (5 switchable engines; models downloaded on demand,
          inference always local)
Rewrite: local rule engine (9-dimension scan + CNKI 5 patterns + 11 deep AI
         patterns, paragraph-level JSON)
Benchmarks: RAID / MGTBench metrics (accuracy / FPR / FNR / F1, per generator)
Extension: engine plugin folder (engines_plugins/*.py) + remotely updatable
           engine list
Multi-device: multi-GPU parallelism + LAN master/worker (UDP discovery + TCP dispatch)
Logs: local run logs only (exportable); no telemetry is uploaded
Packing: small installer; the runtime downloads on demand
(checks first, installs what's missing, with a progress bar)

[Support]
If this project helped you a little, you are welcome to buy the author a
milk tea to support further development:
- Alipay / WeChat Pay: scan the QR codes shown in the app or on the project page
- No pressure at all - give only if you want to. It is not moral coercion.
  Building this project is already meaningful on its own; your support is
  just extra encouragement.
For international users: if you'd like to tip but don't use either of the two
payment methods above, you can contact me on Telegram to send a tip instead
- thank you!!! Telegram: @A9100010 (not my personal account; it is a
purchased one)

[Bug Reports - feedback / suggestions / collaboration all welcome]
Click "Export Logs" in the app and send the package to: gxgx3456@qq.com
or message @A9100010 on Telegram

[License - Commercial Use Prohibited]
The source code of this project is public, but **all commercial use is
prohibited**. Licensed under the PolyForm Noncommercial License 1.0.0.

Permitted: personal study, research, experiment and testing; personal hobby
           projects; use inside noncommercial organizations (schools,
           nonprofits, government bodies); reading the source and giving
           feedback; sharing with the license and attribution kept intact.
Prohibited: any commercial use (including internal company use, client work,
            SaaS hosting); reselling the software or modified versions;
            removing or altering the author's attribution or copyright
            notices; using this project's code / models to train commercial
            products.

For commercial licensing / feedback / suggestions / collaboration, contact:
  gxgx3456@qq.com or Telegram @A9100010

> This license restricts **third-party** commercial use only. It does not
> prevent the author from charging for the project or offering commercial
> licenses.
"""
