# -*- coding: utf-8 -*-
"""AIGC_Toolkit 全功能冒烟测试（不依赖 torch 可用）。"""
import sys, os, re, traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ok, fail = [], []

def check(name, fn):
    try:
        r = fn()
        ok.append(name)
        print("PASS", name, ("-> " + str(r) if r is not None else ""))
    except Exception as e:
        fail.append((name, str(e)))
        print("FAIL", name, "->", e)
        traceback.print_exc(limit=1)

# 1) 核心模块导入
def t_imports():
    import core.detector, core.diagnosis, core.therapy, core.settings, core.i18n, core.meta
    import core.engines
    assert core.engines.EngineManager
    return "version=" + core.meta.APP_VERSION
check("核心模块导入", t_imports)

# 2) i18n 完整性：代码里用到的 tr 键在中英两份词典都存在
def t_i18n():
    import core.i18n as i18n
    used = set()
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scan_dirs = [os.path.join(base, "app"), os.path.join(base, "installer")]
    for root_dir in scan_dirs:
        for root, _, files in os.walk(root_dir):
            if "__pycache__" in root or "logs" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    src = open(os.path.join(root, f), encoding="utf-8").read()
                    # 只匹配独立调用，排除 .tr( 等成员调用
                    used.update(k for k in re.findall(r'(?<![\w.])tr\(\s*"([a-z0-9_]+)"', src) if not k.endswith('_'))
    # 找词典：尝试常见命名
    dicts = None
    for n in ("DICTS", "_DICTS", "TEXTS", "_TEXTS", "STRINGS"):
        if hasattr(i18n, n):
            dicts = getattr(i18n, n)
            break
    if dicts is None:
        # 退化：从模块全局找 dict[str,str] 大对象
        cand = {n: v for n, v in vars(i18n).items() if isinstance(v, dict) and len(v) > 50}
        dicts = max(cand.values(), key=len)
        missing_zh = [k for k in used if k not in dicts]
    else:
        missing_zh = [k for k in used if k not in dicts.get("zh", {})]
        missing_en = [k for k in used if k not in dicts.get("en", {})]
        if missing_en:
            raise AssertionError("缺 en 键: %s" % missing_en)
    if missing_zh:
        raise AssertionError("缺 zh 键: %s" % missing_zh)
    return "%d 个键全部存在" % len(used)
check("i18n 键完整性", t_i18n)

# 3) 设置读写
def t_settings():
    from core.settings import Settings
    s = Settings("..")
    lang = s.get("ui", "language", default="zh")
    assert lang in ("zh", "en")
    mr = s.get("download", "models_dir", default="")
    return "lang=%s models_dir=%r" % (lang, mr)
check("设置读写", t_settings)

# 4) 文本提取 + 分段（txt 路径）
def t_extract():
    import tempfile
    from core.doc_reader import extract_text, split_paragraphs
    p = os.path.join(tempfile.gettempdir(), "smoke_t.txt")
    open(p, "w", encoding="utf-8").write("第一段，随着人工智能的不断发展。首先我们要理解原理。\n\n第二段内容，综上所述值得深入研究。因此具有重要意义。")
    text = extract_text(p)
    paras = split_paragraphs(text, 10)
    assert len(paras) >= 2, paras
    return "%d 段" % len(paras)
check("文本提取/分段", t_extract)

# 5) 诊断
def t_diag():
    from core.diagnosis import diagnose
    paras = ["随着科技的不断发展，首先、其次、综上所述，这一方案具有重要意义。"]
    probs = [0.87]
    d = diagnose(paras, probs, 0.5)
    assert "summary" in d and "paragraphs" in d
    return "risk=%s" % d["summary"].get("overall_risk")
check("诊断报告", t_diag)

# 6) 规则降重（真实改写，不依赖 torch）
def t_treat():
    from core.therapy import treat, export_text
    paras = ["随着人工智能的不断发展，检测技术变得越来越重要。综上所述，值得深入研究。",
             "这是一段人类写的普通文字。"]
    opts = {"target_ratio": 0.5, "strength": "standard"}
    result = treat(paras, [1, 2], opts)
    assert result, list(result)[:5] if isinstance(result, dict) else None
    out_text = export_text(result)
    assert isinstance(out_text, str) and len(out_text) > 0
    return "导出 %d 字" % len(out_text)
check("规则降重+导出", t_treat)

# 7) torch 降级路径
def t_torch():
    from core.engines import TORCH_OK, TORCH_ERROR
    from core.detector import detect_local
    if TORCH_OK:
        return "torch正常（意外但更好）"
    try:
        detect_local({"id": "simpleai"}, "..", ["测试"], {"use_gpu": False})
        raise AssertionError("本应抛错")
    except RuntimeError as e:
        assert "无法加载" in str(e) or "failed to load" in str(e)
        return "友好错误OK"
check("torch降级提示", t_torch)

# 8) 引擎管理器
def t_mgr():
    from core.engines import EngineManager, BUILTIN_ENGINES
    m = EngineManager("..")
    assert m.get("simpleai"), "内置引擎simpleai找不到"
    assert len(BUILTIN_ENGINES) >= 3
    return "%d 内置" % len(BUILTIN_ENGINES)
check("引擎管理器", t_mgr)

# 9) 双语切换冒烟
def t_lang():
    from core.i18n import set_lang, tr, get_lang
    set_lang("en")
    v = tr("app_name")
    set_lang("zh")
    v2 = tr("app_name")
    assert v and v2
    return "%s / %s" % (v2, v)
check("双语切换", t_lang)

# 10) UI 模块导入（不显示窗口）
def t_ui():
    from PySide6.QtWidgets import QApplication
    import ui.main_window, ui.rewrite_dialog, ui.settings_dialog, ui.glass
    return "ui模块OK"
check("UI模块导入", t_ui)

print()
print("=" * 40)
print("通过 %d / %d" % (len(ok), len(ok) + len(fail)))
if fail:
    print("失败项：")
    for n, e in fail:
        print(" -", n, ":", e[:120])
    sys.exit(1)
print("ALL-PASS")

# aigc-toolkit: file purpose marker
