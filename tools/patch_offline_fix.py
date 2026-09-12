# -*- coding: utf-8 -*-
"""AIGC 工具箱通用离线修复补丁（兼容所有历史版本）。

修复内容：
  1. 模型下载添加国内镜像源（hf-mirror.com），国内用户无需 VPN
  2. 引擎优先从本地缓存加载模型，离线可用

用法：
  1. 将此脚本放到 AIGC 工具箱根目录（与 app/ 同级）
  2. 运行: python patch_offline_fix.py
  3. 完成后重启工具箱

兼容版本：v1.0.0 ~ v1.2.x（所有使用 transformers 的版本）
"""
import os
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
if not APP.exists():
    APP = ROOT

VERSION = "1.3.0"


def find_app_root():
    if (ROOT / "app").is_dir():
        return ROOT / "app"
    if APP.is_dir() and (APP / "core").is_dir():
        return APP
    for p in [ROOT, ROOT.parent]:
        if (p / "app" / "core").is_dir():
            return p / "app"
    return None


def patch_main_py(app_root):
    fp = app_root / "main.py"
    if not fp.exists():
        return False, "main.py 不存在"
    text = fp.read_text(encoding="utf-8")

    if "HF_ENDPOINT" in text:
        return False, "已包含镜像设置"

    patterns = [
        (
            r"(import os\s*\n\s*import sys\s*\n)",
            r"\1\nos.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')\n",
        ),
        (
            r"(import sys\s*\n\s*\n\s*sys\.path)",
            r"os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')\n\n\1",
        ),
        (
            r"(from PySide6)",
            r"os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')\n\n\1",
        ),
    ]
    for pat, repl in patterns:
        new = re.sub(pat, repl, text, count=1)
        if new != text:
            fp.write_text(new, encoding="utf-8")
            return True, "添加了 HF_ENDPOINT 镜像"

    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "import" in line and ("sys" in line or "os" in line):
            lines.insert(i, "os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')")
            lines.insert(i + 1, "")
            fp.write_text("\n".join(lines), encoding="utf-8")
            return True, "添加了 HF_ENDPOINT 镜像（行插入）"

    return False, "无法识别 main.py 结构"


def patch_engine_file(app_rel_path, model_call_pattern, engine_name):
    fp = app_root / app_rel_path
    if not fp.exists():
        return False, f"{engine_name}: 文件不存在"

    text = fp.read_text(encoding="utf-8")
    if "local_files_only" in text:
        return False, f"{engine_name}: 已包含离线修复"

    def add_local_only(match):
        indent = " " * (len(match.group(0)) - len(match.group(0).lstrip()))
        original = match.group(0).strip()
        return (
            f"{indent}try:\n"
            f"{indent}    {original.replace('from_pretrained(', 'from_pretrained(').replace(')', ', local_files_only=True)')}\n"
            f"{indent}except Exception:\n"
            f"{indent}    {original}"
        )

    new = re.sub(
        rf"([ \t]*\w+\s*=\s*\w+\.from_pretrained\([^)]+\))",
        add_local_only,
        text,
    )

    if new != text:
        fp.write_text(new, encoding="utf-8")
        return True, f"{engine_name}: 添加了 local_files_only 优先"

    return False, f"{engine_name}: 无法识别模型加载代码"


def patch_perplexity_tokens(app_rel_path):
    fp = app_root / app_rel_path
    if not fp.exists():
        return False
    text = fp.read_text(encoding="utf-8")
    if "local_files_only" in text:
        return False, "已修复"

    old_toks = 'self._tok = AutoTokenizer.from_pretrained(\n                        self.model_id, cache_dir=self.model_dir\n                    )'
    new_toks = (
        'try:\n'
        '                        self._tok = AutoTokenizer.from_pretrained(\n'
        '                            self.model_id, cache_dir=self.model_dir, local_files_only=True\n'
        '                        )\n'
        '                    except Exception:\n'
        '                        self._tok = AutoTokenizer.from_pretrained(\n'
        '                            self.model_id, cache_dir=self.model_dir\n'
        '                        )'
    )
    if old_toks in text:
        text = text.replace(old_toks, new_toks, 1)
        fp.write_text(text, encoding="utf-8")
        return True
    return False


def patch_all_engines(app_root):
    results = []
    engine_files = [
        ("core/engines/simpleai_engine.py", "SimpleAI"),
        ("core/engines/perplexity_engine.py", "Perplexity"),
    ]
    for rel, name in engine_files:
        ok, msg = patch_engine_file(rel, r"from_pretrained", name)
        results.append((ok, msg))

    ok = patch_perplexity_tokens("core/engines/perplexity_engine.py")
    if ok:
        results.append((True, "Perplexity tokenizer 修复"))

    return results


def patch_settings_json(settings_path):
    if not settings_path.exists():
        return False, "settings.json 不存在"
    try:
        import json
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False, "settings.json 读取失败"

    if "download" in data:
        return False, "已包含 download 配置"

    data["download"] = {
        "mirror": "hf-mirror.com",
        "hf_endpoint": "https://hf-mirror.com",
    }
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True, "添加了 download 配置到 settings.json"


def main():
    global app_root

    print("=" * 56)
    print("  AIGC 工具箱 通用离线修复补丁 v%s" % VERSION)
    print("  修复: 模型下载需VPN / HuggingFace连接失败")
    print("=" * 56)
    print()

    app_root = find_app_root()
    if app_root is None:
        print("[ERROR] 找不到 app/ 目录")
        print("  请将此脚本放到 AIGC 工具箱根目录（与 app/ 同级）")
        input("\n按回车退出...")
        sys.exit(1)

    print("检测到 app 目录: %s" % app_root)
    print()

    total = 0
    ok, msg = patch_main_py(app_root)
    status = "OK" if ok else "SKIP"
    print("  [%s] main.py: %s" % (status, msg))
    if ok:
        total += 1

    engine_results = patch_all_engines(app_root)
    for ok, msg in engine_results:
        status = "OK" if ok else "SKIP"
        print("  [%s] %s" % (status, msg))
        if ok:
            total += 1

    settings_path = app_root.parent / "settings.json"
    ok, msg = patch_settings_json(settings_path)
    status = "OK" if ok else "SKIP"
    print("  [%s] settings.json: %s" % (status, msg))
    if ok:
        total += 1

    print()
    if total > 0:
        print("修复完成！共修补 %d 处" % total)
    else:
        print("无需修补（已是最新或文件不匹配）")

    print()
    print("使用说明：")
    print("  ┌─────────────────────────────────────────────┐")
    print("  │ 国内用户（推荐）：                            │")
    print("  │   · 默认使用 hf-mirror.com 镜像，无需 VPN    │")
    print("  │   · 首次下载约 400MB，之后离线可用            │")
    print("  │                                              │")
    print("  │ 海外用户 / 有 VPN：                          │")
    print("  │   · 打开工具箱 → ⑨下载设置 → 选择官方源      │")
    print("  │                                              │")
    print("  │ 模型管理：                                   │")
    print("  │   · ⑨下载设置 → 模型管理 → 下载/删除         │")
    print("  │   · 模型只需下载一次，之后完全离线运行         │")
    print("  └─────────────────────────────────────────────┘")
    print()
    input("按回车退出...")


if __name__ == "__main__":
    main()
