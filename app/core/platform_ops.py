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


def runtime_python(base_dir):
    """运行时解释器路径（不存在时也返回候选路径，由调用方判断）。

    Windows : <base>\\runtime\\python\\python.exe   ← 安装器解压的嵌入版 Python
    Unix    : <base>/runtime/python/bin/python3   ← venv 形态的运行时
    """
    if IS_WIN:
        return os.path.join(runtime_dir(base_dir), "python.exe")
    return os.path.join(runtime_dir(base_dir), "bin", "python3")


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
