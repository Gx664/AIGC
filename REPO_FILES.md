# Repository File Guide

> This document explains **what every uploaded file in this repository is for**, which ones you can safely ignore, and which ones must not be deleted.
> Written for two audiences: people who want to understand the project structure, and people who cloned it and don't know how to run it.

<p align="center"><b>English</b> | <a href="仓库文件说明.md">中文</a></p>

## 1. Three entry points

| What you want to do | Which file to open |
|---|---|
| **Install and use the app** | Download [`AIGC_Toolkit_Setup.exe`](AIGC_Toolkit_Setup.exe) from the repo root and double-click it. Ignore everything else. |
| Understand features and usage | [`README.en.md`](README.en.md) (English) / [`README.md`](README.md) (Chinese) |
| See what changed in each version | [`CHANGELOG.md`](CHANGELOG.md) |

⚠️ **Regular users only need the single file `AIGC_Toolkit_Setup.exe`** (it sits at the top level of this repo). Everything else is for developers.

---

## 2. Root directory files (including the installer)

| File | Purpose |
|---|---|
| **`AIGC_Toolkit_Setup.exe` (23.6 MB)** | **The installer** — the only download entry point for users, placed at the repo root so it's immediately visible. It unpacks the portable Python, copies the application, and creates a desktop shortcut. |
| `README.md` | Chinese main documentation: features, principles, sources of the 9 methods, donation codes |
| `README.en.md` | English documentation, mirroring `README.md` |
| `CHANGELOG.md` | Changelog — what was added or fixed in each version |
| `LICENSE` | The MIT license text |
| `.gitignore` | Tells git which files to keep out of version control (build artifacts, caches, logs). **Do not delete** — without it, `build*/`, `dist*/` and `__pycache__` would get committed and bloat the repo. |
| `engines_manifest.json` | **Remote engine manifest.** Fetched by "Engine Manager → Check for Updates" so new engines or model swaps can ship without repackaging the app. |

📌 **This installer already contains `app/first_run_gui.exe`** — at build time, `datas=[('app','app')]` packs the entire `app/` directory into it. So after installation the bootstrapper is already on disk; nothing extra needs downloading.

> 💡 The installer used to live in `dist/`; it was moved to the repo root to make the download entry point more obvious. New builds still output to `dist/` — just move the file up afterward.

---

## 3. `app/` — the application itself

### 3.1 Two entry points and packaging

| File | Purpose |
|---|---|
| `main.py` | **Main application entry point.** Brings up the PySide6 GUI; ultimately launched by the portable Python |
| `first_run.py` | **Source of the first-run bootstrapper.** Checks whether dependencies (PySide6 / torch / transformers, etc.) are installed, downloads whatever is missing, then launches `main.py` |
| `first_run_gui.exe` (11.4 MB) | The **packaged exe built from `first_run.py`**. Why a separate exe? Because the installer ships the official *embeddable* portable Python, which **has no tkinter** and therefore cannot draw a progress bar — so it must be wrapped by PyInstaller to bundle its own tkinter. |
| `diag_startup.py` | **One-shot troubleshooting script.** Dumps everything needed to diagnose a problem (Python version, dependency status, proxy config, log tail) in one go; invoked by `诊断.cmd` |

> ⚠️ **`app/first_run_gui.exe` is not redundant — do not delete it.**
> It is the **raw material for repackaging the installer**: remove it and the next build of the installer will contain no bootstrapper, so users end up missing PySide6/torch and the main app crashes on start.
> (The installer already sitting in the repo root is unaffected — it swallowed the bootstrapper long ago.)

### 3.2 `app/core/` — core logic (UI-independent)

| File | Purpose |
|---|---|
| `meta.py` | App version and other metadata |
| `settings.py` | Config read/write: decision threshold, parallelism, model paths, saved presets; also where the remote URL of `engines_manifest.json` is read |
| `i18n.py` | Chinese/English UI string tables |
| `about_text.py` | Text for the "About" window (one Chinese set, one English set) |
| `license.py` | Free-edition checks plus a reserved interface for a Pro license (core features stay free forever) |
| `netfix.py` | **Network self-healing.** Automatically bypasses unusable system proxies (e.g. a SOCKS proxy that makes pip/urllib fail outright) and falls back to a direct connection |
| `logging_setup.py` | Logging initialization. Logs contain runtime info only — **no paper content, no telemetry** |
| `detector.py` | Detection pipeline orchestration: split into paragraphs → call engines → aggregate results |
| `cluster.py` | **Multi-device compute pooling**: automatic LAN node discovery and task distribution |
| `diagnosis.py` | Diagnosis engine: 9-dimension scan + CNKI's 5 language patterns, producing a paragraph-level JSON report |
| `therapy.py` | Therapy engine: the three-round rewriting protocol (deterministic rewriting that preserves academic register) |
| `aigc_rules.py` | Rewriting rule data: high-frequency AI word replacement table, colloquialism blacklist, protected-fragment rules |
| `benchmark.py` | Benchmarks: RAID / MGTBench metric computation (accuracy, false-positive rate, F1) |
| `report.py` | Report export (Markdown and other formats) |
| `doc_reader.py` | Reads PDF / DOCX / TXT and extracts plain text |

### 3.3 `app/core/engines/` — pluggable detection engines

| File | Purpose |
|---|---|
| `base.py` | Common base class for engines, defining interfaces such as `predict_paragraphs()` |
| `registry.py` | **Plugin registry.** Implementations register via the `@register("impl")` decorator; new algorithm files dropped into `engines_plugins/` are auto-discovered at startup |
| `catalog.py` | Built-in definitions of the 9 methods (zero dependencies — safe to import from both the UI and the installer) |
| `manager.py` | Engine manager: merges four sources — built-in catalog, local overrides, remote updates, user-defined |
| `simpleai_engine.py` | **SimpleAI Chinese engine** (default): RoBERTa sequence classification, per-paragraph AI probability |
| `perplexity_engine.py` | **GLTR perplexity engine**: scores by linear interpolation between perplexity thresholds |
| `curvature_engine.py` | **Probability-curvature engines**: Fast-DetectGPT (self-sampled perturbation) and DetectGPT (masked perturbation) |
| `binoculars_engine.py` | **Binoculars**: cross-perplexity ratio of two models; no threshold tuning needed |
| `rule_engine.py` | **Rule engine**: used for repair/diagnosis methods that need no model download |

> All engine modules **import torch lazily** — so even if torch is blocked by security software, the engine list still displays correctly.

### 3.4 `app/ui/` — graphical interface (PySide6)

| File | Purpose |
|---|---|
| `main_window.py` | Main window: drop in files, pick an engine, read results |
| `engine_dialog.py` | Engine manager dialog: download models, check for remote updates |
| `benchmark_dialog.py` | Benchmark dialog: import datasets, view metrics |
| `rewrite_dialog.py` | Rewrite dialog: before/after comparison |
| `settings_dialog.py` | Settings dialog: thresholds, paths, parallelism, language |
| `glass.py` | Custom-drawn modern-tool UI styles and widgets |
| `assets/*.svg` | Small UI icons (checkmark, dropdown arrows, etc.) |

### 3.5 `app/assets/` — static resources

| File | Purpose |
|---|---|
| `icon.ico` / `icon.png` | Application icon. `icon.ico` is used for the exe, window, taskbar and shortcuts; `icon.png` is for the README |
| `donate/alipay.jpg` | Alipay donation QR code (shown in README) |
| `donate/wechat_pay.jpg` | WeChat Pay donation QR code |
| `donate/deepseek_usage.png` | Illustration for the API-key gifting note for international users |

---

## 4. `installer/` — installer source code

| File | Purpose |
|---|---|
| `installer.py` | **All installer logic.** It does three things:<br>1. Downloads and unpacks the official embeddable portable Python (with mirror fallback)<br>2. Patches `._pth` and bootstraps pip<br>3. Copies the application, creates a desktop shortcut, writes the uninstall entry<br>The UI is tkinter-based; no admin rights, no registry changes. |

> Installation only gets the *environment* ready — heavy dependencies like torch / PySide6 are installed over the network by `app/first_run_gui.exe` on first launch.

---

## 5. `tools/` — developer self-test scripts

These are used **for acceptance testing during development**; regular users never need to run them.

| File | Purpose |
|---|---|
| `test_engines.py` | Engine framework regression tests (13 cases): **no torch needed, no model downloads** — finishes in seconds |
| `smoke_test.py` | Full-feature smoke test: verifies the main flow works even without torch |
| `test_detect.py` | Offline detection-engine self-test, pure CLI, no UI |
| `fusion_selftest.py` | "Detect → diagnose → rewrite" closed-loop self-test, fully offline |

How to run (replace `<python>` with your interpreter):

```bash
<python> tools/test_engines.py
```

---

## 6. Files that must not be deleted

| File | What breaks if deleted |
|---|---|
| `app/first_run_gui.exe` | The next installer build contains no bootstrapper → users end up missing dependencies → **the app won't open** |
| `AIGC_Toolkit_Setup.exe` | Users lose their only download/install entry point |
| `.gitignore` | Build artifacts, caches and logs get committed, and the repo balloons |
| `engines_manifest.json` | "Check for updates" stops working; engines/models can no longer be added remotely |
| `app/assets/icon.ico` | Packaging fails to find the icon |
| `LICENSE` | The MIT license declaration becomes void |

---

## 7. Summary in one picture

```
The user downloads exactly one file →  AIGC_Toolkit_Setup.exe (at the repo root)
It contains                        →  app/first_run_gui.exe (bootstrapper) + the app + install logic
Everything else                    →  source, UI, icons, docs, self-test scripts — for development and maintenance
```

# aigc-toolkit: file purpose marker
