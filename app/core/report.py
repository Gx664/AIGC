import colorsys
from html import escape

from core.i18n import get_lang, tr

# 四档的基色（绿/黄/红/紫，与论文涂色图同色系），深色文字叠在上面仍可读
_BUCKET_BASE = ("#2e9e4f", "#d4a017", "#d1453b", "#7b4bd0")
# 明度系数：0 = 最浅（占比 0% 的档），1 = 原色。0.18 起步，
# 保证「占比 0%」的档仍有可见底色，能看出这一档存在、只是没命中。
_BUCKET_DIM = 0.18


def _shade(hex_color, weight):
    """按占比给基色调明度 —— 占比越高颜色越饱和（论文涂色图的直观读法）。

    :param hex_color: ``#rrggbb`` 基色
    :param weight: 0~1，占比（0 表示该档未命中）
    :return: ``#rrggbb``
    """
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    w = _BUCKET_DIM + (1.0 - _BUCKET_DIM) * max(0.0, min(1.0, weight))
    return "#%02x%02x%02x" % tuple(
        int(round(c * 255)) for c in colorsys.hsv_to_rgb(h, s, v * w)
    )


def _pct100(frac):
    """把占比转成**和为 100 的整数百分比**。

    为什么不能各自 round：四档之和恒为 1，但各自四舍五入后**和可能是
    99 或 101**（实测 3000 个随机样本里 1014 个如此）。用户会把四个数字
    加起来核对，看到 99% 会以为程序算错了。

    做法：先各自向下取整，再把差额补给原值最大的那档（最大余数法的简化版
    —— 只补一档即可，因为向下取整后差额的绝对值最大为 3：四档占比之和恒为
    1，各自向下取整最多丢掉 1 个百分点的不到，四个加起来不超过 3）。

    :param frac: ``(绿, 黄, 红, 紫)`` 占比（和为 1）
    :return: 四个整数百分比，**和恰为 100**
    """
    vals = [v * 100.0 for v in frac]
    # 全 0 是异常输入（引擎按 rank 分档，必有一档命中，和恒为 1）——
    # 若原样补差额会变成「绿 100%」，反而显示成"全是绿档"这种错误结论。
    # 故全 0 直接返回全 0，让调用方自行决定是否显示。
    if sum(vals) <= 0:
        return [0, 0, 0, 0]
    ints = [int(v) for v in vals]
    diff = 100 - sum(ints)
    if diff:
        # 补给小数部分最大、或（diff<0 时）整数部分最大的一档
        idx = max(range(4), key=lambda i: (vals[i] - ints[i]) if diff > 0
                  else ints[i])
        ints[idx] += diff
    return ints


def _bar_svg(vals):
    """把**已取整**的四档占比画成一根 100% 宽的堆叠柱（论文直方图的横向版）。

    为什么用 SVG 而不是 ``<div>`` 套色块：报告在 ``QTextBrowser`` 里渲染，
    该控件只实现 HTML4 的子集，浮动/弹性布局都不支持，横向排列的色块会
    退化成竖排。SVG 在 Qt 里是原生支持的，且宽度用百分比、不依赖布局。

    :param vals: 四个整数百分比（和恰为 100，见 ``_pct100``）
    :return: ``<svg>`` 片段；全 0 时返回空串
    """
    total = sum(vals)
    if total <= 0:
        return ""
    parts = []
    x = 0.0
    for i, v in enumerate(vals):
        if v <= 0:
            continue
        w = v * 100.0 / total           # 归一到 100% 宽，容忍调用方传入非 100
        parts.append(
            "<rect x='%.3f%%' y='0' width='%.3f%%' height='12' fill='%s'></rect>"
            % (x, w, _shade(_BUCKET_BASE[i], v / 100.0))
        )
        x += w
    return (
        "<svg width='100%%' height='12' viewBox='0 0 100 12' "
        "preserveAspectRatio='none' style='display:block'>%s</svg>" % "".join(parts)
    )


def _bucket_cell(frac):
    """把一段的四档占比渲染成柱状图 + 一行图例。

    柱子是 GLTR 论文 §3 Test-2 的经典产物（原论文是逐 token 涂色 + 直方图）。
    这里给横向堆叠柱 + 同色图例数字，两处颜色一一对应，既能一眼看比例，
    也能读到确切数字。四档顺序（绿/黄/红/紫）与图例顺序一致。

    :param frac: ``(绿, 黄, 红, 紫)`` 占比，或 None（文本过短/非统计派引擎）
    """
    if not frac:
        return ""
    vals = _pct100(frac)
    if sum(vals) <= 0:
        return ""               # 全 0 无信息，不显示空行
    return (
        "<table cellspacing='0' cellpadding='0' style='border-collapse:collapse'>"
        "<tr><td style='padding:2px 0;width:220px'>%s</td>"
        "<td style='padding:2px 0 2px 8px;color:#475569'>%s</td></tr></table>"
        % (_bar_svg(vals), tr("bucket_cell") % tuple(vals))
    )


def build_report(paragraphs, probs, ratio, file_name, engine_name, threshold=0.5,
                 diagnosis=None, buckets=None):
    rows = []
    for i, (para, prob) in enumerate(zip(paragraphs, probs), 1):
        suspicious = prob >= threshold
        bg = "#fff3cd" if suspicious else "#ffffff"
        color = "#b02a37" if suspicious else "#000000"
        snippet = escape(para if len(para) <= 180 else para[:180] + "…")
        rows.append(
            "<tr><td style='background:%s'>%s</td>"
            "<td style='background:%s;color:%s'>%s</td>"
            "<td style='background:%s'>%s</td></tr>"
            % (bg, tr("para_n") % i, bg, color, tr("ai_prob") % (prob * 100), bg, snippet)
        )
        # 四档单独一行（只对统计派引擎有数据）—— 不塞进上面那行，因为那行是
        # 三列表格，柱状图塞进去会把「AI 概率」列撑宽，长段落截图时更难读。
        #
        # 判据用**渲染结果是否为空**，而不是 buckets[i-1] 是否为 None ——
        # 全 0 元组是非空的（真值），但渲染为空串，若按后者判断会生成一行
        # 空的 <tr>（踩过）。
        if buckets and i - 1 < len(buckets):
            cell = _bucket_cell(buckets[i - 1])
            if cell:
                rows.append(
                    "<tr><td colspan='3' style='background:%s'>%s</td></tr>"
                    % (bg, cell)
                )
    html = [
        "<h2>%s</h2>" % escape(str(file_name)),
        "<p style='font-size:17px'>%s</p>"
        % tr("report_summary") % (engine_name, ratio * 100, threshold * 100),
        "<p>%s</p>" % tr("report_legend"),
    ]
    # 柱状图的读法（柱长 = 占比）需要一句说明，否则用户不知道那根彩色条是什么。
    # 只在真有段落带四档数据时才出 —— 非统计派引擎显示这句会让人以为数据丢了。
    if any(_bucket_cell(b) for b in (buckets or [])):
        html.append("<p>%s</p>" % tr("bucket_legend"))
    html += [
        "<table border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse'>",
        "".join(rows),
        "</table>",
    ]
    if diagnosis:
        s = diagnosis.get("summary", {})
        high = s.get("high_risk_paras", 0)
        medium = s.get("medium_risk_paras", 0)
        top = s.get("top_patterns", [])[:4]
        footer = [
            "<p style='margin-top:14px;font-size:14px;color:#1d4ed8;font-weight:700;'>%s</p>"
            % tr("report_diag_footer") % (high, medium),
        ]
        if top:
            names = []
            for t in top:
                names.append("%s×%d" % (t["zh"] if get_lang() == "zh" else t["en"], t["count"]))
            footer.append(
                "<p style='font-size:13px;color:#475569;'>%s</p>"
                % tr("report_diag_top") % "、".join(names)
            )
        footer.append(
            "<p style='font-size:13px;color:#475569;'>%s</p>"
            % tr("report_diag_hint")
        )
        html += footer
    return "".join(html)
