# -*- coding: utf-8 -*-
"""运行组件（PyTorch 等）的下载策略 —— 供首次启动引导器与主程序共用。

背景
----
PyTorch 有两个发行版：

* **CUDA 版**：捆了 NVIDIA 运行库，约 2.5～3.5 GB，有独立显卡时检测快很多
* **CPU 版**：约 0.2 GB，没有显卡时是唯一选择，有显卡时也能跑但慢

以前是"自动判断"（查得到 nvidia-smi 就装 CUDA 版），用户没得选。现在改成
**有独立显卡时给用户选**，并把选择记进 ``settings.json``，重装 / 修复时沿用。

本模块只依赖标准库（外加项目内的 ``settings``），因为引导器在依赖装齐之前
就要 import 它 —— 那时 torch / PySide6 都还不存在。
"""
import os
import shutil

from . import platform_ops
from .settings import Settings

# ---------------------------------------------------------------- 常量
PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

# ------------------------------------------------- 慎重修改：torch 源列表
#
# 🔴 判断一个源能不能用，**必须用 pip 亲测**，不能只看浏览器能不能打开：
#
#       pip index versions torch --index-url <源>
#
#   因为 pip 会去请求 ``<源>/torch/``（pip 的 search_scope.get_index_urls_locations
#   把 index_url 与包名拼起来），只有「按包名分目录」的 **PEP 503 索引**才走得通。
#   2026-10-01 逐个实测的结果（含踩过的坑）：
#
#     mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/   → 整站 404，已死
#     mirrors.aliyun.com/pytorch-wheels/{cu128,cpu}  → ⚠️ 最坑的一个：根目录打得开、
#         能列出几千个 .whl，看着非常健康；但它是"所有轮子摊平在根目录"的布局，
#         ``<源>/torch/`` 是 **404**，pip 一律报
#         ``No matching distribution found for torch`` —— 完全不能用
#     腾讯云 / CERNET / 北大 / 浙大 / 华为云 / 南大 / USTC / BFSU → 无此镜像
#     mirror.sjtu.edu.cn/pytorch-wheels/{cpu,cu128}  → ✅ 唯一可用的国内源
#         pip 实测返回 2.14.1+cpu / 2.11.0+cu128；平台齐全
#         （cpu 频道：Linux x86_64/aarch64、macOS arm64/x86_64、Windows x64；
#           cu128 频道：Linux 两种架构 + Windows，macOS 没有也不该有 —— 苹果无 CUDA）
#         且自带 torch 的全部纯 Python 依赖（filelock/sympy/networkx/jinja2/
#         fsspec/mpmath…）与 nvidia-* 分包，`--index-url` 屏蔽 PyPI 也不会缺件
#
#   ⚠️ 别把上面这些死源/假可用源加回来：轻则每次安装白等一轮超时，重则直接装不上。
#   测试 ``_diag/test_unix_adapt.py`` 里有守卫会拦。
#   清华的 **PyPI** 镜像（PYPI_MIRROR，装普通包用）仍然好使，与这里是两码事。

# CUDA 版 torch 的候选源，按顺序尝试（上交 → 官方）
TORCH_CUDA_MIRRORS = [
    "https://mirror.sjtu.edu.cn/pytorch-wheels/cu128",
    "https://download.pytorch.org/whl/cu128",
]

# CPU 版 torch 的候选源（**仅 Unix 用**，见 cpu_mirrors()）
TORCH_CPU_MIRRORS = [
    "https://mirror.sjtu.edu.cn/pytorch-wheels/cpu",
    "https://download.pytorch.org/whl/cpu",
]

# 已证实不可用、不许再回到候选列表里的源（测试用）
DEAD_MIRRORS = (
    "mirrors.tuna.tsinghua.edu.cn/pytorch-wheels",
    "mirrors.aliyun.com/pytorch-wheels",
    "mirrors.cloud.tencent.com/pytorch-wheels",
    "mirrors.cernet.edu.cn/pytorch-wheels",
)


def all_torch_mirrors():
    """所有可能被用到的 torch 源（供测试守卫统一检查）。"""
    return tuple(TORCH_CUDA_MIRRORS) + tuple(TORCH_CPU_MIRRORS)

# 界面与检测组件（不含 torch/torchvision，那两个单独按变体安装）
#
# ⚠️ 这里写的是 **pip 发行包名**，不是 import 名，两者不一致时务必写发行名。
# 曾经写成 "docx" 造成线上事故（2026-10-01 用户反馈）：
# PyPI 上的 ``docx`` 是 2011 年的 Python 2 版本（单文件 docx.py），Python 3 下
# 一 import 就抛 ``No module named 'exceptions'``；正确的包名是 ``python-docx``。
# 相关的名称映射 / 严格校验 / 冲突清理见下面三个常量。
DEPS = ["PySide6", "transformers", "accelerate", "python-docx", "pypdf", "numpy"]

# pip 包名 → import 名（只有两者不一致时才需要登记）
DEP_IMPORT_NAME = {
    "python-docx": "docx",
}

# 反向映射：import 名 → pip 包名
IMPORT_NAME_DEP = {v: k for k, v in DEP_IMPORT_NAME.items()}

# 这些 import 名除了检查"能不能找到"，还要真跑一次 ``import`` 才算健康。
# 原因：``find_spec`` 不执行代码，像远古 docx.py 那种"装上了但一 import 就炸"
# 的包会被误判成健康 —— 这正是那次事故排查困难的根源。
STRICT_IMPORT = ("docx",)

# 安装正确包之前必须先卸掉的旧包（import 名相同、pip 名不同，会互相遮蔽）
CONFLICTING_OLD_PKGS = {
    "python-docx": ("docx",),
}

VARIANT_CUDA = "cuda"
VARIANT_CPU = "cpu"
VARIANTS = (VARIANT_CUDA, VARIANT_CPU)

# 界面提示用的体积说明（粗略值，仅作提示）
VARIANT_SIZE = {
    VARIANT_CUDA: "约 2.5～3.5 GB",
    VARIANT_CPU: "约 0.2 GB",
}

_VARIANT_LABEL = {
    VARIANT_CUDA: "CUDA（显卡加速，检测快）",
    VARIANT_CPU: "CPU（体积小，通用）",
}


# ---------------------------------------------------------------- 纯逻辑
def import_name(pip_name):
    """pip 包名 → import 名（未登记时两者相同）。"""
    return DEP_IMPORT_NAME.get(pip_name, pip_name)


def dep_of_import(import_name):
    """import 名 → pip 包名（未登记时原样返回）。"""
    return IMPORT_NAME_DEP.get(import_name, import_name)


def needs_strict_import(import_name):
    """该 import 名是否需要"真跑一次 import"才算健康。"""
    return import_name in STRICT_IMPORT


def old_pkgs_to_remove(pip_name):
    """装 ``pip_name`` 之前应先卸载的旧包名（元组，可能为空）。"""
    return CONFLICTING_OLD_PKGS.get(pip_name, ())


def normalize_variant(value):
    """把任意输入收敛成 ``"cuda"`` / ``"cpu"``，无法识别时返回空串。"""
    v = str(value or "").strip().lower()
    return v if v in VARIANTS else ""


def default_variant(has_gpu):
    """没得选时的默认变体：有显卡默认 CUDA，否则 CPU。"""
    return VARIANT_CUDA if has_gpu else VARIANT_CPU


def needs_prompt(has_gpu):
    """是否需要弹选择框。

    只有**有独立显卡**时才问：这时 CUDA 版（快、约 3GB）和 CPU 版（小、慢）
    差别巨大，值得让用户选。没有显卡时 CUDA 版毫无意义，直接装 CPU 版，
    不打扰用户。
    """
    return bool(has_gpu)


def variant_label(variant):
    return _VARIANT_LABEL.get(normalize_variant(variant), "")


def has_nvidia():
    """粗略判断本机有没有 NVIDIA 独立显卡（引导器与主程序都用这个）。

    macOS 一律 False —— 苹果机器没有 NVIDIA 驱动（Apple Silicon 走 PyTorch
    自带支持的 MPS，官方 wheel 直接可用），问用户"要 CUDA 还是 CPU"没有意义。
    """
    if platform_ops.IS_MAC:
        return False
    if shutil.which("nvidia-smi"):
        return True
    if not platform_ops.IS_WIN:
        return False
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.exists(os.path.join(sysroot, "System32", "nvapi64.dll"))


def cpu_mirrors():
    """CPU 版 torch 的候选源，按顺序尝试。

    ⚠️ 为什么 Unix 不能直接用 PyPI 镜像：PyPI 上 **Linux** 的 ``torch`` wheel
    默认捆了 CUDA 运行库（下载约 2 GB，解压更大）。用户明明选了"CPU 版"
    （约 0.2 GB），却按普通 PyPI 源去下，会白等几十分钟且磁盘暴涨。
    Windows 的 PyPI wheel 本身就是 CPU 版，所以保持原样走 PyPI 镜像 ——
    **这个分支不能动，动了就是改变 Windows 现有行为**。
    """
    if platform_ops.IS_WIN:
        return [PYPI_MIRROR]
    return list(TORCH_CPU_MIRRORS)


def pick_variant(has_gpu, saved="", ask=None):
    """决定最终装哪个变体。

    :param has_gpu: 本机是否有 NVIDIA 显卡
    :param saved:   上次记住的选择（可为空）
    :param ask:     可选的询问回调，签名 ``ask(default) -> "cuda"/"cpu"/None``；
                    返回 None 表示用默认值。只有 ``needs_prompt()`` 为真时才会调用。
    :return: ``"cuda"`` 或 ``"cpu"``
    """
    saved = normalize_variant(saved)
    if saved:
        return saved
    if not needs_prompt(has_gpu):
        return VARIANT_CPU
    default = default_variant(has_gpu)
    if ask is None:
        return default
    got = normalize_variant(ask(default))
    return got or default


# ---------------------------------------------------------------- 读写记忆
def get_variant(base_dir):
    """读取记住的变体；没记过或读失败返回空串。"""
    try:
        return normalize_variant(
            Settings(base_dir).get("runtime", "torch_variant", default="")
        )
    except Exception:
        return ""


def set_variant(base_dir, variant):
    """记住变体选择；失败时静默（不因为记不住而让安装失败）。"""
    v = normalize_variant(variant)
    if not v:
        return False
    try:
        Settings(base_dir).set(v, "runtime", "torch_variant")
        return True
    except Exception:
        return False
