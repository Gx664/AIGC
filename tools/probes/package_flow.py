# -*- coding: utf-8 -*-
r"""装机与发布流程检查（**静态分析，不真装**）。

为什么静态检查而不是真跑
------------------------
``installer.perform_install()`` 会做三件有副作用的事：

1. ``winreg.CreateKey(HKCU, ...\\Uninstall\\AIGC_Toolkit)`` —— **写注册表**
2. ``shutil.rmtree(pydir)`` / ``rmtree(appdir)`` —— **递归删目录**
3. 联网下载 Python embeddable 包（约 10MB）

在临时目录里"试装"仍会留下注册表项，污染系统。

**回归验证方案**：
* ``smoke_test.py`` 已覆盖"设置/引擎清单可被安装器导入"（零依赖要求）
* 本探针做**静态核查**：
  1. 装机要复制的文件是否齐全（``app/`` 下的运行必需文件）
  2. 新加的标定数据 ``engines_calibration.json`` 是否在 ``app/`` 内
     （**这条最关键** —— 放外面就随 copytree 丢失，用户拿不到新阈值）
  3. ``installer`` 的零依赖约束（不得 import torch / PySide6）
  4. ``app/`` 里有无不该发布的文件（日志、缓存、pyc）
  5. 卸载时是否清得干净（注册表 + 快捷方式 + 目录）

**不联网、不写盘、不碰注册表。**
"""
import ast
import os

from . import ROOT, head

APP = os.path.join(ROOT, "app")

# 运行时必需（缺了程序起不来）
REQUIRED = [
    "main.py",
    "first_run.py",
    "core/__init__.py",
    "core/settings.py",
    "core/gpuinfo.py",
    "core/selfcheck.py",
    "core/engines/__init__.py",
    "core/engines/manager.py",
    "core/engines/catalog.py",
    "core/engines/engines_calibration.json",
    "ui/__init__.py",
    "ui/main_window.py",
]

# 不该随包发布的（体积 / 隐私 / 无用）
SHOULD_NOT_SHIP = [".pyc", ".log", "settings.json", "engines.json", "license.key"]


def run_package_check(v):
    """装机与发布流程静态检查。"""
    head("PKG", "装机 / 发布流程检查（静态，不真装）")

    ok_all = True

    # ------------------------------------------------------ 1. 必需文件
    print("--- 1. 装机后运行必需的文件（app/ 内，随 copytree 复制）---")
    for rel in REQUIRED:
        p = os.path.join(APP, rel.replace("/", os.sep))
        mark = "OK  " if os.path.isfile(p) else "**缺失**"
        if not os.path.isfile(p):
            ok_all = False
        print("   [%s] %s" % (mark, rel))
    print()

    # ------------------------------------------------------ 2. 标定数据位置
    print("--- 2. 标定数据是否在 app/ 内（关键：放外面会随安装丢失）---")
    in_app = os.path.join(APP, "core", "engines", "engines_calibration.json")
    at_root = os.path.join(ROOT, "engines_calibration.json")
    print("   app 内: %s" % ("有" if os.path.isfile(in_app) else "**无**"))
    print("   项目根: %s" % ("有（撤职：不会随安装复制）"
                            if os.path.isfile(at_root) else "无（正确）"))
    if not os.path.isfile(in_app):
        ok_all = False
        print("   !! 标定数据不在 app/ 内 —— 用户装完读不到新阈值")
    else:
        import json

        try:
            with open(in_app, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            n = len(d.get("engines", []))
            print("   内容: %d 条标定项，updated=%s"
                  % (n, d.get("updated", "?")))
        except Exception as e:
            print("   !! 解析失败: %s" % e)
            ok_all = False
    print()

    # ------------------------------------------------------ 3. installer 零依赖
    print("--- 3. installer 的零依赖约束（不得 import torch / PySide6）---")
    ins = os.path.join(ROOT, "installer", "installer.py")
    banned = []
    if os.path.isfile(ins):
        try:
            with open(ins, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module.split(".")[0]]
                for nm in names:
                    if nm in ("torch", "PySide6", "numpy", "transformers"):
                        banned.append((node.lineno, nm))
        except Exception as e:
            print("   解析 installer 失败: %s" % e)
    if banned:
        ok_all = False
        print("   !! 发现重依赖导入（安装器应零依赖）:")
        for ln, nm in banned:
            print("      line %d: %s" % (ln, nm))
    else:
        print("   OK —— 无 torch / PySide6 / numpy / transformers 导入")
    print()

    # ------------------------------------------------------ 4. 不该发布的文件
    print("--- 4. app/ 内不该随包发布的文件 ---")
    bad = []
    for dirpath, dirnames, filenames in os.walk(APP):
        # __pycache__ 安装器已 ignore，但仍列出提醒
        for fn in filenames:
            low = fn.lower()
            if any(low.endswith(s) for s in (".pyc", ".log")):
                bad.append(os.path.relpath(os.path.join(dirpath, fn), APP))
            if fn in ("settings.json", "engines.json", "license.key"):
                bad.append(os.path.relpath(os.path.join(dirpath, fn), APP))
    if bad:
        print("   发现 %d 个:" % len(bad))
        for b in bad[:20]:
            print("      %s" % b)
        print("   注：__pycache__/*.pyc 已被 installer 的 ignore_patterns 排除")
    else:
        print("   OK —— 无")
    print()

    # ------------------------------------------------------ 5. 卸载完整性
    print("--- 5. 卸载流程是否清得干净（静态核查 installer/uninstaller.py）---")
    try:
        # 2026-09 起卸载器是**独立文件**（installer/uninstaller.py，打包成 exe 随安装分发），
        # 不再是 installer.py 里的模板字符串 —— 所以核查对象换成它本身。
        with open(os.path.join(ROOT, "installer", "uninstaller.py"),
                  "r", encoding="utf-8") as fh:
            src = fh.read()
        with open(ins, "r", encoding="utf-8") as fh:
            inst_src = fh.read()
        # **注意**：不要搜 "models" 字面量来判断"删模型目录"——
        # 模型在 <base_dir>/models，属 TARGET 之内，被 `rd /s /q TARGET`
        # 一起删除（卸载提示语也写了"含模型文件"）。搜字面量会误报。
        checks = [
            ("删注册表卸载项", "DeleteKey" in src),
            ("删桌面快捷方式", "Desktop" in src and "os.remove" in src),
            ("删安装目录（含 models/；非空时 rd 自动失败）",
             'rd /s /q' in src and "TARGET" in src),
            ("延迟删除（避开自身 exe 的文件锁）", "ping 127.0.0.1" in src),
            ("自删卸载器 exe", "del /f /q" in src),
            ("运行环境路径取自注册表 RuntimeDir", "RuntimeDir" in src),
            ("安装器复制并注册卸载器 exe", "uninstaller.exe" in inst_src),
            ("旧模板字符串已退场", "UNINSTALLER_TEMPLATE" not in inst_src),
        ]
        for name, ok in checks:
            print("   [%s] %s" % ("OK  " if ok else "**缺**", name))
            if not ok:
                ok_all = False
    except Exception as e:
        print("   读取失败: %s" % e)
        ok_all = False
    print()

    # ------------------------------------------------------ 6. app/settings.json
    print("--- 6. app/settings.json（会被 copytree 复制，但不会被读）---")
    stray = os.path.join(APP, "settings.json")
    if os.path.isfile(stray):
        try:
            import json as _json

            with open(stray, "r", encoding="utf-8") as fh:
                d = _json.load(fh)
            md = (d.get("download") or {}).get("models_dir", "")
            print("   存在。download.models_dir=%r" % md)
            print("   评估：Settings 读的是 <base_dir>/settings.json（base_dir=exe 所在目录），")
            print("         不是 app/settings.json —— 故该文件**不会被读取**，")
            print("         属开发时残留；复制给用户无害但是冗余。")
            if md:
                ok_all = False
                print("   !! 且含本机路径（发布前必须清空或删除本文件）")
            else:
                print("   内容干净（无本机路径），可不处理；建议发布前删除以减体积。")
        except Exception as e:
            print("   解析失败: %s" % e)
    else:
        print("   不存在（干净）")
    print()

    print("=" * 68)
    if ok_all:
        print("装机流程检查通过（关键项：标定数据在 app/ 内、installer 零依赖）")
    else:
        print("!! 有未通过项，见上")
    print("=" * 68)
    v.add("PKG", ok_all, "装机流程静态检查 %s" % ("通过" if ok_all else "有未通过项"))
