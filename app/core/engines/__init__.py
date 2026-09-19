# torch 加载失败（如被安全软件拦截）时不再拖垮整个应用：
# 应用可正常启动，仅本地 AI 检测不可用，并在触发检测时给出明确提示。
TORCH_OK = True
TORCH_ERROR = ""

try:
    from .perplexity_engine import PerplexityEngine
    from .simpleai_engine import SimpleAIEngine
except Exception as _e:  # noqa: BLE001
    TORCH_OK = False
    TORCH_ERROR = "%s: %s" % (type(_e).__name__, _e)
    PerplexityEngine = None
    SimpleAIEngine = None

from .manager import BUILTIN_ENGINES, EngineManager  # noqa: E402


def torch_available():
    return TORCH_OK


def create_engine(cfg, base_dir):
    if not TORCH_OK:
        from core.i18n import tr

        raise RuntimeError(tr("torch_unavailable") % TORCH_ERROR)
    t = cfg.get("type", "classifier")
    if t == "perplexity":
        return PerplexityEngine(cfg, base_dir)
    return SimpleAIEngine(cfg, base_dir)
