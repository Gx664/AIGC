# -*- coding: utf-8 -*-
"""探针公共工具：输出、路径、结论汇总。

原 15 个探针脚本每个都重复了一遍 sys.stdout 包装、sys.path 注入、
head()/verdict() 定义。这些收敛到本模块，探针函数只管验证逻辑。
"""
import io
import os
import sys

# 项目根：本文件在 tools/probes/ 下，上溯两级
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(ROOT, "app")

if APP not in sys.path:
    sys.path.insert(0, APP)


class Verdicts(object):
    """收集各探针的结论，供主程序汇总。

    原实现是每个脚本自己一个 RESULT 列表 + 自己打汇总，
    跨脚本无法汇总。这里改为统一收集。
    """

    def __init__(self):
        self.rows = []

    def add(self, tag, ok, detail):
        self.rows.append((tag, ok, detail))
        print(">>> 结论: %s | %s" % ("BUG 确认" if ok else "未复现", detail))

    def table(self):
        print("\n" + "#" * 68)
        for tag, ok, d in self.rows:
            print("  [%s] %-6s %s" % ("BUG" if ok else "OK ", tag, d))
        print("确认 bug: %d / %d"
              % (sum(1 for _, o, _ in self.rows if o), len(self.rows)))

    def bug_count(self):
        return sum(1 for _, o, _ in self.rows if o)


def head(tag, title):
    print("\n" + "=" * 68)
    print("【%s】%s" % (tag, title))
    print("=" * 68)


# --------------------------------------------------------------- 标定值落盘
CALIB_PATH = os.path.join(APP, "core", "engines", "engines_calibration.json")


def save_calibration(engine_id, params, meta):
    """把标定结果**直接写入** ``engines_calibration.json``。

    为什么要有这个函数：标定值是**跑出来的**，不该由人手抄进代码或文档
    （抄写会错、会忘、无法追溯）。探针跑完就写盘，程序启动时自动读取。

    :param engine_id: 引擎 id（如 ``"binoculars"``）
    :param params:    要覆盖的参数，如 ``{"threshold": 0.83, "scale": 0.12}``
    :param meta:      出处，写入 ``_calibration`` 字段（n / acc / criterion / tool / date …）

    **合并语义**：同 id 已存在则更新其 params 与 _calibration；不存在则新增。
    其它引擎的条目不动。
    """
    import json

    try:
        if os.path.isfile(CALIB_PATH):
            with io.open(CALIB_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"version": "1.0", "updated": "", "note": "", "engines": []}
    except Exception:
        data = {"version": "1.0", "updated": "", "note": "", "engines": []}

    engines = data.setdefault("engines", [])
    found = False
    for e in engines:
        if e.get("id") == engine_id:
            e["params"] = params
            e["_calibration"] = meta
            found = True
            break
    if not found:
        engines.append({"id": engine_id, "params": params, "_calibration": meta})

    import datetime
    data["updated"] = datetime.date.today().isoformat()
    data.setdefault(
        "note",
        "标定结果覆盖表。由标定探针写入（probes.save_calibration），"
        "优先级高于内置 catalog.py。_calibration 记录样本量、判据与出处。")

    os.makedirs(os.path.dirname(CALIB_PATH), exist_ok=True)
    with io.open(CALIB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("      [已写入] %s <- %s" % (os.path.basename(CALIB_PATH), engine_id))
    return CALIB_PATH



def setup_stdout():
    """控制台编码不可靠（PowerShell 下中文会乱码），强制 utf-8。"""
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

