# -*- coding: utf-8 -*-
"""平台适配层：Windows / macOS / Linux 的差异全部收在这一个文件里。

设计原则
--------
1. **只放事实与动作** —— 路径在哪、用哪个字体、图标叫什么名、解释器什么位置、
   怎么建/删桌面入口。业务逻辑不进来。
2. **不改动 Windows 现有行为** —— 所有 Windows 分支返回的值必须与改造前一致
   （字体仍 `Microsoft YaHei UI`、图标仍 `icon.ico`、数据目录仍是安装目录）。
3. **import 无副作用** —— 不建目录、不读注册表、不碰环境变量。
4. **不依赖第三方库** —— 纯标准库，且延迟 import 平台专有模块（winreg 等）。
"""

import os
import sys

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

APP_NAME = "AIGC_Toolkit"
APP_ID = "com.gx664.aigc-toolkit"

# 各平台首选中文界面字体（取列表第一个；Qt / Tk 找不到会自己回退，不会报错）
_FONT_CANDIDATES = {
    "win": ["Microsoft YaHei UI", "Microsoft YaHei", "SimHei"],
    "mac": ["PingFang SC", "Heiti SC", "Songti SC"],
    "linux": ["Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "DejaVu Sans"],
}

# 图标候选（按优先级）。macOS 的 .icns 由 CI 在打包时生成到 packaging/，
# 没打进去时回退 .png —— Qt 两种都能读。
_ICON_CANDIDATES = {
    "win": ["icon.ico", "icon.png"],
    "mac": ["icon.icns", "icon.png"],
    "linux": ["icon.png", "icon.ico"],
}


def platform_key():
    """返回 'win' / 'mac' / 'linux' / 其它平台的原样字符串。"""
    if IS_WIN:
        return "win"
    if IS_MAC:
        return "mac"
    if IS_LINUX:
        return "linux"
    return sys.platform


def ui_font_family():
    """Qt 界面首选字体名（与改造前的 Windows 行为一致）。"""
    return _FONT_CANDIDATES[platform_key()][0]


def ui_font_candidates():
    """Qt 界面字体候选列表，按优先级。"""
    return list(_FONT_CANDIDATES[platform_key()])


def tk_font(size=14, bold=False):
    """Tk 界面字体元组（首启引导器是 tkinter 写的）。"""
    return (ui_font_family(), size, "bold") if bold else (ui_font_family(), size)


def icon_candidates():
    """图标文件名候选（不含目录），按优先级。"""
    return list(_ICON_CANDIDATES[platform_key()])


def find_icon(*dirs):
    """在给定目录里按候选顺序找图标，返回绝对路径；都没有则返回空串。"""
    for name in icon_candidates():
        for d in dirs:
            if not d:
                continue
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return ""


def home_dir():
    return os.path.expanduser("~")


def user_data_dir(app=APP_NAME):
    """用户级数据目录（配置 / 日志 / 模型缓存的默认落点）。

    Windows : %LOCALAPPDATA%\\AIGC_Toolkit
    macOS   : ~/Library/Application Support/AIGC_Toolkit
    Linux   : $XDG_DATA_HOME/AIGC_Toolkit（默认 ~/.local/share/AIGC_Toolkit）
    """
    k = platform_key()
    if k == "win":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(home_dir(), "AppData", "Local")
    elif k == "mac":
        base = os.path.join(home_dir(), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(home_dir(), ".local", "share")
    return os.path.join(base, app)


def user_config_dir(app=APP_NAME):
    """用户级配置目录（Linux 用 XDG_CONFIG_HOME，其余同数据目录）。"""
    if platform_key() == "linux":
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home_dir(), ".config")
        return os.path.join(base, app)
    return user_data_dir(app)


def effective_base_dir(base_dir):
    """数据根目录。

    Windows 保持现状（安装目录，settings.json / logs / models 都在那儿）；
    Unix 走用户级目录 —— 因为 .app 在 /Applications 下、AppImage 也可能只读，
    往安装位置写数据会失败。
    """
    if IS_WIN:
        return base_dir
    return user_data_dir()


def runtime_dir(base_dir):
    """运行时根目录（与安装器实际布局一致：<base>/runtime/python/）。"""
    return os.path.join(base_dir, "runtime", "python")


def python_in(root):
    """给定一个 Python 安装根目录，返回其中的解释器路径。

    Windows : <root>\\python.exe
    Unix    : <root>/bin/python3
    """
    if IS_WIN:
        return os.path.join(root, "python.exe")
    return os.path.join(root, "bin", "python3")


def runtime_python(base_dir):
    """**打包自带**解释器的路径（只读用途；不存在时也返回候选路径）。

    Windows : <base>\\runtime\\python\\python.exe   ← 安装器解压的嵌入版 Python
    Unix    : <base>/runtime/python/bin/python3   ← CI 解入的独立 CPython
    """
    return python_in(runtime_dir(base_dir))


def runtime_root(base_dir):
    """真正用来装依赖的运行目录。

    Windows : ``<base>/runtime/python``（安装目录里，本来就可写）
    Unix    : ``<数据目录>/runtime/python``

    为什么 Unix 要挪个地方：macOS 的 .app 常放在 /Applications、AppImage 是
    只读的 squashfs 镜像，往包里 ``pip install`` 必然失败；而且 AppImage 每次
    挂载点都不同（``/tmp/.mount_xxxx``），在那儿建 venv 下次启动就废了。
    所以 Unix 侧把打包自带的解释器**复制一份**到用户目录，依赖装在副本里。
    Windows 走 ``effective_base_dir`` 后原样返回，与改造前完全一致。
    """
    return runtime_dir(effective_base_dir(base_dir))


def work_python(base_dir):
    """真正装依赖、跑主程序的解释器。

    Windows : ``<base>/runtime/python/python.exe``（与 ``runtime_python`` 相同）
    Unix    : ``<数据目录>/runtime/python/bin/python3``（打包自带那份的副本）
    """
    return python_in(runtime_root(base_dir))


def runtime_is_local(base_dir):
    """运行目录是否已经落在可写位置（Windows 恒为真，Unix 看有没有落地副本）。"""
    if IS_WIN:
        return True
    return os.path.exists(work_python(base_dir))


def program_base_dir(exe_path):
    """由可执行文件位置反推**程序根目录**（含 ``app/`` 与 ``runtime/``）。

    两种打包布局都要认：
      * Windows —— 引导器 ``first_run_gui.exe`` 放在 ``<安装目录>/app/`` 里，
        上一层才是程序根；
      * Unix    —— PyInstaller 的 onedir 可执行文件与 ``app/`` 平级，
        自己就是程序根。
    判据是"这个目录看起来像不像 app 目录"（名字叫 app，或直接有 ``main.py``）。

    注意 **不能**用 ``sys._MEIPASS`` 顶替：单文件模式那是临时解包目录，
    每次启动路径都变，拿它当数据目录会让用户设置凭空消失。
    """
    d = os.path.dirname(os.path.abspath(exe_path))
    name = os.path.basename(os.path.normpath(d))
    if name == "app" or os.path.isfile(os.path.join(d, "main.py")):
        return os.path.dirname(os.path.normpath(d))
    return os.path.normpath(d)


def app_source_dir(base_dir):
    """``app/`` 源码目录的实际位置（含 ``main.py`` / ``core/`` / ``ui/``）。

    为什么不能写死 ``<base>/app``：PyInstaller 6 不再把 datas 摊在产物根，
    而是塞进 ``_internal/``；macOS 的 .app 里更靠外一层（``Contents/Frameworks``
    或 ``Contents/Resources``，且相对 ``Contents/MacOS`` 是上一级）。
    所以按可能性探测，判据是"这一层有没有 ``main.py``"。

    Windows 上安装器会把 app/ 源码放在 ``<安装目录>/app/``（与引导器 exe 同级），
    第一个候选即命中，行为与改造前一致。
    """
    cands = [
        os.path.join(base_dir, "app"),
        os.path.join(base_dir, "_internal", "app"),
        os.path.join(base_dir, os.pardir, "Frameworks", "app"),
        os.path.join(base_dir, os.pardir, "Resources", "app"),
        os.path.join(base_dir, "Contents", "Frameworks", "app"),
        os.path.join(base_dir, "Contents", "Resources", "app"),
    ]
    for c in cands:
        if os.path.isfile(os.path.join(c, "main.py")):
            return os.path.normpath(c)
    for c in cands:  # 退一步：main.py 缺失但目录在（让调用方给出更有用的报错）
        if os.path.isdir(c):
            return os.path.normpath(c)
    return os.path.join(base_dir, "app")


def export_env(base_dir, key="AIGC_TOOLKIT_HOME"):
    """把程序根目录与数据根目录写进环境变量，供子进程 / 主程序复用。"""
    os.environ[key] = os.path.abspath(base_dir)
    os.environ["AIGC_TOOLKIT_DATA"] = effective_base_dir(base_dir)
    return os.environ[key]


def data_subdir(base_dir, name):
    """在数据根目录下取子目录并确保存在，返回路径。"""
    p = os.path.join(effective_base_dir(base_dir), name)
    os.makedirs(p, exist_ok=True)
    return p


# --------------------------------------------------------------------------
# 桌面入口
# --------------------------------------------------------------------------
def desktop_dir():
    """桌面目录（找不到就返回空串）。"""
    k = platform_key()
    if k == "win":
        p = os.path.join(home_dir(), "Desktop")
    elif k == "mac":
        p = os.path.join(home_dir(), "Desktop")
    else:
        p = os.path.join(home_dir(), "Desktop")
    return p if os.path.isdir(p) else ""


def applications_dir():
    """Linux 的 .desktop 安装位置（用户级，不需要 root）。"""
    if not IS_LINUX:
        return ""
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(home_dir(), ".local", "share")
    return os.path.join(base, "applications")


def shortcut_mode():
    """桌面入口的形态：

    win   -> 'lnk'      由 installer.py 用 COM 创建（保持现状，本模块不重复实现）
    mac   -> 'bundle'   .app 本身就是入口，不需要另建快捷方式
    linux -> 'desktop'  写一个 .desktop 文件到 ~/.local/share/applications
    """
    k = platform_key()
    if k == "win":
        return "lnk"
    if k == "mac":
        return "bundle"
    return "desktop"


def desktop_entry_text(exec_path, icon_path="", name="AIGC 检测工具箱"):
    """生成 Linux .desktop 文件内容（纯字符串，方便测试）。"""
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=%s" % name,
        "Exec=\"%s\"" % exec_path,
        "Terminal=false",
        "Categories=Utility;TextTools;",
    ]
    if icon_path:
        lines.append("Icon=%s" % icon_path)
    return "\n".join(lines) + "\n"


def install_desktop_entry(exec_path, icon_path=""):
    """Linux：写 .desktop 入口。返回写入路径；平台不支持则返回空串。"""
    if not IS_LINUX:
        return ""
    d = applications_dir()
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "%s.desktop" % APP_NAME)
    with open(p, "w", encoding="utf-8") as f:
        f.write(desktop_entry_text(exec_path, icon_path))
    try:
        os.chmod(p, 0o755)
    except OSError:
        pass
    return p


def remove_desktop_entry():
    """Linux：删掉 .desktop 入口。返回删除的文件路径，未删到返回空串。"""
    if not IS_LINUX:
        return ""
    p = os.path.join(applications_dir(), "%s.desktop" % APP_NAME)
    if os.path.exists(p):
        os.remove(p)
        return p
    return ""


def uninstall_supported():
    """是否有"注册到系统卸载列表"这件事。

    win   -> True（HKCU 卸载键）
    其余  -> False：Linux 靠删目录 + .desktop，macOS 靠拖动 .app 到废纸篓，
            系统层面没有注册表那种入口。
    """
    return IS_WIN


def describe():
    """给日志 / 诊断用的一行摘要。"""
    return "平台=%s 数据目录=%s 运行时=%s 入口=%s" % (
        platform_key(),
        user_data_dir(),
        runtime_python("<base>"),
        shortcut_mode(),
    )
