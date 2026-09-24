# -*- coding: utf-8 -*-
"""RAID / MGTBench 评测基准：用带标注的真实样本给检测器做体检。

为什么要这个模块
----------------
检测器"看着准"和"实测准"是两回事。这里把带标注的样本喂给当前选中的引擎，
输出 RAID / MGTBench 的核心指标：

* 准确率 accuracy
* **假阳性率 FPR** —— 把人类写的判成 AI 的比例（对写论文的人最要命的指标）
* 假阴性率 FNR —— 把 AI 写的放过
* 精确率 / 召回率 / F1
* 按生成模型分项的检出率（RAID 的做法），以及 human 行的误报率

样本从哪来
----------
1. ``builtin``：内置一小批中英对照样本，开箱即可跑一次「快速体检」；
2. ``file``：导入官方数据集的子集（CSV / JSONL 均可，自动识别列名）。
   官方数据（公开、需自行下载后导入）：
   RAID     https://github.com/liamdugan/raid
   MGTBench https://github.com/xinleihe/MGTBench

内置样本是作者手写的快速自检集，**不是**官方基准的成绩，
所以报告里会显式标注这一点 —— 要看真实水平请导入官方数据。
"""
import csv
import json
import os

# --------------------------------------------------------------------------
# 内置快速体检样本：label 1 = AI 生成，0 = 人类写作
# --------------------------------------------------------------------------
BUILTIN_SAMPLES = [
    # ---- 人类写作（学术 / 实验记录口吻，具体、不规整）----
    {
        "text": "我在 2023 年 3 月到 6 月跑了 14 所乡镇中学的问卷，回收 1372 份，"
        "剔除填答时间不足 4 分钟的 61 份，有效样本 1311 份。有个班只交了 9 份，"
        "当时以为卷子印少了，后来发现是班主任把卷子扣了，想让学生先做模拟卷。",
        "label": 0, "model": "human", "source": "builtin", "lang": "zh",
    },
    {
        "text": "第三组的数据一直对不上，查了两周才发现是恒温箱的门封条老化，"
        "下午温度会比设定值高 1.8 度左右。重做了 11 个样本以后曲线才正常，"
        "但这批数据和前两批已经不能直接合并了，只能单独报。",
        "label": 0, "model": "human", "source": "builtin", "lang": "zh",
    },
    {
        "text": "我们原本想用回归，做完残差图发现异方差挺明显，就换成稳健标准误。"
        "系数的方向和预期一致，但显著性掉了不少，特别是第二个变量，p 值从 0.03 变成 0.11。"
        "导师说这反而更可信，不然要怀疑是不是把控制变量加错了。",
        "label": 0, "model": "human", "source": "builtin", "lang": "zh",
    },
    {
        "text": "访谈一共做了 17 个人，到第 12 个的时候基本不再出现新说法了。"
        "有个受访者中途接了个电话，回来以后明显换了口吻，那一段我没用。"
        "编码是两个人分别做的，不一致的地方吵了两次，最后按第三个人裁决。",
        "label": 0, "model": "human", "source": "builtin", "lang": "zh",
    },
    {
        "text": "写这章的时候我把 2018 年那版全删了。那版啰嗦，而且有几处引用是转引的，"
        "原作者其实没说过那个话。这次所有引文都回到原文核对过一遍，"
        "有一篇是俄语的，拜托了隔壁实验室的同学帮忙看的。",
        "label": 0, "model": "human", "source": "builtin", "lang": "zh",
    },
    {
        "text": "Between 2019 and 2021 we ran the trials at three sites, and two of them failed. "
        "The first was a wiring error on our side; the second we never fully explained. "
        "What survived was the third site: 412 usable readings, after dropping the ones "
        "logged during the storm on the 14th, when the recorder kept resetting itself.",
        "label": 0, "model": "human", "source": "builtin", "lang": "en",
    },
    {
        "text": "The reviewer asked for a robustness check, so I reran everything with the "
        "outliers trimmed at 2 SD instead of 3. The main effect holds, but the interaction "
        "term loses about a third of its size. I have put both versions in the appendix "
        "rather than pretending only one of them exists.",
        "label": 0, "model": "human", "source": "builtin", "lang": "en",
    },
    {
        "text": "My supervisor hated the second chapter and I think she was right. "
        "It took four rewrites before the argument actually lined up with the evidence. "
        "The version in the appendix is the one I submitted first, kept mainly so I can "
        "see how badly I was overreaching.",
        "label": 0, "model": "human", "source": "builtin", "lang": "en",
    },
    # ---- AI 生成（典型 AI 腔：对举、排比、总分总）----
    {
        "text": "随着信息技术的不断发展，教育信息化已成为推动教育现代化的重要力量。"
        "首先，它打破了时空限制，使优质教育资源得以广泛共享；其次，它促进了教学方式的深刻变革，"
        "显著提升了课堂互动效率；此外，它还为学生的个性化学习提供了有力支撑。"
        "综上所述，教育信息化对教育质量的提升具有不可忽视的重要意义。",
        "label": 1, "model": "gpt-4", "source": "builtin", "lang": "zh",
    },
    {
        "text": "数字化转型不仅是技术的升级，更是管理理念的深刻变革。企业需要从战略层面统筹规划，"
        "从组织层面协同推进，从执行层面持续优化。值得注意的是，转型的关键不在于工具本身，"
        "而在于人。只有将技术能力与业务场景深度融合，才能真正释放数字化的价值。",
        "label": 1, "model": "gpt-4", "source": "builtin", "lang": "zh",
    },
    {
        "text": "本研究从三个维度构建了评价指标体系。第一，在投入维度，考察资源要素的配置效率；"
        "第二，在过程维度，关注运行机制的协同程度；第三，在产出维度，衡量服务供给的实际效果。"
        "该框架既兼顾了系统性，又体现了可操作性，为后续实证研究奠定了坚实基础。",
        "label": 1, "model": "claude", "source": "builtin", "lang": "zh",
    },
    {
        "text": "人工智能正在深刻改变我们的生活方式与工作模式，其影响广泛而深远。"
        "一方面，它能够高效处理海量数据，帮助人们从重复劳动中解放出来；"
        "另一方面，它也带来了隐私保护、算法偏见等一系列亟待解决的伦理挑战。"
        "因此，如何在创新与规范之间取得平衡，成为当前亟待回答的重要课题。",
        "label": 1, "model": "gpt-3.5", "source": "builtin", "lang": "zh",
    },
    {
        "text": "Artificial intelligence has emerged as a transformative force across numerous "
        "industries. It enables organizations to automate routine tasks, uncover patterns "
        "in large datasets, and deliver more personalized experiences to their customers. "
        "Moreover, it continues to evolve rapidly, creating both opportunities and challenges "
        "for stakeholders. In conclusion, its impact is profound and multifaceted.",
        "label": 1, "model": "gpt-4", "source": "builtin", "lang": "en",
    },
    {
        "text": "The study of urban mobility requires a comprehensive framework that accounts "
        "for multiple interacting factors. First, it must consider the physical infrastructure. "
        "Second, it must incorporate behavioural patterns. Third, it must address policy "
        "instruments. By integrating these dimensions, researchers can develop a more nuanced "
        "understanding of how cities function.",
        "label": 1, "model": "claude", "source": "builtin", "lang": "en",
    },
    {
        "text": "Climate change represents one of the most pressing challenges of our time. "
        "It affects ecosystems, economies, and communities in ways that are both complex and "
        "far-reaching. Addressing it requires coordinated action at local, national, and "
        "international levels. Only through sustained collective effort can we hope to build "
        "a more sustainable and resilient future for generations to come.",
        "label": 1, "model": "gpt-3.5", "source": "builtin", "lang": "en",
    },
]

# 导入外部数据集时用于识别列的候选名（小写）
_TEXT_KEYS = ("text", "generation", "content", "response", "document", "para", "paragraph")
_LABEL_KEYS = ("label", "is_ai", "ground_truth", "y", "target", "ai", "generated", "machine")
_MODEL_KEYS = ("model", "generator", "source", "llm", "attacker", "source_id")


def builtin_samples():
    return [dict(s) for s in BUILTIN_SAMPLES]


# --------------------------------------------------------------------------
# 样本导入
# --------------------------------------------------------------------------
def _pick(row, keys, default=None):
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for k in keys:
        if k in lower and str(lower[k]).strip() != "":
            return lower[k]
    return default


def _coerce_label(value):
    """把各种写法的标签统一成 1（AI）/ 0（人类）。"""
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("1", "1.0", "true", "ai", "machine", "generated", "gpt", "chatgpt", "yes"):
        return 1
    if s in ("0", "0.0", "false", "human", "real", "human-written", "no"):
        return 0
    try:
        return 1 if float(s) >= 0.5 else 0
    except Exception:  # noqa: BLE001
        return None


def load_samples(path, max_samples=200, text_key=None, label_key=None, model_key=None):
    """从 CSV / JSONL / JSON 导入样本；返回 (samples, 说明)。"""
    if not path or not os.path.exists(path):
        return [], "文件不存在"
    ext = os.path.splitext(path)[1].lower()
    rows = []
    try:
        if ext in (".jsonl", ".ndjson"):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            obj = json.loads(line)
                            if isinstance(obj, dict):
                                rows.append(obj)
                        except Exception:  # noqa: BLE001
                            continue
        elif ext == ".json":
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            rows = data if isinstance(data, list) else data.get("data") or data.get("samples") or []
            rows = [r for r in rows if isinstance(r, dict)]
        else:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
                rows = [dict(r) for r in csv.DictReader(f)]
    except Exception as e:  # noqa: BLE001
        return [], "读取失败：%s" % e

    if not rows:
        return [], "文件里没有可用记录"

    tkeys = ((text_key,) if text_key else ()) + _TEXT_KEYS
    lkeys = ((label_key,) if label_key else ()) + _LABEL_KEYS
    mkeys = ((model_key,) if model_key else ()) + _MODEL_KEYS

    samples, skipped = [], 0
    for r in rows:
        text = _pick(r, tkeys)
        label = _coerce_label(_pick(r, lkeys))
        if not text or label is None:
            skipped += 1
            continue
        text = str(text).strip()
        if len(text) < 12:
            skipped += 1
            continue
        samples.append(
            {
                "text": text,
                "label": label,
                "model": str(_pick(r, mkeys, "unknown") or "unknown"),
                "source": os.path.basename(path),
                "lang": "zh" if any("\u4e00" <= c <= "\u9fff" for c in text[:40]) else "en",
            }
        )
        if len(samples) >= max_samples:
            break
    note = "导入 %d 条（跳过 %d 条）" % (len(samples), skipped)
    return samples, note


# --------------------------------------------------------------------------
# 指标
# --------------------------------------------------------------------------
def evaluate(pairs, threshold=0.5):
    """pairs: [(label, prob)] —— 返回混淆矩阵与常用指标。"""
    tp = fp = tn = fn = 0
    for label, prob in pairs:
        pred = 1 if (prob is not None and prob >= threshold) else 0
        if label == 1:
            if pred == 1:
                tp += 1
            else:
                fn += 1
        else:
            if pred == 1:
                fp += 1
            else:
                tn += 1
    n = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "n": n,
        "threshold": threshold,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "accuracy": round((tp + tn) / n, 4) if n else 0.0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        # 假阳性率：把人类写的冤枉成 AI 的比例（越低越好）
        "fpr": round(fp / (fp + tn), 4) if (fp + tn) else 0.0,
        # 假阴性率：把 AI 写的放过
        "fnr": round(fn / (fn + tp), 4) if (fn + tp) else 0.0,
    }


def evaluate_grouped(records, threshold=0.5):
    """按生成模型分组：每个 generator 给出检出率，human 行给出误报率。"""
    groups = {}
    for r in records:
        groups.setdefault(r["model"], []).append((r["label"], r["prob"]))
    out = []
    for name, pairs in sorted(groups.items()):
        stat = evaluate(pairs, threshold)
        stat["group"] = name
        out.append(stat)
    return out


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run(samples, engine, device="cpu", threshold=0.5, engine_params=None,
        progress_cb=None):
    """用给定引擎跑一遍评测，返回报告 dict。"""
    params = dict(engine_params or {})
    texts = [s["text"] for s in samples]
    probs = engine.predict_paragraphs(
        texts,
        device,
        progress_cb=progress_cb,
        **params
    )
    records = []
    for s, p in zip(samples, probs):
        records.append(
            {
                "text": s["text"][:120],
                "label": s["label"],
                "prob": p,
                "model": s.get("model", "unknown"),
                "source": s.get("source", ""),
                "lang": s.get("lang", ""),
            }
        )
    overall = evaluate([(r["label"], r["prob"]) for r in records], threshold)
    overall["by_model"] = evaluate_grouped(records, threshold)
    by_lang = {}
    for lang in sorted({r["lang"] for r in records if r["lang"]}):
        by_lang[lang] = evaluate(
            [(r["label"], r["prob"]) for r in records if r["lang"] == lang], threshold
        )
    overall["by_lang"] = by_lang
    overall["records"] = records
    return overall


def to_markdown(result, engine_name="", bench_name="", sample_note=""):
    """把报告渲染成 Markdown（便于存档 / 贴进论文附录）。"""
    lines = [
        "# %s 评测报告" % (bench_name or "检测器评测"),
        "",
        "- 检测引擎：%s" % (engine_name or "-"),
        "- 样本：%s" % (sample_note or "-"),
        "- 判定阈值：%.2f" % result.get("threshold", 0.5),
        "",
        "## 总体指标",
        "",
        "| 指标 | 数值 | 说明 |",
        "|---|---|---|",
        "| 样本数 | %d | |" % result["n"],
        "| 准确率 | %.1f%% | (TP+TN)/N |" % (result["accuracy"] * 100),
        "| 假阳性率 FPR | %.1f%% | 人类写的被判成 AI |" % (result["fpr"] * 100),
        "| 假阴性率 FNR | %.1f%% | AI 写的被放过 |" % (result["fnr"] * 100),
        "| 精确率 | %.1f%% | |" % (result["precision"] * 100),
        "| 召回率 | %.1f%% | |" % (result["recall"] * 100),
        "| F1 | %.3f | |" % result["f1"],
        "",
        "## 按来源分项",
        "",
        "| 来源 / 生成模型 | 样本 | 准确率 | FPR | 召回率 |",
        "|---|---|---|---|---|",
    ]
    for g in result.get("by_model", []):
        lines.append(
            "| %s | %d | %.1f%% | %.1f%% | %.1f%% |"
            % (g["group"], g["n"], g["accuracy"] * 100, g["fpr"] * 100, g["recall"] * 100)
        )
    by_lang = result.get("by_lang") or {}
    if by_lang:
        lines += ["", "## 按语言分项", "", "| 语言 | 样本 | 准确率 | FPR |", "|---|---|---|---|"]
        for lang, st in by_lang.items():
            lines.append(
                "| %s | %d | %.1f%% | %.1f%% |"
                % (lang, st["n"], st["accuracy"] * 100, st["fpr"] * 100)
            )
    lines += [
        "",
        "## 逐条明细",
        "",
        "| # | 真值 | 概率 | 判定 | 来源 | 片段 |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(result.get("records", []), 1):
        truth = "AI" if r["label"] == 1 else "人写"
        prob = r["prob"] if r["prob"] is not None else -1
        pred = "AI" if prob >= result.get("threshold", 0.5) else "人写"
        mark = "✅" if (r["label"] == 1) == (pred == "AI") else "❌"
        lines.append(
            "| %d | %s | %.2f | %s %s | %s | %s |"
            % (i, truth, prob, pred, mark, r["model"], r["text"].replace("|", "/"))
        )
    lines += [
        "",
        "> 说明：内置样本是作者手写的快速自检集，只用于验证引擎是否正常工作，",
        "> 不代表官方基准成绩。要看真实水平，请从 RAID / MGTBench 官方仓库",
        "> 下载数据子集后通过「导入样本」评测。",
        "",
    ]
    return "\n".join(lines)
