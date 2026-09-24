from html import escape

from core.i18n import get_lang, tr


def build_report(paragraphs, probs, ratio, file_name, engine_name, threshold=0.5, diagnosis=None):
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
    html = [
        "<h2>%s</h2>" % file_name,
        "<p style='font-size:17px'>%s</p>"
        % tr("report_summary") % (engine_name, ratio * 100, threshold * 100),
        "<p>%s</p>" % tr("report_legend"),
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
