# AI 检测工具箱（AIGC Detector Toolkit）

<p align="center"><b>中文</b> | <a href="README.en.md">English</a></p>

> 免费的本地 AI 率检测 —— 宿舍算力也能跑，论文不上传，结果在自己手里。

## 简介

一款**本地运行**的 AIGC 检测桌面工具：拖入论文（PDF / DOCX / TXT），选择检测引擎，即可得到整篇 AI 生成占比与段落级报告。

- **全程离线推理**：检测模型本地下载一次，论文内容不会上传给任何平台，保护隐私
- **多引擎可选**：SimpleAI 中文检测（默认）、GLTR 困惑度检测、Fast-DetectGPT 参考实现、以及可自定义的任意 HuggingFace 模型
- **参数高度自定义**：判定阈值、段落切分、并行数等均可调整，预设可存档、导出、导入
- **多设备算力合并**：同一台机器多显卡自动并行；局域网内可把室友的电脑、Pad、手机都加入并行计算
- **中英双语**：软件界面、安装器与数据看板均支持一键切换 中文 / English
- **免费开源**：预留收费接口，核心功能永远免费

## 灵感故事

这个项目的灵感来自我的一位**大学生朋友**。

他的毕业论文需要**反复查 AI 率**——每改一版都要查一次，学校提供的官方检测入口不仅次数有限，而且相当费钱。听着他的抱怨，我冒出一个想法：**宿舍里总会有人打游戏，游戏电脑基本都有独立显卡，完全跑得动本地 AI 检测**；一张显卡不够，还能用数据线 / 局域网把室友的电脑连起来，甚至把 **Pad、手机** 也加进来合并算力。

于是就有了这个项目：让论文检测**回归本地、免费、可控**。

## 权威性依据（为什么可信）

本项目**不是自创检测算法**，而是把以下经过**学术评审**的开源方法与论文落地集成：

| 项目 / 论文 | 权威性证据 | 链接 |
|---|---|---|
| **SimpleAI / HC3**（默认中文引擎） | 论文《How Close is ChatGPT to Human Experts? Comparison Corpus, Evaluation, and Detection》，arXiv:2301.07597；数据集、代码、模型全部公开，被大量研究引用 | [arXiv](https://arxiv.org/abs/2301.07597) · [GitHub](https://github.com/Hello-SimpleAI/chatgpt-comparison-detection) |
| **Fast-DetectGPT**（参考实现） | 论文《Fast-DetectGPT: Efficient Zero-Shot Detection of Machine-Generated Text via Conditional Probability Curvature》，arXiv:2310.05130，发表于 **ICLR 2024**（国际学习表征会议，AI 领域顶级会议） | [arXiv](https://arxiv.org/abs/2310.05130) · [GitHub](https://github.com/baoguangsheng/fast-detect-gpt) |
| **GLTR**（统计检测方法） | 论文《GLTR: Statistical Detection and Visualization of Generated Text》，arXiv:1906.04043，来自 **MIT**，发表于 **NeurIPS 2019**（神经信息处理系统顶级会议） | [arXiv](https://arxiv.org/abs/1906.04043) · [GitHub](https://github.com/HendrikStrobelt/GLTR) |
| **DetectGPT**（零样本检测） | 论文《DetectGPT: Zero-Shot Machine-Generated Text Detection using Probability Curvature》，arXiv:2301.11305，发表于 **ICML 2023**（机器学习顶级会议，Oral 论文），来自斯坦福大学；无需训练数据即可零样本检测 | [arXiv](https://arxiv.org/abs/2301.11305) · [GitHub](https://github.com/ericmitchell/DetectGPT) |
| **Binoculars**（零样本检测） | 论文《Spotting LLMs With Binoculars: Zero-Shot Detection of Machine-Generated Text》，arXiv:2401.12070，发表于 **ICML 2024**（机器学习顶级会议），检测准确率领先，代码开源 | [arXiv](https://arxiv.org/abs/2401.12070) · [GitHub](https://github.com/AHans30/Binoculars) |
| **RAID**（评测基准） | 论文《RAID: A Shared Benchmark for Robust Evaluation of Machine-Generated Text Detectors》，arXiv:2401.09985，发表于 **ACL 2024**（计算语言学顶级会议）；目前最大、最全面的 AI 文本检测评测基准（600 万+ 条文本），用于公平评估各类检测器 | [arXiv](https://arxiv.org/abs/2401.09985) · [ACL](https://aclanthology.org/2024.acl-long.674/) · [GitHub](https://github.com/liamdugan/raid) |
| **MGTBench**（评测基准） | 论文《MGTBench: Benchmarking Machine-Generated Text Detection》，arXiv:2303.14822；首个面向大语言模型（LLM）的机器生成文本检测基准框架 | [arXiv](https://arxiv.org/abs/2303.14822) · [GitHub](https://github.com/xinleihe/MGTBench) |

> 声明：检测效果受模型与文本类型影响，结果仅供自测参考，不代表任何权威机构结论；请以学校 / 期刊官方认定为准。

## 特别感谢（算力合并）

本项目"多设备并行检测"借鉴了以下两个开源项目的思路：

- **[exo](https://github.com/exo-explore/exo)**（exo-explore/exo，GitHub 约 4.6 万 star）：把日常设备（手机、Pad、笔记本、游戏主机）组成 **P2P 分布式 AI 集群**，自动发现设备、动态切分模型，用普通家用设备跑大模型。
- **[llama.cpp](https://github.com/ggml-org/llama.cpp)**（ggml-org/llama.cpp）：最受欢迎的本地 LLM 推理框架之一，其 [RPC 分布式推理](https://github.com/ggml-org/llama.cpp/tree/master/tools/rpc) 可在异构设备（如 Mac Metal + NVIDIA CUDA）间切分模型层，是本项目困惑度类引擎跨设备计算的参考方案。

感谢以上项目及其社区，让"宿舍算力合并"成为可能。

## 支持与赞赏 · Support

如果这个项目对你有一点帮助，可以**请作者喝杯奶茶**，支持继续开发：

<p align="center">
  <img src="docs/donate/alipay.jpg" width="220" alt="支付宝赞赏码 / Alipay" title="支付宝 / Alipay">
  <img src="docs/donate/wechat_pay.jpg" width="220" alt="微信支付赞赏码 / WeChat Pay" title="微信支付 / WeChat Pay">
</p>

<p align="center">支付宝（Alipay）｜微信支付（WeChat Pay）</p>

**想给就给，不想给就不给，绝非道德绑架。** 作者还是一名初中生，零花钱不多，但做这个项目本身已经很有意义，你的支持只是额外的鼓励。

### For international users

If you don't use Alipay or WeChat Pay, you can also **gift any AI API key** (any provider is welcome) to **gxgx3456@qq.com**. Please include:

- Model name (模型型号)
- API / model URL and port (模型地址与端口)
- If you'd like to be credited, mark it as "特别感谢 / Special Thanks"

Recommended: [DeepSeek](https://platform.deepseek.com/api_keys) — great value. If you really want to gift one, **DeepSeek V4 Flash** is the most cost-effective choice. (Screenshot reference: [docs/donate/deepseek_usage.png](docs/donate/deepseek_usage.png))

## 使用数据看板（开源 · 任何人都能看）

> ⚠️ 先分清两样东西：
> - **项目主体**：AI 检测工具箱（检测论文 AI 率）——目录 `app/`、`installer/`，安装包 [dist/AIGC_Toolkit_Setup.exe](dist/AIGC_Toolkit_Setup.exe)
> - **数据看板**：查看匿名使用统计的工具（不参与检测）——就是下面的电脑版 / 安卓版

看板展示匿名统计（总启动次数、检测次数、在线设备、引擎/显卡分布、GitHub 下载量等），**任何人都可以看**。数据仅包含匿名元数据，不含论文内容与任何个人信息。电脑版检测软件安装后默认开启匿名统计（设置里可一键关闭），使用数据会自动出现在这里。

### 电脑版看板（Windows）

- 免安装 exe：[tools/dist/AIGC_Dashboard.exe](tools/dist/AIGC_Dashboard.exe) —— **下载后双击即用**（已内置查看密钥，无需配置）
- 源码：[tools/dashboard.py](tools/dashboard.py)
- 想让手机 / 其他设备（同一 Wi-Fi）也能看电脑上的看板：双击 [tools/run_dashboard_lan.bat](tools/run_dashboard_lan.bat)

### 安卓版看板（APK · 推荐）

- 安装包：[tools/dist/AIGC_Dashboard_allinone_v10.apk](tools/dist/AIGC_Dashboard_allinone_v10.apk) —— **下载安装后打开即可直接看数据**（已内置查看密钥）
- 看板页面右上角有 **中 / EN 切换按钮**，电脑版与安卓版通用
- 源码：[tools/apk_self/](tools/apk_self/)（自打包壳）与 [tools/android_webview/](tools/android_webview/)（Android Studio 工程）

### 手机免安装方案（Termux，可选）

- 压缩包：[tools/phone/AIGC_Dashboard_phone.zip](tools/phone/AIGC_Dashboard_phone.zip)（已内置查看密钥，免配置）
- 使用方法见 [tools/phone/README-phone.txt](tools/phone/README-phone.txt)

### 自建配置（fork / 自托管时）

预编译的 exe / APK 已内置作者项目的**查看密钥**（仅供查看这份公开的匿名统计）。源码中的密钥文件（`tools/dashboard_config.example.json`、`tools/apk_self/assets/posthog_key.txt`）保持占位符；**如果你 fork 自建，请填入你自己的 PostHog personal_api_key 与 project_id 后再打包**，不要沿用本仓库预编译包里的密钥。

## 技术架构

- 界面：Python + PySide6（玻璃拟态 UI）
- 检测引擎：transformers（SimpleAI 中文分类 / 困惑度检测）
- 多设备：同机多卡自动并行 + 局域网主从节点（UDP 自动发现 + TCP 任务分发）
- 统计：匿名遥测（PostHog，可一键关闭）+ 本地运行日志（可导出）
- 打包：小体积安装器，运行时环境按需下载（先检查、缺什么装什么、带进度条）

## 开发声明

本项目由作者独立开发，**部分代码由 DeepSeek V4 Flash + Codex 辅助编写与调试**。

## Bug 反馈

软件内点击「导出日志」打包日志后，发送至：**gxgx3456@qq.com**

## 免责声明

本人还是一名学生，**项目发布时 14 岁**，代码可能存在不足，不好勿喷，欢迎友善的建议与改进。本项目免费开源，仅供学习交流。

## 开源协议

[MIT](LICENSE)
