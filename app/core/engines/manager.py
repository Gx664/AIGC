# -*- coding: utf-8 -*-
"""引擎注册表：内置清单 + 本地覆盖 + 远端更新 + 用户自定义。

合并优先级（后者覆盖前者）
--------------------------
``catalog.BUILTIN_ENGINES``  <  ``<base_dir>/engines_remote.json``（远端拉取）
                            <  ``<base_dir>/engines_catalog.json``（本地覆盖）
                            <  ``<base_dir>/engines.json``（用户自己加的）

这样「以后要加新模型」有三条路，都不需要重新打包：
1. 用户手动加一条 —— 走 engines.json；
2. 用户放个 engines_catalog.json 覆盖任意字段；
3. 点「检查更新」从远端 manifest 拉新条目。
"""
import json
import os

from . import catalog

# 向后兼容：老代码 / 老设置里还在用 BUILTIN_ENGINES 这个名字
BUILTIN_ENGINES = catalog.BUILTIN_ENGINES


class EngineManager:
    """引擎注册表。所有条目都是 dict，至少含 id / name / category / impl。"""

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.custom_path = os.path.join(base_dir, "engines.json")
        self.catalog_path = os.path.join(base_dir, "engines_catalog.json")
        self.remote_path = os.path.join(base_dir, "engines_remote.json")
        self.plugins_dir = os.path.join(base_dir, "engines_plugins")
        self.custom = []
        self.local_catalog = []
        self.remote = []
        self.plugins_loaded = []
        self.plugins_errors = []
        self.load_custom()
        self._load_plugins()

    # ------------------------------------------------------------ 持久化文件
    @staticmethod
    def _read_json(path, default):
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else data.get("engines", [])
        except Exception:
            return default

    @staticmethod
    def _write_json(path, data):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def load_custom(self):
        self.custom = self._read_json(self.custom_path, [])
        self.local_catalog = self._read_json(self.catalog_path, [])
        self.remote = self._read_json(self.remote_path, [])

    def _save_custom(self):
        self._write_json(self.custom_path, self.custom)

    def _load_plugins(self):
        try:
            from .registry import load_plugins

            self.plugins_loaded, self.plugins_errors = load_plugins(self.plugins_dir)
        except Exception as e:  # noqa: BLE001
            self.plugins_loaded, self.plugins_errors = [], [str(e)]

    # ------------------------------------------------------------------ 查询
    def all(self):
        engines = {}
        for e in catalog.BUILTIN_ENGINES:
            engines[e["id"]] = dict(e)
        for src in (self.remote, self.local_catalog, self.custom):
            for e in src:
                eid = e.get("id")
                if not eid:
                    continue
                base = engines.get(eid, {})
                merged = dict(base)
                merged.update(e)
                merged.setdefault("category", catalog.CAT_DETECT)
                merged.setdefault("impl", "classifier")
                engines[eid] = merged
        out = []
        for e in engines.values():
            e.setdefault("category", catalog.CAT_DETECT)
            e.setdefault("impl", "classifier")
            e.setdefault("models", [])
            e.setdefault("tags", [])
            out.append(e)
        return self._sort(out)

    def _sort(self, engines):
        order = list(catalog.CATEGORY_ORDER)
        for e in engines:
            e["_order"] = order.index(e["category"]) if e["category"] in order else 9
        engines.sort(key=lambda e: (e["_order"], e.get("name", "")))
        for e in engines:
            e.pop("_order", None)
        return engines

    def by_category(self, category):
        return [e for e in self.all() if e.get("category") == category]

    def runnable(self):
        """可以被「检测」流程直接调用的引擎（默认只有检查类）。"""
        return [
            e
            for e in self.all()
            if e.get("runnable", e.get("category") == catalog.CAT_DETECT)
        ]

    def usable_impls(self):
        """当前已成功加载的实现名（torch 被拦或插件出错时会变少）。"""
        try:
            from .registry import registered

            return registered()
        except Exception:  # noqa: BLE001
            return []

    def get(self, engine_id):
        for e in self.all():
            if e["id"] == engine_id:
                return e
        return None

    def categories_present(self):
        present = []
        for e in self.all():
            if e["category"] not in present:
                present.append(e["category"])
        return [c for c in catalog.CATEGORY_ORDER if c in present] or list(catalog.CATEGORY_ORDER)

    def is_custom(self, engine_id):
        return any(c.get("id") == engine_id for c in self.custom)

    def is_builtin(self, engine_id):
        return catalog.by_id(engine_id) is not None

    # ------------------------------------------------------------------ 写入
    def add_custom(self, cfg):
        cfg.setdefault("category", catalog.CAT_DETECT)
        for e in self.custom:
            if e["id"] == cfg["id"]:
                e.update(cfg)
                self._save_custom()
                return
        self.custom.append(cfg)
        self._save_custom()

    def remove(self, engine_id):
        self.custom = [e for e in self.custom if e["id"] != engine_id]
        self._save_custom()

    # -------------------------------------------------------- 预留：远端更新
    def refresh_from_remote(self, url, timeout=15):
        """从远端 manifest 拉取引擎清单并落盘。

        manifest 格式：``{"version": "1", "engines": [ ...条目... ]}``
        成功返回 (True, 新增/更新条数)；失败返回 (False, 错误说明)。
        """
        if not url:
            return False, "未配置更新地址"
        try:
            import urllib.request

            req = urllib.request.Request(url, headers={"User-Agent": "AIGC-Toolkit"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
            data = json.loads(raw)
            engines = data if isinstance(data, list) else data.get("engines", [])
            if not isinstance(engines, list):
                return False, "清单格式不正确"
            known = {e["id"] for e in self.all()}
            fresh = [e for e in engines if isinstance(e, dict) and e.get("id")]
            if not fresh:
                return False, "清单里没有可用条目"
            self._write_json(self.remote_path, fresh)
            self.remote = fresh
            added = len([e for e in fresh if e["id"] not in known])
            return True, added
        except Exception as e:  # noqa: BLE001
            return False, str(e)
