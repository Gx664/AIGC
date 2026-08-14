import json
import os

BUILTIN_ENGINES = [
    {
        "id": "simpleai",
        "name": "SimpleAI 中文检测（轻量，推荐）",
        "type": "classifier",
        "model_id": "Hello-SimpleAI/chatgpt-detector-roberta-chinese",
        "size_hint": "约 400MB",
        "desc": "基于 RoBERTa 的中文文本检测器，CPU/GPU 均可，适合论文检测。",
        "params": {"max_len": 500},
    },
    {
        "id": "gltr",
        "name": "GLTR 困惑度检测（实验）",
        "type": "perplexity",
        "model_id": "gpt2",
        "size_hint": "约 500MB",
        "desc": "用语言模型计算困惑度，越低越像 AI。英文文本效果较好。",
        "params": {"ppl_high": 25.0, "ppl_low": 12.0},
    },
    {
        "id": "fastdetectgpt",
        "name": "Fast-DetectGPT（重，建议显卡）",
        "type": "perplexity",
        "model_id": "EleutherAI/gpt-neo-2.7B",
        "size_hint": "约 5.4GB",
        "desc": "效果较强但模型大，建议在 4090/5090 上使用。",
        "params": {"ppl_high": 20.0, "ppl_low": 10.0},
    },
]


class EngineManager:
    """引擎注册表：内置引擎 + 用户自定义引擎。"""

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.custom_path = os.path.join(base_dir, "engines.json")
        self.custom = []
        self.load_custom()

    def load_custom(self):
        if not os.path.exists(self.custom_path):
            return
        try:
            with open(self.custom_path, "r", encoding="utf-8") as f:
                self.custom = json.load(f)
        except Exception:
            self.custom = []

    def _save_custom(self):
        os.makedirs(self.base_dir, exist_ok=True)
        with open(self.custom_path, "w", encoding="utf-8") as f:
            json.dump(self.custom, f, ensure_ascii=False, indent=2)

    def all(self):
        engines = {e["id"]: e for e in BUILTIN_ENGINES}
        for e in self.custom:
            engines[e["id"]] = e
        return list(engines.values())

    def get(self, engine_id):
        for e in self.all():
            if e["id"] == engine_id:
                return e
        return None

    def add_custom(self, cfg):
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
