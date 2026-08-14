from .perplexity_engine import PerplexityEngine
from .simpleai_engine import SimpleAIEngine
from .manager import BUILTIN_ENGINES, EngineManager


def create_engine(cfg, base_dir):
    t = cfg.get("type", "classifier")
    if t == "perplexity":
        return PerplexityEngine(cfg, base_dir)
    return SimpleAIEngine(cfg, base_dir)
