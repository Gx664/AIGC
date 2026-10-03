# -*- coding: utf-8 -*-
r"""UI 配置合理性检查：设置项是否真的被用、默认值是否合理。

为什么需要
----------
``settings.json`` 里有一堆配置项（threshold / max_len / use_gpu /
max_workers / suggest_threshold ...）。**光有项不代表有效** ——
可能出现：

* 界面给了开关，但代码根本不读（用户改了没用）
* 代码读了某个键，但设置里没有（永远是默认值）
* 默认值与引擎实际需要的不一致（如判定阈值 0.5 vs 引擎 scale）

本探针做**交叉核对**：

1. ``settings.DEFAULTS`` 的每个键，在 ``app/`` 里是否被 ``get()`` 读取
2. 代码里 ``get("a","b")`` 的键，是否都在 DEFAULTS 里（防拼写错/漏声明）
3. UI 上"有控件"的设置项，是否真被用（防"假开关"）
4. 关键默认值的合理性（阈值范围、max_len 与模型上限）

**只读，不写任何文件。**
"""
import os
import re

from . import ROOT, head

APP = os.path.join(ROOT, "app")


def _iter_py(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def _settings_keys():
    """从 settings.py 的 DEFAULTS 提取全部键路径，如 'detect.threshold'。"""
    from core.settings import DEFAULTS

    keys = set()

    def walk(d, prefix):
        for k, v in d.items():
            path = "%s.%s" % (prefix, k) if prefix else k
            if isinstance(v, dict):
                walk(v, path)
            else:
                keys.add(path)

    walk(DEFAULTS, "")
    return keys


def run_config_check(v):
    """UI 配置合理性检查。"""
    head("UICFG", "UI 配置合理性检查（设置项是否真被使用）")

    declared = _settings_keys()
    print("settings.py 声明 %d 个配置项" % len(declared))
    print()

    # ------------------------------ 收集代码里的 get() 调用
    #
    # ⚠️ **这段扫描已降级为"仅提示"** —— 用正则在源码里找 `xxx.get("a","b")`
    # 无法可靠区分「Settings 实例」与「普通 dict / i18n」：
    # 实测即便按变量名过滤，仍会把 `tr` 的 fallback、dict 取值误判成设置项
    # （如 model.unknown / overall_risk.low）。
    # 要准确必须走 AST 做类型推导，成本远高于收益，故：
    #   * 第 1、2 节结果**仅供参考**，不作为"bug"
    #   * 第 3 节（默认值合理性）是**可靠**的，作为判定依据
    used = {}          # 键 -> [文件:行]
    pat = re.compile(r'\.get\(\s*"([^"]+)"\s*,\s*"([^"]+)"')
    setter_pat = re.compile(r'\b(settings|_settings)\b')
    for path in _iter_py(APP):
        if path.endswith("settings.py"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except Exception:
            continue
        s_vars = set()
        for ln in lines:
            m = re.search(r'(\w+)\s*=\s*Settings\(', ln)
            if m:
                s_vars.add(m.group(1))
        for i, ln in enumerate(lines, 1):
            if not pat.search(ln):
                continue
            m = re.search(r'(\w+(?:\.\w+)*)\.get\(', ln)
            if not m:
                continue
            recv = m.group(1)
            base = recv.split(".")[-1] if "." in recv else recv
            is_cfg = (base in s_vars) or bool(setter_pat.search(base))
            if not is_cfg:
                continue
            for mm in pat.finditer(ln):
                key = "%s.%s" % (mm.group(1), mm.group(2))
                used.setdefault(key, []).append(
                    "%s:%d" % (os.path.relpath(path, APP), i))

    print("代码中被 get() 读取 %d 个键" % len(used))
    print()

    # ------------------------------ 1. 声明了但没人用
    unused = sorted(k for k in declared if k not in used)
    print("--- 1. 声明了但代码里没读到【仅供参考，见文件头说明】---")
    if unused:
        for k in unused:
            print("   %s" % k)
        print("   注：正则扫描无法区分设置与普通 dict/i18n，结果可能不准确；")
        print("       需人工核对（如 rewrite.* 项多由 _collect_params 汇总后写入）")
    else:
        print("   （无）")
    print()

    # ------------------------------ 2. 读了但没声明
    undeclared = sorted(k for k in used if k not in declared)
    print("--- 2. 代码读了但 settings 里没声明【仅供参考】---")
    if undeclared:
        for k in undeclared:
            print("   %s    <- %s" % (k, ", ".join(used[k][:3])))
    else:
        print("   （无）")
    print()

    # ------------------------------ 3. 关键默认值合理性
    print("--- 3. 关键默认值合理性 ---")
    from core.settings import DEFAULTS

    det = DEFAULTS.get("detect", {})
    checks = []

    thr = det.get("threshold")
    checks.append(("detect.threshold 在 (0,1)", isinstance(thr, (int, float))
                   and 0 < thr < 1, thr))
    mlen = det.get("max_len")
    checks.append(("detect.max_len > 0", isinstance(mlen, int) and mlen > 0,
                   mlen))
    mw = det.get("max_workers")
    checks.append(("detect.max_workers >= 0", isinstance(mw, int) and mw >= 0,
                   mw))
    st = (DEFAULTS.get("rewrite") or {}).get("suggest_threshold")
    checks.append(("rewrite.suggest_threshold 在 (0,1)",
                   isinstance(st, (int, float)) and 0 < st < 1, st))
    eng = det.get("engine")
    checks.append(("detect.engine 非空", bool(eng), eng))
    for name, ok, val in checks:
        print("   [%s] %-42s = %r" % ("OK  " if ok else "**异常**", name, val))
    print()

    # ------------------------------ 4. 界面控件与设置项的对应
    print("--- 4. 界面上的设置控件（看有无'假开关'）---")
    try:
        with open(os.path.join(APP, "ui", "main_window.py"),
                  "r", encoding="utf-8") as fh:
            src = fh.read()
        # 常见设置类控件
        widgets = [
            ("阈值滑块", "thr_slider"),
            ("阈值数值框", "thr_spin"),
            ("最小段长", "min_len"),
            ("降重建议阈值", "suggest_thr"),
            ("并行数", "workers"),
        ]
        for label, attr in widgets:
            has_w = ("self.%s" % attr) in src
            # 该控件是否被写入 settings
            saved = re.search(
                r'settings\.set\([^)]*"%s"' % attr, src) is not None
            print("   %-14s 控件=%s  写回 settings=%s"
                  % (label, "有" if has_w else "无",
                     "是" if saved else "（经 _collect_params 汇总）"))
    except Exception as e:
        print("   检查失败: %s" % e)
    print()

    print("=" * 68)
    # 判定只依据**可靠**的部分：关键默认值合理性（第 3 节）。
    # 第 1/2 节的键扫描仅供参考（正则在源码上区分不了设置与普通 dict）。
    bad = [n for n, ok, _ in checks if not ok]
    if bad:
        print("!! 关键默认值异常 %d 项: %s" % (len(bad), bad))
    else:
        print("关键默认值全部合理（第 1/2 节键扫描仅供参考）")
    print("=" * 68)
    v.add("UICFG", not bad,
          "默认值 %d 项检查，异常 %d；键扫描（参考）：声明 %d / 使用 %d"
          % (len(checks), len(bad), len(declared), len(used)))
