# -*- coding: utf-8 -*-
"""检测引擎离线自测脚本（无需 UI，纯 CLI）。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core.diagnosis import diagnose
from core.doc_reader import extract_text, split_paragraphs

SAMPLE_AI = """
本研究至关重要，具有重要的理论价值与现实意义。研究表明，该方法显著提升了系统性能，具有深远影响。本研究不仅提高了效率，而且降低了成本，甚至实现了全自动运行。

众所周知，相关研究指出该领域具有广阔的应用前景。从宏观到微观，涵盖了从理论到实践的各个方面。本研究深入分析了现有方法的局限性，提出了一种创新的解决方案。

不仅提高了效率，而且降低了成本，甚至实现了全自动运行。具有良好的应用前景，为后续研究提供了理论和实验依据。尽管取得了一定的成果，但本研究仍存在一些不足之处，有待进一步研究。

相关研究指出，该方法具有重要的理论价值与现实意义。从基础研究到工程应用，该方法体现了系统优化的特征。本研究的结果表明，该方法在多个方面具有显著优势。

未来的研究可以进一步探讨该方法的应用范围。尚需深入研究其在不同场景下的表现。本研究为该领域的发展奠定了重要基础，具有不可忽视的作用。
"""

SAMPLE_HUMAN = """
今天天气不错，我和小明去公园走了走。湖边的柳树发芽了，春天真的来了。
晚上吃了火锅，毛肚很新鲜，就是有点辣。回家路上堵车，到家都九点了。
"""


def test_engine(name, paragraphs, expected_label):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    result = diagnose(paragraphs, probs=None, threshold=0.5)
    summary = result["summary"]
    print(f"  段落数: {summary['total_paragraphs']}")
    print(f"  句子数: {summary['total_sentences']}")
    print(f"  整体风险: {summary['overall_risk']}")
    print(f"  9维风险计数: {summary['risk_count_9dim']}")
    print(f"  高风险段: {summary['high_risk_paras']}")
    print(f"  中风险段: {summary['medium_risk_paras']}")

    if summary.get("top_patterns"):
        print(f"  主要模式:")
        for p in summary["top_patterns"][:5]:
            print(f"    - {p['zh']} ({p['count']}处)")

    if summary.get("style_warnings"):
        print(f"  语体警告: {summary['style_warnings'][:3]}")

    if expected_label == "high":
        ok = summary["overall_risk"] in ("high", "medium")
    else:
        ok = summary["overall_risk"] == expected_label
    status = "PASS" if ok else "FAIL"
    print(f"\n  [{status}] 期望={expected_label}, 实际={summary['overall_risk']}")
    return ok


def test_file(path):
    print(f"\n{'='*60}")
    print(f"  文件检测: {os.path.basename(path)}")
    print(f"{'='*60}")
    text = extract_text(path)
    paras = split_paragraphs(text, min_len=20)
    print(f"  提取段落: {len(paras)}")
    if not paras:
        print("  [SKIP] 无有效段落")
        return True

    result = diagnose(paras, probs=None, threshold=0.5)
    summary = result["summary"]
    print(f"  整体风险: {summary['overall_risk']}")
    print(f"  高风险段: {summary['high_risk_paras']}")
    print(f"  中风险段: {summary['medium_risk_paras']}")

    if summary.get("top_patterns"):
        print(f"  主要模式:")
        for p in summary["top_patterns"][:5]:
            print(f"    - {p['zh']} ({p['count']}处)")

    for pr in result["paragraphs"][:3]:
        lv = pr["risk_level"]
        sc = pr["risk_score"]
        txt = pr["text"][:50]
        print(f"    [{lv:6s}] {sc:.3f}  {txt}...")

    print(f"\n  [PASS] 文件检测完成")
    return True


if __name__ == "__main__":
    ok1 = test_engine("AI 生成文本检测", SAMPLE_AI.split("\n\n"), "high")
    ok2 = test_engine("人工撰写文本检测", SAMPLE_HUMAN.split("\n\n"), "low")

    pdfs = sys.argv[1:]
    ok3 = True
    for p in pdfs:
        if os.path.isfile(p):
            ok3 &= test_file(p)

    print(f"\n{'='*60}")
    all_ok = ok1 and ok2 and ok3
    print(f"  结果: {'ALL PASS' if all_ok else 'SOME FAILED'}")
    print(f"{'='*60}")
    sys.exit(0 if all_ok else 1)

# aigc-toolkit: file purpose marker
