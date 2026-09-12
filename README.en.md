# AIGC Detector Toolkit

> Free local AI-written ratio detection - dorm PCs can run it, your paper never leaves your computer, and the results stay in your hands.

<p align="center"><a href="README.md">中文</a> | <b>English</b></p>

## Introduction

A **fully local** AIGC detection desktop tool: drag in a paper (PDF / DOCX / TXT), choose a detection engine, and get the overall AI-written ratio plus a paragraph-level report.

- **Fully offline inference**: the detection model is downloaded once; your paper is never uploaded to any platform
- **Custom model storage path**: keep models on any drive (e.g. D:) so they don't eat C: space; reinstalling the app never deletes downloaded models
- **Multiple engines**: SimpleAI Chinese detection (default), GLTR perplexity detection, Fast-DetectGPT reference implementation, and any custom HuggingFace model
- **Highly customizable**: threshold, paragraph splitting, worker count and more; presets can be saved, exported and imported
- **Multi-device compute pooling**: automatic multi-GPU parallelism on one machine; add roommates' PCs, Pads and phones over LAN
- **Detect → Diagnose → Treat**: after detecting the AI ratio, a fully local rule
  engine diagnoses AI traces (paragraph-level JSON report), then applies
  deterministic rewriting that keeps the academic register
- **Bilingual UI**: the app and installer support one-click switching between 中文 / English
- **Free & open source**: a paid API is reserved, but the core features stay free forever

## Detect → Diagnose → Treat (new in v1.1)

Detection is only the first step. This project merges the methodology of two MIT
open-source projects into a complete loop - **everything runs locally, with no
external AI calls**:

### Diagnosis (local rule engine)

Scans three groups of signals and outputs a **paragraph-level structured JSON report** (exportable):

| Group | What it covers |
|---|---|
| 9-dimension scan | template phrases, burstiness (sentence-length CV), paragraph symmetry, passive voice, nested numbers, colon lists, punctuation, **colloquial warning**, **em-dash density** (the last two are "over-rewriting" gates that protect academic register) |
| CNKI's 5 language patterns | predictable rhythm, uniform density, fixed term position, overlapping connectives, template-functional paragraphs |
| 11 deep AI patterns | significance inflation, synonym cycling, rule of three, copula avoidance, vague attribution, formulaic challenges, suspended analysis, generic conclusions, em-dash overuse, false ranges, paired contrast closures |

Each paragraph gets: risk level, matched patterns with evidence snippets,
sentence-level markers, and suggested actions.

### Treatment (three-round protocol, deterministic rewriting)

1. **Round 1 (subtraction)**: protect spans first (citations, figure/formula
   numbers, data/percentages/P-values, technical terms, quotations - **never
   touched**), then word-level replacements (Chinese AI high-frequency words,
   rotating variants), sentence restructuring, and breaking parallels/numbering;
2. **Round 2 (addition)**: rhythm engineering - deterministic long-sentence
   splitting (target CV ≈ 0.45); **never fabricates facts, data or references**;
3. **Round 3 (self-check)**: Anti-AI audit + register guard - any colloquial/online
   slang must be restored to formal academic language, at most one em-dash per
   paragraph, **register comes before change ratio**.

Four iron rules apply throughout: no full AI rewrite, >40% change only through
structural rewriting and template removal, deterministic replacements, and a
hard academic-register floor.

After detection, if the overall AI ratio exceeds the threshold you set (default
30%, adjustable), the app suggests entering the rewrite flow; you can also click
"Rewrite" at any time.

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
| **aigc-reduce** (rewrite rules reference) | Implemented from the detection principles of CNKI 3.0 (98.6% accuracy, 1.2% false-positive rate), Wanfang, PaperPass and PaperPure; deep AI patterns originate from Wikipedia's "Signs of AI writing" (WikiProject AI Cleanup) and the Humanizer skill; MIT | [GitHub](https://github.com/xiaofenggan01/aigc-reduce) |
| **cnki-aigc---skill** (diagnosis patterns reference) | Real-world method based on CNKI's "5 language patterns": overall AI ratio 20.6% -> 10.1% (-10.5 points), all red segments dropped to suspicious; MIT | [GitHub](https://github.com/qingshanliuci/cnki-aigc---skill) |

> Disclaimer: results depend on the model and text type. They are for self-checking only and are not the verdict of any authority - the official judgement of your school / journal always wins.

## Special Thanks (Compute Pooling)

The "multi-device parallel detection" feature borrows ideas from these two open-source projects:

- **[exo](https://github.com/exo-explore/exo)** (exo-explore/exo, ~46k stars on GitHub): turns everyday devices (phones, Pads, laptops, gaming PCs) into a **P2P distributed AI cluster** with auto-discovery and dynamic model splitting, running large models on ordinary home hardware.
- **[llama.cpp](https://github.com/ggml-org/llama.cpp)** (ggml-org/llama.cpp): one of the most popular local LLM inference frameworks; its [RPC distributed inference](https://github.com/ggml-org/llama.cpp/tree/master/tools/rpc) splits model layers across heterogeneous devices (e.g. Mac Metal + NVIDIA CUDA), serving as the reference for our cross-device perplexity engines.

Thanks to those projects and their communities for making "dorm compute pooling" possible.

## Special Thanks (Diagnosis & Treatment)

The "Detect → Diagnose → Treat" loop directly merges the methodology of two MIT open-source projects:

- **[aigc-reduce](https://github.com/xiaofenggan01/aigc-reduce)** (xiaofenggan01/aigc-reduce): three-round protocol, replacement tables, Chinese AI high-frequency word lists, colloquial blacklist and 9-dimension scanning methodology. Our rewrite engine follows its rules exactly, insisting "de-AI-ing ≠ colloquializing", with the formal academic register as a hard floor.
- **[cnki-aigc---skill](https://github.com/qingshanliuci/cnki-aigc---skill)** (qingshanliuci/cnki-aigc---skill): a real-world method based on CNKI's "5 language patterns" (measured 20.6% -> 10.1%). Our diagnosis engine follows its patterns.

Thanks to both authors and their communities for making the full detect → diagnose → treat flow possible.

## Support & Donate

If this project helped you a little, you are welcome to **buy the author a milk tea** to support further development:

<p align="center">
  <img src="docs/donate/alipay.jpg" width="220" alt="Alipay QR code" title="Alipay">
  <img src="docs/donate/wechat_pay.jpg" width="220" alt="WeChat Pay QR code" title="WeChat Pay">
</p>

<p align="center">Alipay ｜ WeChat Pay</p>

### For international users

If you don't use Alipay or WeChat Pay, you can also **gift any AI API key** (any provider is welcome) to **gxgx3456@qq.com**. Please include:

- Model name
- API / model URL and port
- If you'd like to be credited, mark it as "特别感谢 / Special Thanks"

Recommended: [DeepSeek](https://platform.deepseek.com/api_keys) - great value. If you really want to gift one, **DeepSeek V4 Flash** is the most cost-effective choice. (Screenshot reference: [docs/donate/deepseek_usage.png](docs/donate/deepseek_usage.png))

## Tech Stack

- UI: Python + PySide6 (glassmorphism)
- Detection: transformers (SimpleAI Chinese classifier / perplexity detection)
- Diagnosis: local rule engine (9-dimension scan + CNKI 5 language patterns + 11 deep AI patterns, paragraph-level JSON)
- Treatment: three-round protocol (deterministic rewriting + protected spans + register guard, fully offline)
- Multi-device: multi-GPU parallelism + LAN master/worker (UDP auto-discovery + TCP task dispatch)
- Logs: local run logs (exportable; never contains paper content)
- Packing: small installer; the runtime downloads on demand (checks first, installs what's missing, with a progress bar)

## Development Note

Developed independently by the author; **part of the code was written and debugged with the help of DeepSeek V4 Flash + Codex**.

## Bug Reports

Click "Export Logs" in the app and send the package to: **gxgx3456@qq.com**

## Disclaimer

The author is still a student; the code may have flaws. Please be kind - friendly suggestions and improvements are always welcome. This project is free and open source, for learning and exchange only.

## License

[MIT](LICENSE)
