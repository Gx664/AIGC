# -*- coding: utf-8 -*-
"""显卡与 CUDA 探测（**纯标准库**，安装器与首次启动引导器共用）。

为什么要单独一个模块
--------------------
安装器必须零依赖（不能 import torch），但"该装哪个 CUDA 版本的 torch"
得看用户机器：有 NVIDIA 卡且驱动够新 → 装 CUDA 版；否则装 CPU 版。
所以这里只用 subprocess + 文件判断，一行都不碰 torch。

CUDA 版本怎么定（关键原理，别想当然）
-------------------------------------
``nvidia-smi`` 输出里的 ``CUDA Version: 12.9`` 是**驱动支持的最高 CUDA 版本**。
按 CUDA 的 minor version compatibility：12.x 的驱动能跑任何 12.y（y ≤ 驱动上限）
编译出来的程序，**反过来不行** —— 拿 cu129 的 wheel 去跑只支持 12.6 的驱动，
会报 ``CUDA driver version is insufficient for CUDA runtime version``。

所以**必须选 ≤ 驱动上限的档位**，越高越好（``_CUDA_BY_DRIVER`` 从新到旧，
取第一个命中的）。

实测备注（2026-09-24）
---------------------
国内镜像里**只有上海交大**同时有 cu128/cu129 的 **Windows** wheel；
阿里云、华为云的索引里只有 Linux wheel，不能当源（详见 first_run.py）。
"""
import os
import re
import shutil
import subprocess

# 探测结果的文案走 i18n（中英双语）。两种导入都要兼容：
#   installer 侧把 `app/core` 挂进 sys.path -> `i18n`
#   主程序侧把 `app` 挂进 sys.path          -> `core.i18n`
try:
    from i18n import tr
except ImportError:  # pragma: no cover
    from core.i18n import tr

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# 驱动支持的 CUDA 版本 -> 装哪个 torch 索引。**顺序即优先级**（从新到旧），
# 取第一个满足 ``cur >= need`` 的档位。
_CUDA_BY_DRIVER = (
    ("12.9", "cu129"),   # 本项目开发/验证环境就是 cu129
    ("12.8", "cu128"),
    ("12.6", "cu126"),
    ("12.4", "cu124"),
    ("12.1", "cu121"),
    ("11.8", "cu118"),
)

# 低于这个版本直接走 CPU 版（再老的驱动连 cu118 都跑不动）
MIN_CUDA = (11, 8)

# 驱动版本号 -> 它支持的最高 CUDA 版本。**新驱动不一定在 nvidia-smi 里打
# ``CUDA Version`` 字段**（610.x 起改成 ``CUDA UMD Version``，字段名还会继续变），
# 正则一旦落空就只剩这张表可兜底，否则会把好卡误判成"驱动过旧"。
# 取值来源：NVIDIA 每个 CUDA  Toolkit 的最低驱动要求（R525→12.0，R580→13.0）。
_DRIVER_MAJOR_CUDA = (
    (580, "13.0"),
    (570, "12.8"),
    (550, "12.4"),
    (525, "12.0"),
    (470, "11.4"),
)

# nvidia-smi 里表示"驱动支持的最高 CUDA 版本"的字段名。按新旧顺序逐个试，
# 后面每加一种新写法只需往这里追加一条，不用改正则。
_CUDA_FIELDS = ("CUDA Version", "CUDA UMD Version")


def nvidia_smi_path():
    """找 nvidia-smi.exe：先 PATH，再 System32（装驱动时固定落这儿）。"""
    p = shutil.which("nvidia-smi")
    if p:
        return p
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    p = os.path.join(sysroot, "System32", "nvidia-smi.exe")
    return p if os.path.exists(p) else None


def _run(cmd, timeout=25):
    """跑一条命令，返回 ``(returncode, stdout+stderr)``；异常一律当成失败。"""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except Exception:
        return -1, ""


def _nvapi_present():
    """没有 nvidia-smi 时，靠 nvapi64.dll 判断机器上有没有 NVIDIA 驱动栈。"""
    if os.name != "nt":
        return False
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.exists(os.path.join(sysroot, "System32", "nvapi64.dll"))


def pick_torch_index(cuda_version):
    """把 ``nvidia-smi`` 报的 CUDA 版本映射成 torch 索引名。

    取**第一个 ≤ 驱动上限**的档位；驱动太老或版本串不认识 → 返回 ``""``（CPU 版）。

    :param cuda_version: 形如 ``"12.9"`` 的字符串（``nvidia-smi`` 里读出来的）
    :return: ``"cu129"`` / ``"cu128"`` / ... / ``""``
    """
    if not cuda_version:
        return ""
    try:
        cur = tuple(int(x) for x in str(cuda_version).split(".")[:2])
    except (ValueError, TypeError):
        return ""
    if len(cur) < 2 or cur < MIN_CUDA:
        return ""
    for need, idx in _CUDA_BY_DRIVER:
        want = tuple(int(x) for x in need.split("."))
        if cur >= want:
            return idx
    return ""


def cuda_from_driver(driver):
    """``nvidia-smi`` 没报 CUDA 字段时，用驱动版本号反推它支持的最高 CUDA。

    新驱动（610+）把 ``CUDA Version`` 改名成 ``CUDA UMD Version``，再往后还会变；
    正则落空时如果就此判定"驱动过旧"，好卡会被误杀成CPU。所以最后用驱动主版本
    兜底：R525 起支持 12.0，R580 起支持 13.0。

    :param driver: 形如 ``"610.47"`` / ``"580.65"`` 的驱动版本
    :return: 形如 ``"12.8"`` 的字符串，认不出返回 ``""``
    """
    if not driver:
        return ""
    m = re.match(r"\s*(\d+)", str(driver))
    if not m:
        return ""
    major = int(m.group(1))
    for need_major, cuda in _DRIVER_MAJOR_CUDA:
        if major >= need_major:
            return cuda
    return ""


def parse_cuda_from_smi(full_output):
    """从 ``nvidia-smi`` 默认输出里取"驱动支持的最高 CUDA 版本"。

    字段名按 ``_CUDA_FIELDS`` 逐个试，谁先命中用谁——不同驱动版本报的名字不一样。

    :param full_output: ``nvidia-smi`` 无参数运行的完整输出
    :return: 形如 ``"12.9"`` 的字符串，没有则 ``""``
    """
    text = full_output or ""
    for field in _CUDA_FIELDS:
        m = re.search(re.escape(field) + r"\s*:\s*([\d.]+)", text)
        if m:
            return m.group(1)
    return ""


def detect():
    """探测显卡与 CUDA，返回「该装哪套 torch」的建议。

    :return: dict

        ==============  ================================================
        ``device``      ``"cuda"`` / ``"cpu"``
        ``has_nvidia``  是否检测到 NVIDIA 显卡
        ``gpu``         显卡名（可能为空串）
        ``driver``      驱动版本（可能为空串）
        ``cuda``        驱动支持的最高 CUDA（可能为空串）
        ``index``       torch 索引名（``"cu129"`` 等）或 ``""``（CPU 版）
        ``reason``      给界面/日志显示的一句话
        ==============  ================================================
    """
    info = {"device": "cpu", "has_nvidia": False, "gpu": "", "driver": "",
            "cuda": "", "index": "", "reason": ""}

    smi = nvidia_smi_path()
    if not smi:
        if _nvapi_present():
            info["has_nvidia"] = True
            info["reason"] = tr("gpu_reason_no_driver")
        else:
            info["reason"] = tr("gpu_reason_no_card")
        return info

    rc, out = _run([smi, "--query-gpu=name,driver_version",
                    "--format=csv,noheader"])
    if rc == 0 and out.strip():
        parts = [p.strip() for p in out.strip().splitlines()[0].split(",")]
        if len(parts) >= 2:
            info["has_nvidia"] = True
            info["gpu"] = parts[0]
            info["driver"] = parts[1]
    if not info["has_nvidia"]:
        # 老驱动可能不支持 --query-gpu，退回解析默认输出里的 Driver Version
        rc2, out2 = _run([smi])
        if rc2 == 0 and out2.strip() and "NVIDIA-SMI" in out2:
            info["has_nvidia"] = True
            m = re.search(r"Driver Version:\s*([\d.]+)", out2)
            if m:
                info["driver"] = m.group(1)

    if not info["has_nvidia"]:
        info["reason"] = tr("gpu_reason_no_card_short")
        return info

    # CUDA Version 只在默认输出里（--query-gpu 不提供这一项）
    _, full = _run([smi])
    info["cuda"] = parse_cuda_from_smi(full)
    if not info["cuda"]:
        # 新驱动换了字段名（610+ 报 "CUDA UMD Version"），正则落空就用驱动号反推，
        # 不能因为读不到字段就断言"驱动过旧"——那是把好卡误判成 CPU 的最常见原因。
        info["cuda"] = cuda_from_driver(info["driver"])

    idx = pick_torch_index(info["cuda"])
    gpu_name = info["gpu"] or "NVIDIA 显卡"
    if idx:
        info["device"] = "cuda"
        info["index"] = idx
        info["reason"] = tr("gpu_reason_cuda") % (
            gpu_name, info["driver"] or "?", info["cuda"] or "?", idx)
    else:
        info["reason"] = tr("gpu_reason_driver_old") % (
            gpu_name, info["cuda"] or "?")
    return info
