# AIGC Detector Toolkit · Changelog

[更新日志.md](更新日志.md) ｜ **English**

> What changed in each version. Newest first.
> To see what a user actually notices, read the **"Visible to users"** subsection of each entry.

---

## 📌 Maintenance rules for this file (mandatory on every release)

These rules apply to this project from 2026-09-25 onward:

1. **Add a section to [`更新日志.md`](更新日志.md)** (Chinese) — newest version on top,
   listing Added / Fixed / Changed, and always calling out **what users will actually notice**.
2. **Mirror it here in English** — the two files must stay one-to-one. Editing one means editing the other.
3. **Ship it inside the app too** — add the new version's entry to the **update notes** list in the
   About window (source: `app/core/about_text.py`, both the Chinese and English blocks),
   so users can read what changed without going online.
4. **Rebuild both exes** — `AIGC_Toolkit_Setup.exe` + `app/first_run_gui.exe`.
   ⚠️ Source-only edits are invisible to users until you rebuild.
5. **Push to GitHub** — only after all of the above is done and self-tested.

> Why this rule exists: v1.3.1 changed source only and was never rebuilt, so the About window's
> update notes never caught up either — users could see nothing at all in the app. v1.3.2 paid that debt
> back when it was finally rebuilt. From the day this file was created, **the changelog goes to both
> GitHub and inside the app**, with no more "written in source, invisible to users" gaps.

---

## Repo docs tidy-up · Chinese changelog created (2026-09-25)

> **Documentation only — no program logic changed.** The installer and bootstrapper are still v1.3.2,
> so **there is no need to download anything new**. Documentation tidy-up, **no version bump**.

### Added: this repo's Chinese changelog `更新日志.md`
- Added a Chinese changelog (`更新日志.md`), mirrored by this English file, with language links both ways
- Wrote down the **maintenance rules** above: every future update must put the changelog
  **both** on GitHub (`更新日志.md` + `CHANGELOG.md`) **and inside the app** (the About window's update notes)

### Backfill: v1.3.1 / v1.3.2 entries added to the in-app update notes
- The About window's update-notes list stopped at v1.3.0 — v1.3.1 and v1.3.2 were missing
- Backfilled here (source `app/core/about_text.py`, Chinese and English blocks);
  **users will see them after the next rebuild**

### Visible to users
- The repo now has a Chinese changelog you can read top to bottom
- (The in-app backfill only takes effect **on the next rebuild**; the installer was not rebuilt this time)

---

## v1.3.2 (2026-09-25)

> This is the **first real release of v1.3.1**. v1.3.1 only changed source and was never rebuilt,
> so what users downloaded was still v1.3.0. This version packs all of v1.3.1's changes plus the
> text clean-up below into the installer.

### Visible to users
- **Upgrading no longer wipes your settings or your models**: theme, thresholds and presets are kept;
  multi-GB models are no longer deleted and re-downloaded
- **Machines that once had a VPN / proxy client installed could not install this app at all — now they can**
- **The installer no longer carries the author's local files** (device id, run logs)
- Installer size: 23.59 MB → **22.13 MB**

### Changed: "Disclaimer" section removed
- Deleted the whole disclaimer paragraph ("The author is still a student; the code may have flaws...")
  from the About window and the project docs — 4 places in total:
  `app/core/about_text.py` (Chinese `【免责声明】` + English `[Disclaimer]`), `README.md`, `README.en.md`
- Also removed the equivalent self-description in the "Support" section (one place per language)
- **Kept** the functional notice "results depend on the model and text type; use them for self-checking
  only — the official verdict of your school/journal always wins". It concerns the tool, not the author,
  and users need to know it.

### Fixed: the installer could never succeed on one class of machines (malformed leftover proxy)
- **Symptom**: the portable Python downloaded fine, then it stalled while bootstrapping pip:
  `ERROR: Could not install packages due to an OSError: Please check proxy URL.
   It is malformed and could be missing the host.`
- **Root cause**: after a proxy/VPN client is uninstalled, `HKCU\...\Internet Settings` can be left with
  `http` / `https` / `ftp` all set to `http://` — **a scheme with no host**.
  `urllib.request.getproxies()` hands that to pip, pip cannot parse it, and the connection never opens.
  Meanwhile `app/core/netfix.py`'s self-heal only recognised the `socks://` prefix and classified
  `http://` as "a normal proxy, leave it alone" — so the self-heal never ran.
- **Fix**: `is_unusable_proxy()` now also rejects "has a scheme but no host";
  `unusable_system_proxy()` reads `urllib.request.getproxies()` directly (the common entry point for
  urllib / requests / pip, covering both environment variables and the registry) instead of looking only at
  the registry's `ProxyEnable` — that value may already be 0 while the leftover is still being read.
  On a hit it takes the existing path: `NO_PROXY=*` + clear the unusable proxy variables, so the main
  process and the pip child process both go direct.
- **Scope**: not just the installer — the app downloads models through the same code path, so
  "model download hangs" may have the same cause. Machines that once had a VPN/proxy installed should upgrade.
- Verified: 12 boundary cases for `is_unusable_proxy()` all pass (socks variants, `http://`, `http://:8080`,
  normal proxies, proxy with user:password, ...). Measured after the fix, `getproxies()` goes from
  `{'http': 'http://', 'https': 'http://', 'ftp': 'http://'}` to `{'no': '*'}`,
  and the child process gets a clean environment too.

### Fixed: overwrite install reset the user's settings
- At the end of installation, `installer/installer.py` used to **unconditionally overwrite**
  `<install dir>/settings.json` with only two keys (`install_dir` and `language`) —
  so any theme, threshold, engine or parameter preset the user had tuned was cleared on every upgrade.
- Now it reads the old file, updates only those two keys, and writes it back; everything else is preserved.
- Also removed an unused `shutil.ignore_patterns(...)` variable.

### Cleanup: the installer no longer carries the author's local files
- `AIGC_Toolkit_Setup.spec` has `datas=[('app','app')]`, which packs the entire `app/` folder into the
  installer, so every build had been carrying:
  - `app/settings.json` — containing **the author's local device id**; the app actually reads
    `<install dir>/settings.json` (see `app/main.py`), so this file was legacy junk that leaked data
  - `app/logs/` — the author's own run logs and diagnostics
  - `app/__pycache__/` — `.pyc` files from several Python versions, including **compiled copies of older wording**
- These are now moved out of `app/` before packing; `diag_startup.py`'s "installed content" check now looks at
  the install-root `settings.json` (it used to check the one under `app/`, which would falsely report missing).
- Size: installer 23.59 MB → 21.47 MB, bootstrapper 11.38 MB → 10.35 MB.

### Both exes rebuilt (v1.3.1's changes take effect from here)
- `AIGC_Toolkit_Setup.exe` (installer) and `app/first_run_gui.exe` (first-run bootstrapper) both rebuilt
- Changes that had existed only in source now genuinely reach the installed app:
  ① development statement removed; ② the three in-app "noncommercial use only" notices;
  ③ overwrite install keeps user data and no longer resets settings; ④ machines with a leftover
  malformed proxy can install again
- Version number synced in 4 places: `installer/installer.py:APP_VER`, `app/core/meta.py:APP_VERSION`,
  this file, `使用手册.md`

---

## v1.3.1 (2026-09-24)

> Both changes are user-facing: the licence became noncommercial, and the installer gained
> overwrite-install without losing data.
> ⚠️ Source only — **the exes were not rebuilt in this version**, so users only got these changes in v1.3.2.

### Visible to users
- Three visible "noncommercial use only" notices inside the app; licence switched away from MIT
- The installer supports overwrite install, so upgrading no longer loses user data

### Changed: licence switched to noncommercial-only
- `LICENSE` changed from **MIT** to the **PolyForm Noncommercial License 1.0.0**.
  MIT explicitly allows commercial use and even resale, which is the exact opposite of
  "no commercial use" — the licence file had to be replaced for that to have any legal effect.
- `README.md` / `README.en.md` licence sections rewritten: explicit "✅ permitted" and "❌ prohibited"
  lists plus a commercial-licensing contact. Three "free and open source" phrases became
  "free for personal use" / "source-available, commercial use prohibited" (strictly speaking, a licence
  that restricts fields of use is not an OSI-approved open-source licence).
- `app/core/about_text.py` (Chinese and English) About-window text updated to match
- **Three visible notices added inside the app**:
  ① a permanent line under the title bar: `© 2026 gxgx3456 · 禁止商业使用`;
  ② a red banner + orange note at the top of the About window;
  ③ the licence section in the About body (permitted / prohibited lists + licensing email)
- `仓库文件说明.md` / `REPO_FILES.md` `LICENSE` rows updated

### Added: installer supports overwrite install (no user data lost)
- **Old behaviour**: installation did `shutil.rmtree(appdir)` — delete the whole `app/` folder, then copy
  the new version in. Three side effects: ① the user's `logs/` was erased, so old logs were gone when a
  problem appeared after upgrading; ② unless the user had changed the model path, models defaulted to
  `<install dir>/models` and were deleted along with `app/` — several GB to re-download;
  ③ while the app was running, `app.log` was locked, so `rmtree` failed and "reinstall over a running app"
  simply did not install.
- **New behaviour**: per-file overwrite — new files are written, files removed from the new version are
  cleaned up, but `logs/`, `models/`, `cache/` and `config/` are preserved as a whole (neither overwritten
  nor deleted). A single locked file is logged and skipped instead of aborting the install.
- The install log prints one line: `覆盖安装完成：新增 N，更新 N，清理旧文件 N，保留 N`
- The portable Python runtime (`runtime/python`) already had reuse logic, so overwriting does not re-download it

### Verification
- The overwrite logic was tested against simulated directories with 10 assertions (add / update /
  clean up removed files / logs preserved / log content not overwritten / models dir preserved /
  model files intact) — **10/10 passed**
- All changed files pass a syntax check

---

## Development statement removed (2026-09-23)

> **Text only — no program logic changed.** The installer and bootstrapper remain v1.3.0.

- Removed the "development statement" paragraph from the project docs and the About window — 4 places:
  `README.md` / `README.en.md` / `app/core/about_text.py` (Chinese + English blocks)
- That paragraph disclosed the author's AI toolchain, which is personal development detail and no
  longer shown publicly
- Also fixed a leftover line break in the English disclaimer (after an earlier edit,
  `The author is still a student;` had ended up on its own line)

---

## Repository tidy-up (2026-09-23)

> **Repository content only — no program code changed.** The installer and bootstrapper remain v1.3.0;
> no need to re-download.

- Removed 5 dev-only scripts from `tools/` (`download_simpleai_model.py`, `run_detection_test.bat`,
  `make_icon.py`, `grab_screen.py`, `patch_offline_fix.py`): they hard-coded the dev machine's absolute
  paths and are useless to users; models and dependencies are handled by the first-run bootstrapper
- Removed 4 byte-for-byte duplicate images under `docs/` that already exist in `app/assets/`;
  the README now references `app/assets/` directly
- Kept the test scripts under `tools/`: `test_engines.py`, `smoke_test.py`, `test_detect.py`, `fusion_selftest.py`
- The repo is back to four kinds of content — source, exe, docs, tests — with no dev-machine traces

---

## v1.3.0 (2026-09-19)

> This is the **first time v1.2.8's "nine engines" actually shipped** — v1.2.8 existed in source only,
> with the installer exe still at v1.2.7. Both exes are rebuilt now, so a fresh install is the new version.

### Visible to users
- Brand new app icon (window, taskbar, installer, desktop shortcut, uninstall entry)
- On small screens (1440×900) fullscreen no longer clips button text or produces "melted text"

### Added: brand new app icon
- Window, taskbar, installer, first-run bootstrapper, desktop shortcut and the
  Windows "Settings > Apps" uninstall entry all use the new icon
  (green rounded square + magnifier + binary document)
- Multi-size `.ico` (16 / 24 / 32 / 48 / 64 / 128 / 256) — sharp on HiDPI and in small taskbar slots
- **Transparent background, no white box**: everything outside the rounded corners is transparent, so no
  white square in either light or dark themes; the generation watermark and drop shadow in the bottom-right
  of the source image were cropped away
- Taskbar grouping fixed: the process identity is declared explicitly, so the window is no longer
  counted as `pythonw.exe` (the taskbar icon used to be Python's)

### Fixed: clipped button text in fullscreen ("melted text")
- Root cause (measured): the left panel's minimum height is about 1082px while a 1440×900 screen offers
  only 900px in fullscreen, so Qt squeezed every widget proportionally — buttons went from 34px to 21px
  while their text needed 34px, hence the clipping. In a normal window Qt quietly grew the window to 1082
  (off the bottom of the screen) so it was not visible.
- The left panel now scrolls instead of being squeezed; buttons have a minimum height lock; a shared
  "keep windows on screen" helper was applied to the main window / engine manager / download settings /
  rewrite / about windows
- Also fixed clipped text on the "Browse... / Delete" buttons in download settings (they were pinned with
  `setFixedWidth(70/60)`)
- Regression: widgets squeezed in any window **19 → 0** (both normal and fullscreen)

### Includes everything from v1.2.8
All 9 academic methods are runnable modules grouped into Detectors / Rewriters / Benchmarks;
models are always downloaded on demand and never bundled; plugin and remote-manifest extension points are
ready — see the v1.2.8 entry below.

---

## v1.2.8 (2026-09-19)

### Added: all 9 engines implemented, grouped into Detectors / Rewriters / Benchmarks
The README and About window had listed 9 academic methods, but only 3 actually ran; the rest were paper
citations. This version makes all of them real:

**Detectors (5 — is this text AI-written?)**
- `SimpleAI / HC3` (default Chinese engine) — existing
- `GLTR` perplexity — existing
- `Fast-DetectGPT` — **rewritten to follow the paper's conditional probability curvature**
  (sampling approximation); no longer "perplexity with a different model"
- `DetectGPT` — **added**, the paper's masked-perturbation implementation: T5 refills randomly removed
  spans, then log-probability curvature is compared
- `Binoculars` — **added**, cross-perplexity ratio of two same-tokenizer models, no threshold tuning

**Rewriters (2 — diagnose + reduce, built-in rules, no model download)**
- `aigc-reduce` three-round protocol and CNKI 5-language-pattern diagnosis — existing, now visible and
  selectable in the engine manager

**Benchmarks (2 — audit a detector)**
- `RAID`, `MGTBench` — **new runnable modules**: run labelled samples to get accuracy,
  false-positive rate (human text flagged as AI), false-negative rate, precision/recall/F1, broken down by
  generator and language; import a subset of the official datasets (CSV / JSONL) and export a Markdown report

### Added: models always downloaded on demand, never bundled
As before, the engine list only declares which model, how big, and where from; the user clicks download in
"Download settings". The default Chinese setup needs only SimpleAI (~400MB);
GLTR/Binoculars are about 0.5–1.9GB; Fast-DetectGPT about 5.4GB.

### Added: extension points (adding models later needs no rebuild)
1. **Engine plugin folder** `engines_plugins/*.py` — drop in a file that declares `@register("my_impl")`
   and it is discovered at startup;
2. **Remotely updatable engine list** — host an `engines_manifest.json` anywhere reachable, paste the URL
   in "Engine manager → Check for updates" and new engine / model entries appear;
3. **Models declared by the list** — each engine's HuggingFace model lives in the list's `models` field,
   so swapping a model (e.g. Binoculars to a Falcon pair) is a JSON edit, not a code change.

### UI
- Engine manager rebuilt: the left side groups entries into Detectors / Rewriters / Benchmarks, the right
  side shows model list, size, paper reference and whether it is downloaded locally; built-in rule engines
  are labelled "built-in, ready"
- The detector dropdown lists detectors only, no longer mixing in rewriters / benchmarks
- New "Benchmarks" entry point (main window + engine manager)
- Download settings lists models per engine and shows download status

### Misc
- Corrected a false claim in the About window: removed "anonymous telemetry (can be turned off)"
  (this project has no telemetry); the tech-stack section now lists the 5 engines and 2 benchmark families accurately
- Added regression tests `tools/test_engines.py` (13 checks: list completeness, categories, list coverage,
  plugin auto-discovery, model resolution, benchmark metrics, sample import, rewriter availability)

---

## v1.2.7 (2026-09-19)

### Fixed: the root cause of install failures — the official Python installer's "orphaned MSI registration"
- The installer **no longer calls the official .exe installer**; it uses the official **embeddable portable
  package** (`python-3.12.10-embed-amd64.zip`): download → extract to `runtime\python` → patch `._pth` →
  bootstrap pip. No registry writes, no admin rights, uninstall = delete the folder — which ends both
  "silent install exits 0 but nothing is installed" and "uninstall/repair always fails with 1603"
- Automatically cleans up an incomplete old runtime and a legacy `venv` before installing

### Fixed: the root cause of download failures — socks system proxies
- Added **network self-heal** (`app/core/netfix.py` on the source side plus `sitecustomize.py` inside the
  portable runtime): VPNs and accelerators often set the Windows system proxy to `socks://127.0.0.1:xx`,
  which Python's urllib / requests / pip cannot use — the symptoms are `BadStatusLine` or
  `Missing dependencies for SOCKS support` while every download fails (curl works fine). Such a proxy is now
  detected and the app switches to a direct connection
- The download chain is now three-stage: **urllib → direct urllib (bypassing the system proxy) → system curl**,
  with size and file-header (`PK`) validation afterwards so an error page can never be mistaken for a package

### Fixed
- The first-run bootstrapper now runs pip with the **runtime Python** (when packaged as an exe,
  `sys.executable` pointed at the exe itself and pip could not run at all)
- The desktop shortcut / launch command **points straight at `first_run_gui.exe`** (it used to invoke
  pythonw to "run" an exe — feeding an executable to an interpreter, which always fails)
- When the bootstrapper is packaged as an exe and cannot find `runtime\python`, it now says so clearly
  instead of ploughing on

### Improved
- All install logic extracted into module-level functions, with the GUI as a thin shell; added a
  **headless install**: `AIGC_Toolkit_Setup.exe --cli <target dir>` (useful for batch deployment and self-testing)
- Launch scripts, error messages and the manual-package picker all speak of the portable package now

---

## v1.2.6 (2026-09-19)

### Fixed
- **Text ghosting / melted text under HiDPI scaling**: removed translucent window and shadow effects
  (they render misaligned at fractional scaling) and pinned the "Microsoft YaHei UI" font

### Improved
- Rebuilt the UI to the design spec: hairline borders, a single accent colour (#2563eb under 5% coverage),
  neutral grey background, corner radius ≤16px, thin progress bar — replacing the glassmorphism gradient look

---

## v1.2.5 (2026-09-18)

### Fixed
- **Crash on launch**: when `torch` was blocked by security software (measured with Sogou's
  `SCAegis64.sys` driver), the app now starts in a degraded mode with a clear message instead of crashing

---

## v1.2.4 (2026-09-18)

### Added
- **Uninstall entry in Control Panel**: after installation the app can be removed from
  Windows "Settings > Apps" or Control Panel "Programs and Features"
  - Before uninstalling it lists the folders that will be deleted and suggests emailing a bug report first
    (gxgx3456@qq.com)
  - Uninstalling also removes the registry uninstall key, the desktop shortcut and the whole install folder
    (including model files)
- **Install options** (both on by default):
  - Create a desktop shortcut
  - Launch after installation (starts the first-run bootstrapper)
- The installer's **fullscreen button moved to the top-right corner** (system button style, Esc to exit)

### Improved
- The About page gained update notes for v1.2.3 / v1.2.4 (bilingual)

---

## v1.2.3 (2026-09-18)

### Added
- **Automatic rewrite loop** (previously semi-automatic, one round only):
  - A new "Auto rewrite (loop and re-check)" button in the rewrite window
  - Each round: rule-based rewriting → re-check the whole text's AI ratio with the local model →
    if still over the threshold, rewrite only the offending paragraphs again
  - Loops until the AI ratio reaches the target (configurable, default ≤25%) or the max round count
    (configurable, default 3, to prevent endless loops)
  - A dialog reports the paragraphs rewritten per round, the re-checked AI ratio and the final AI ratio;
    the paragraph list and diagnosis refresh as well

### Improved (installer download strategy, fixing download failures for some users)
- Download sources expanded to **npmmirror → Huawei Cloud → python.org**, tried in order
  (Chinese mirrors need no VPN)
- For each source: if Python's own download fails, fall back to **system curl** (independent network stack)
- Size validation after download (<5MB is treated as a bad package, then it re-downloads from another source)
- If every source fails, the user can **pick a local installer package** — no network needed at all

---

## v1.2.2 (2026-09-13)

### Fixed
- Python silent install "exit code 0 but it failed": when the official installer is confused by stale
  registry records, the real install directory is recovered from the registry / default locations and copied;
  if that still fails it retries once in visible mode
- Added a **fullscreen button in the top-left corner** of the installer (long logs are easier to read; Esc to exit)
- The first-run bootstrapper now writes a file log (`app/logs/first_run.log`) and captures the main app's stderr

---

## v1.2.1 / v1.2.0 (early 2026-09)

- **Lightweight installer**: AI components (PyTorch / models) download on first launch; CPU/CUDA auto-selected
- **Customizable model storage path** (e.g. on drive D); detection and rewrite engines resolve the model
  directory from one configuration
- First-run bootstrapper `first_run.py`: downloads with a progress bar, then starts the app automatically
- Built-in Chinese mirror acceleration (HF mirror / Tsinghua PyPI / npmmirror)
- Model path, rewrite target and other settings can be saved into presets

---

## Feedback

Found a bug or have a suggestion? Email **gxgx3456@qq.com**
