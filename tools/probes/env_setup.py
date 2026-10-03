# -*- coding: utf-8 -*-
r"""安装 / 运行环境检查：路径校验、CUDA 映射、卸载器 exe、进度解析、启动自检。

为什么要做成探针
----------------
这五块逻辑以前**只能靠"真装一次"来验**：真装要下载运行时、写注册表、
建快捷方式、几分钟、还有副作用（所以 `package_flow` 只敢做静态核查）。
拆成纯函数后就能**秒级、无副作用**地反复验，改一行跑一次。

与 `package_flow` 的分工：
    `package_flow`  —— 装机流程**静态核查**（必需文件、零依赖、卸载完整性）
    `env_setup`     —— 本轮新增的**可执行逻辑**（校验 / 映射 / 模板 / 进度 / 自检）
"""
import ast
import os
import sys
import time

from . import ROOT, head

_APP = os.path.join(ROOT, "app")
_CORE = os.path.join(_APP, "core")
_INST = os.path.join(ROOT, "installer")


def _load_installer():
    """导入 installer 模块（它自己会把 app/core 挂进 sys.path 供 i18n 用）。"""
    if _INST not in sys.path:
        sys.path.insert(0, _INST)
    import installer
    return installer


def run_env_setup(v):
    head("ENV", "安装 / 运行环境检查（路径校验 / CUDA 映射 / 卸载器 / 进度 / 自检）")
    ok_all = True
    inst = _load_installer()

    # ---------------------------------------------------- 1. 路径校验各档
    print("--- 1. 运行环境路径校验（check_runtime_path）---")
    home = os.path.expanduser("~")
    cases = [
        ("", "error", "空输入"),
        (r"D:\AIGC\rt?x", "error", "非法字符 ?"),
        (r"D:\CON", "error", "保留名 CON"),
        (r"D:\CON\sub", "error", "保留名在中间"),
        (r"Z:\nope", "error", "盘符不存在"),
        ("D:\\" + "a" * 210, "error", "过长"),
        (r"D:\foo.", "error", "点结尾"),
        ("D:\\", "error", "盘根"),
        (r"C:\Windows", "error", "系统目录"),
        (home, "error", "用户主目录"),
        (os.path.join(home, "Desktop"), "error", "桌面"),
        (r"relative\path", "error", "相对路径"),
        (r"D:\AIGC_env_probe_ok", "ok", "正常-不存在"),
        (r"D:\Project\AIGC", "warn", "非空目录"),
        (r"D:\不存在的目录\x", "warn", "中文路径"),
    ]
    bad = 0
    for path, want, name in cases:
        lvl, _msg = inst.check_runtime_path(path)
        if lvl != want:
            bad += 1
            print("   [FAIL] %-14s 期望 %-6s 实得 %s" % (name, want, lvl))
    print("   %d/%d 符合预期" % (len(cases) - bad, len(cases)))
    if bad:
        ok_all = False
    print()

    # ------------------------------------------------- 2. CUDA -> 索引映射
    print("--- 2. 驱动 CUDA -> torch 索引映射（pick_torch_index）---")
    if _CORE not in sys.path:
        sys.path.insert(0, _CORE)
    import gpuinfo

    mapping = [("12.9", "cu129"), ("13.0", "cu129"), ("12.8", "cu128"),
               ("12.7", "cu126"), ("12.6", "cu126"), ("12.5", "cu124"),
               ("12.4", "cu124"), ("12.3", "cu121"), ("12.1", "cu121"),
               ("12.0", "cu118"), ("11.8", "cu118"), ("11.6", ""),
               ("", ""), ("abc", "")]
    bad = 0
    for cuda, want in mapping:
        got = gpuinfo.pick_torch_index(cuda)
        if got != want:
            bad += 1
            print("   [FAIL] CUDA %-6r 期望 %-7r 实得 %r" % (cuda, want, got))
    print("   %d/%d 符合预期" % (len(mapping) - bad, len(mapping)))
    if bad:
        ok_all = False
    # 映射表不能有重复档位（重复说明写错了）
    idxs = [i for _c, i in gpuinfo._CUDA_BY_DRIVER]
    if len(idxs) != len(set(idxs)):
        ok_all = False
        print("   [FAIL] 映射表有重复索引: %s" % idxs)
    # 老驱动必须回落到 CPU 版（否则装了也跑不起来）
    if gpuinfo.pick_torch_index("11.6") != "":
        ok_all = False
        print("   [FAIL] CUDA 11.6 应回落到 CPU 版")
    print()

    # ---------------------------------------------------- 3. 卸载器（独立 exe）
    print("--- 3. 卸载器 installer/uninstaller.py（三个勾 / 自删 / 语法）---")
    unp = os.path.join(_INST, "uninstaller.py")
    try:
        with open(unp, "r", encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        ok_all = False
        src = ""
        print("   [FAIL] 读不到 %s: %s" % (unp, e))
    checks = [
        ("三个勾变量都在",
         all(k in src for k in ("chk_cache =", "chk_run =", "chk_models ="))),
        ("三个勾默认都不打（False）",
         src.count("tk.BooleanVar(value=False)") >= 3),
        ("三类清理各自独立",
         all(k in src for k in ("cache_dirs", "run_dir", "models_dir"))),
        ("模型只删自己的子目录（不整删 models_dir）",
         "_ENGINE_DIRS" in src and "rmtree(models_dir" not in src),
        ("运行环境路径取自注册表（用户可能放到别的盘）",
         "RuntimeDir" in src),
        ("自删：延迟 del exe + rd 目录（避开自身文件锁）",
         "ping 127.0.0.1" in src and "del /f /q" in src and "rd /s /q" in src),
        ("卸载器声明不改用户环境", "不会修改" in src),
    ]
    for name, cond in checks:
        print("   [%s] %s" % ("OK  " if cond else "FAIL", name))
        if not cond:
            ok_all = False
    try:
        ast.parse(src)
        print("   [OK  ] 卸载器语法正确（ast.parse）")
    except SyntaxError as e:
        ok_all = False
        print("   [FAIL] 卸载器语法错: %s" % e)

    # 安装器一侧：旧方案（生成 .py 交给 pythonw）必须已经彻底退场，
    # 否则等于两套卸载器并存 —— 用户点哪个都说不清
    print("   --- 安装器与卸载器的接口 ---")
    try:
        with open(os.path.join(_INST, "installer.py"), "r", encoding="utf-8") as f:
            inst_src = f.read()
        pairs = [
            ("安装器已不再生成 .py 卸载器（无 UNINSTALLER_TEMPLATE）",
             "UNINSTALLER_TEMPLATE" not in inst_src),
            ("安装器复制并注册卸载器 exe", "uninstaller.exe" in inst_src),
            ("RuntimeDir 写进注册表（卸载器据此删环境）",
             "RuntimeDir" in inst_src and "RuntimeDir" in src),
            ("注册表键两边一致",
             "AIGC_Toolkit" in inst_src and "AIGC_Toolkit" in src),
        ]
        for name, cond in pairs:
            print("   [%s] %s" % ("OK  " if cond else "FAIL", name))
            if not cond:
                ok_all = False
    except OSError as e:
        ok_all = False
        print("   [FAIL] 读 installer.py 失败: %s" % e)
    print()

    # ------------------------------------------------- 4. 进度解析（分母）
    print("--- 4. 下载进度解析（PipProgress 的分母来源）---")
    if _APP not in sys.path:
        sys.path.insert(0, _APP)
    import first_run as fr

    units = [
        ("Downloading torch-2.8.0+cu129-cp312-cp312-win_amd64.whl (2.6 GB)",
         2.6 * 1024 ** 3),
        ("Downloading PySide6-6.9.2-cp39-abi3-win_amd64.whl (250 kB)",
         250 * 1024),
        ("Downloading numpy-2.0.0.tar.gz (18.3 MB)", 18.3 * 1024 ** 2),
    ]
    bad = 0
    for line, want in units:
        m = fr._PIP_SIZE_RE.search(line)
        got = (float(m.group(1)) * fr._SIZE_UNIT.get((m.group(2) or "").lower(), 1)
               if m else None)
        if got is None or abs(got - want) > 2:
            bad += 1
            print("   [FAIL] %r -> %s，期望 %s" % (line[:46], got, want))
    print("   %d/%d 解析正确" % (len(units) - bad, len(units)))
    if bad:
        ok_all = False
    # 非下载行不能误匹配（否则分母虚高，百分比永远涨不上去）
    if fr._PIP_SIZE_RE.search("Collecting torch"):
        ok_all = False
        print("   [FAIL] 'Collecting torch' 被误判为下载行")
    print()

    # ------------------------------------------------------- 5. 启动自检
    print("--- 5. 启动自检（selfcheck.run_check 真跑一次）---")
    import selfcheck

    t0 = time.time()
    level, problems = selfcheck.run_check()
    dt = time.time() - t0
    print("   level=%s  耗时 %.2f 秒  问题=%s" % (level, dt, problems or "无"))
    # 开发机依赖齐全 -> 不该是 error；超过 10 秒会明显拖慢启动
    if level == "error":
        ok_all = False
        print("   [FAIL] 开发机自检不该是 error")
    if dt > 10:
        ok_all = False
        print("   [FAIL] 自检太慢（%.1f 秒），启动时会明显拖" % dt)
    print()

    # --------------------------------------------------- 6. 依赖表一致性
    print("--- 6. 依赖表与源（导入名 / pip 名不能混用）---")
    deps = {mod: pkg for mod, pkg, _spec in fr.DEPS}
    # docx 的 pip 名必须是 python-docx —— 直接把 docx 交给 pip 会装到别的东西
    if deps.get("docx") != "python-docx":
        ok_all = False
        print("   [FAIL] docx 的 pip 名应为 python-docx，实为 %r" % deps.get("docx"))
    else:
        print("   [OK  ] docx -> python-docx")
    if not all(spec for m, _p, spec in fr.DEPS if m in ("transformers", "PySide6")):
        ok_all = False
        print("   [FAIL] transformers / PySide6 缺少版本约束")
    else:
        print("   [OK  ] transformers / PySide6 有版本约束")
    # pip 缓存必须在自有目录里（不能写进用户全局 %LOCALAPPDATA%\pip\Cache）
    if fr.PIP_CACHE.startswith(fr.APP_DIR):
        print("   [OK  ] pip 缓存指向自有目录: %s" % os.path.basename(fr.PIP_CACHE))
    else:
        ok_all = False
        print("   [FAIL] pip 缓存目录不合预期: %s" % fr.PIP_CACHE)
    # torch 源里不能留已失效的清华地址（实测 404）
    if any("tuna.tsinghua" in m for m in fr.TORCH_MIRRORS):
        ok_all = False
        print("   [FAIL] torch 源里仍有失效的清华地址")
    else:
        print("   [OK  ] torch 源: %s"
              % ", ".join(m.split("/")[2] for m in fr.TORCH_MIRRORS))
    print()

    v.add("ENV", not ok_all,
          "路径校验 %d/%d、CUDA 映射 %d/%d、卸载器 exe、进度解析、自检 %.2fs"
          % (len(cases) - (0 if ok_all else 1), len(cases),
             len(mapping), len(mapping), dt))
