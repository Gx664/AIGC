# -*- coding: utf-8 -*-
"""引擎框架回归测试：不需要 torch / 不需要真的下载模型。

覆盖：
  1. 引擎清单完整性（9 项、三类、字段齐备）
  2. EngineManager 分类 / 本地覆盖 / 远端清单更新
  3. 注册表与插件自动发现
  4. 模型清单解析（条目声明即真相，换模型不改代码）
  5. 评测基准：样本导入、混淆矩阵指标、端到端跑通、Markdown 报告
  6. 修复类内置引擎可用

用法（任选一个 python）：
    python tools/test_engines.py
"""
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

PASS, FAIL = [], []


def case(fn):
    def wrapper():
        try:
            fn()
            PASS.append(fn.__name__)
            print("  [OK]   %s" % fn.__name__)
        except Exception as e:  # noqa: BLE001
            FAIL.append((fn.__name__, "%s: %s" % (type(e).__name__, e)))
            print("  [FAIL] %s -> %s: %s" % (fn.__name__, type(e).__name__, e))
            traceback.print_exc()

    wrapper.__name__ = fn.__name__
    return wrapper


def _tmp():
    return tempfile.mkdtemp(prefix="aigc_eng_")


# ---------------------------------------------------------------- 1. 清单
@case
def test_catalog_nine_engines():
    from core.engines import catalog

    engines = catalog.BUILTIN_ENGINES
    assert len(engines) == 9, "应有 9 个条目，实际 %d" % len(engines)
    ids = [e["id"] for e in engines]
    assert len(set(ids)) == 9, "id 有重复：%s" % ids
    for e in engines:
        for key in ("id", "name", "category", "impl", "desc"):
            assert e.get(key), "%s 缺字段 %s" % (e.get("id"), key)
        assert e["category"] in ("detect", "repair", "benchmark"), e["category"]
        assert isinstance(e.get("models", []), list)
    assert len(catalog.by_category("detect")) == 5
    assert len(catalog.by_category("repair")) == 2
    assert len(catalog.by_category("benchmark")) == 2


@case
def test_catalog_covers_nine_methods():
    """9 项学术方法都要在清单里有对应条目。"""
    from core.engines import catalog

    blob = " ".join(
        (e.get("name", "") + e.get("paper", "") + e.get("venue", "") + e.get("impl", ""))
        for e in catalog.BUILTIN_ENGINES
    ).lower()
    for needle in (
        "simpleai", "gltr", "fast-detectgpt", "detectgpt", "binoculars",
        "raid", "mgtbench", "aigc-reduce", "cnki",
    ):
        assert needle in blob, "清单里找不到 %s" % needle


# ------------------------------------------------------------- 2. manager
@case
def test_manager_categories():
    from core.engines import EngineManager

    tmp = _tmp()
    try:
        mgr = EngineManager(tmp)
        assert len(mgr.all()) == 9
        assert len(mgr.by_category("detect")) == 5
        assert len(mgr.by_category("repair")) == 2
        assert len(mgr.by_category("benchmark")) == 2
        # 检测流程只应看到检查类引擎
        names = [e["id"] for e in mgr.runnable()]
        assert sorted(names) == sorted(
            ["simpleai", "gltr", "fastdetectgpt", "detectgpt", "binoculars"]
        ), names
        assert mgr.get("binoculars")["category"] == "detect"
        assert mgr.is_builtin("gltr") is True
        assert mgr.is_custom("gltr") is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@case
def test_manager_local_override():
    """engines_catalog.json 能覆盖内置字段（用户不升级软件也能改名/换模型）。"""
    import json

    from core.engines import EngineManager

    tmp = _tmp()
    try:
        with open(os.path.join(tmp, "engines_catalog.json"), "w", encoding="utf-8") as f:
            json.dump([{"id": "gltr", "name": "我的 GLTR", "model_id": "gpt2-medium"}], f)
        mgr = EngineManager(tmp)
        e = mgr.get("gltr")
        assert e["name"] == "我的 GLTR", e["name"]
        assert e["model_id"] == "gpt2-medium"
        assert e["category"] == "detect", "覆盖时不应丢掉未声明的字段"
        assert len(mgr.all()) == 9
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@case
def test_manager_remote_manifest():
    """远端清单更新：新增条目落盘，重启后仍生效。"""
    import json

    from core.engines import EngineManager

    tmp = _tmp()
    try:
        manifest = os.path.join(tmp, "manifest.json")
        with open(manifest, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": "1",
                    "engines": [
                        {
                            "id": "future_detector",
                            "name": "未来新检测器",
                            "category": "detect",
                            "impl": "classifier",
                            "models": [{"repo": "someone/new-model", "size": "约 200MB"}],
                        }
                    ],
                },
                f,
            )
        mgr = EngineManager(tmp)
        url = "file:///" + manifest.replace("\\", "/").lstrip("/")
        ok, added = mgr.refresh_from_remote(url)
        assert ok is True, "拉取失败：%s" % added
        assert added == 1, added
        assert mgr.get("future_detector") is not None
        assert len(mgr.by_category("detect")) == 6
        # 重新打开（模拟重启）后依然在
        mgr2 = EngineManager(tmp)
        assert mgr2.get("future_detector")["name"] == "未来新检测器"

        ok2, info2 = mgr.refresh_from_remote("")
        assert ok2 is False and info2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------ 3. registry
@case
def test_registry_impls():
    from core.engines import registered

    impls = registered()
    for need in (
        "classifier", "perplexity", "curvature", "binoculars",
        "rule_rewrite", "cnki_diagnose",
    ):
        assert need in impls, "注册表里缺少 %s（现有：%s）" % (need, impls)


@case
def test_plugin_autoload():
    """往 engines_plugins/ 丢一个 py 就能扩展新算法，无需重新打包。"""
    from core.engines import EngineManager, get_impl

    tmp = _tmp()
    try:
        pdir = os.path.join(tmp, "engines_plugins")
        os.makedirs(pdir, exist_ok=True)
        with open(os.path.join(pdir, "demo_engine.py"), "w", encoding="utf-8") as f:
            f.write(
                "from core.engines.base import BaseEngine\n"
                "from core.engines.registry import register\n"
                "\n"
                "@register('demo_plugin_impl')\n"
                "class DemoEngine(BaseEngine):\n"
                "    MODELS = ()\n"
                "    needs_torch = False\n"
                "    def predict_paragraphs(self, paragraphs, device=None, progress_cb=None, **kw):\n"
                "        return [0.42] * len(paragraphs)\n"
            )
        EngineManager(tmp)  # 初始化时会自动加载插件目录
        cls = get_impl("demo_plugin_impl")
        assert cls is not None, "插件没有被自动发现"
        inst = cls({"id": "d"}, tmp)
        assert inst.predict_paragraphs(["a", "b"], "cpu") == [0.42, 0.42]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 4. repos
@case
def test_repos_resolution():
    """清单里的 models 说了算：换模型只改清单，不改引擎代码。"""
    from core.engines import catalog
    from core.engines.binoculars_engine import BinocularsEngine
    from core.engines.curvature_engine import CurvatureEngine
    from core.engines.rule_engine import RuleRewriteEngine
    from core.engines.simpleai_engine import SimpleAIEngine

    tmp = _tmp()
    try:
        cfg = catalog.by_id("detectgpt")
        repos = CurvatureEngine(cfg, tmp).repos()
        assert [r[0] for r in repos] == ["gpt2", "t5-base"], repos
        assert repos[0][1] == "causal" and repos[1][1] == "seq2seq", repos

        fast = CurvatureEngine(catalog.by_id("fastdetectgpt"), tmp).repos()
        assert fast[0][0] == "EleutherAI/gpt-neo-2.7B"

        bino = BinocularsEngine(catalog.by_id("binoculars"), tmp).repos()
        assert [r[0] for r in bino] == ["gpt2", "gpt2-medium"]

        cls = SimpleAIEngine(catalog.by_id("simpleai"), tmp).repos()
        assert cls[0][1] == "seq"

        # 不声明 models 时退回类内默认
        assert CurvatureEngine({"id": "x", "impl": "curvature"}, tmp).repos()[0][0] == "gpt2"
        # 规则引擎没有模型
        assert RuleRewriteEngine(catalog.by_id("aigc_reduce"), tmp).repos() == ()

        # 换模型的场景：清单里改成别的仓库，引擎立刻跟着走
        swapped = BinocularsEngine(
            {"id": "b", "impl": "binoculars",
             "models": [{"repo": "tiiuae/falcon-7b"}, {"repo": "tiiuae/falcon-7b-instruct"}]},
            tmp,
        )
        assert [r[0] for r in swapped.repos()] == ["tiiuae/falcon-7b", "tiiuae/falcon-7b-instruct"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@case
def test_engine_resources_and_state():
    from core.engines import catalog
    from core.engines.curvature_engine import CurvatureEngine

    tmp = _tmp()
    try:
        eng = CurvatureEngine(catalog.by_id("detectgpt"), tmp)
        res = eng.resources()
        assert len(res) == 2 and res[0]["role"]
        assert eng.is_installed() is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------ 5. benchmark
@case
def test_benchmark_metrics():
    from core import benchmark

    pairs = [(1, 0.9), (1, 0.6), (1, 0.2), (0, 0.4), (0, 0.8)]
    st = benchmark.evaluate(pairs, 0.5)
    assert st["tp"] == 2 and st["fn"] == 1 and st["fp"] == 1 and st["tn"] == 1, st
    assert abs(st["accuracy"] - 0.6) < 1e-6, st
    assert abs(st["fpr"] - 0.5) < 1e-6, st
    assert abs(st["fnr"] - 1 / 3) < 1e-4, st
    assert abs(st["f1"] - 2 / 3) < 1e-3, st


@case
def test_benchmark_import_csv_jsonl():
    import csv
    import json

    from core import benchmark

    tmp = _tmp()
    try:
        csv_path = os.path.join(tmp, "sub.csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["text", "label", "model"])
            w.writerow(["这是一段人类写的实验记录，细节很多。", "human", "human"])
            w.writerow(["综上所述，本文具有重要的理论意义和实践价值。", "ai", "gpt-4"])
            w.writerow(["", "", ""])
        samples, note = benchmark.load_samples(csv_path)
        assert len(samples) == 2, (len(samples), note)
        assert samples[1]["label"] == 1 and samples[0]["label"] == 0

        jl = os.path.join(tmp, "sub.jsonl")
        with open(jl, "w", encoding="utf-8") as f:
            for row in [
                {"generation": "人工写的段落，含具体数字 1372 份。", "model": "human",
                 "label": 0},
                {"generation": "首先，我们要认识到这一问题的重要性。", "model": "claude",
                 "label": 1},
            ]:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        samples2, _ = benchmark.load_samples(jl)
        assert len(samples2) == 2
        assert samples2[1]["model"] == "claude"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@case
def test_benchmark_end_to_end():
    """用 stub 引擎跑通 RAID 全流程，并产出 Markdown 报告。"""
    from core import benchmark

    class StubEngine:
        def predict_paragraphs(self, paragraphs, device, progress_cb=None, **kw):
            out = []
            for i, p in enumerate(paragraphs):
                # 简单启发式：AI 腔高频词命中就判高
                hit = any(k in p for k in ("综上所述", "首先", "此外", "Moreover", "In conclusion", "First,"))
                out.append(0.9 if hit else 0.1)
                if progress_cb:
                    progress_cb(i + 1, len(paragraphs))
            return out

    samples = benchmark.builtin_samples()
    assert len(samples) >= 12, len(samples)
    res = benchmark.run(samples, StubEngine(), device="cpu", threshold=0.5)
    assert res["n"] == len(samples)
    assert 0.0 <= res["accuracy"] <= 1.0
    assert res["by_model"], "缺少按模型分项"
    assert res["by_lang"], "缺少按语言分项"
    assert len(res["records"]) == len(samples)

    md = benchmark.to_markdown(res, "StubEngine", "RAID 评测基准", "测试样本")
    assert "假阳性率" in md and "逐条明细" in md
    assert "RAID 评测基准" in md


# --------------------------------------------------------------- 6. 修复类
@case
def test_repair_engines_work():
    from core.engines import catalog
    from core.engines.rule_engine import CnkiDiagnoseEngine, RuleRewriteEngine

    tmp = _tmp()
    try:
        para = "综上所述，随着信息技术的不断发展，教育信息化已成为重要力量。首先，它打破了时空限制；其次，它提升了效率。"
        rule = RuleRewriteEngine(catalog.by_id("aigc_reduce"), tmp)
        result = rule.rewrite([para])
        assert "summary" in result and "paragraphs" in result
        assert rule.audit("本文具有重要的理论意义。") is not None

        cnki = CnkiDiagnoseEngine(catalog.by_id("cnki_skill"), tmp)
        diag = cnki.diagnose([para], probs=[0.8], threshold=0.5)
        assert diag.get("paragraphs"), "诊断结果为空"
        assert cnki.scan([para])
        scores = cnki.predict_paragraphs([para])
        assert len(scores) == 1 and 0.0 <= scores[0] <= 1.0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("=" * 66)
    print("引擎框架回归测试（引擎清单 / 注册表 / 评测基准 / 修复引擎）")
    print("=" * 66)

    from core.engines import TORCH_ERROR, TORCH_OK

    print("torch 可用：%s %s" % (TORCH_OK, ("(%s)" % TORCH_ERROR) if TORCH_ERROR else ""))

    for fn in (
        test_catalog_nine_engines,
        test_catalog_covers_nine_methods,
        test_manager_categories,
        test_manager_local_override,
        test_manager_remote_manifest,
        test_registry_impls,
        test_plugin_autoload,
        test_repos_resolution,
        test_engine_resources_and_state,
        test_benchmark_metrics,
        test_benchmark_import_csv_jsonl,
        test_benchmark_end_to_end,
        test_repair_engines_work,
    ):
        fn()

    print("-" * 66)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    for name, err in FAIL:
        print("  FAIL %s -> %s" % (name, err))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

# aigc-toolkit: file purpose marker
