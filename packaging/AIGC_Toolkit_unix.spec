# -*- mode: python ; coding: utf-8 -*-
"""Linux / macOS 打包配置（与 Windows 的两个 spec 对应）。

用法（在仓库根目录执行）：
    pyinstaller --noconfirm --distpath dist-unix --workpath build-unix \
        packaging/AIGC_Toolkit_unix.spec

产物：
    Linux  -> dist-unix/AIGC_Toolkit/AIGC_Toolkit
    macOS  -> dist-unix/AIGC_Toolkit.app

打完之后 CI 还要做两件事（spec 管不了）：
    1. 把解好的便携 Python 拷进去：<产物>/runtime/python/...
    2. Linux 打成 AppImage / macOS 打成 dmg

⚠️ 本 spec 在 `packaging/` 子目录里，所以 **里面一律不许写相对路径** ——
   PyInstaller 把 spec 内的相对路径按【spec 所在目录】解析，而不是你
   invoke pyinstaller 时的当前目录。写 'packaging/unix_launcher.py' 会被
   拼成 packaging/packaging/unix_launcher.py，直接
   `ERROR: script '...' not found`（CI 首次实跑就栽在这）。
   统一用 SPECPATH 推出绝对路径。
"""
import os
import re
import sys

IS_MAC = sys.platform == "darwin"

# SPECPATH 是 PyInstaller 注入的全局变量 = spec 文件所在目录（绝对路径）
SPEC_DIR = os.path.abspath(SPECPATH)                 # <repo>/packaging
REPO_ROOT = os.path.dirname(SPEC_DIR)                # <repo>

# 版本号从 app/core/meta.py 现读，避免又多出一处要手工同步的地方
_m = re.search(
    r'APP_VERSION\s*=\s*"([^"]+)"',
    open(os.path.join(REPO_ROOT, "app", "core", "meta.py"), encoding="utf-8").read(),
)
VERSION = _m.group(1) if _m else "0.0.0"

# macOS 用 .icns（CI 里由 icon.png 现生成），Linux 用 .png
ICON = (
    os.path.join(SPEC_DIR, "icon.icns")
    if IS_MAC
    else os.path.join(REPO_ROOT, "app", "assets", "icon.png")
)
if not os.path.exists(ICON):
    ICON = None

# 引导界面是 tkinter 写的，而 first_run.py 是被 runpy 在运行时加载的
# —— PyInstaller 的静态分析看不到它，不显式声明就会打出个一启动就
# "No module named 'tkinter'" 的空壳。
#
# ⚠️ 2026-10-04 实测补漏（AppImage 进 appimage.github.io catalog 被打回）：
#   **光声明 tkinter 远远不够。** 分析入口是 unix_launcher.py，它只 import
#   os / runpy / sys —— 于是 first_run.py 里那 9 个模块级标准库
#   （queue / re / shutil / subprocess / threading / time / traceback /
#     importlib.util / os）**一个都不会进 PYZ**。在干净机器上首启直接：
#       ModuleNotFoundError: No module named 'queue'
#       File ".../_internal/app/first_run.py", line 14, in <module>
#   Windows 侧没有这个问题，因为 first_run_gui.spec 的分析入口就是
#   app/first_run.py，分析器走得进去。
#
#   修法：把 "first_run" 交给分析器。它会顺着 first_run.py 的 import 图把它的
#   **模块级标准库**（queue / re / shutil / subprocess / threading / time /
#   traceback / importlib.util …）和它 import 的 core 子模块
#   （platform_ops / runtime_deps / i18n / gpuinfo / meta / netfix，以及传递
#    依赖 settings）一并收进来。
#
#   副作用必须配对处理：core 因此变成一个**冻结包**，它的 __path__ 指向
#   <_MEIPASS>/core —— 于是 core 里没有被 first_run 静态引用的子模块
#   （如 core.engines.*，主程序才用）在运行时只能从磁盘解析，必须把 core/
#   源码也铺成数据文件（见下面 datas 的第二项）。Windows 的 first_run_gui.spec
#   就是同样的组合（hiddenimport first_run 的等价效果 + datas 铺 core）。
HIDDEN = [
    "first_run",
    "tkinter",
    "tkinter.ttk",
    "tkinter.font",
    "tkinter.filedialog",
    "tkinter.messagebox",
]

# 这些重依赖由用户首启时按需安装（对应 Windows 的 first_run）。
# 静态分析本来就不会收集它们（都写在与入口无关的 app/ 源码里），
# 这里再排除一次是双保险，顺便防止哪天不小心把 GB 级内容卷进来。
EXCLUDES = [
    "PySide6", "shiboken6",
    "torch", "torchvision",
    "transformers", "accelerate", "safetensors", "tokenizers", "huggingface_hub",
    "numpy", "docx", "pypdf", "PIL",
]

a = Analysis(
    [os.path.join(SPEC_DIR, "unix_launcher.py")],
    pathex=[os.path.join(REPO_ROOT, "app")],
    binaries=[],
    datas=[
        # 整份 app/ 源码：便携 Python 跑主程序时从这里加载（那也是 core 的
        # 权威副本，包含 engines_calibration.json 等数据）
        (os.path.join(REPO_ROOT, "app"), "app"),
        # core/ 再放一份到 _MEIPASS/core —— 与 Windows 的 first_run_gui.spec
        # 一致，理由见上面 HIDDEN 的注释：first_run.py 被分析后 core/* 会被
        # 冻进 PYZ，而冻结包的 __path__ 就是 <_MEIPASS>/core；不铺这份数据，
        # 冻结包里 core.engines 之类就再也 import 不到了。
        (os.path.join(REPO_ROOT, "app", "core"), "core"),
    ],
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AIGC_Toolkit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # macOS 上 console=True 会让 .app 启动时弹出终端窗口；Linux 上没有这个问题，
    # 反而方便用户从终端看到引导日志。
    console=not IS_MAC,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='AIGC_Toolkit',
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name='AIGC_Toolkit.app',
        icon=ICON,
        bundle_identifier='com.gx664.aigc-toolkit',
        version=VERSION,
        info_plist={
            # 高分屏、深色外观、最低系统版本
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,
            'LSMinimumSystemVersion': '11.0',
            'CFBundleShortVersionString': VERSION,
            'CFBundleVersion': VERSION,
            # 没有开发者证书，产物是未签名的 —— 用户首次打开需手动放行一次
            # （macOS 15+ 用「系统设置 → 隐私与安全性 → 仍要打开」，老版本才用右键→打开；
            #  也可跑一次 xattr 清掉隔离标记，见使用手册）
            'LSApplicationCategoryType': 'public.app-category.utilities',
        },
    )
