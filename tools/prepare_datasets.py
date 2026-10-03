# -*- coding: utf-8 -*-
r"""数据集加载与预处理（**内存中处理，不写任何中间文件**）。

设计原则（用户明确要求）
------------------------
**原始数据一个字节都不改，处理只在进入模型之前做。**

理由：
1. 磁盘上不会出现"这份数据是哪来的、怎么处理的"说不清的第二份文件；
2. 原始数据更新后自动跟随，不存在两份数据不一致的问题；
3. 只有一条数据路径，出错时排查点唯一。

所以本模块只提供**加载函数**，不提供 ``--build`` 之类的落盘命令。

为什么要预处理
--------------
现有数据集的原始形态各有问题（2026-09-23 实测）：

==========================  ==========================================
数据                          原始形态的问题
==========================  ==========================================
``HC3_zh_all.jsonl``        嵌套结构（1 问 + N 人写 + M AI），
                            **未展开**；这是原始 HC3 的固有格式
``ghostbuster-data/``       顶层除 essay/wp/reuter 外，还有
                            ``other``（**仅人写**，无 AI 对照）、
                            ``perturb``（扰动攻击）、
                            ``<gen>/logprobs/``（**token+概率**，
                            不是纯文本）—— 都要挑出来
==========================  ==========================================

论文口径（arXiv:2301.07597 §5.3）
--------------------------------
> We extracted **all the `<question, answer>` pairs**, and assigned label
> `0` to pairs with human answers and label `1` to pairs with ChatGPT answers.

即**按 pair 展开、保留 question**。这是本项目此前丢掉的维度 ——
没有 question，同一答案挂在多个问题下就会被误认成"完全重复"
（实测旧集有 32 组 / 94 条，全部集中在 finance split）。

输出格式
--------
``{"text", "label", "source", "lang", "question", "sub"}``

* ``label``    0 = 人写，1 = AI
* ``source``   数据集来源（``hc3_zh/medicine`` / ``ghostbuster/essay`` …）
* ``sub``      生成器 / 子类（``human`` / ``gpt`` / ``claude`` / ``chatgpt``）

用法
----
::

    python tools/prepare_datasets.py --check     # 体检：看数据构成与问题

探针里这样调用（**不落盘**）::

    from prepare_datasets import load_hc3, load_ghost

    rows = load_hc3()        # -> [{"text", "label", ...}, ...]
    rows = load_ghost()      # 同上
"""
import argparse
import collections
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HF_CACHE = r"D:\hf_cache"
GHOST_ROOT = os.path.join(HF_CACHE, "ghostbuster-data")

HC3_RAW = os.path.join(HF_CACHE, "HC3_zh_all.jsonl")
HC3_1TO1 = os.path.join(HF_CACHE, "hc3_zh_1to1.jsonl")
GHOST_ESSAY = os.path.join(HF_CACHE, "ghost_essay_1to1.jsonl")
GHOST_MULTI = os.path.join(HF_CACHE, "ghost_multi.jsonl")

# 文本最短字符数。低于此值的样本对 PPL 类引擎没有判别意义。
MIN_CHARS = 100

# ---------------------------------------------------------------- 目录常量
# logprobs 子目录：Ghostbuster 在 reuter/wp 下额外提供「token + 概率」格式，
# 内容不是纯文本。**必须跳过** —— 旧 ghost_multi.jsonl 就是因为把它当文本
# 读了，导致 1194 条里 833 条（69.8%）是坏的。
_LOGPROB_DIR = "logprobs"

# 不作为「生成器」看待的目录名
_SKIP_DIRS = {"logprobs", "prompts"}

# Ghostbuster 顶层可用 split（其余为特定用途，见 rebuild 的 docstring）
GHOST_SPLITS = ("essay", "wp", "reuter")



def _read_jsonl(path):
    """读 jsonl，容忍坏行。"""
    out = []
    if not os.path.isfile(path):
        return out
    with io.open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


_TOKEN_PROB_RE = re.compile(r"^\S+\s+[0-9]*\.?[0-9]+$")


def looks_like_logprobs(text):
    """判定 text 是否是「token 概率」格式（而非纯文本）。

    判据：按行看，**过半**的行形如 ``token 1.234``（词 + 浮点数）。
    单看一行会误判（正常英文句子也可能以「词 数字」开头），
    所以要求多数行命中 —— 实测对 ghost_multi 的 833 条能全部命中，
    对正常文本不误报（hc3 的 2 条误报由此消除）。
    """
    lines = [ln.strip() for ln in (text or "").split("\n") if ln.strip()]
    if len(lines) < 4:
        return False
    head = lines[:40]
    hit = sum(1 for ln in head if _TOKEN_PROB_RE.match(ln))
    return hit >= max(3, len(head) * 0.5)


def strip_logprobs(text):
    """把「token 概率」格式还原成纯文本（去概率、还原 GPT-2 字节级空格）。"""
    out = []
    for ln in (text or "").split("\n"):
        m = re.match(r"^(\S+)\s+[0-9]*\.?[0-9]+$", ln.strip())
        if m:
            out.append(m.group(1))
        elif ln.strip():
            out.append(ln.strip())
    # GPT-2 用 Ġ 表示前导空格，Ċ 表示换行（字节级 BPE 的可见形式）
    s = "".join(out)
    s = s.replace("\u0120", " ").replace("\u010a", "\n")
    return s.strip()


def dedup_pairs(rows, keep="first"):
    """按 ``(question, text)`` 去重 —— 论文口径下同一对只算一个样本。

    **为什么必须有**：HC3 展开后实测有 406 条冗余，分两类：

    ==================================  ======  ==========================
    类型                                  组数    处置
    ==================================  ======  ==========================
    同 text / **不同 question**            197     ✅ **保留** —— 论文口径
                                                  下是合法 pair（一条答案
                                                  回答多个问题）
    同 text / **同一 question**          **11**    ❌ **去掉** —— 同一问题
                                                  下的重复答案是采集冗余
    ==================================  ======  ==========================

    第 2 类的实际来源已查明：HC3 的 ``psychology`` split 源自百度 AI Studio
    心理问答，**同一楼的长回复被重复采集**（最极端的一组重复 9 次），
    另有 finance 的同款问题被重复贴同一段招行说明。
    **这是原始数据的采集冗余，不是本次展开逻辑的问题。**

    :param keep: 同 pair 保留哪一条（``"first"`` / ``"last"``）
    """
    seen = set()
    out = []
    src = rows if keep == "first" else list(reversed(rows))
    for r in src:
        key = (r.get("question") or "", r["text"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    if keep != "first":
        out.reverse()
    return out


# ------------------------------------------------------------------ HC3
def load_hc3(path=HC3_RAW, min_chars=MIN_CHARS, dedup=True):
    """加载 HC3 中文（展开成 pair，论文 §5.3 口径）。

    输入：``{"question", "human_answers": [...], "chatgpt_answers": [...], "source"}``
    输出：每对 ``<question, answer>`` 一条记录，**保留 question**。

    这是本项目此前丢掉的信息 —— 没有 question，同一答案挂在多个问题下
    时就会被误认成"完全重复"（旧 ``hc3_zh_1to1.jsonl`` 的 94 条假重复
    就是这么来的）。

    :param dedup: 按 ``(question, text)`` 去重（见 ``dedup_pairs``）
    """
    rows = _read_jsonl(path)
    out = []
    for r in rows:
        q = (r.get("question") or "").strip()
        src = "hc3_zh/%s" % (r.get("source") or "unknown")
        for a in (r.get("human_answers") or []):
            t = (a or "").strip()
            if len(t) >= min_chars:
                out.append({"text": t, "label": 0, "source": src, "lang": "zh",
                            "question": q, "sub": "human"})
        for a in (r.get("chatgpt_answers") or []):
            t = (a or "").strip()
            if len(t) >= min_chars:
                out.append({"text": t, "label": 1, "source": src, "lang": "zh",
                            "question": q, "sub": "chatgpt"})
    return dedup_pairs(out) if dedup else out


def load_hc3_1to1(path=HC3_1TO1, min_chars=MIN_CHARS):
    """加载旧的中文 1:1 集（**无 question**，仅供对照/复现旧结论）。

    新代码请用 ``load_hc3()`` —— 它保留 question，且样本量更大
    （旧集 3000 条有 94 条因丢 question 而看似重复）。
    """
    out = []
    for r in _read_jsonl(path):
        t = (r.get("text") or "").strip()
        if len(t) < min_chars:
            continue
        out.append({"text": t, "label": int(r.get("label") or 0),
                    "source": r.get("source") or "", "lang": r.get("lang") or "zh",
                    "question": "", "sub": r.get("model") or ""})
    return out


# ------------------------------------------------------- Ghostbuster 原件
def _find_txt(gdir, max_depth=2):
    """在生成器目录下找 .txt，但**不进入 logprobs**。

    为什么不能简单递归：Ghostbuster 的目录层级**不统一**（实测）：

    ================  ==========================================
    split/gen         文件位置
    ================  ==========================================
    essay/human       本层直接是 ``1.txt`` …
    wp/human          本层直接是 ``1.txt`` …
    **reuter/human**  ``AaronPressman/1.txt`` —— 多一层人名目录
    ================  ==========================================

    且 reuter / wp 下另有 ``<gen>/logprobs/``（token+概率，**必须跳过**）。
    所以策略是：向下最多 ``max_depth`` 层找 .txt，
    但遇到名为 ``logprobs`` 的目录立即剪枝。
    """
    found = []

    def walk(d, depth):
        if depth > max_depth:
            return
        try:
            entries = sorted(os.listdir(d))
        except Exception:
            return
        for name in entries:
            fp = os.path.join(d, name)
            if name.lower() in _SKIP_DIRS:
                continue
            if os.path.isfile(fp):
                if name.endswith(".txt"):
                    found.append(fp)
            elif os.path.isdir(fp):
                if name.lower() == _LOGPROB_DIR:
                    continue          # 剪枝：logprobs 里是 token+概率
                if depth < max_depth:
                    walk(fp, depth + 1)

    walk(gdir, 0)
    return found


def load_ghost(root=GHOST_ROOT, min_chars=MIN_CHARS, splits=None, dedup=True):
    """加载 Ghostbuster 英文（**从原件读，不用 ghost_multi.jsonl**）。

    为什么不"清洗" ``ghost_multi.jsonl``：那份文件里 **69.8%** 的 text
    混进了 ``<split>/<gen>/logprobs/`` 的内容（token+概率），
    而**原件就在本地**（``D:\\hf_cache\\ghostbuster-data\\``），
    直接重建比反向还原更可靠、可验证。

    顶层目录是 **数据集（split）**，其下是 **生成器（gen）**：

    ================  =============================  ==========
    顶层               含义                            用途
    ================  =============================  ==========
    essay             Student Essay（人类作文）       ✅ 用
    wp                Writing Prompts                 ✅ 用
    reuter            Reuters 新闻                    ✅ 用
    **other**         BAWE / ETS / Lang8 等**人类语料**  ⚠️ **仅人写**，无 AI 对照
    perturb          扰动实验（改写攻击）             ❌ 不用
    perturb_old      同上（旧版）                     ❌ 不用
    ================  =============================  ==========

    **`other` 必须排除**：它里面只有人写文本（bawe / ets / lang8 都是人类作文
    语料），没有对应的 AI 版本 —— 混进来会把人机比拉到 8:1（实测）。

    :param splits: 要用的 split；None = ``("essay", "wp", "reuter")``
    """
    if splits is None:
        splits = ("essay", "wp", "reuter")
    out = []
    if not os.path.isdir(root):
        return out
    for split in sorted(os.listdir(root)):
        sdir = os.path.join(root, split)
        if not os.path.isdir(sdir) or split not in splits:
            continue
        for gen in sorted(os.listdir(sdir)):
            gdir = os.path.join(sdir, gen)
            if not os.path.isdir(gdir) or gen in _SKIP_DIRS:
                continue
            # ``prompts`` 是提示词本身（不是待检测的生成结果），且两个 split
            # 下都有 1000 个 txt —— 不排除会混进来 2000 条噪声。
            if gen.lower() == "prompts":
                continue
            for fp in _find_txt(gdir):
                try:
                    with io.open(fp, "r", encoding="utf-8", errors="replace") as f:
                        t = f.read().strip()
                except Exception:
                    continue
                if len(t) < min_chars:
                    continue
                if looks_like_logprobs(t):
                    continue
                out.append({"text": t, "label": 0 if gen == "human" else 1,
                            "source": "ghostbuster/%s" % split, "lang": "en",
                            "question": "", "sub": gen})
    # 已做的处理：长度过滤 + logprobs 识别 + 按 pair 去重；**不做**人机平衡
    # （平衡交给 balance() 显式调用 —— 避免"加载"隐式改变数据分布）。
    # Ghostbuster 实测 0 重复，开关保留以防数据更新后出现。
    return dedup_pairs(out) if dedup else out



def sample_pairs_per_question(rows, seed=42, min_per_class=1):
    """按问题配对抽样：**每个问题各抽一条人写 + 一条 AI**（1:1）。

    论文依据
    --------
    arXiv:2301.07597 §4.1（语言分析章节）原文：

    > Since the number of human/ChatGPT answers is **unbalanced**, we
    > **randomly sample one answer from humans and one answer from ChatGPT**
    > during our statistical process.

    论文在需要平衡的场景（统计/可比性）里就是这么做的。**检测实验（§5.3）
    则相反** —— ``We extracted all the <question, answer> pairs``，不做平衡，
    靠 **F1** 指标消化不平衡。两种做法都有原文依据，取决于要报什么指标。

    为什么按问题配对（比论文再严一点）
    ----------------------------------
    论文只说"随机各抽一条"，没限定是否同一问题。但**同一问题**下的人机答案
    才构成严格对照（内容主题一致，排除话题差异的干扰）。
    所以本函数：**在每个 question 内部**各抽 1 条人写、1 条 AI。

    适用场景：需要报 **acc / FPR** 时 —— 查重工具**误报比漏报严重**，
    FPR 需要平衡集才解释得清（不平衡时误报率会被多数类稀释）。

    :param min_per_class: 该问题下两类都至少有这么多条才纳入（默认 1:1）
    """
    import random

    by_q = collections.defaultdict(lambda: {0: [], 1: []})
    for r in rows:
        by_q[r.get("question") or ""][r["label"]].append(r)

    rnd = random.Random(seed)
    out = []
    for q in sorted(by_q.keys()):
        g = by_q[q]
        if len(g[0]) < 1 or len(g[1]) < 1:
            continue                      # 缺一侧的问题无法配对，跳过
        out.append(rnd.choice(g[0]))
        out.append(rnd.choice(g[1]))
    rnd.shuffle(out)
    return out


def balance(rows, seed=42, per_class=None):
    """[通用] 把人机比压成 1:1（不要求 question）。

    与 ``sample_pairs_per_question`` 的区别：

    ==============================  ================================
    函数                             依据 / 适用
    ==============================  ================================
    ``sample_pairs_per_question``   论文 §4.1 原文；按问题配对，
                                    **有 question 的数据优先用它**
    ``balance``（本函数）            无 question 的数据（Ghostbuster）
                                    只能按类随机抽，退而求其次
    ==============================  ================================

    **注意 Ghostbuster 的 6:1 是固有结构**（1 份人类文本 : 6 种生成方式），
    且它没有人机配对的字段（无 question），所以只能用本函数。

    :param per_class: 每类取多少；None = 少数类的全部
    """
    import random

    hu = [r for r in rows if r["label"] == 0]
    ai = [r for r in rows if r["label"] == 1]
    k = min(len(hu), len(ai)) if per_class is None else int(per_class)
    k = min(k, len(hu), len(ai))
    rnd = random.Random(seed)
    out = rnd.sample(hu, k) + rnd.sample(ai, k)
    rnd.shuffle(out)
    return out


def load_balanced(lang="zh", min_chars=MIN_CHARS, seed=42):
    """一步拿到 1:1 平衡集（内存处理，不落盘）。

    * ``"zh"`` -> HC3，用 **按问题配对抽样**（论文 §4.1 口径）
    * ``"en"`` -> Ghostbuster，用 **按类随机抽样**（它没有 question 字段）
    """
    if lang == "zh":
        return sample_pairs_per_question(load_hc3(min_chars=min_chars), seed=seed)
    return balance(load_ghost(min_chars=min_chars), seed=seed)



# ------------------------------------------------------------------ 体检
def report(name, rows, fh=None):
    """打印一个数据集的构成与质量问题。"""
    def p(s):
        print(s)
        if fh:
            fh.write(s + "\n")

    n = len(rows)
    ai = sum(1 for r in rows if r["label"] == 1)
    hu = n - ai
    p("=== %s ===" % name)
    p("  条数=%d（AI %d / 人写 %d，比例 %.3f:1）" % (n, ai, hu, ai / hu if hu else 0))
    p("  来源数=%d" % len(set(r["source"] for r in rows)))
    p("  带 question 的=%d (%.1f%%)"
      % (sum(1 for r in rows if r.get("question")), 
         sum(1 for r in rows if r.get("question")) * 100.0 / n if n else 0))
    # 精确重复 —— 分两类，因为处置不同（见 dedup_pairs）
    cnt = collections.Counter(r["text"] for r in rows)
    dups = {k: v for k, v in cnt.items() if v > 1}
    extra = sum(v - 1 for v in dups.values())
    has_q = bool(rows) and any(r.get("question") for r in rows)
    if has_q:
        # 有 question 时按 pair 分开统计
        same_q, diff_q = [], []
        for k in dups:
            qs = set(r.get("question") or "" for r in rows if r["text"] == k)
            (diff_q if len(qs) > 1 else same_q).append(k)
        n_same = sum(cnt[k] - 1 for k in same_q)
        n_diff = sum(cnt[k] - 1 for k in diff_q)
        p("  同 text 不同 question = %d 组 / %d 条 [合法]（论文 pair 口径）"
          % (len(diff_q), n_diff))
        p("  **同 text 同 question = %d 组 / %d 条 [采集冗余，已去除]**"
          % (len(same_q), n_same))
    else:
        p("  **完全重复 = %d 组 / %d 条冗余 (%.1f%%)**"
          % (len(dups), extra, extra * 100.0 / n if n else 0))
    p("  去重后条数 = %d" % len(dedup_pairs(rows)))
    # 长度
    ls = sorted(len(r["text"]) for r in rows)
    if ls:
        p("  长度: min=%d 中位=%d max=%d" % (ls[0], ls[len(ls) // 2], ls[-1]))
    # 来源分布（前 10）
    sc = collections.Counter(r["source"] for r in rows)
    p("  来源分布(前10): %s" % dict(sc.most_common(10)))
    p("")
    return {"n": n, "ai": ai, "hu": hu, "dup_groups": len(dups),
            "dup_extra": sum(v - 1 for v in dups.values())}


def check():
    """体检：看各数据集的构成与问题（**不写任何文件**）。"""
    print("=" * 68)
    print("数据集体检（只读，不写任何文件）")
    print("=" * 68)
    print()

    print("--- 原始数据（不动）---")
    raw = _read_jsonl(HC3_RAW)
    print("=== HC3_zh_all.jsonl ===")
    print("  条数=%d（原始嵌套格式，未展开）" % len(raw))
    print("  字段=%s" % (sorted(raw[0].keys()) if raw else []))
    print()

    print("--- 旧数据集（有问题，新代码勿用）---")
    rows = _read_jsonl(GHOST_MULTI)
    bad = [r for r in rows if looks_like_logprobs(r.get("text"))]
    print("=== ghost_multi.jsonl ===")
    print("  条数=%d" % len(rows))
    print("  **logprobs 污染=%d (%.1f%%)**  <- 不可直接用"
          % (len(bad), len(bad) * 100.0 / len(rows) if rows else 0))
    report("hc3_zh_1to1.jsonl（丢 question 的旧集）", load_hc3_1to1())
    rows = _read_jsonl(GHOST_ESSAY)
    report("ghost_essay_1to1.jsonl（仅 essay 一个 split）",
           [{"text": (r.get("text") or "").strip(), "label": int(r.get("label") or 0),
             "source": r.get("source") or "", "question": "", "sub": r.get("model") or ""}
            for r in rows if len((r.get("text") or "").strip()) >= MIN_CHARS])

    print("--- 处理后的结果（内存，不落盘）---")
    hc3 = load_hc3()
    report("load_hc3() 中文｜论文 §5.3：全量 pair（报 F1 用）", hc3)
    report("load_balanced('zh')｜论文 §4.1：按问题各抽 1 条（报 acc/FPR 用）",
           sample_pairs_per_question(hc3))
    gh = load_ghost()
    report("load_ghost() 英文｜论文 §5.3：全量", gh)
    report("load_balanced('en')｜1:1（英文无 question，按类抽）", balance(gh))
    return hc3, gh


def main():
    ap = argparse.ArgumentParser(
        description="数据集加载与预处理（内存处理，不落盘）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--check", action="store_true", help="体检（默认行为）")
    args = ap.parse_args()
    # 控制台可能是 GBK（Windows 中文默认）—— 直接 print 非 GBK 字符会抛
    # UnicodeEncodeError。这里把 stdout 换成 UTF-8，并在无法编码时用替代符，
    # 避免"能跑的程序因为一个字符崩掉"。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        check()
    except KeyboardInterrupt:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


