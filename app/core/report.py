from html import escape

from core.i18n import tr


def build_report(paragraphs, probs, ratio, file_name, engine_name, threshold=0.5):
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
    return "".join(html)
