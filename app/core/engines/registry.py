# -*- coding: utf-8 -*-
"""引擎实现注册表 —— 新增检测 / 修复方法不必改动框架代码。

新增一个引擎只要两步
--------------------
1) 写一个类并注册::

       from core.engines.base import BaseEngine
       from core.engines.registry import register

       @register("my_impl")
       class MyEngine(BaseEngine):
           MODELS = (("your-org/your-model", "causal", "打分模型"),)

           def predict_paragraphs(self, paragraphs, device, progress_cb=None, **params):
               # 必须返回 list[float]，每个元素 ∈ [0,1]，表示该段是 AI 写的概率
               ...

2) 在引擎清单里加一条声明（内置 catalog、本地 engines_catalog.json，
   或远端 manifest 都可以）::

       {"id": "mine", "impl": "my_impl", "category": "detect", ...}

之后它就会自动出现在「引擎管理」里，可以下载、可以被检测流程调用。

插件目录
--------
``<base_dir>/engines_plugins/*.py`` 在启动时会自动导入，里面的
``@register`` 同样生效 —— 以后发布新方法，用户把文件丢进去即可，
不需要改动主程序、也不需要重新打包。
"""
import importlib.util
import os
import sys

_REGISTRY = {}


def register(impl):
    """把引擎类登记到注册表（装饰器）。"""

    def deco(cls):
        cls.impl = impl
        _REGISTRY[impl] = cls
        return cls

    return deco


def get_impl(impl):
    return _REGISTRY.get(impl)


def registered():
    """已登记的全部实现名（供 UI 的「可用算法」筛选）。"""
    return sorted(_REGISTRY.keys())


def has(impl):
    return impl in _REGISTRY


def load_plugins(plugin_dir):
    """自动发现 plugin_dir 下的 *.py 插件；单个插件失败不影响主程序。"""
    loaded, errors = [], []
    if not plugin_dir or not os.path.isdir(plugin_dir):
        return loaded, errors
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    for fn in sorted(os.listdir(plugin_dir)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        path = os.path.join(plugin_dir, fn)
        try:
            mod_name = "aigc_engine_plugin_%s" % os.path.splitext(fn)[0]
            spec = importlib.util.spec_from_file_location(mod_name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            loaded.append(fn)
        except Exception as e:  # noqa: BLE001
            errors.append("%s: %s" % (fn, e))
    return loaded, errors
