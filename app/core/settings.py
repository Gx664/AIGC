import json
import os

DEFAULTS = {
    "app": {
        "install_dir": "",
        "theme": "glass_blue",
    },
    "detect": {
        "engine": "simpleai",
        "threshold": 0.5,
        "min_para_len": 20,
        "max_len": 500,
        "use_gpu": True,
        "max_workers": 0,
        "use_cluster": False,
    },
    "rewrite": {
        "suggest_threshold": 0.30,
        "target_ratio": 0.40,
        "word_level": True,
        "sentence_level": True,
        "parallel": True,
        "dash_fix": True,
        "split_long": True,
        "style_guard": True,
    },
    "presets": {},
}


class Settings:
    """设置 + 参数预设存档。"""

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.path = os.path.join(base_dir, "settings.json")
        self.data = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self._merge(self.data, saved)
        except Exception:
            pass

    @staticmethod
    def _merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                Settings._merge(dst[k], v)
            else:
                dst[k] = v

    def save(self):
        os.makedirs(self.base_dir, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, *keys, default=None):
        d = self.data
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    def set(self, value, *keys):
        d = self.data
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        self.save()

    def save_preset(self, name, params):
        self.data.setdefault("presets", {})[name] = params
        self.save()

    def load_preset(self, name):
        return dict(self.data.get("presets", {}).get(name, {}))

    def list_presets(self):
        return list(self.data.get("presets", {}).keys())

    def delete_preset(self, name):
        self.data.get("presets", {}).pop(name, None)
        self.save()

    def export_presets(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data.get("presets", {}), f, ensure_ascii=False, indent=2)

    def import_presets(self, path):
        with open(path, "r", encoding="utf-8") as f:
            presets = json.load(f)
        self.data.setdefault("presets", {}).update(presets)
        self.save()
