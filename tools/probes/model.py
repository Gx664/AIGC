# -*- coding: utf-8 -*-
"""模型类探针：transformers 兼容性、fp16 对照、2.7B 溢出实测。

来源（原 4 个脚本，逻辑一字未改）：
  probe_transformers_api_signature.py
  probe_transformers_real_call.py
  probe_dtype_fp16_vs_fp32.py
  probe_vram_spill_2p7b.py

**副作用**：加载模型、占显存；vram_spill 极慢（2.7B 模型）。
"""
import os

from . import ROOT, head

OUT_PATH = os.path.join(os.environ.get("TEMP", "."), "dtype_probe_out.txt")
SPILL_OUT = os.path.join(os.environ.get("TEMP", "."), "spill_probe_out.txt")


def _emit_factory(path):
    """同时打印与写文件（控制台编码不可靠，读文件更稳）。"""
    f = None
    try:
        f = open(path, "w", encoding="utf-8")
    except Exception:
        pass

    def emit(s=""):
        print(s)
        if f:
            f.write(str(s) + "\n")
            f.flush()
    return emit


def run_api_signature(v):
    """transformers API 存在性（inspect.signature，**有误报**）。"""
    import inspect

    import transformers

    head("4.1", "transformers API 存在性（inspect，注意有误报）")
    print("transformers %s" % transformers.__version__)
    print()
    print("!! 本探针用 inspect.signature 检查形参，对 from_pretrained(**kwargs)")
    print("!! 这类签名看不到真实形参，**会误报不支持**。")
    print("!! 判断兼容性请以 xformers_call（真调用）为准。")
    print()

    checks = [
        ("AutoModelForCausalLM.from_pretrained",
         transformers.AutoModelForCausalLM.from_pretrained,
         ("cache_dir", "local_files_only", "torch_dtype", "dtype")),
        ("AutoTokenizer.from_pretrained",
         transformers.AutoTokenizer.from_pretrained,
         ("cache_dir", "local_files_only")),
    ]
    for label, fn, kws in checks:
        try:
            sig = inspect.signature(fn)
            params = set(sig.parameters)
        except Exception as e:
            print("   %s: 取签名失败 %s" % (label, e))
            continue
        has_var_kw = any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
        print("   %s" % label)
        for kw in kws:
            mark = "有" if kw in params else ("kwargs 兜底" if has_var_kw else "无")
            print("      %-18s : %s" % (kw, mark))
    print()
    v.add("4.1", False, "inspect 结果不可信，见同组 xformers_call")


def run_real_call(v):
    """真调用验证（不下载任何文件）—— 排除上一条的误报。"""
    import transformers

    head("4.1b", "真调用验证（不下载任何文件）")
    print("transformers %s" % transformers.__version__)
    print()

    print("A) from_pretrained(**kwargs) 签名 —— 用 help 文本核对真实形参")
    doc = transformers.AutoModelForCausalLM.from_pretrained.__doc__ or ""
    for kw in ("cache_dir", "local_files_only", "torch_dtype", "dtype", "device_map"):
        print("      文档提及 %-18s : %s" % (kw, kw in doc))
    print()

    print("B) 真调用：故意传不存在的仓库名 + 不存在的参数，看报什么错")
    print("   若参数不被接受 -> TypeError/ValueError('unexpected keyword')")
    print("   若参数被接受 -> 报仓库不存在/网络错误")
    print()

    cases = [
        ("cache_dir + local_files_only（base.py:106 的写法）",
         dict(cache_dir=os.path.join(ROOT, "app", "models", "probe"),
              local_files_only=True)),
        ("torch_dtype（老写法）", dict(torch_dtype="auto", local_files_only=True)),
        ("dtype（新写法）", dict(dtype="auto", local_files_only=True)),
    ]
    ok_params = []
    for label, kw in cases:
        kw = dict(kw)
        try:
            transformers.AutoModelForCausalLM.from_pretrained(
                "___definitely_not_a_real_repo___", **kw)
            print("   UNEXPECTED OK   %s" % label)
        except TypeError as e:
            print("   TypeError   %s -> %s" % (label, e))
        except Exception as e:
            msg = str(e)[:110].replace("\n", " ")
            print("   已接受参数  %s -> %s: %s" % (label, type(e).__name__, msg))
            ok_params.append(label)
    print()

    print("C) AutoTokenizer 同样测试")
    try:
        transformers.AutoTokenizer.from_pretrained(
            "___definitely_not_a_real_repo___",
            cache_dir=os.path.join(ROOT, "app", "models", "probe"),
            local_files_only=True)
    except TypeError as e:
        print("   TypeError -> %s" % e)
    except Exception as e:
        print("   已接受参数 -> %s: %s"
              % (type(e).__name__, str(e)[:110].replace("\n", " ")))
    print()

    print("D) generate 关键字：用 generate 的 docstring 与 GenerationConfig 核对")
    gdoc = transformers.GenerationMixin.generate.__doc__ or ""
    for kw in ("do_sample", "top_p", "temperature", "max_new_tokens", "pad_token_id"):
        print("      generate 文档提及 %-16s : %s" % (kw, kw in gdoc))
    try:
        from transformers import GenerationConfig

        gc = GenerationConfig()
        have = gc.to_dict()
        print()
        print("      GenerationConfig 实际字段:")
        for kw in ("do_sample", "top_p", "temperature", "max_new_tokens",
                   "pad_token_id", "top_k", "num_beams"):
            print("         %-16s = %r" % (kw, have.get(kw, "<缺失>")))
    except Exception as e:
        print("      GenerationConfig 探测失败: %s" % e)
    print()

    print("E) 用极小本地模型真跑 generate（不联网，纯随机权重）")
    import torch
    from transformers import GPT2Config, GPT2LMHeadModel

    cfg = GPT2Config(vocab_size=99, n_positions=64, n_embd=32,
                     n_layer=1, n_head=1)
    m = GPT2LMHeadModel(cfg)
    try:
        ids = torch.randint(1, 90, (1, 8))
        out = m.generate(ids, do_sample=True, top_p=0.96, temperature=1.0,
                         max_new_tokens=4, pad_token_id=0)
        print("   OK  generate(do_sample/top_p/temperature/max_new_tokens/pad_token_id)")
        print("       输出形状 = %r" % (tuple(out.shape),))
    except TypeError as e:
        print("   FAIL TypeError -> %s" % e)
    except Exception as e:
        print("   FAIL %s: %s" % (type(e).__name__, str(e)[:160]))
    print()

    class TokStub:
        def __call__(self, text, return_tensors="pt", truncation=False, **kw):
            class E:
                pass

            e = E()
            e.input_ids = torch.randint(1, 90, (1, 12))
            return e

    print("F) 用极小本地模型真跑 base.avg_logprob（不联网）")
    from core.engines.base import BaseEngine

    class Probe(BaseEngine):
        impl = "probe"
        needs_torch = False

        def predict_paragraphs(self, *a, **k):
            return []

    try:
        p = Probe({"id": "probe"}, os.path.join(ROOT, "app"))
        lp = p.avg_logprob("hello world test", m, TokStub(), "cpu", chunk=4)
        print("   OK  avg_logprob = %.6f（真跑通，chunk=4 分块）" % lp)
        lp2 = p.avg_logprob("hello world test", m, TokStub(), "cpu", chunk=256)
        print("   OK  avg_logprob = %.6f（chunk=256 单块）" % lp2)
    except Exception as e:
        print("   FAIL %s: %s" % (type(e).__name__, str(e)[:200]))
    print()

    print("G) 用极小本地模型真跑 Binoculars 打分链路")
    try:
        from core.engines.binoculars_engine import BinocularsEngine

        class BinoProbe(BinocularsEngine):
            def _get(self, repo, kind, device=None, **kw):
                if kind == "tokenizer":
                    return TokStub()
                return m

        bp = BinoProbe({"id": "probe_bino", "impl": "binoculars"},
                       os.path.join(ROOT, "app"))
        probs = bp.predict_paragraphs(["这是一段测试文本，用于验证公式。"], "cpu")
        print("   OK  Binoculars predict_paragraphs -> %r" % probs)
        print("       （随机权重模型，概率无意义，只看能否跑通）")
    except Exception as e:
        import traceback

        print("   FAIL %s: %s" % (type(e).__name__, str(e)[:200]))
        traceback.print_exc(limit=2)

    v.add("4.1b", len(ok_params) >= 2,
          "%d/%d 个参数写法被真调用接受（未报 TypeError）"
          % (len(ok_params), len(cases)))


# ------------------------------------------------------- fp16 对照
def run_dtype_compare(v):
    """fp16 vs fp32：同一批文本、同一引擎、只改权重精度。

    结论（2026-09-23）：fp16 不影响判定 —— Kendall 排序一致率 1.0000（190/190）。
    详见 docs/FIXES.md §1。
    """
    import json

    import torch

    emit = _emit_factory(OUT_PATH)

    emit("=" * 68)
    emit("半精度对照探针：fp16 vs fp32（只读项目源码，不写项目内文件）")
    emit("=" * 68)
    emit("torch %s  |  cuda available = %s"
         % (torch.__version__, torch.cuda.is_available()))
    if not torch.cuda.is_available():
        emit("无 CUDA，退出（fp16 对照需要 GPU）。")
        v.add("dtype", False, "无 CUDA，未测")
        return
    DEVICE = "cuda:0"
    free, total = torch.cuda.mem_get_info(0)
    emit("显存: free=%.2fGB / total=%.2fGB"
         % (free / 1024 ** 3, total / 1024 ** 3))

    from core.engines import catalog, create_engine

    cfg = catalog.by_id("gltr")
    eng = create_engine(cfg, ROOT)
    params = dict(cfg.get("params") or {})
    emit("引擎: gltr  params=%s" % params)

    def load_jsonl(path, n, lang):
        half = n // 2
        ai, hu = [], []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                text = (row.get("text") or "").strip()
                if len(text) < 20:
                    continue
                label = str(row.get("label", "")).strip()
                if label == "1" and len(ai) < half:
                    ai.append(text)
                elif label == "0" and len(hu) < half:
                    hu.append(text)
                if len(ai) >= half and len(hu) >= half:
                    break
        emit("  载入 %s: AI %d / 人写 %d" % (lang, len(ai), len(hu)))
        return [(t, 1) for t in ai] + [(t, 0) for t in hu]

    def run_once(texts, dtype):
        orig_load = eng._load

        def patched(repo, kind, dev, **kw):
            if kind != "tokenizer":
                kw["torch_dtype"] = dtype
            return orig_load(repo, kind, dev, **kw)

        eng._cache.clear()
        eng._load = patched
        try:
            out = eng.predict_paragraphs(texts, DEVICE, **dict(params))
        finally:
            eng._load = orig_load
            eng._cache.clear()
            torch.cuda.empty_cache()
        return out

    def ranks(x):
        order = sorted(range(len(x)), key=lambda i: x[i])
        r = [0] * len(x)
        for pos, idx in enumerate(order):
            r[idx] = pos
        return r

    def best_threshold(probs, labels):
        best_t, best_acc = 0.5, -1.0
        for t in sorted(set(probs)):
            acc = sum(1 for p, y in zip(probs, labels)
                      if (p >= t) == (y == 1)) / len(probs)
            if acc > best_acc:
                best_acc, best_t = acc, t
        return best_t

    def score_at(probs, labels, t):
        tp = sum(1 for p, y in zip(probs, labels) if p >= t and y == 1)
        fp = sum(1 for p, y in zip(probs, labels) if p >= t and y == 0)
        tn = sum(1 for p, y in zip(probs, labels) if p < t and y == 0)
        fn = sum(1 for p, y in zip(probs, labels) if p < t and y == 1)
        n = len(probs)
        return ((tp + tn) / n if n else 0.0,
                fp / (fp + tn) if (fp + tn) else 0.0)

    summary = []
    for lang, path in (("中文 HC3", r"D:\hf_cache\hc3_zh_1to1.jsonl"),
                       ("英文 Ghostbuster",
                        r"D:\hf_cache\ghost_essay_1to1.jsonl")):
        if not os.path.isfile(path):
            emit("\n跳过 %s：%s 不存在" % (lang, path))
            continue
        emit("\n" + "#" * 68)
        emit("# %s  n=20" % lang)
        emit("#" * 68)
        rows = load_jsonl(path, 20, lang)
        texts = [r[0] for r in rows]
        labels = [r[1] for r in rows]

        emit("\n[fp32] 运行中...")
        p32 = run_once(texts, torch.float32)
        emit("[fp16] 运行中...")
        p16 = run_once(texts, torch.float16)

        emit("\n  逐条对比 (fp32 / fp16 / 差):")
        for a, b, y in zip(p32, p16, labels):
            emit("    %-4s %8.4f %8.4f  %+.6f"
                 % ("AI" if y == 1 else "人写", a, b, b - a))
        summary.append((lang, p32, p16, labels))

    v.add("dtype", _finish_dtype(emit, summary), "见输出文件 %s" % OUT_PATH)


def _finish_dtype(emit, summary):
    """把对照结果算出汇总指标。"""
    rows = []
    for lang, p32, p16, labels in summary:
        n = len(p32)
        diffs = [abs(a - b) for a, b in zip(p32, p16)]
        med = sorted(diffs)[n // 2]
        order32 = sorted(range(n), key=lambda i: p32[i])
        order16 = sorted(range(n), key=lambda i: p16[i])
        r32 = [0] * n
        r16 = [0] * n
        for pos, idx in enumerate(order32):
            r32[idx] = pos
        for pos, idx in enumerate(order16):
            r16[idx] = pos
        conc = tot = 0
        for i in range(n):
            for j in range(i + 1, n):
                tot += 1
                if (r32[i] - r32[j]) * (r16[i] - r16[j]) > 0:
                    conc += 1
        kendall = conc / tot if tot else 1.0
        rows.append((lang, max(diffs), med, kendall))

    emit("\n" + "=" * 68)
    emit("汇总")
    emit("=" * 68)
    for lang, mx, med, ken in rows:
        emit("%-18s 分数差 max=%.6f 中位=%.6f | Kendall 排序一致率=%.4f"
             % (lang, mx, med, ken))
    emit("")
    emit("判读: Kendall 接近 1.0 -> fp16 未改变排序，判定结论不受影响")
    emit("输出文件: %s" % OUT_PATH)
    return bool(rows) and all(r[3] >= 0.999 for r in rows)


# -------------------------------------------------- 2.7B 显存溢出实测
def _vram_snapshot():
    """读一次显存三件套（不依赖 torch 之外的东西，随时可调）。

    注意 nvidia-smi **看不到共享显存**，必须走 Win32 性能计数器。
    """
    import subprocess

    snap = {}
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=memory.used,temperature.gpu,power.draw,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            creationflags=0x08000000,
        ).stdout.strip()
        p = [x.strip() for x in out.split(",")]
        snap["dedicated_mb"] = float(p[0])
        snap["temp"] = float(p[1])
        snap["power"] = float(p[2])
        snap["util"] = float(p[3])
    except Exception:
        for k in ("dedicated_mb", "temp", "power", "util"):
            snap[k] = float("nan")

    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_"
             "GPUAdapterMemory | Measure-Object -Property SharedUsage -Sum).Sum"],
            capture_output=True, text=True, timeout=20,
            creationflags=0x08000000,
        ).stdout.strip()
        snap["shared_mb"] = float(out) / 1024.0 / 1024.0 if out else float("nan")
    except Exception:
        snap["shared_mb"] = float("nan")

    try:
        import torch

        if torch.cuda.is_available():
            snap["torch_reserved_gb"] = torch.cuda.memory_reserved(0) / 1024 ** 3
        else:
            snap["torch_reserved_gb"] = float("nan")
    except Exception:
        snap["torch_reserved_gb"] = float("nan")
    return snap


def run_vram_spill(v):
    """gpt-neo-2.7B 溢出实测：fp32 / fp16 都真跑，跑时每秒采样共享显存。

    结论（2026-09-23）：fp32 溢出（共享显存 +2163 MB），fp16 不溢出（+27 MB）。
    但 fp16 在显存余量仅 3GB 时仍被拖慢 10 倍（温度 32℃、功耗 129W）。
    详见 docs/FIXES.md §5。
    """
    import json
    import threading
    import time

    import torch

    emit = _emit_factory(SPILL_OUT)
    n_lines = int(os.environ.get("PROBE_N", "5"))

    emit("=" * 68)
    emit("gpt-neo-2.7B 溢出实测（fp32 / fp16 都跑，全程采样共享显存）")
    emit("=" * 68)
    emit("torch %s   cuda=%s" % (torch.__version__, torch.cuda.is_available()))
    if not torch.cuda.is_available():
        emit("无 CUDA，退出")
        v.add("vram", False, "无 CUDA，未测")
        return
    free, total = torch.cuda.mem_get_info(0)
    emit("显存 free=%.2fGB / total=%.2fGB"
         % (free / 1024 ** 3, total / 1024 ** 3))
    b0 = _vram_snapshot()
    emit("开跑前全局: 专用 %.0f MB  共享 %.0f MB"
         % (b0["dedicated_mb"], b0["shared_mb"]))
    if b0["dedicated_mb"] > 3000:
        emit("  ！注意: 已有 %.1f GB 专用显存被其他进程占用，"
             "本测试结论需扣除此背景" % (b0["dedicated_mb"] / 1024.0))

    # 样本
    half = max(1, n_lines // 2)
    ai, hu = [], []
    with open(r"D:\hf_cache\hc3_zh_1to1.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            t = (row.get("text") or "").strip()
            if len(t) < 20:
                continue
            lb = str(row.get("label", "")).strip()
            if lb == "1" and len(ai) < half:
                ai.append(t)
            elif lb == "0" and len(hu) < half:
                hu.append(t)
            if len(ai) >= half and len(hu) >= half:
                break
    texts = ai + hu
    emit("样本: %d 条（HC3 中文）" % len(texts))

    from core.engines import catalog, create_engine

    params = dict(catalog.by_id("fastdetectgpt").get("params") or {})
    emit("参数: %s" % params)

    class Sampler(object):
        def __init__(self, interval=1.0):
            self.interval = interval
            self.series = []
            self._stop = threading.Event()
            self._th = None

        def start(self):
            self._stop.clear()
            self._th = threading.Thread(target=self._loop)
            self._th.daemon = True
            self._th.start()

        def _loop(self):
            while not self._stop.is_set():
                s = _vram_snapshot()
                s["t"] = time.time()
                self.series.append(s)
                self._stop.wait(self.interval)

        def stop(self):
            self._stop.set()
            if self._th:
                self._th.join(timeout=5)

        def summary(self):
            def col(k):
                return [s[k] for s in self.series if s.get(k) == s.get(k)]
            out = {"n": len(self.series)}
            for k in ("dedicated_mb", "shared_mb", "temp", "power"):
                v_list = col(k)
                out[k + "_max"] = max(v_list) if v_list else float("nan")
                out[k + "_avg"] = (sum(v_list) / len(v_list) if v_list
                                   else float("nan"))
            return out

    results = []
    for dtype_name, dtype in (("fp16", torch.float16),
                              ("fp32", torch.float32)):
        emit("\n" + "#" * 68)
        emit("# %s   （gpt-neo-2.7B，目标 %d 条）" % (dtype_name, n_lines))
        emit("#" * 68)

        base = _vram_snapshot()
        emit("\n  [跑前基线] 专用 %.0f MB  共享 %.0f MB  温度 %.0fC  功耗 %.0fW"
             % (base["dedicated_mb"], base["shared_mb"],
                base["temp"], base["power"]))

        cfg = catalog.by_id("fastdetectgpt")
        eng = create_engine(cfg, ROOT)
        orig_load = eng._load

        def patched(repo, kind, dev, **kw):
            if kind != "tokenizer":
                kw["torch_dtype"] = dtype
            return orig_load(repo, kind, dev, **kw)

        eng._load = patched
        sampler = Sampler(interval=1.0)
        sampler.start()

        try:
            t0 = time.time()
            model = eng.mdl(0, "cuda:0")
            t_load = time.time() - t0
            dtype_real = str(next(model.parameters()).dtype)
        except Exception as e:
            sampler.stop()
            eng._load = orig_load
            emit("\n  >>> 加载失败: %s: %s" % (type(e).__name__, e))
            results.append((dtype_name, None, e))
            continue

        a = _vram_snapshot()
        emit("\n  加载 %.1f 秒，实际 dtype = %s" % (t_load, dtype_real))
        emit("  加载后: 专用 %.0f MB  共享 %.0f MB  torch保留 %.2f GB"
             % (a["dedicated_mb"], a["shared_mb"], a["torch_reserved_gb"]))

        emit("\n  --- 单条耗时（%d 条，取中位并剔除首条预热）---" % min(
            n_lines, len(texts)))
        times = []
        for i in range(min(n_lines, len(texts))):
            t0 = time.time()
            r = eng.predict_paragraphs([texts[i]], "cuda:0", **params)
            dt = time.time() - t0
            times.append(dt)
            emit("    第 %d 条: %7.1f 秒  -> %.6f" % (i + 1, dt, r[0]))
        warm = times[1:] if len(times) > 1 else times
        med = sorted(warm)[len(warm) // 2]
        emit("    **中位 = %.1f 秒**  ->  外推 200 条 = %.1f 分钟"
             % (med, med * 200 / 60.0))

        sampler.stop()
        s = sampler.summary()
        emit("\n  === %s 总结 ===" % dtype_name)
        emit("    采样点 %d 个" % s.get("n", 0))
        emit("    专用显存  max %.0f MB   avg %.0f MB"
             % (s.get("dedicated_mb_max", 0), s.get("dedicated_mb_avg", 0)))
        emit("    共享显存  max %.0f MB   avg %.0f MB   <- 溢出证据"
             % (s.get("shared_mb_max", 0), s.get("shared_mb_avg", 0)))
        emit("    温度 avg %.0f C  |  功耗 avg %.0f W"
             % (s.get("temp_avg", 0), s.get("power_avg", 0)))

        spill = s.get("shared_mb_max", 0) - base["shared_mb"]
        if spill > 128:
            emit("\n    >>> 判定: **溢出 %d MB**（共享峰值 %.0f，基线 %.0f）"
                 % (int(spill), s.get("shared_mb_max", 0), base["shared_mb"]))
        else:
            emit("\n    >>> 判定: 未溢出（共享峰值增量 %d MB）" % int(spill))
        results.append((dtype_name, {"load_s": t_load, "median_s": med,
                                     "spill_mb": spill,
                                     "shared_max": s.get("shared_mb_max", 0),
                                     "temp_avg": s.get("temp_avg", 0),
                                     "power_avg": s.get("power_avg", 0)}, None))

        eng._load = orig_load
        eng._cache.clear()
        del model, eng
        try:
            import gc

            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass
        time.sleep(3)

    emit("\n" + "=" * 68)
    emit("汇总")
    emit("=" * 68)
    emit("%-6s %10s %11s %12s %10s" %
         ("精度", "加载s", "单条中位s", "外推200条", "共享峰值MB"))
    for name, res, err in results:
        if err or not res:
            emit("%-6s 失败: %s" % (name, err))
            continue
        emit("%-6s %10.1f %11.1f %9.1f分 %10.0f" %
             (name, res["load_s"], res["median_s"],
              res["median_s"] * 200 / 60.0, res["shared_max"]))
    emit("")
    emit("判定溢出看「共享峰值MB」：明显高于跑前基线 = 溢出到内存")
    emit("输出文件: %s" % SPILL_OUT)

    ok = any(r and r["spill_mb"] > 128 for _, r, _ in results if r)
    v.add("vram", ok, "溢出情况: %s"
          % ", ".join("%s %+.0fMB" % (n, r["spill_mb"])
                      for n, r, _ in results if r) if results else "未测")
