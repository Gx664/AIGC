# -*- coding: utf-8 -*-
"""离线修复补丁 - 修复模型下载需VPN / HuggingFace连接失败问题。

用法：
  1. 将此脚本放到 AIGC 工具箱根目录（与 app/ 同级）
  2. 运行: python patch_offline_fix.py
  3. 完成后重启工具箱
"""
import os
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"

PATCHES = {
    "main.py": {
        "find": 'import os\nimport sys\n\nsys.path',
        "replace": 'import os\nimport sys\n\nos.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")\n\nsys.path',
    },
    "core/engines/simpleai_engine.py": {
        "find": 'self._tok = AutoTokenizer.from_pretrained(\n                        self.model_id, cache_dir=self.model_dir\n                    )',
        "replace": 'try:\n                        self._tok = AutoTokenizer.from_pretrained(\n                            self.model_id, cache_dir=self.model_dir, local_files_only=True\n                        )\n                    except Exception:\n                        self._tok = AutoTokenizer.from_pretrained(\n                            self.model_id, cache_dir=self.model_dir\n                        )',
    },
    "core/engines/simpleai_engine.py_model": {
        "find": 'm = AutoModelForSequenceClassification.from_pretrained(\n                    self.model_id, cache_dir=self.model_dir\n                )',
        "replace": 'try:\n                    m = AutoModelForSequenceClassification.from_pretrained(\n                        self.model_id, cache_dir=self.model_dir, local_files_only=True\n                    )\n                except Exception:\n                    m = AutoModelForSequenceClassification.from_pretrained(\n                        self.model_id, cache_dir=self.model_dir\n                    )',
    },
    "core/engines/perplexity_engine.py": {
        "find": 'self._tok = AutoTokenizer.from_pretrained(\n                        self.model_id, cache_dir=self.model_dir\n                    )',
        "replace": 'try:\n                        self._tok = AutoTokenizer.from_pretrained(\n                            self.model_id, cache_dir=self.model_dir, local_files_only=True\n                        )\n                    except Exception:\n                        self._tok = AutoTokenizer.from_pretrained(\n                            self.model_id, cache_dir=self.model_dir\n                        )',
    },
    "core/engines/perplexity_engine.py_model": {
        "find": 'm = AutoModelForCausalLM.from_pretrained(\n                    self.model_id, cache_dir=self.model_dir\n                )',
        "replace": 'try:\n                    m = AutoModelForCausalLM.from_pretrained(\n                        self.model_id, cache_dir=self.model_dir, local_files_only=True\n                    )\n                except Exception:\n                    m = AutoModelForCausalLM.from_pretrained(\n                        self.model_id, cache_dir=self.model_dir\n                    )',
    },
}


def patch_file(rel_path, find_str, replace_str):
    fp = APP / rel_path
    if not fp.exists():
        print(f"  [SKIP] {rel_path} 不存在")
        return False
    text = fp.read_text(encoding="utf-8")
    if find_str not in text:
        print(f"  [SKIP] {rel_path} 已修补或内容不匹配")
        return False
    bak = fp.with_suffix(fp.suffix + ".bak")
    shutil.copy2(fp, bak)
    text = text.replace(find_str, replace_str, 1)
    fp.write_text(text, encoding="utf-8")
    print(f"  [OK]   {rel_path} 已修补 (备份: {bak.name})")
    return True


def main():
    print("=" * 50)
    print("  AIGC 工具箱离线修复补丁")
    print("  修复: 模型下载需VPN / HuggingFace连接失败")
    print("=" * 50)
    print()

    if not APP.exists():
        print("[ERROR] 找不到 app/ 目录，请将此脚本放到工具箱根目录")
        input("按回车退出...")
        sys.exit(1)

    count = 0
    for key, rule in PATCHES.items():
        rel = key.replace("_model", "")
        if patch_file(rel, rule["find"], rule["replace"]):
            count += 1

    print()
    if count > 0:
        print(f"修复完成！共修补 {count} 处")
    else:
        print("无需修补（已是最新或文件不匹配）")

    print()
    print("使用说明：")
    print("  1. 首次使用请开VPN下载模型（仅需一次）")
    print("  2. 之后离线使用无需VPN")
    print("  3. 模型下载走 hf-mirror.com 国内镜像")
    print()
    input("按回车退出...")


if __name__ == "__main__":
    main()
