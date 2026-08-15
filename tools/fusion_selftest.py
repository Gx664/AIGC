# -*- coding: utf-8 -*-
"""检测 → 诊断 → 治疗 闭环自检（离线，无需联网）。

用法：
    python tools/fusion_selftest.py

覆盖：
    1. 9 维扫描 + 知网 5 种语言模式 + 11 种深度 AI 痕迹 → 段落级 JSON
    2. 三轮降重协议：受保护片段原样保留、确定性替换、语体守门
    3. 受保护片段（引用/编号/数据/P 值/公式）往返还原
"""

import json
import os
import sys

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
sys.path.insert(0, APP_DIR)

from core.diagnosis import diagnose
from core.therapy import protect_spans, restore_spans, treat


SAMPLE = [
    "近年来，随着人工智能技术的不断发展，该领域受到了广泛关注。首先，深度学习模型在自然语言处理方面取得了显著的成效；其次，多模态学习在图像识别领域展现了巨大的潜力；最后，强化学习在决策系统中发挥着重要作用。综上所述，人工智能技术具有广阔的应用前景，为相关研究提供了重要的参考价值。",
    "SPI和KC含量的增加导致凝胶的L*显著降低（P<0.05），归因于两方面，首先，由于SPI本身呈黄绿色、KC呈浅黄色，浓度升高使凝胶内有色物质总量增加。此外，蛋白质分子的聚集及交联度增加会增强对光线的吸收，降低反射光线强度。上述结果一致表明，蛋白与多糖浓度的变化显著影响复合凝胶的色泽。",
    "本研究旨在构建一套系统性的动态监测体系，从宏观到微观全方位赋能传统产业转型升级。通过深度剖析典型案例，进一步揭示了产业政策与技术创新之间的传导机制。该机制在统计推断意义上获得支持，具有重要的理论意义和实践价值，为后续研究提供了坚实的理论基础。",
]


def main():
    print("=" * 62)
    print("  检测 → 诊断 → 治疗 闭环自检")
    print("=" * 62)

    print("\n[1/4] 诊断（9 维 + 知网 5 模式 + 11 种深度痕迹）...")
    diag = diagnose(SAMPLE, probs=[0.82, 0.74, 0.91], threshold=0.5)
    s = diag["summary"]
    print("      段落 %d ｜ 高风险 %d ｜ 中风险 %d ｜ 整体风险 %s"
          % (s["total_paragraphs"], s["high_risk_paras"], s["medium_risk_paras"], s["overall_risk"]))
    top = "、".join("%s×%d" % (t["zh"], t["count"]) for t in s["top_patterns"][:5])
    print("      主要模式：%s" % top)
    assert s["high_risk_paras"] >= 1, "应至少识别出 1 个高风险段落"
    assert s["top_patterns"], "应识别出若干 AI 痕迹模式"
    assert diag["paragraphs"][0]["sentences"], "段落应包含逐句信息"
    json.dumps(diag, ensure_ascii=False)  # 必须可 JSON 序列化
    print("      OK")

    print("\n[2/4] 治疗（三轮协议，确定性改写）...")
    res = treat(SAMPLE, options={"target_ratio": 0.4})
    sumr = res["summary"]
    print("      已改 %d/%d 段 ｜ 平均修改率 %d%%"
          % (sumr["rewritten"], sumr["selected"], sumr["avg_mod_ratio"] * 100))
    changed = [r for r in res["paragraphs"] if r["changed"]]
    assert changed, "应产生至少一个改写段落"
    for r in changed[:2]:
        assert r["original"] != r["revised"]
        print("      段 %d 修改率 %d%% ｜ 剩余信号：%s"
              % (r["index"], r["mod_ratio"] * 100, "、".join(r["remaining"]) if r["remaining"] else "无"))
    print("      OK")

    print("\n[3/4] 受保护片段往返还原...")
    p = "实验结果表明，样品于 4℃ 下保存 24 h（Zhang et al., 2021），浓度从 12.3% 升至 45.6%，P<0.05，如图 3 所示，β 系数为 0.82，与前人研究[12]一致。"
    masked, spans = protect_spans(p)
    restored = restore_spans(masked, spans)
    assert restored == p, "受保护片段还原失败"
    print("      还原一致（引用/编号/数据/P 值/公式均保留）")
    print("      OK")

    print("\n[4/4] 语体守门（口语化不应被制造）...")
    bad = "说白了，这个结果真的强"
    out = treat([bad])["paragraphs"][0]
    assert "说白了" not in out["revised"] and "真的强" not in out["revised"], "口语词应被改回书面表达"
    print("      改写结果：%s" % out["revised"])
    print("      OK")

    print("\n" + "=" * 62)
    print("  全部通过 ✅")
    print("=" * 62)


if __name__ == "__main__":
    main()
