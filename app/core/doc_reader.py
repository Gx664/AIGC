import os


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
