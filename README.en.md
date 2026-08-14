# AIGC Detector Toolkit

> Free local AI-written ratio detection - dorm PCs can run it, your paper never leaves your computer, and the results stay in your hands.

<p align="center"><a href="README.md">中文</a> | <b>English</b></p>

## Introduction

A **fully local** AIGC detection desktop tool: drag in a paper (PDF / DOCX / TXT), choose a detection engine, and get the overall AI-written ratio plus a paragraph-level report.

- **Fully offline inference**: the detection model is downloaded once; your paper is never uploaded to any platform
- **Multiple engines**: SimpleAI Chinese detection (default), GLTR perplexity detection, Fast-DetectGPT reference implementation, and any custom HuggingFace model
- **Highly customizable**: threshold, paragraph splitting, worker count and more; presets can be saved, exported and imported
- **Multi-device compute pooling**: automatic multi-GPU parallelism on one machine; add roommates' PCs, Pads and phones over LAN
- **Bilingual UI**: the app, installer and dashboards support one-click switching between 中文 / English
- **Free & open source**: a paid API is reserved, but the core features stay free forever

## Inspiration

This project was inspired by my **college-student friend**.

His graduation thesis had to be **re-checked for AI-written ratio again and again** - once per revision - while the official school service is limited and expensive. Hearing his complaints, it hit me: **there is always someone gaming in a dorm, and gaming PCs basically all have dedicated GPUs that can easily run local AI detection**; if one GPU is not enough, link roommates' computers with an Ethernet cable / LAN, or even add **Pads and phones** to the compute pool.

So this project was born: bringing thesis detection **back to local, free and controllable**.

## Why You Can Trust It

This project does **not invent its own algorithms** - it integrates the following **peer-reviewed** open-source methods and papers:

| Project / Paper | Evidence | Links |
|---|---|---|
| **SimpleAI / HC3** (default Chinese engine) | Paper "How Close is ChatGPT to Human Experts? Comparison Corpus, Evaluation, and Detection", arXiv:2301.07597; dataset, code and models are fully public and widely cited | [arXiv](https://arxiv.org/abs/2301.07597) · [GitHub](https://github.com/Hello-SimpleAI/chatgpt-comparison-detection) |
| **Fast-DetectGPT** (reference implementation) | Paper "Fast-DetectGPT: Efficient Zero-Shot Detection of Machine-Generated Text via Conditional Probability Curvature", arXiv:2310.05130, published at **ICLR 2024** (top AI conference) | [arXiv](https://arxiv.org/abs/2310.05130) · [GitHub](https://github.com/baoguangsheng/fast-detect-gpt) |
| **GLTR** (statistical detection method) | Paper "GLTR: Statistical Detection and Visualization of Generated Text", arXiv:1906.04043, from **MIT**, published at **NeurIPS 2019** (top conference) | [arXiv](https://arxiv.org/abs/1906.04043) · [GitHub](https://github.com/HendrikStrobelt/GLTR) |
| **DetectGPT** (zero-shot detection) | Paper "DetectGPT: Zero-Shot Machine-Generated Text Detection using Probability Curvature", arXiv:2301.11305, published at **ICML 2023** (top ML conference, Oral), from Stanford; zero-shot detection without training data | [arXiv](https://arxiv.org/abs/2301.11305) · [GitHub](https://github.com/ericmitchell/DetectGPT) |
| **Binoculars** (zero-shot detection) | Paper "Spotting LLMs With Binoculars: Zero-Shot Detection of Machine-Generated Text", arXiv:2401.12070, published at **ICML 2024** (top ML conference), state-of-the-art accuracy, open source | [arXiv](https://arxiv.org/abs/2401.12070) · [GitHub](https://github.com/AHans30/Binoculars) |
| **RAID** (benchmark) | Paper "RAID: A Shared Benchmark for Robust Evaluation of Machine-Generated Text Detectors", arXiv:2401.09985, published at **ACL 2024** (top NLP conference); the largest and most comprehensive benchmark for AI-text detectors (6M+ texts) for fair evaluation | [arXiv](https://arxiv.org/abs/2401.09985) · [ACL](https://aclanthology.org/2024.acl-long.674/) · [GitHub](https://github.com/liamdugan/raid) |
| **MGTBench** (benchmark) | Paper "MGTBench: Benchmarking Machine-Generated Text Detection", arXiv:2303.14822; the first benchmarking framework for machine-generated text detection against LLMs | [arXiv](https://arxiv.org/abs/2303.14822) · [GitHub](https://github.com/xinleihe/MGTBench) |

> Disclaimer: results depend on the model and text type. They are for self-checking only and are not the verdict of any authority - the official judgement of your school / journal always wins.

## Special Thanks (Compute Pooling)

The "multi-device parallel detection" feature borrows ideas from these two open-source projects:

- **[exo](https://github.com/exo-explore/exo)** (exo-explore/exo, ~46k stars on GitHub): turns everyday devices (phones, Pads, laptops, gaming PCs) into a **P2P distributed AI cluster** with auto-discovery and dynamic model splitting, running large models on ordinary home hardware.
- **[llama.cpp](https://github.com/ggml-org/llama.cpp)** (ggml-org/llama.cpp): one of the most popular local LLM inference frameworks; its [RPC distributed inference](https://github.com/ggml-org/llama.cpp/tree/master/tools/rpc) splits model layers across heterogeneous devices (e.g. Mac Metal + NVIDIA CUDA), serving as the reference for our cross-device perplexity engines.

Thanks to those projects and their communities for making "dorm compute pooling" possible.

## Support & Donate

If this project helped you a little, you are welcome to **buy the author a milk tea** to support further development:

<p align="center">
  <img src="docs/donate/alipay.jpg" width="220" alt="Alipay QR code" title="Alipay">
  <img src="docs/donate/wechat_pay.jpg" width="220" alt="WeChat Pay QR code" title="WeChat Pay">
</p>

<p align="center">Alipay ｜ WeChat Pay</p>

**No pressure at all - give only if you want to. It is not moral coercion.** The author is still a student with a tiny allowance, but building this project is already meaningful on its own; your support is just extra encouragement.

### For international users

If you don't use Alipay or WeChat Pay, you can also **gift any AI API key** (any provider is welcome) to **gxgx3456@qq.com**. Please include:

- Model name
- API / model URL and port
- If you'd like to be credited, mark it as "特别感谢 / Special Thanks"

Recommended: [DeepSeek](https://platform.deepseek.com/api_keys) - great value. If you really want to gift one, **DeepSeek V4 Flash** is the most cost-effective choice. (Screenshot reference: [docs/donate/deepseek_usage.png](docs/donate/deepseek_usage.png))

## Usage Dashboard (Open Source · Anyone Can View)

> ⚠️ Two things to tell apart:
> - **Main project**: the AIGC Detector Toolkit (detects AI-written text) - folders `app/`, `installer/`, installer [dist/AIGC_Toolkit_Setup.exe](dist/AIGC_Toolkit_Setup.exe)
> - **Usage dashboard**: tools for viewing anonymous usage stats (not part of detection) - the PC / Android versions below

This project also ships an **open-source usage dashboard** showing the software's anonymous usage statistics (total starts, detection count, online devices, engine/GPU distribution, GitHub download counts, etc.) - **anyone can view it**. It only contains anonymous metadata, never your paper content or personal information. The desktop detector app enables anonymous stats by default after installation (can be disabled in one click), so its usage data automatically shows up here.

### PC dashboard (Windows)

- Portable exe: [tools/dist/AIGC_Dashboard.exe](tools/dist/AIGC_Dashboard.exe) - **double-click and it just works** (view key built in, no config needed)
- Source: [tools/dashboard.py](tools/dashboard.py)
- To let phones / other devices (same Wi-Fi) view the dashboard on your PC: double-click [tools/run_dashboard_lan.bat](tools/run_dashboard_lan.bat)

### Android dashboard (APK · recommended)

- Installer: [tools/dist/AIGC_Dashboard_allinone_v10.apk](tools/dist/AIGC_Dashboard_allinone_v10.apk) - **install it, open it, and you can view the data directly** (view key built in)
- The dashboard has a **中 / EN toggle button** in the top-right corner (PC and Android)
- Source: [tools/apk_self/](tools/apk_self/) (self-packaged shell) and [tools/android_webview/](tools/android_webview/) (Android Studio project)

### Phone without APK (Termux, optional)

- Zip: [tools/phone/AIGC_Dashboard_phone.zip](tools/phone/AIGC_Dashboard_phone.zip) (view key built in, no config needed)
- Usage: see [tools/phone/README-phone.txt](tools/phone/README-phone.txt)

### Build your own config (fork / self-host)

The prebuilt exe / APK contains the author's **view key** (only for viewing this public anonymous statistics). Key files in the source (`tools/dashboard_config.example.json`, `tools/apk_self/assets/posthog_key.txt`) stay as placeholders; **if you fork and self-host, fill in your own PostHog personal_api_key and project_id before repackaging** - do not reuse the key in the prebuilt packages.

## Tech Stack

- UI: Python + PySide6 (glassmorphism)
- Detection: transformers (SimpleAI Chinese classifier / perplexity detection)
- Multi-device: multi-GPU parallelism + LAN master/worker (UDP auto-discovery + TCP task dispatch)
- Statistics: anonymous telemetry (PostHog, one-click disable) + local run logs (exportable)
- Packing: small installer; the runtime downloads on demand (checks first, installs what's missing, with a progress bar)

## Development Note

Developed independently by the author; **part of the code was written and debugged with the help of DeepSeek V4 Flash + Codex**.

## Bug Reports

Click "Export Logs" in the app and send the package to: **gxgx3456@qq.com**

## Disclaimer

The author is still a student; the code may have flaws. Please be kind - friendly suggestions and improvements are always welcome. This project is free and open source, for learning and exchange only.

## License

[MIT](LICENSE)
