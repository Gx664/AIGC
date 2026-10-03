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
    m = re.search(r"CUDA Version:\s*([\d.]+)", full or "")
    info["cuda"] = m.group(1) if m else ""

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
