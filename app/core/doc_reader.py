import os
import re

# ---------------------------------------------------------------- PDF 版面重建
# 阈值来自 2026-09-24 实测（Elsevier 论文 14.68MB）：
#   * 同一行内片段 y 差 ≤ 2pt；正文行距 12.0pt 稳定；段间距 13.2~20.6pt
#   * 页眉 y≈753（页高 792）→ 顶部 6% 以内不算正文
#   * **字号不可靠**（实测被读成 1.0）→ 一律不用字号做判据
_PDF_EPS_Y = 2.0          # 同一行内文本片段的 y 容差（pt）
_PDF_HEAD_ZONE = 0.06     # 页顶 6% = 页眉
_PDF_FOOT_ZONE = 0.07     # 页底 7% = 页脚
_PDF_GAP_EXTRA = 2.0      # 行距 > 基准 + 2pt → 段间距（12.0 → 13.2 也抓得到）
_PDF_SHORT_RATIO = 0.62   # 行宽 < 栏宽 62% → 段落末行
_PDF_TITLE_MAX = 40       # 短行阈值：标题 / 图注 / 条目
_PDF_LONG_PARA = 1200     # 单段超这么多字就按句末标点再切
_SENT_END = "。！？；.!?;:\"'”’)）]】"
# 段落起始特征：编号条目、图表注、常见章节名
_PARA_HEAD_RE = re.compile(
    r"^(\[\d+\]|\(\d+\)|（\d+）|\d+[.)、]|[一二三四五六七八九十]+[、.]"
    r"|[①②③④⑤⑥⑦⑧⑨⑩]|[•·]\s|-\s"
    r"|(Fig|Figure|Table|图|表)\s*\d+"
    r"|(Abstract|Keywords|Introduction|Related work|Method|Results|Discussion"
    r"|Conclusion|References|Appendix|Acknowledg)\b)",
    re.I,
)


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        return _read_txt(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext == ".pdf":
        return _read_pdf(path)
    raise ValueError("仅支持 PDF / DOCX / TXT 文件")


def _read_txt(path):
    for enc in ("utf-8", "gb18030"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _read_docx(path):
    try:
        from docx import Document
    except ImportError as e:
        raise RuntimeError(_docx_hint(e)) from e

    doc = Document(path)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def _docx_hint(err):
    """把 DOCX 解析失败翻译成用户看得懂、能照做的提示。

    背景（2026-10-01 用户反馈）：引导器把依赖名写成 ``docx``，pip 于是装到了
    PyPI 上 2011 年的 Python 2 版本（单文件 ``docx.py``，内部
    ``from exceptions import PendingDeprecationWarning``）。用户上传 .docx 后
    只看到 "No module named 'exceptions'"，既不知道哪来的、也不知道怎么办。
    """
    missing = getattr(err, "name", "") or ""
    if missing == "exceptions":
        return (
            "读取 DOCX 失败：文档解析组件装成了错误的版本。\n\n"
            "当前安装的是 Python 2 时代的 docx 0.2.4（早已停止维护），"
            "它在 Python 3 下无法使用。\n\n"
            "修复方法：使用最新版安装程序；首次启动时的引导器会自动识别并"
            "替换为正确的 python-docx 组件。"
        )
    if missing == "docx":
        return (
            "读取 DOCX 失败：缺少文档解析组件 python-docx。\n\n"
            "修复方法：重新运行安装程序，或重启软件让引导器自动补齐组件。"
        )
    return "读取 DOCX 失败：%s" % err


def _read_pdf(path):
    """读 PDF：**先做版面重建**，再交给 ``split_paragraphs`` 按空行分段。

    为什么要重建版面（2026-09-24 修）
    --------------------------------
    ``page.extract_text()`` 返回的是**排版行**（每行自带 ``\\n``），而段落之间
    没有空行；``split_paragraphs`` 只认空行 → 整篇被并成**一段**。实测一份
    14.68MB 的 Elsevier 论文：原来只得到 1 段，"占比 + 逐段报告"全部失效。

    做法：``visitor_text`` 回调取每个文本片段的坐标 → 聚成行 → 剔页眉页脚与
    跨页重复行 → 按 x0 分栏 → 按**行距跳变 / 末行变短 / 编号标题行**切段 →
    段落之间填 ``\\n\\n``（于是下游一行都不用改）。

    坐标拿不到时（扫描件、异常 PDF）自动退回整页取文本，**不会比原来更差**。
    """
    paras = _pdf_paragraphs(path)
    if paras:
        return "\n\n".join(paras)
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError(
            "读取 PDF 失败：缺少文档解析组件 pypdf。\n\n"
            "修复方法：重新运行安装程序，或重启软件让引导器自动补齐组件。"
        ) from e

    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _pdf_paragraphs(path):
    """整份 PDF → 段落列表；任何异常都返回空列表（交给调用方回退）。"""
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        pages = []
        for page in reader.pages:
            pages.append(_pdf_page_lines(page))
        repeated = _pdf_furniture(pages)
        out = []
        for lines in pages:
            out.extend(_pdf_page_paragraphs(lines, repeated))
        return _pdf_split_long(out)
    except Exception:
        return []


def _pdf_page_lines(page):
    """取一页的行：``[(x0, y, text)]``，按阅读顺序（上→下、左→右）。"""
    rows = []

    def visit(text, cm, tm, font_dict, font_size):
        s = (text or "").strip()
        if not s:
            return
        # **必须把 cm 乘进去**：``tm`` 只是文本矩阵，受当前变换矩阵 ``cm``
        # 影响。实测某 Elsevier PDF 里 tm 的 y 是 0、-2.6、-5.2… 这种累积值，
        # 直接当坐标用会把 12pt 的行距算成 2.6pt，全篇也就分不出行了。
        x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
        y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
        rows.append((float(x), float(y), s))

    try:
        page.extract_text(visitor_text=visit)
    except Exception:
        return []
    rows.sort(key=lambda r: (-r[1], r[0]))
    grouped = []
    for x, y, s in rows:
        if grouped and abs(grouped[-1][1] - y) <= _PDF_EPS_Y:
            grouped[-1][2].append((x, s))
            grouped[-1][0] = min(grouped[-1][0], x)
        else:
            grouped.append([x, y, [(x, s)]])
    lines = []
    for x, y, seg in grouped:
        seg.sort()
        lines.append((x, y, "".join(t for _x, t in seg)))
    return lines


def _pdf_furniture(pages):
    """跨页重复出现的短行（页眉/页脚/期刊名/网址）→ 整行剔除。"""
    counts = {}
    for lines in pages:
        for _x, _y, s in lines:
            if len(s) <= 100:
                counts[s] = counts.get(s, 0) + 1
    need = 2 if len(pages) < 6 else max(2, int(len(pages) * 0.5))
    return {s for s, c in counts.items() if c >= need}


def _pdf_page_paragraphs(lines, repeated):
    """一页 → 段落列表（先切栏，再在每栏内重排段落）。

    页眉页脚**不用绝对坐标判**：不同 PDF 的坐标基准差异极大（实测有的
    y 只有 0~30，有的 0~790），绝对阈值必然误伤。改成**按行数比例砍头尾**
    —— ``lines`` 已按阅读顺序排好，头 6% 与尾 7% 直接不看；跨页重复出现的
    短行再单独剔除一遍。
    """
    lines = [ln for ln in lines if ln[2] and ln[2] not in repeated]
    n = len(lines)
    if not n:
        return []
    head = int(n * _PDF_HEAD_ZONE)
    foot = int(n * _PDF_FOOT_ZONE)
    keep = lines[head: n - foot] if n - foot > head else lines
    paras = []
    for column in _pdf_columns(keep):
        paras.extend(_pdf_reflow(column))
    return paras


def _pdf_columns(items):
    """按 x0 把一页切成 1~2 栏（实测双栏的 x0 分两簇：56.7 / 304.7）。"""
    if not items:
        return []
    xs = sorted({round(x, 1) for x, _y, _s in items})
    if len(xs) < 2:
        return [items]
    span = xs[-1] - xs[0]
    cut = None
    for i in range(len(xs) - 1):
        if xs[i + 1] - xs[i] > 0.15 * span:
            cut = (xs[i] + xs[i + 1]) / 2.0
            break
    if cut is None:
        return [items]
    left = [it for it in items if it[0] < cut]
    right = [it for it in items if it[0] >= cut]
    return [left, right] if left and right else [items]


def _pdf_reflow(items):
    """栏内的行 → 段落：行距跳变、末行变短、编号/标题行都能断段。"""
    if not items:
        return []
    items = sorted(items, key=lambda r: -r[1])
    gaps = [items[i][1] - items[i + 1][1] for i in range(len(items) - 1)]
    base = _median([g for g in gaps if g > 0])
    wmax = max(len(s) for _x, _y, s in items) or 1
    paras = []
    buf = []
    for i, line in enumerate(items):
        if buf:
            prev = buf[-1]
            gap = prev[1] - line[1]
            ended = prev[2].rstrip().endswith(tuple(_SENT_END))
            short_prev = len(prev[2]) < wmax * _PDF_SHORT_RATIO
            heads_para = bool(_PARA_HEAD_RE.match(line[2].strip()))
            independent = (
                len(line[2]) < _PDF_TITLE_MAX
                and not line[2].rstrip().endswith(tuple(_SENT_END))
                and i + 1 < len(items)
                and (items[i][1] - items[i + 1][1]) > base + _PDF_GAP_EXTRA
            )
            if (base and gap > base + _PDF_GAP_EXTRA) or heads_para \
                    or (ended and short_prev) or independent:
                paras.append(_pdf_join(buf))
                buf = []
        buf.append(line)
    if buf:
        paras.append(_pdf_join(buf))
    return [p for p in paras if p.strip()]


def _pdf_join(buf):
    """同一段的多行粘起来：中文直接接，英文补空格并修断词连字符。"""
    out = ""
    for _x, _y, s in buf:
        s = s.strip()
        if not s:
            continue
        if not out:
            out = s
            continue
        if _is_cjk(out[-1]) or _is_cjk(s[0]):
            out = out.rstrip("-") + s
        elif out.endswith("-"):
            out = out[:-1] + s
        else:
            out = out + " " + s
    return out


def _is_cjk(ch):
    """汉字 / 全角标点（决定拼行时要不要补空格）。"""
    return "\u2e80" <= ch <= "\u9fff" or "\uff00" <= ch <= "\uffef"


def _median(values):
    if not values:
        return 0.0
    values = sorted(values)
    n = len(values)
    mid = n // 2
    if n % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def _pdf_split_long(paras):
    """过长的段（表格混排把整页并在一起）按句末标点再切。"""
    out = []
    for p in paras:
        if len(p) <= _PDF_LONG_PARA:
            out.append(p)
            continue
        buf = ""
        for chunk in re.split(r"(?<=[。！？；.!?])", p):
            if buf and len(buf) + len(chunk) > _PDF_LONG_PARA:
                out.append(buf)
                buf = chunk
            else:
                buf += chunk
        if buf:
            out.append(buf)
    return out


def split_paragraphs(text, min_len=20):
    raw = [line.strip() for line in text.splitlines()]
    paras = []
    buf = []
    for line in raw:
        if line:
            buf.append(line)
        else:
            if buf:
                paras.append("".join(buf))
                buf = []
    if buf:
        paras.append("".join(buf))
    merged = []
    for p in paras:
        if merged and len(p) < min_len:
            merged[-1] += p
        else:
            merged.append(p)
    return [p for p in merged if len(p) >= min_len]
