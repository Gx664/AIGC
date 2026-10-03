import json
import os
import shutil
import sys

DEFAULTS = {
    "app": {
        "install_dir": "",
        "theme": "glass_blue",
    },
    "download": {
        "mirror": "hf-mirror.com",
        "hf_endpoint": "https://hf-mirror.com",
        "models_dir": "",
    },
    "engines": {
        # 引擎清单更新地址：从这里可以拉到新引擎 / 新模型条目，无需升级软件
        "manifest_url": "https://raw.githubusercontent.com/Gx664/AIGC/main/engines_manifest.json",
        "plugins_dir": "",
    },
    "runtime": {
        # 运行组件（PyTorch）的发行版选择：cuda=显卡加速版 / cpu=通用小体积版。
        # 空串表示"还没选过"，由首次启动引导器按是否有显卡决定并写入。
        "torch_variant": "",
    },
    "benchmark": {
        "threshold": 0.5,
        "max_samples": 200,
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


def base_dir():
    """用户数据（设置 / 模型 / license / 日志）的根目录 = **安装目录**。

    为什么必须与安装器一致（2026-09-24 修）
    ---------------------------------------
    主程序是用 runtime 解释器跑 ``app/main.py`` 的，``sys.frozen`` 为 False。
    此前这里（以及 ``ui/main_window.py`` 的 ``BASE_DIR``）取的是 ``app\\`` 目录，
    而安装器把设置写在 ``<安装目录>\\settings.json`` —— 两边差一层 ``app``：

    * 安装器写的语言 / 安装目录记录**永远读不到**；
    * 用户改的设置落在 ``app\\settings.json``，而重装时安装器会 ``rmtree(app)``
      再整目录复制 → **用户的阈值与参数预设一起丢**；
    * 模型落在 ``app\\models``，卸载器找的却是 ``<安装目录>\\models`` ——
      勾了"同时删除已下载的模型"也删不掉（它算出的大小恒为 0）。

    源码模式下上溯三级 = 仓库根，与安装布局同构（``<根>\\settings.json``）。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate_legacy_layout(base_dir_path):
    """把旧布局（用户数据在 ``app/`` 里）搬到安装目录根 —— 只做一次。

    旧路径 → 新路径：
        ``<base>/app/settings.json``        → ``<base>/settings.json``
        ``<base>/app/license.key``          → ``<base>/license.key``
        ``<base>/app/engines_catalog.json`` → ``<base>/engines_catalog.json``
        ``<base>/app/engines_remote.json``  → ``<base>/engines_remote.json``
        ``<base>/app/models/``              → ``<base>/models/``

    **目标已存在就不动**（用户当前的数据优先，宁可少搬不可覆盖）；
    任何异常都吞掉 —— 启动路径上不能因为搬文件失败而打不开程序。

    :param base_dir_path: 安装目录（见 ``base_dir()``）
    :return: 实际搬过的条目名列表（调用方写日志用）
    """
    moved = []
    for name in ("settings.json", "license.key",
                 "engines_catalog.json", "engines_remote.json"):
        src = os.path.join(base_dir_path, "app", name)
        dst = os.path.join(base_dir_path, name)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                shutil.move(src, dst)
                moved.append(name)
            except OSError:
                pass
    models_src = os.path.join(base_dir_path, "app", "models")
    models_dst = os.path.join(base_dir_path, "models")
    if os.path.isdir(models_src) and not os.path.isdir(models_dst):
        try:
            shutil.move(models_src, models_dst)
            moved.append("models/")
        except OSError:
            pass
    return moved


def models_root(base_dir):
    """模型缓存根目录：优先用设置里的 download.models_dir，否则 <base_dir>/models。"""
    d = ""
    try:
        d = Settings(base_dir).get("download", "models_dir", default="") or ""
    except Exception:
        pass
    return d if d else os.path.join(base_dir, "models")


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
