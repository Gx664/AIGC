# -*- coding: utf-8 -*-
"""引擎包入口：模块加载容错 + 实现注册表 + 统一工厂。

torch 加载失败（如被安全软件驱动拦截）时不再拖垮整个应用：
引擎清单与管理界面照常可用，只有真正跑检测时才会给出明确提示。
"""
import importlib

from .manager import BUILTIN_ENGINES, EngineManager  # noqa: F401
from .registry import get_impl, load_plugins, register, registered  # noqa: F401

# torch 是否可用单独判定。引擎模块一律在函数内部才 import torch，
# 所以即使 torch 被拦住，9 个引擎条目、模型清单、下载界面仍然完整可见。
TORCH_OK = True
TORCH_ERROR = ""
try:
    import torch  # noqa: F401
except Exception as _e:  # noqa: BLE001
    TORCH_OK = False
    TORCH_ERROR = "%s: %s" % (type(_e).__name__, _e)

# 需要尝试加载的引擎实现模块；单个失败不影响其余引擎
_ENGINE_MODULES = (
    "simpleai_engine",
    "perplexity_engine",
    "curvature_engine",
    "binoculars_engine",
    "rule_engine",
)

MODULE_ERRORS = {}
for _name in _ENGINE_MODULES:
    try:
        importlib.import_module("." + _name, __package__)
    except Exception as _e:  # noqa: BLE001
        MODULE_ERRORS[_name] = "%s: %s" % (type(_e).__name__, _e)

# 旧字段 type -> 新字段 impl（兼容老设置里的自定义引擎）
_TYPE_ALIAS = {
    "classifier": "classifier",
    "perplexity": "perplexity",
    "curvature": "curvature",
    "binoculars": "binoculars",
}


def torch_available():
    return TORCH_OK


def resolve_impl(cfg):
    """条目里的 impl 优先；没有就退回旧的 type 字段。"""
    impl = cfg.get("impl") or ""
    if impl:
        return impl
    return _TYPE_ALIAS.get(cfg.get("type", "classifier"), "classifier")


def create_engine(cfg, base_dir):
    """按条目声明创建引擎实例（注册表驱动，支持插件）。"""
    impl = resolve_impl(cfg)
    cls = get_impl(impl)
    if cls is None:
        from core.i18n import tr

        raise RuntimeError(tr("engine_impl_missing") % (impl, ", ".join(registered()) or "-"))
    if getattr(cls, "needs_torch", True) and not TORCH_OK:
        from core.i18n import tr

        raise RuntimeError(tr("torch_unavailable") % TORCH_ERROR)
    return cls(cfg, base_dir)

# aigc-toolkit: file purpose marker
