# -*- coding: utf-8 -*-
"""静态类探针：AST 扫描 + 原作者代码风格核查。

来源：
  probe_static_scan_ast.py
  probe_author_style.py / probe_style_check.py / probe_style_diff.py（3 合 1）

本组无副作用、不加载模型，秒级完成。
"""
import ast
import os
import re
import subprocess

from . import ROOT, head

SCAN_DIRS = [os.path.join(ROOT, "app"), os.path.join(ROOT, "installer"),
             os.path.join(ROOT, "tools")]


def _git(args):
    """调 git 取已跟踪文件（风格核查只统计 git 跟踪的 .py）。"""
    return subprocess.check_output(["git"] + args, cwd=ROOT, text=True,
                                   errors="replace")


def py_files():
    for base in SCAN_DIRS:
        for r, dirs, fs in os.walk(base):
            if "__pycache__" in r:
                continue
            for f in fs:
                if f.endswith(".py"):
                    yield os.path.join(r, f)


def run_static_scan(v):
    """3.0 BOM / 3.1 未用导入 / 3.2 行长 / 3.3 静默 except / 3.4 参数签名。"""
    files = sorted(py_files())

    # ---- 3.0 BOM 检查（2026-09-23 新增）----
    # `.py` 带 UTF-8 BOM 时 Python 能跑，但 `ast.parse` 会报
    # `invalid non-printable character U+FEFF` —— 静态检查 / linter /
    # 部分工具链会因此失败。常见成因：Windows 上用 PowerShell 的
    # `Set-Content -Encoding UTF8` 或 `WriteAllText(..., UTF8Encoding $true)`
    # 批量改文件，**两者都会写 BOM**。
    head("3.0", "UTF-8 BOM 检查（.py 不应带 BOM）")
    bom_files = []
    for fp in files:
        try:
            with open(fp, "rb") as fh:
                if fh.read(3) == b"\xef\xbb\xbf":
                    bom_files.append(fp)
        except Exception:
            pass
    if bom_files:
        for fp in bom_files:
            print("   **带 BOM**: %s" % os.path.relpath(fp, ROOT))
        print("   -> 用 UTF8Encoding($false) 回写可去除")
    else:
        print("   无（%d 个文件全部干净）" % len(files))
    print()

    head("3.1", "未使用导入（AST）")
    print("扫描 .py 文件: %d 个" % len(files))
    print()

    unused = []
    for fp in files:
        try:
            src = open(fp, encoding="utf-8").read()
            tree = ast.parse(src)
        except Exception as e:
            print("  解析失败 %s: %s" % (os.path.basename(fp), e))
            continue
        imported = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    nm = (a.asname or a.name).split(".")[0]
                    imported[nm] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name == "*":
                        continue
                    imported[a.asname or a.name] = node.lineno
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                p = node
                while isinstance(p, ast.Attribute):
                    p = p.value
                if isinstance(p, ast.Name):
                    used.add(p.id)
        lines = src.splitlines()
        for nm, ln in sorted(imported.items()):
            if nm in used:
                continue
            if ln - 1 < len(lines) and "noqa" in lines[ln - 1]:
                continue
            unused.append((os.path.relpath(fp, ROOT), ln, nm))
    print("未使用导入共 %d 处:" % len(unused))
    for rel, ln, nm in unused:
        print("   %-46s :%-4d %s" % (rel, ln, nm))

    head("3.2", "行长超 80 字符（A9）")
    rows = []
    total_over = 0
    for fp in files:
        lines = open(fp, encoding="utf-8", errors="replace").read().splitlines()
        over = [(i, len(l)) for i, l in enumerate(lines, 1) if len(l) > 80]
        if over:
            rows.append((os.path.relpath(fp, ROOT), len(lines), len(over),
                         max(x[1] for x in over)))
            total_over += len(over)
    rows.sort(key=lambda r: -r[2])
    print("超长行合计 %d 处，涉及 %d 个文件" % (total_over, len(rows)))
    print("   %-46s %6s %6s %6s" % ("文件", "总行", "超长", "最长"))
    for rel, tot, ov, mx in rows[:16]:
        print("   %-46s %6d %6d %6d" % (rel, tot, ov, mx))

    head("3.3", "静默 except（吞异常）")
    silent = []
    for fp in files:
        lines = open(fp, encoding="utf-8", errors="replace").read().splitlines()
        for i, l in enumerate(lines):
            s = l.strip()
            if s in ("pass", "continue") and i > 0:
                prev = lines[i - 1].strip()
                if prev.startswith("except") or prev.startswith("finally"):
                    silent.append((os.path.relpath(fp, ROOT), i, prev, s))
    print("静默 except 共 %d 处:" % len(silent))
    for rel, ln, prev, s in silent:
        print("   %-40s :%-4d %s -> %s" % (rel, ln, prev, s))

    head("3.4", "引擎 predict_paragraphs 签名 vs benchmark 传参")
    import inspect

    from core.engines import catalog
    from core.engines.rule_engine import CnkiDiagnoseEngine, RuleRewriteEngine

    for cls in (RuleRewriteEngine, CnkiDiagnoseEngine):
        sig = inspect.signature(cls.predict_paragraphs)
        print("   %s.predict_paragraphs%s" % (cls.__name__, sig))
    print()
    print("   benchmark_dialog.py:212 传入 params = dict(cfg.get('params') or {})")
    for eid in ("aigc_reduce", "cnki_skill", "raid", "mgtbench"):
        e = catalog.by_id(eid)
        # by_id 找不到时返回 None —— 直接 .get() 会 AttributeError。
        # 加防护：清单变更后探针不该整个崩掉。
        print("   catalog[%s].params = %r"
              % (eid, e.get("params") if e else "**清单里没有该条目**"))
    print()
    print("   -> 修复/评测类引擎 params 为空或少字段，predict_paragraphs")
    print("      收到的是 {}，CnkiDiagnoseEngine 期待 probs/threshold，规则引擎期待 options")
    _cnki = catalog.by_id("cnki_skill")
    if not _cnki:
        print("   （跳过：清单里没有 cnki_skill）")
        return
    cp = CnkiDiagnoseEngine(_cnki, os.path.join(ROOT, "app"))
    try:
        r = cp.predict_paragraphs(["这段文本用于测试参数传递。"], None, **{})
        print("   CnkiDiagnoseEngine.predict_paragraphs(**{}) -> %r" % r)
    except Exception as e:
        print("   抛错: %s: %s" % (type(e).__name__, e))
    rp = RuleRewriteEngine(catalog.by_id("aigc_reduce"), os.path.join(ROOT, "app"))
    try:
        r = rp.predict_paragraphs(["这段文本用于测试参数传递。"], None, **{})
        print("   RuleRewriteEngine.predict_paragraphs(**{}) -> %r" % r)
    except Exception as e:
        print("   抛错: %s: %s" % (type(e).__name__, e))
    print()
    print("   传入不存在的键会怎样:")
    for k in ({"threshold": 0.5}, {"probs": [0.9]}):
        try:
            RuleRewriteEngine(catalog.by_id("aigc_reduce"), ROOT).predict_paragraphs(
                ["测试文本内容。"], None, **k)
            print("      RuleRewriteEngine **%r -> 未报错" % k)
        except Exception as e:
            print("      RuleRewriteEngine **%r -> %s: %s" % (k, type(e).__name__, e))
        try:
            CnkiDiagnoseEngine(catalog.by_id("cnki_skill"), ROOT).predict_paragraphs(
                ["测试文本内容。"], None, **k)
            print("      CnkiDiagnoseEngine **%r -> 未报错" % k)
        except Exception as e:
            print("      CnkiDiagnoseEngine **%r -> %s: %s" % (k, type(e).__name__, e))

# ------------------------------------------------------------ 风格核查
def run_style_report(v):
    """原作者风格逐项调查 + 格式检查 + 改动一致性核对（原 3 个脚本合并）。

    输出到控制台（不再落盘）。
    """
    out_path = None
    log = None

    def w(s=""):
        print(s)

    tracked = _git(["ls-files", "*.py"]).splitlines()
    files = [f for f in tracked if os.path.exists(os.path.join(ROOT, f))]
    srcs = {}
    for f in files:
        try:
            srcs[f] = open(os.path.join(ROOT, f), encoding="utf-8",
                           errors="replace").read()
        except Exception:
            pass

    head("A", "原作者代码风格逐项调查")
    w("=" * 76)
    w("原作者代码风格逐项调查（%d 个文件）" % len(srcs))
    w("=" * 76)
    w("说明：本表目的是弄清原作者风格，供改动时对齐。")
    w()

    def stat(fn, name, note=""):
        hits = {f: fn(s) for f, s in srcs.items()}
        hits = {f: val for f, val in hits.items() if val}
        tot = sum(hits.values()) if hits and all(
            isinstance(x, int) for x in hits.values()) else 0
        w("--- %s ---" % name)
        if note:
            w("    skill 要求: %s" % note)
        if not hits:
            w("    原作者: 无（0 个文件）")
        else:
            w("    原作者: %d 处，涉及 %d 个文件"
              % (tot if tot else len(hits), len(hits)))
            for f, val in sorted(hits.items(), key=lambda x: -x[1])[:6]:
                w("      %-40s %s" % (f, val))
        w()

    def count_cn_comment(s):
        n = 0
        for l in s.splitlines():
            st = l.strip()
            if st.startswith("#") and any("\u4e00" <= c <= "\u9fff" for c in st):
                n += 1
        return n

    stat(count_cn_comment, "A.1 中文行注释", "skill 要求注释全英文")

    def count_cn_docstring(s):
        try:
            tree = ast.parse(s)
        except Exception:
            return 0
        n = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Module)):
                ds = ast.get_docstring(node)
                if ds and any("\u4e00" <= c <= "\u9fff" for c in ds):
                    n += 1
        return n

    stat(count_cn_docstring, "A.1 中文 docstring", "skill 要求 docstring 全英文")
    stat(lambda s: len(re.findall(r"os\.path\.join\(", s)),
         "A.2 os.path.join() 用量", "skill 强制用 pathlib.Path 的 / 运算符")
    stat(lambda s: len(re.findall(r"Path\(__file__\)|from pathlib import", s)),
         "A.2 pathlib 用量", "skill 强制 pathlib")
    stat(lambda s: len(re.findall(r"\bprint\(", s)), "A.2 print() 用量",
         "skill 要求放弃 logging，统一 print")
    stat(lambda s: len(re.findall(r"\blogging\.", s)), "A.2 logging 用量",
         "skill 要求放弃 logging")
    stat(lambda s: len(re.findall(r"=\s*\[\]", s)), "A.2 `= []`（空列表字面量）",
         "skill 建议改用 list()")
    stat(lambda s: len(re.findall(r'=\s*"', s)), 'A.11 赋值用双引号 " 的次数',
         "skill 要求单引号")
    stat(lambda s: len(re.findall(r"=\s*'", s)), "A.11 赋值用单引号 ' 的次数",
         "skill 要求单引号")
    stat(lambda s: sum(1 for l in s.splitlines() if len(l) > 80),
         "A.9 行长 > 80", "skill 要求 <= 80")

    # ------------------------------------------------ 格式检查（10 项）
    long_lines, long_lines_pct = [], []
    tab_indent, trailing_ws, no_encoding = [], [], []
    bare_except, mutable_default, eq_none = [], [], []
    broad_short, todo = [], []

    for rel in files:
        src = srcs.get(rel, "")
        if not src:
            continue
        lines = src.splitlines()
        rel_n = rel.replace("\\", "/")

        over100 = [(i, len(l)) for i, l in enumerate(lines, 1) if len(l) > 100]
        if over100:
            long_lines.append((rel_n, len(over100), max(n for _, n in over100)))
        over79 = [i for i, l in enumerate(lines, 1) if len(l) > 79]
        if over79:
            long_lines_pct.append((rel_n, len(over79), len(lines)))
        for i, l in enumerate(lines, 1):
            if l.startswith("\t") or re.match(r"^ +\t", l):
                tab_indent.append((rel_n, i))
                break
        n_tw = sum(1 for l in lines if l != l.rstrip() and l.strip())
        if n_tw:
            trailing_ws.append((rel_n, n_tw))
        has_nonascii = any(ord(c) > 127 for c in src)
        headtxt = "\n".join(lines[:2])
        if has_nonascii and "coding" not in headtxt and "-*-" not in headtxt:
            no_encoding.append(rel_n)

        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                bare_except.append((rel_n, node.lineno))
            if isinstance(node, ast.Compare):
                for op, comp in zip(node.ops, node.comparators):
                    if isinstance(op, (ast.Eq, ast.NotEq)) and \
                            isinstance(comp, ast.Constant) and comp.value is None:
                        eq_none.append((rel_n, node.lineno,
                                        "== None" if isinstance(op, ast.Eq)
                                        else "!= None"))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in list(node.args.defaults) + list(node.args.kw_defaults):
                    if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                        mutable_default.append((rel_n, node.lineno, node.name))
        for i, l in enumerate(lines, 1):
            st = l.strip()
            if st.startswith("print(") and rel_n.startswith("app/core/engines"):
                broad_short.append((rel_n, i, st[:50]))
            if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", l):
                todo.append((rel_n, i, st[:60]))

    w("=" * 76)
    w("原作者代码格式检查（git 已跟踪的 %d 个 .py）" % len(files))
    w("=" * 76)
    w()
    w("【1】行长 > 100 字符（PEP8 上限 79，这里用宽松阈值）")
    if long_lines:
        long_lines.sort(key=lambda x: -x[1])
        for rel, n, mx in long_lines:
            w("   %-44s %4d 处，最长 %d" % (rel, n, mx))
    else:
        w("   无")
    w()
    w("【2】行长 > 79 字符（PEP8 标准）—— 仅列前 12 个文件")
    if long_lines_pct:
        long_lines_pct.sort(key=lambda x: -x[1])
        tot = sum(n for _, n, _ in long_lines_pct)
        w("   合计 %d 处，涉及 %d 个文件" % (tot, len(long_lines_pct)))
        for rel, n, ln in long_lines_pct[:12]:
            w("   %-44s %4d / %4d 行 (%.0f%%)" % (rel, n, ln, n * 100.0 / ln))
    else:
        w("   无")
    w()
    w("【3】制表符缩进（应为空格）")
    w("   %s" % ("；".join("%s:%d" % x for x in tab_indent) if tab_indent else "无"))
    w()
    w("【4】行尾空白")
    if trailing_ws:
        trailing_ws.sort(key=lambda x: -x[1])
        for rel, n in trailing_ws:
            w("   %-44s %4d 行" % (rel, n))
    else:
        w("   无")
    w()
    w("【5】缺少编码声明（文件含非 ASCII 但首两行无 coding）")
    w("   %s" % (("、".join(no_encoding)) if no_encoding else "无"))
    w()
    w("【6】裸 except（`except:` 不带异常类型）")
    for rel, ln in bare_except or []:
        w("   %s:%d" % (rel, ln))
    if not bare_except:
        w("   无")
    w()
    w("【7】`== None` / `!= None`（应写 is None / is not None）")
    for rel, ln, txt in eq_none or []:
        w("   %s:%d  %s" % (rel, ln, txt))
    if not eq_none:
        w("   无")
    w()
    w("【8】可变类型作默认参数（def f(x=[]) 之类）")
    for rel, ln, name in mutable_default or []:
        w("   %s:%d  函数 %s" % (rel, ln, name))
    if not mutable_default:
        w("   无")
    w()
    w("【9】引擎模块里的 print(（应为日志）")
    for rel, ln, txt in broad_short or []:
        w("   %s:%d  %s" % (rel, ln, txt))
    if not broad_short:
        w("   无")
    w()
    w("【10】TODO / FIXME / XXX / HACK 注释")
    for rel, ln, txt in todo or []:
        w("   %s:%d  %s" % (rel, ln, txt))
    if not todo:
        w("   无")
    w()

    # --------------------------------------- 改动 vs 原作者一致性
    diff_path = None
    log2 = None

    def w2(s=""):
        print(s)

    changed = _git(["diff", "--name-only"]).splitlines()
    w2("=" * 74)
    w2("我改动过的文件的风格一致性核对")
    w2("=" * 74)
    w2()
    n_changed = 0
    for rel in changed:
        if not rel.endswith(".py"):
            continue
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        src = open(p, encoding="utf-8", errors="replace").read()
        lines = src.splitlines()
        has_nonascii = any(ord(c) > 127 for c in src)
        headtxt = "\n".join(lines[:2])
        coding = "coding" in headtxt or "-*-" in headtxt
        diff = _git(["diff", "-U0", "--", rel])
        added = [ln[1:] for ln in diff.splitlines()
                 if ln.startswith("+") and not ln.startswith("+++")
                 and ln[1:].strip()]
        over79 = sum(1 for l in added if len(l) > 79)
        over100 = sum(1 for l in added if len(l) > 100)
        mx = max((len(l) for l in added), default=0)
        w2("%-44s" % rel)
        w2("   编码声明: %-4s (文件含中文: %s)"
           % ("有" if coding else "无", has_nonascii))
        w2("   我新增行: %d 行" % len(added))
        w2("   其中 >79: %d 行, >100: %d 行, 最长 %d" % (over79, over100, mx))
        try:
            orig = _git(["show", "HEAD:" + rel])
            orig_lines = [l for l in orig.splitlines() if l.strip()]
            o79 = sum(1 for l in orig_lines if len(l) > 79)
            w2("   原作者原版: %d 行, 其中 >79: %d 行 (%.0f%%)"
               % (len(orig_lines), o79,
                  o79 * 100.0 / max(len(orig_lines), 1)))
        except Exception as e:
            w2("   原作者原版: 读取失败 (%s)" % e)
        w2()
        n_changed += 1
    print()
    v.add("style", bool(no_encoding) or bool(long_lines),
          "风格核查完成：行长>100 %d 个文件、缺编码声明 %d 个、改动文件 %d 个"
          % (len(long_lines), len(no_encoding), n_changed))
