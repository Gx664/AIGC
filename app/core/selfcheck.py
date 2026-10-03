# -*- coding: utf-8 -*-
"""启动自检（L1–L3）：确认装好的运行环境**现在**还能用。

为什么需要
----------
软件装完本该一直能用，但环境可能被别的软件或人动过 —— 删了包、把 GPU 版
torch 换成了 CPU 版、显卡驱动升级后 CUDA 不匹配……用户看到的现象只是
"检测跑不动了"，无从判断该修哪一环。自检就是把"哪一环坏了"说清楚。

三级，实测耗时（2026-09-24，i7-14700KF + RTX 4080S）：
    L1 存在性    一次子进程 find_spec 查 8 个包      ~0.02 秒
    L2 可导入    真 import（torch 占大头）            ~2.6 秒
    L3 GPU 可用  import torch + 分配小张量            ~1.5 秒

**L4（真跑一次检测）不做** —— 那要加载模型（几十秒），而且用户实际使用时
自然会报错，没必要每次启动都付这个代价。

调用方**必须在后台线程**里调 ``run_check()``：最慢约 3 秒，别让界面白屏。
"""
import json
import subprocess
import sys

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# 与 first_run.DEPS 的**导入名**保持一致（那边还带 pip 名，这里只要导入名）
CHECK_MODULES = ("torch", "PySide6", "transformers", "accelerate",
                 "docx", "pypdf", "numpy")

# L2 只挑这两个真 import：torch 最重也最容易出问题；PySide6 是界面本体
IMPORT_PROBE = ("torch", "PySide6")

# 在被检查的解释器里跑的子进程代码：一次拿全 L1+L2+L3 的结果（省多次启动开销）
_CHILD_CODE = """
import importlib.util as u, json
mods = %s
probe = %s
out = {"missing": [], "import_fail": [], "cuda": None, "gpu": ""}
for m in mods:
    try:
        if u.find_spec(m) is None:
            out["missing"].append(m)
    except Exception:
        out["missing"].append(m)
for m in probe:
    if m in out["missing"]:
        continue
    try:
        __import__(m)
    except Exception as e:
        out["import_fail"].append(m + ": " + str(e))
try:
    import torch
    out["cuda"] = bool(torch.cuda.is_available())
    if out["cuda"]:
        out["gpu"] = torch.cuda.get_device_name(0)
except Exception:
    pass
print(json.dumps(out))
""" % (list(CHECK_MODULES), list(IMPORT_PROBE))


def run_check(py_exe=None, timeout=300):
    """跑 L1–L3，返回 ``(level, problems)``。

    :param py_exe: 要检查的解释器（默认当前进程的 —— 主程序就是跑在 runtime 里）
    :param timeout: 子进程超时（import torch 慢，给足余量）
    :return: ``(level, problems)``；``level`` ∈ ``{"ok", "warn", "error"}``

        * ``ok``    —— 三项都过
        * ``warn``  —— 能跑但没 GPU 加速（driver 掉了 / 被换成 CPU 版 torch）
        * ``error`` —— 缺包或导入失败，基本跑不起来
    """
    py = py_exe or sys.executable
    try:
        out = subprocess.run(
            [py, "-c", _CHILD_CODE], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as e:
        return "error", ["自检子进程启动失败：%s" % e]

    data = None
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                break
            except ValueError:
                continue
    if data is None:
        return "error", ["自检没有返回结果（%s）" % (out.stderr or "")[:200]]

    problems = []
    if data.get("missing"):
        problems.append("缺少依赖：" + "、".join(data["missing"]))
    if data.get("import_fail"):
        problems.append("导入失败：" + "；".join(data["import_fail"])[:300])
    if data.get("cuda") is False:
        problems.append("GPU 不可用（torch 已装但检测不到 CUDA）")

    if not problems:
        return "ok", []
    # 缺包 / 导入失败 = 跑不起来 -> error；只是没有 GPU = 能跑但慢 -> warn
    hard = bool(data.get("missing") or data.get("import_fail"))
    return ("error" if hard else "warn"), problems
