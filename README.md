# AI 检测工具箱（AIGC Detector Toolkit）

<p align="center">
  <img src="app/assets/icon.png" width="120" alt="AI 检测工具箱">
</p>

<p align="center"><b>中文</b> | <a href="README.en.md">English</a></p>

> ⛔ **禁止商业使用（Noncommercial only）**
> 本项目源码公开，但**禁止任何形式的商业使用** —— 个人学习 / 研究 / 非营利组织使用免费，
> 采用 [PolyForm Noncommercial License 1.0.0](LICENSE)。商用请先联系作者获得书面授权。
> 详见 [开源协议](#开源协议)。

> 免费的本地 AI 率检测 —— 宿舍算力也能跑，论文不上传，结果在自己手里。

## 📖 从这里开始

- 👉 **[仓库文件说明.md](仓库文件说明.md)** —— **每个文件是干什么的**、哪个能删哪个不能删、clone 下来怎么跑（[English](REPO_FILES.md)）
- 📝 **[更新日志.md](更新日志.md)** —— 每个版本改了什么，都标了**「用户可见变化」**（English: [CHANGELOG.md](CHANGELOG.md)）
- ❓ 遇到问题？见文末 [Bug 反馈](#bug-反馈)，直接发邮件

> **只想安装使用的话，你只需要下载 [`AIGC_Toolkit_Setup.exe`](AIGC_Toolkit_Setup.exe) 一个文件**（就在本仓库根目录），双击安装即可，其余文件都不用管。

## ✨ 功能介绍

| 能力 | 说明 |
|---|---|
| **整篇 AI 率检测** | 拖入 PDF / DOCX / TXT 论文，直接给出整篇 AI 生成占比 |
| **段落级定位** | 逐段输出 AI 概率，红色高亮最可疑的段落，照着改就行 |
| **检测 → 诊断 → 降重闭环** | 先诊断 11 种 AI 痕迹（段落级 JSON 报告），再按「三轮降重协议」做确定性改写，**降重 ≠ 口语化**，守住学术书面语体 |
| **自动降重** | 改写后本地复检，没降到目标 AI 率就继续改，循环到达标为止 |
| **5 个检测引擎** | SimpleAI 中文（默认）、GLTR 困惑度、Fast-DetectGPT、DetectGPT、Binoculars；也可接入任意 HuggingFace 模型 |
| **模型按需下载** | 软件不预置模型，用哪个下哪个；下载一次后完全离线运行 |
| **评测基准** | 内置 RAID / MGTBench：用带标注样本测出准确率、假阳性率、按生成模型分项；可导入官方数据集子集 |
| **全程离线** | 推理全在本机跑，论文不上传任何平台；模型下载一次后就断网可用 |
| **多设备算力合并** | 同机多显卡自动并行；局域网内可把室友的电脑、Pad、手机并入并行计算 |
| **模型路径可自定义** | 模型可放任意磁盘（如 D 盘），装在 C 盘也不占空间，重装软件不影响已下载的模型 |
| **参数高度自定义** | 判定阈值、段落切分、并行数等均可调；预设可存档、导出、导入 |
| **中英双语** | 软件界面与安装器均支持一键切换 中文 / English |

## 简介

一款**本地运行**的 AIGC 检测桌面工具：拖入论文（PDF / DOCX / TXT），选择检测引擎，即可得到整篇 AI 生成占比与段落级报告。

- **全程离线推理**：检测模型本地下载一次，论文内容不会上传给任何平台，保护隐私
- **模型保存路径可自定义**：模型可存到任意磁盘（如 D 盘），装在 C 盘也不怕占空间；重装软件不影响已下载的模型
- **5 个检测引擎**：SimpleAI 中文（默认）、GLTR 困惑度、Fast-DetectGPT、DetectGPT、Binoculars，也支持任意 HuggingFace 模型
- **模型按需下载**：软件不预置模型，用哪个下哪个，下载一次后完全离线可用
- **评测基准**：内置 RAID / MGTBench，用带标注样本给自己的检测结果做体检（准确率、假阳性率、按生成模型分项）
- **参数高度自定义**：判定阈值、段落切分、并行数等均可调整，预设可存档、导出、导入
- **多设备算力合并**：同一台机器多显卡自动并行；局域网内可把室友的电脑、Pad、手机都加入并行计算
- **检测 → 诊断 → 治疗闭环**：检测出 AI 率后，本地规则引擎诊断 AI 痕迹（段落级 JSON 报告），
  再按“三轮降重协议”做保学术语体的确定性降重
- **中英双语**：软件界面与安装器均支持一键切换 中文 / English
- **个人免费**：预留收费接口，个人非商业用途永远免费，**禁止任何形式的商业使用**

## 检测 → 诊断 → 治疗（v1.1 新增）

检测只是第一步。本项目融合了两个 MIT 开源项目的方法论，形成完整闭环，**全部本地运行、不调用任何外部 AI**：

### 诊断（本地规则引擎）

扫描以下三类信号，输出**段落级结构化 JSON 报告**（可导出）：

| 类别 | 内容 |
|---|---|
| 9 维特征扫描 | 模板句式密度、突发性（句长变异系数 CV）、段落对称性、被动语态、嵌套编号、冒号并列、标点规律、**口语化预警**、**破折号密度**（后两项是“降重过度”门禁，守学术语体） |
| 知网 5 种语言模式 | 句法节奏可预测性、信息密度均匀性、术语句法位置固定、连接词功能重叠、模板段功能全等性 |
| 11 种深度 AI 痕迹 | 重要性膨胀、同义词轮换、三板斧强迫症、系词回避、模糊归因、公式化挑战段、悬浮式分析、空洞结论、破折号过度使用、虚假范围、成对转折收束 |

每一段都会给出：风险等级、命中的模式与证据片段、逐句标记、建议动作。

### 治疗（三轮降重协议，确定性改写）

1. **第一轮（减法）**：先圈出受保护片段（引用编号、图表/公式编号、数据/百分比/P 值、专业术语、引语，**一字不动**），再做词级替换（中文 AI 高频词，多个变体轮换）、句级重构、拆排比/编号；
2. **第二轮（加法）**：节奏工程——确定性长句拆分（目标 CV ≈ 0.45），**绝不编造原文没有的事实、数据或文献**；
3. **第三轮（自检）**：Anti-AI 审计 + 语体守门——口语化/网络用语必须改回书面学术表达，破折号每段 ≤1 个，**语体优先于修改率**。

四条铁律全程生效：禁止 AI 全量重写、修改率 >40% 只靠结构改写与模板去除、确定性替换、保持学术语体。

检测完成后，如果整篇 AI 率超过你设置的阈值（默认 30%，可改），软件会弹出建议进入降重；也可以随时点「开始降重」。

## 灵感故事

这个项目的灵感来自我的一位**大学生朋友**。

他的毕业论文需要**反复查 AI 率**——每改一版都要查一次，学校提供的官方检测入口不仅次数有限，而且相当费钱。听着他的抱怨，我冒出一个想法：**宿舍里总会有人打游戏，游戏电脑基本都有独立显卡，完全跑得动本地 AI 检测**；一张显卡不够，还能用数据线 / 局域网把室友的电脑连起来，甚至把 **Pad、手机** 也加进来合并算力。

于是就有了这个项目：让论文检测**回归本地、免费、可控**。

## 集成的 9 项方法（全部已实现，不是纸面引用）

本项目**不是自创检测算法**，而是把以下经过**学术评审**的方法**全部落地成可运行的引擎或评测模块**，分「检查 / 修复 / 评测」三类。模型不预置，用到哪个下哪个。

### 检查引擎（5 个 · 判断文本是否 AI 生成）

| 项目 / 论文 | 在本项目里怎么实现的 | 链接 |
|---|---|---|
| **SimpleAI / HC3**（默认中文引擎） | RoBERTa 序列分类模型，逐段输出 AI 概率；论文《How Close is ChatGPT to Human Experts?》 | [arXiv](https://arxiv.org/abs/2301.07597) · [GitHub](https://github.com/Hello-SimpleAI/chatgpt-comparison-detection) |
| **GLTR** | 语言模型困惑度：PPL ≤ 低阈值判 0.85、≥ 高阈值判 0.15，中间线性插值；MIT 出品，NeurIPS 2019 | [arXiv](https://arxiv.org/abs/1906.04043) · [GitHub](https://github.com/HendrikStrobelt/GLTR) |
| **Fast-DetectGPT** | **按论文的条件概率曲率实现**：用打分模型自身采样构造扰动样本 x̃，比较 `logP(x) − E[logP(x̃)]`；ICLR 2024 | [arXiv](https://arxiv.org/abs/2310.05130) · [GitHub](https://github.com/baoguangsheng/fast-detect-gpt) |
| **DetectGPT** | **按论文的掩码扰动实现**：T5 补全随机挖掉的片段得到 x̃，比较对数概率曲率；零样本，斯坦福，ICML 2023 (Oral) | [arXiv](https://arxiv.org/abs/2301.11305) · [GitHub](https://github.com/ericmitchell/DetectGPT) |
| **Binoculars** | 同词表双模型交叉困惑度比 `B = logPPL_observer / crossPPL_performer`，B 越小越像 AI；只看比值，免调阈值；ICML 2024 | [arXiv](https://arxiv.org/abs/2401.12070) · [GitHub](https://github.com/AHans30/Binoculars) |

### 修复引擎（2 个 · 诊断 + 降重 · 内置规则，不需要下载模型）

| 项目 | 在本项目里怎么实现的 | 链接 |
|---|---|---|
| **aigc-reduce** | 三轮降重协议完整落地：9 维扫描 + AI 高频词替换表 + 口语化负面清单 + 受保护片段，确定性改写、语体守门。规则来自知网 3.0 / 万方 / PaperPass / PaperPure 的检测原理 | [GitHub](https://github.com/xiaofenggan01/aigc-reduce) |
| **cnki-aigc---skill** | 知网 5 种语言模式（句法节奏 / 信息密度 / 术语句法位置 / 连接词功能 / 模板段功能）落地为段落级诊断，输出结构化 JSON；该做法实测 20.6% → 10.1% | [GitHub](https://github.com/qingshanliuci/cnki-aigc---skill) |

### 评测基准（2 个 · 给检测器做体检）

| 项目 / 论文 | 在本项目里怎么实现的 | 链接 |
|---|---|---|
| **RAID** | 可运行的评测模块：拿带标注样本跑出准确率、**假阳性率**（人类文章被判成 AI 的比例）、假阴性率，并按生成模型分项；ACL 2024，600 万+ 条文本 | [arXiv](https://arxiv.org/abs/2401.09985) · [ACL](https://aclanthology.org/2024.acl-long.674/) · [GitHub](https://github.com/liamdugan/raid) |
| **MGTBench** | 同一套样本上算精确率 / 召回率 / F1，横向比较不同检测器；首个面向 LLM 的检测基准框架 | [arXiv](https://arxiv.org/abs/2303.14822) · [GitHub](https://github.com/xinleihe/MGTBench) |

两个基准都支持**导入官方数据集子集**（CSV / JSONL）跑真实评测，也能导出 Markdown 报告。
内置那 15 条只是作者手写的快速自检集，不代表官方成绩。

> 另外，「深度 AI 痕迹」清单源自 Wikipedia “Signs of AI writing”（WikiProject AI Cleanup 维护），经 aigc-reduce 本地化适配。
>
> 声明：检测效果受模型与文本类型影响，结果仅供自测参考，不代表任何权威机构结论；请以学校 / 期刊官方认定为准。

## 扩展：换模型 / 加新引擎（不用重新打包）

1. **换模型**：安装目录下建 `engines_catalog.json`，写你要覆盖的字段即可，例如把 Binoculars 换成 Falcon 组合：
   ```json
   [{"id": "binoculars", "models": [{"repo": "tiiuae/falcon-7b"}, {"repo": "tiiuae/falcon-7b-instruct"}]}]
   ```
2. **加新算法**：往 `engines_plugins/` 丢一个 `.py`，用 `@register("my_impl")` 声明并实现 `predict_paragraphs()`，启动时自动发现。
3. **远端清单**：引擎管理 →「检查更新」→ 填 `engines_manifest.json` 的地址，以后有新引擎 / 新模型直接拉取，无需升级软件。

## 特别感谢（算力合并）

本项目"多设备并行检测"借鉴了以下两个开源项目的思路：

- **[exo](https://github.com/exo-explore/exo)**（exo-explore/exo，GitHub 约 4.6 万 star）：把日常设备（手机、Pad、笔记本、游戏主机）组成 **P2P 分布式 AI 集群**，自动发现设备、动态切分模型，用普通家用设备跑大模型。
- **[llama.cpp](https://github.com/ggml-org/llama.cpp)**（ggml-org/llama.cpp）：最受欢迎的本地 LLM 推理框架之一，其 [RPC 分布式推理](https://github.com/ggml-org/llama.cpp/tree/master/tools/rpc) 可在异构设备（如 Mac Metal + NVIDIA CUDA）间切分模型层，是本项目困惑度类引擎跨设备计算的参考方案。

感谢以上项目及其社区，让"宿舍算力合并"成为可能。

## 特别感谢（诊断与治疗）

“检测 → 诊断 → 治疗”闭环直接融合了以下两个 MIT 开源项目的方法论：

- **[aigc-reduce](https://github.com/xiaofenggan01/aigc-reduce)**（xiaofenggan01/aigc-reduce）：提供三轮降重协议、替换表、中文 AI 高频词清单、口语化负面清单与 9 维扫描方法论。本项目降重引擎完全按其规则实现，坚持“降重 ≠ 口语化”，保持学术书面语体为硬底线。
- **[cnki-aigc---skill](https://github.com/qingshanliuci/cnki-aigc---skill)**（qingshanliuci/cnki-aigc---skill）：基于知网 AIGC 检测器“5 种语言模式”的实战方法（实测 20.6% → 10.1%）。本项目诊断引擎按其模式实现。

感谢两位作者与相关社区，让"检测、诊断、治疗"的完整流程成为可能。

## 支持与赞赏 · Support

这个项目对个人完全免费。如果它对你有一点帮助，可以**请作者喝杯奶茶**，支持继续开发；或者**把项目分享给需要的同学**、点个 ⭐ **Star**，同样是最好的支持。

> ⚠️ **本项目禁止任何形式的商业使用。** 个人学习、研究、交流免费；如需商用请先联系作者获得书面授权。

<p align="center">
  <img src="app/assets/donate/alipay.jpg" width="220" alt="支付宝赞赏码 / Alipay" title="支付宝 / Alipay">
  <img src="app/assets/donate/wechat_pay.jpg" width="220" alt="微信支付赞赏码 / WeChat Pay" title="微信支付 / WeChat Pay">
</p>

<p align="center">支付宝（Alipay）｜微信支付（WeChat Pay）</p>

也欢迎发邮件到 **gxgx3456@qq.com** 说声加油。

### For international users

You can also **gift an AI API key** (any provider is welcome) to **gxgx3456@qq.com**. Please include:

- Model name (模型型号)
- API / model URL and port (模型地址与端口)
- If you'd like to be credited, mark it as "特别感谢 / Special Thanks"

Recommended: [DeepSeek](https://platform.deepseek.com/api_keys) — great value. If you really want to gift one, **DeepSeek V4 Flash** is the most cost-effective choice. (Screenshot reference: [app/assets/donate/deepseek_usage.png](app/assets/donate/deepseek_usage.png))

## 技术架构

- 界面：Python + PySide6（自绘现代工具风 UI）
- 检测引擎：transformers —— 5 个可切换引擎（分类 / 困惑度 / 概率曲率 / 双模型），模型按需下载、全程离线推理
- 诊断：本地规则引擎（9 维扫描 + 知网 5 种语言模式 + 11 种深度 AI 痕迹，段落级 JSON）
- 治疗：三轮降重协议（确定性改写 + 受保护片段 + 语体守门，完全离线）
- 评测：RAID / MGTBench 指标（准确率 / 假阳性率 / 假阴性率 / F1，按生成模型分项）
- 扩展：引擎插件目录（`engines_plugins/*.py`）+ 可远端更新的引擎清单
- 多设备：同机多卡自动并行 + 局域网主从节点（UDP 自动发现 + TCP 任务分发）
- 日志：本地运行日志（可导出，不含论文内容）；**不含任何遥测上报**
- 打包：小体积安装器，运行时环境按需下载（先检查、缺什么装什么、带进度条）

## Bug 反馈

软件内点击「导出日志」打包日志后，发送至：**gxgx3456@qq.com**

## 开源协议

**本项目的代码公开，但禁止商业使用。** 采用 [PolyForm Noncommercial License 1.0.0](LICENSE)。

### ✅ 允许

- 个人学习、研究、实验、测试
- 个人爱好项目、私人娱乐
- 学校、非营利组织、政府机构等非商业组织内部使用
- 阅读源码、提交 Issue、提出改进建议
- 在保留协议与署名的前提下转载、分享

### ❌ 禁止

- **任何商业用途**（含公司内部使用、为客户提供服务、SaaS 托管等）
- **转售软件或修改后的版本**
- **去除或篡改作者署名、版权声明**
- 将本项目的代码 / 模型用于训练商业产品

### 如需商业授权

请邮件联系：**gxgx3456@qq.com**，说明用途与范围。

> 本协议限制的是**他人**的商业使用，不影响作者本人对项目收费或提供商业授权。
