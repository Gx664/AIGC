# packaging/ — Linux / macOS 构建素材

本目录放**非 Windows** 平台的打包素材。Windows 的两个 spec 仍在仓库根目录
（`first_run_gui.spec`、`AIGC_Toolkit_Setup.spec`），不在这里。

## 文件

| 文件 | 作用 |
|---|---|
| `unix_launcher.py` | Linux / macOS 的启动入口，PyInstaller 的入口脚本 |
| `AIGC_Toolkit_unix.spec` | 一份 spec 同时负责 Linux 与 macOS（macOS 上额外套一层 BUNDLE 出 .app） |
| `icon.icns` | macOS 图标，由 CI 用 `sips` + `iconutil` 从 `app/assets/icon.png` 现生成，**不入库** |

`unix_launcher.py` 刻意保持很薄：只负责**定位程序根目录**，然后把
`app/first_run.py` 跑起来。检查依赖、装依赖、启动主程序全在 `first_run.py` 里
—— 与 Windows 共用同一套逻辑，平台差异则全部落在 `app/core/platform_ops.py`。

## 云端构建

流水线在 `.github/workflows/cross-platform-build.yml`，两个 job：

| job | 机器 | 产物 |
|---|---|---|
| Linux 构建 | `ubuntu-22.04` | `AIGC_Toolkit-x.y.z-x86_64.AppImage` |
| macOS 构建 | `macos-14`（Apple Silicon） | `AIGC_Toolkit-x.y.z-macos-arm64.dmg` |

两条流水线都在**云端**跑，本地不需要装任何 Linux / macOS 环境。触发方式：
手动（Actions 页面 Run workflow）或打 `v*` tag。

每个 job 做这些事：

1. 装系统库（Linux 额外装 `tk`，引导界面是 tkinter 写的）
2. 语法自检 + `tools/test_engines.py`（不需要 torch）
3. 清理 `__pycache__`（免得字节码被打进产物）
4. 从 [python-build-standalone](https://github.com/astral-sh/python-build-standalone)
   下载 **便携 Python**（自动匹配 runner 架构），解压到 `runtime/python/`
5. PyInstaller 打包 → 把 `runtime/` 拷进产物
6. 产物自检：用**产物自带**的解释器跑一遍 `platform_ops.describe()`，确认 `app/` 能加载
7. Linux 打 AppImage / macOS 打 dmg（内含「首次打开说明」）

> 公共仓库的 Actions 用量免费；私有仓库每月 2000 分钟免费额度。

## 平台适配层（P1，已完成）

平台差异集中收在 **`app/core/platform_ops.py`** 一个文件里，纯标准库、import 无副作用：

| 能力 | Windows | macOS | Linux |
|---|---|---|---|
| 数据目录 | 安装目录（不变） | `~/Library/Application Support/AIGC_Toolkit` | `$XDG_DATA_HOME/AIGC_Toolkit` |
| 界面字体 | Microsoft YaHei UI | PingFang SC | Noto Sans CJK SC |
| 图标格式 | `.ico` | `.icns` → 回退 `.png` | `.png` |
| 打包自带解释器 | `<base>/runtime/python/python.exe` | `<base>/runtime/python/bin/python3` | 同 macOS |
| **实际使用的解释器** | 同上（安装目录可写） | `<数据目录>/runtime/python/bin/python3` | 同 macOS |
| 桌面入口 | `.lnk`（仍由 `installer.py` 负责） | `.app` 本身 | `~/.local/share/applications/*.desktop` |
| 系统卸载入口 | HKCU 卸载键 | 无（拖到废纸篓） | 无（删目录 + 删 .desktop） |

接入点：`app/main.py`（字体 / 图标 / 数据目录）、`app/ui/main_window.py`
（拆出 `BASE_DIR`＝程序目录 / `DATA_DIR`＝数据目录）、`app/first_run.py`
（引导器路径 / 日志位置 / 图标）。

## Unix 首次启动流程（与 Windows 对称）

Windows 是「安装器带便携 Python → `first_run_gui.exe` 装组件 → 主程序」；
Unix 把前两步合成一个可执行文件（AppImage / .app），流程是：

```
第一次运行
 ├─ 1. 把包里的 runtime/python 复制到用户数据目录
 │      （包体在 /Applications 或 AppImage 里是只读的；AppImage 每次挂载点
 │        还都不一样，直接在里面建环境下次启动就废了）
 ├─ 2. 检查 PySide6 / transformers / python-docx / pypdf / numpy / torch
 ├─ 3. 缺就装（有 NVIDIA 显卡会问 CUDA 还是 CPU；Linux/macOS 的 torch 走
 │      **上交 pytorch-wheels/{cu128,cpu}** 频道，官网 download.pytorch.org 兜底
 │      —— PyPI 上 Linux 的 torch 默认捆 CUDA，约 2 GB，不能用 PyPI 装）
 ├─ 4. Linux 顺带写一个 .desktop 到应用菜单
 └─ 5. 启动主程序

之后每次运行：依赖齐全 → 直接进主界面（不闪窗、不重复下载）
```

## 运行组件两选项（P2，已完成）

首次启动装 PyTorch 时，**检测到独立显卡会让用户选**：

| 选项 | 体积 | 说明 |
|---|---|---|
| CUDA 版 | 约 2.5～3.5 GB | 用显卡加速，检测更快（有显卡时的默认选中项） |
| CPU 版 | 约 0.2 GB | 体积小，不用显卡 |

* 选择记进 `settings.json` 的 `runtime.torch_variant`，重装 / 修复时沿用，不再重复问
* **没有独立显卡就不问**，直接装 CPU 版（macOS 一律视为没有 —— 苹果机没有 NVIDIA 驱动）
* CUDA 的多个源全部失败时**自动回退 CPU 版**，不让用户卡在"装不上"
* 主程序「设置 → 下载与模型管理」里能看到当前版本，并说明如何切换

逻辑集中在 **`app/core/runtime_deps.py`**（纯标准库 —— 引导器在依赖装齐之前就要 import 它），
由 `app/first_run.py`（选择框）与 `app/ui/settings_dialog.py`（只读展示）共用。

## 🔴 torch 下载源：判断标准只有一个 —— pip 实测

**别用浏览器判断源能不能用。** pip 取包时会去请求 `<源>/torch/`
（pip 里 `search_scope.get_index_urls_locations()` 把 index_url 与包名拼起来），
所以只有「按包名分目录」的 **PEP 503 索引**才走得通。判断命令：

```bash
python -m pip index versions torch --index-url <源>
```

2026-10-01 逐个实测（本机 + 阿里云/腾讯云/CERNET/北大/浙大/华为云/南大/USTC/BFSU 全试过）：

| 源 | 浏览器打开 | pip 能否用 | 说明 |
|---|---|---|---|
| `mirror.sjtu.edu.cn/pytorch-wheels/{cpu,cu128}` | ✅ | ✅ **唯一可用的国内源** | 按频道分目录、平台与依赖齐全 |
| `download.pytorch.org/whl/{cpu,cu128}` | ✅ | ✅ | 官方，境外；兜底用 |
| `mirrors.aliyun.com/pytorch-wheels/{cpu,cu128}` | ✅ 能列出几千个 .whl | ❌ **404** | 轮子摊平在根目录，没有 `/torch/` 这层，pip 报 `No matching distribution found` |
| `mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/` | ❌ 404 | ❌ | 整站已下线 |
| 腾讯云 / CERNET / 北大 / 浙大 / 华为云 / 南大 / USTC / BFSU | ❌ | ❌ | 没有这个镜像 |

所以 `app/core/runtime_deps.py` 里两个源列表都写成
**「上交 → 官方」**，并把踩过的站收进 `DEAD_MIRRORS`，测试守卫会拦着不让加回来。

> 清华的 **PyPI** 镜像（`pypi.tuna.tsinghua.edu.cn/simple`，装 PySide6 等普通包用）
> 与上面是两码事，**仍然正常**，没有动它。

## 回归测试

本机（Windows）可跑，两条都在验「Windows 行为一字不变」：

| 脚本 | 项数 | 覆盖 |
|---|---|---|
| `_diag/test_platform_ops.py` | 13 | 路径 / 字体 / 图标 / .desktop 内容 |
| `_diag/test_unix_adapt.py` | 39 | 新增的 `work_python` / `runtime_root` / `runtime_is_local`、Unix 的 CPU 源、launcher 在两种打包布局下的根目录判定、torch 源守卫、文案中英对齐 |
| `_diag/check_torch_mirrors_live.py` | 12 | **需要联网**：用 pip 逐个实测 torch 源（含拉黑源必须确实不可用） |
| `_diag/verify_platform_p1.py` | 9 | 接入点是否真的走了适配层 |
| `_diag/smoke_first_run_pick.py` | 11 | 真实建 tkinter 选择框（需带 tkinter 的解释器） |

## ⚠️ 当前状态

已经具备：

- 三端同一套 `app/` 源码，平台差异收进 `platform_ops`
- 云端能装依赖、跑引擎回归测试、出 AppImage 与 dmg（**待首次实跑验证**）
- Unix 首启的「运行时落地 → 装依赖 → 启动」链路有代码、有测试
- Linux 桌面入口、macOS .app 图标（CI 现生成 .icns）均已接好
- CPU / CUDA 两个下载选项，引导器与主程序共用

还缺：

1. **首次云端实跑** —— 流水线尚未在 GitHub 上真正跑过一次，
   AppImage 打包、dmg 制作、便携 Python 版本匹配都要跑一遍才知道有没有坑
2. **macOS 签名** —— 没有苹果开发者证书，产物是未签名的，用户首次打开需右键"打开"
   或跑 `xattr -dr com.apple.quarantine`（dmg 里已附说明文件）
3. **Intel 版 macOS 包** —— 目前只出 arm64；需要时把 `macos-14` 换成 `macos-13` 再跑一遍
4. **实机验证** —— 目前所有 Unix 侧结论都来自本机（Windows）的模拟测试，
   真机上的 Qt 依赖、中文字体、桌面环境差异还没验过
