# -*- coding: utf-8 -*-
"""生成 docs/intro_preview.html（中英切换预览页）。
用法：python tools/build_preview.py（在项目根目录运行）。
"""

import base64
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DONATE = os.path.join(ROOT, "app", "assets", "donate")
SPEC = importlib.util.spec_from_file_location(
    "about_text", os.path.join(ROOT, "app", "core", "about_text.py")
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def uri(name, mime):
    with open(os.path.join(DONATE, name), "rb") as f:
        return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode())


T = {
    "lang_btn": {"zh": "EN", "en": "中文"},
    "page_title": {"zh": "AI 检测工具箱 · 简介效果预览", "en": "AIGC Detector Toolkit · Preview"},
    "page_sub": {"zh": "上面是 GitHub 仓库简介效果，下面是软件「关于」窗口效果 · 支持与赞赏已包含", "en": "GitHub README preview above, in-app About window below · Support & donate included"},
    "sec_gh": {"zh": "GITHUB README 预览", "en": "GITHUB README PREVIEW"},
    "sec_app": {"zh": "软件「关于」窗口预览", "en": "APP \"ABOUT\" WINDOW PREVIEW"},
    "p_title": {"zh": "AI 检测工具箱（AIGC Detector Toolkit）", "en": "AIGC Detector Toolkit"},
    "p_quote": {"zh": "免费的本地 AI 率检测 —— 宿舍算力也能跑，论文不上传，结果在自己手里。", "en": "Free local AI-written ratio detection - dorm PCs can run it, your paper never leaves your computer, and results stay in your hands."},
    "h_intro": {"zh": "简介", "en": "Introduction"},
    "intro1": {"zh": "一款本地运行的 AIGC 检测桌面工具：拖入论文（PDF / DOCX / TXT），选择检测引擎，即可得到整篇 AI 生成占比与段落级报告。全程离线推理、多引擎可选、参数高度自定义、同机多卡自动并行、局域网可把室友电脑 / Pad / 手机加入并行计算。", "en": "A fully local AIGC detection desktop tool: drag in a paper (PDF/DOCX/TXT), pick an engine, and get the overall AI ratio plus a paragraph-level report. Fully offline, multi-engine, highly customizable, multi-GPU and LAN cluster ready."},
    "h_inspire": {"zh": "灵感故事", "en": "Inspiration"},
    "inspire_body": {"zh": "灵感来自我的一位大学生朋友：毕业论文要反复查 AI 率，每改一版都要查，学校官方检测入口次数有限而且费钱。我想到：宿舍里打游戏的同学电脑基本都有独立显卡，跑得动本地检测；一张卡不够还能用数据线 / 局域网连室友的电脑，甚至 Pad、手机也能加入算力。于是就有了这个项目。", "en": "Inspired by my college-student friend: his thesis had to be re-checked for AI-written ratio again and again, while the official school service is limited and expensive. Dorm gaming PCs can run local detection, and roommates' computers, Pads and phones can be pooled for more power."},
    "h_authority": {"zh": "权威性依据（为什么可信）", "en": "Why You Can Trust It"},
    "th1": {"zh": "项目 / 论文", "en": "Project / Paper"},
    "th2": {"zh": "权威性证据", "en": "Evidence"},
    "a1_name": {"zh": "SimpleAI / HC3（默认中文引擎）", "en": "SimpleAI / HC3 (default Chinese engine)"},
    "a1_ev": {"zh": "论文 arXiv:2301.07597；数据集、代码、模型全部公开，被大量研究引用", "en": "Paper arXiv:2301.07597; dataset, code and models fully public and widely cited"},
    "a2_name": {"zh": "Fast-DetectGPT（参考实现）", "en": "Fast-DetectGPT (reference implementation)"},
    "a2_ev": {"zh": "论文 arXiv:2310.05130，发表于 ICLR 2024（AI 顶级会议）", "en": "Paper arXiv:2310.05130, published at ICLR 2024 (top AI conference)"},
    "a3_name": {"zh": "GLTR（统计检测方法）", "en": "GLTR (statistical detection method)"},
    "a3_ev": {"zh": "论文 arXiv:1906.04043，来自 MIT，发表于 NeurIPS 2019（顶级会议）", "en": "Paper arXiv:1906.04043, from MIT, published at NeurIPS 2019 (top conference)"},
    "a4_name": {"zh": "DetectGPT（零样本检测）", "en": "DetectGPT (zero-shot detection)"},
    "a4_ev": {"zh": "论文 arXiv:2301.11305，发表于 ICML 2023（顶级会议，Oral），斯坦福；无需训练数据即可零样本检测", "en": "Paper arXiv:2301.11305, published at ICML 2023 (top conference, Oral), Stanford; zero-shot detection without training data"},
    "a5_name": {"zh": "Binoculars（零样本检测）", "en": "Binoculars (zero-shot detection)"},
    "a5_ev": {"zh": "论文 arXiv:2401.12070，发表于 ICML 2024（顶级会议），准确率领先，代码开源", "en": "Paper arXiv:2401.12070, published at ICML 2024 (top conference), state-of-the-art accuracy, open source"},
    "a6_name": {"zh": "RAID（评测基准）", "en": "RAID (benchmark)"},
    "a6_ev": {"zh": "论文 arXiv:2401.09985，发表于 ACL 2024（计算语言学顶级会议）；最大、最全面的 AI 文本检测评测基准（600 万+ 文本）", "en": "Paper arXiv:2401.09985, published at ACL 2024 (top NLP conference); the largest and most comprehensive AI-text detector benchmark (6M+ texts)"},
    "a7_name": {"zh": "MGTBench（评测基准）", "en": "MGTBench (benchmark)"},
    "a7_ev": {"zh": "论文 arXiv:2303.14822；首个面向大语言模型（LLM）的机器生成文本检测基准框架", "en": "Paper arXiv:2303.14822; the first benchmarking framework for machine-generated text detection against LLMs"},
    "note_disclaimer": {"zh": "声明：检测效果受模型与文本类型影响，结果仅供自测参考，请以学校 / 期刊官方认定为准。", "en": "Disclaimer: results depend on the model and text type. For self-checking only - the official verdict of your school/journal always wins."},
    "h_thanks": {"zh": "特别感谢（算力合并）", "en": "Special Thanks (Compute Pooling)"},
    "thanks1": {"zh": "exo（exo-explore/exo，约 4.6 万 star）：P2P 分布式 AI 集群，手机 / Pad / 笔记本自动组网", "en": "exo (exo-explore/exo, ~46k stars): P2P distributed AI cluster with auto-discovery across phones, Pads and laptops"},
    "thanks2": {"zh": "llama.cpp（ggml-org/llama.cpp）：RPC 异构设备分布式推理参考方案", "en": "llama.cpp (ggml-org/llama.cpp): RPC distributed inference across heterogeneous devices"},
    "h_support": {"zh": "支持与赞赏 · Support", "en": "Support & Donate"},
    "support_body": {"zh": "如果这个项目对你有一点帮助，可以请作者喝杯奶茶，支持继续开发：", "en": "If this project helped you a little, buy the author a milk tea to support further development:"},
    "alipay": {"zh": "支付宝 Alipay", "en": "Alipay"},
    "wechat": {"zh": "微信支付 WeChat Pay", "en": "WeChat Pay"},
    "nopressure": {"zh": "想给就给，不想给就不给，绝非道德绑架。作者还是一名学生，零花钱不多，但做这个项目本身已经很有意义，你的支持只是额外的鼓励。", "en": "No pressure at all - give only if you want to. The author is a student; building this project is already meaningful on its own."},
    "h_intl": {"zh": "For international users", "en": "For international users"},
    "intl1": {"zh": "If you don't use Alipay or WeChat Pay, you can also gift any AI API key (any provider is welcome) to gxgx3456@qq.com. Please include: model name, API / model URL and port. If you'd like to be credited, mark it as \"特别感谢 / Special Thanks\".", "en": "If you don't use Alipay or WeChat Pay, you can also gift any AI API key (any provider is welcome) to gxgx3456@qq.com. Please include: model name, API / model URL and port. If you'd like to be credited, mark it as \"Special Thanks\"."},
    "deepseek_note": {"zh": "推荐：DeepSeek —— 很有性价比。如果真要送，DeepSeek V4 Flash 最划算。", "en": "Recommended: DeepSeek - great value. If you really want to gift one, DeepSeek V4 Flash is the most cost-effective choice."},
    "screenshot_cap": {"zh": "DeepSeek 官方用量 / API 页面示例（截图不包含任何 API Key）", "en": "DeepSeek official usage / API page (screenshot contains no API keys)"},
    "h_tech": {"zh": "技术架构", "en": "Tech Stack"},
    "tech1": {"zh": "界面：Python + PySide6（玻璃拟态 UI）", "en": "UI: Python + PySide6 (glassmorphism)"},
    "tech2": {"zh": "检测引擎：transformers（SimpleAI 中文分类 / 困惑度检测）", "en": "Detection: transformers (SimpleAI Chinese classifier / perplexity)"},
    "tech3": {"zh": "多设备：同机多卡自动并行 + 局域网主从节点", "en": "Multi-device: multi-GPU parallelism + LAN master/worker"},
    "tech4": {"zh": "统计：匿名遥测（可关闭）+ 本地运行日志（可导出）", "en": "Statistics: anonymous telemetry (optional) + local run logs (exportable)"},
    "tech5": {"zh": "打包：小体积安装器，运行时环境按需下载（先检查、缺什么装什么、带进度条）", "en": "Packing: small installer; runtime downloads on demand (checks first, with progress bar)"},
    "h_dev": {"zh": "开发声明", "en": "Development Note"},
    "dev_body": {"zh": "本项目由作者独立开发，部分代码由 DeepSeek V4 Flash + Codex 辅助编写与调试。", "en": "Developed independently by the author; part of the code was written and debugged with DeepSeek V4 Flash + Codex."},
    "h_bug": {"zh": "Bug 反馈", "en": "Bug Reports"},
    "bug_body": {"zh": "软件内点击「导出日志」打包日志后，发送至：gxgx3456@qq.com", "en": "Click \"Export Logs\" in the app and send the package to: gxgx3456@qq.com"},
    "h_disclaimer": {"zh": "免责声明", "en": "Disclaimer"},
    "disc_body": {"zh": "本人还是一名学生，代码可能存在不足，不好勿喷，欢迎友善的建议与改进。本项目免费开源，仅供学习交流。", "en": "The author is still a student; the code may have flaws. Please be kind. Free and open source, for learning and exchange only."},
    "license_p": {"zh": "开源协议：MIT", "en": "License: MIT"},
    "app_close": {"zh": "关闭", "en": "Close"},
    "footer_note": {"zh": "预览页仅用于查看效果 · 实际内容以 README.md 与软件「关于」为准", "en": "Preview only - see README.md and the in-app About for the real content"},
}


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__PAGE_TITLE__</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Microsoft YaHei UI","PingFang SC",system-ui,sans-serif; background:#0f172a; color:#e2e8f0; padding:26px; }
  .wrap { max-width:960px; margin:0 auto; }
  .head { text-align:center; margin-bottom:24px; position:relative; }
  .head h1 { font-size:24px; font-weight:800; margin-bottom:6px; }
  .head p { color:#94a3b8; font-size:13px; }
  #langBtn { position:absolute; right:0; top:0; background:rgba(59,130,246,.85); color:#fff; border:none;
    padding:7px 16px; border-radius:10px; cursor:pointer; font-size:13px; }
  section { background:#1e293b; border:1px solid rgba(255,255,255,.08); border-radius:18px; padding:26px 30px; margin-bottom:30px; }
  .sec-label { display:inline-block; font-size:12px; color:#94a3b8; letter-spacing:2px; margin-bottom:14px;
    border:1px dashed #475569; border-radius:8px; padding:4px 10px; }
  h2 { font-size:22px; margin:22px 0 10px; color:#fff; }
  h3 { font-size:17px; margin:18px 0 8px; color:#93c5fd; }
  h4 { font-size:14px; margin:12px 0 6px; color:#cbd5e1; }
  p, li { font-size:14px; line-height:1.85; color:#cbd5e1; }
  ul { padding-left:22px; }
  .quote { border-left:4px solid #3b82f6; background:rgba(59,130,246,.08); padding:12px 16px; border-radius:0 10px 10px 0; margin:10px 0; }
  table { width:100%; border-collapse:collapse; margin:12px 0; font-size:13px; }
  th, td { border:1px solid #334155; padding:9px 12px; text-align:left; vertical-align:top; }
  th { background:#273449; color:#e2e8f0; }
  a { color:#60a5fa; }
  .qr-row { display:flex; gap:24px; justify-content:center; flex-wrap:wrap; margin:18px 0 10px; }
  .qr-item { text-align:center; }
  .qr-item img { width:210px; height:auto; border-radius:14px; border:1px solid #475569; display:block; }
  .qr-item p { font-size:13px; color:#94a3b8; margin-top:6px; }
  .deepseek-img { text-align:center; margin:12px 0; }
  .deepseek-img img { max-width:460px; width:100%; border-radius:12px; border:1px solid #475569; }
  .note { font-size:12px; color:#94a3b8; }
  .appwin { border:1px solid rgba(255,255,255,.14); border-radius:18px; overflow:hidden; box-shadow:0 20px 60px rgba(0,0,0,.5); }
  .app-titlebar { background:linear-gradient(90deg,#2563eb,#7c3aed); color:#fff; font-weight:700; font-size:14px; padding:11px 16px; }
  .app-body { background:linear-gradient(135deg,#dbeafe,#ede9fe,#fce7f3); padding:18px 20px; }
  .app-about { background:rgba(255,255,255,.72); border-radius:14px; padding:18px 20px; font-size:13px; line-height:1.8; color:#1e293b; max-height:460px; overflow:auto; }
  .app-about b { color:#1d4ed8; }
  .app-qr { display:flex; gap:18px; justify-content:center; margin:16px 0 6px; flex-wrap:wrap; }
  .app-qr .item { text-align:center; }
  .app-qr img { width:190px; border-radius:12px; border:1px solid #cbd5e1; }
  .app-qr p { font-size:12px; color:#475569; font-weight:600; margin-top:4px; }
  .app-close { text-align:right; }
  .app-close button { background:linear-gradient(135deg,#2563eb,#7c3aed); color:#fff; border:none; padding:8px 26px; border-radius:12px; font-size:13px; cursor:pointer; }
  footer { text-align:center; color:#64748b; font-size:12px; margin-top:10px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <button id="langBtn" onclick="toggleLang()">EN</button>
    <h1 data-i18n="page_title">AI 检测工具箱 · 简介效果预览</h1>
    <p data-i18n="page_sub">上面是 GitHub 仓库简介效果，下面是软件「关于」窗口效果 · 支持与赞赏已包含</p>
  </div>

  <section>
    <span class="sec-label" data-i18n="sec_gh">GITHUB README 预览</span>
    <h2 data-i18n="p_title">AI 检测工具箱（AIGC Detector Toolkit）</h2>
    <div class="quote" data-i18n="p_quote">免费的本地 AI 率检测 —— 宿舍算力也能跑，论文不上传，结果在自己手里。</div>

    <h3 data-i18n="h_intro">简介</h3>
    <p data-i18n="intro1">一款本地运行的 AIGC 检测桌面工具：拖入论文（PDF / DOCX / TXT），选择检测引擎，即可得到整篇 AI 生成占比与段落级报告。全程离线推理、多引擎可选、参数高度自定义、同机多卡自动并行、局域网可把室友电脑 / Pad / 手机加入并行计算。</p>

    <h3 data-i18n="h_inspire">灵感故事</h3>
    <p data-i18n="inspire_body">灵感来自我的一位大学生朋友：毕业论文要反复查 AI 率，每改一版都要查，学校官方检测入口次数有限而且费钱。我想到：宿舍里打游戏的同学电脑基本都有独立显卡，跑得动本地检测；一张卡不够还能用数据线 / 局域网连室友的电脑，甚至 Pad、手机也能加入算力。于是就有了这个项目。</p>

    <h3 data-i18n="h_authority">权威性依据（为什么可信）</h3>
    <table>
      <tr><th data-i18n="th1">项目 / 论文</th><th data-i18n="th2">权威性证据</th></tr>
      <tr><td data-i18n="a1_name">SimpleAI / HC3（默认中文引擎）</td><td data-i18n="a1_ev">论文 arXiv:2301.07597；数据集、代码、模型全部公开，被大量研究引用</td></tr>
      <tr><td data-i18n="a2_name">Fast-DetectGPT（参考实现）</td><td data-i18n="a2_ev">论文 arXiv:2310.05130，发表于 ICLR 2024（AI 顶级会议）</td></tr>
      <tr><td data-i18n="a3_name">GLTR（统计检测方法）</td><td data-i18n="a3_ev">论文 arXiv:1906.04043，来自 MIT，发表于 NeurIPS 2019（顶级会议）</td></tr>
      <tr><td data-i18n="a4_name">DetectGPT（零样本检测）</td><td data-i18n="a4_ev">论文 arXiv:2301.11305，发表于 ICML 2023（顶级会议，Oral），斯坦福；无需训练数据即可零样本检测</td></tr>
      <tr><td data-i18n="a5_name">Binoculars（零样本检测）</td><td data-i18n="a5_ev">论文 arXiv:2401.12070，发表于 ICML 2024（顶级会议），准确率领先，代码开源</td></tr>
      <tr><td data-i18n="a6_name">RAID（评测基准）</td><td data-i18n="a6_ev">论文 arXiv:2401.09985，发表于 ACL 2024（计算语言学顶级会议）；最大、最全面的 AI 文本检测评测基准（600 万+ 文本）</td></tr>
      <tr><td data-i18n="a7_name">MGTBench（评测基准）</td><td data-i18n="a7_ev">论文 arXiv:2303.14822；首个面向大语言模型（LLM）的机器生成文本检测基准框架</td></tr>
    </table>
    <p class="note" data-i18n="note_disclaimer">声明：检测效果受模型与文本类型影响，结果仅供自测参考，请以学校 / 期刊官方认定为准。</p>

    <h3 data-i18n="h_thanks">特别感谢（算力合并）</h3>
    <ul>
      <li data-i18n="thanks1">exo（exo-explore/exo，约 4.6 万 star）：P2P 分布式 AI 集群，手机 / Pad / 笔记本自动组网</li>
      <li data-i18n="thanks2">llama.cpp（ggml-org/llama.cpp）：RPC 异构设备分布式推理参考方案</li>
    </ul>

    <h3 data-i18n="h_support">支持与赞赏 · Support</h3>
    <p data-i18n="support_body">如果这个项目对你有一点帮助，可以请作者喝杯奶茶，支持继续开发：</p>
    <div class="qr-row">
      <div class="qr-item"><img src="__IMG_ALIPAY__" alt="支付宝赞赏码"><p data-i18n="alipay">支付宝 Alipay</p></div>
      <div class="qr-item"><img src="__IMG_WECHAT__" alt="微信支付赞赏码"><p data-i18n="wechat">微信支付 WeChat Pay</p></div>
    </div>
    <p><b data-i18n="nopressure">想给就给，不想给就不给，绝非道德绑架。作者还是一名学生，零花钱不多，但做这个项目本身已经很有意义，你的支持只是额外的鼓励。</b></p>
    <h4 data-i18n="h_intl">For international users</h4>
    <p data-i18n="intl1">If you don't use Alipay or WeChat Pay, you can also gift any AI API key (any provider is welcome) to gxgx3456@qq.com. Please include: model name, API / model URL and port. If you'd like to be credited, mark it as "特别感谢 / Special Thanks".</p>
    <p data-i18n="deepseek_note">推荐：DeepSeek —— 很有性价比。如果真要送，DeepSeek V4 Flash 最划算。</p>
    <div class="deepseek-img"><img src="__IMG_DEEPSEEK__" alt="DeepSeek 用量页面示例"><p class="note" data-i18n="screenshot_cap">DeepSeek 官方用量 / API 页面示例（截图不包含任何 API Key）</p></div>

    <h3 data-i18n="h_tech">技术架构</h3>
    <ul>
      <li data-i18n="tech1">界面：Python + PySide6（玻璃拟态 UI）</li>
      <li data-i18n="tech2">检测引擎：transformers（SimpleAI 中文分类 / 困惑度检测）</li>
      <li data-i18n="tech3">多设备：同机多卡自动并行 + 局域网主从节点</li>
      <li data-i18n="tech4">统计：匿名遥测（可关闭）+ 本地运行日志（可导出）</li>
      <li data-i18n="tech5">打包：小体积安装器，运行时环境按需下载（先检查、缺什么装什么、带进度条）</li>
    </ul>

    <h3 data-i18n="h_dev">开发声明</h3>
    <p data-i18n="dev_body">本项目由作者独立开发，部分代码由 DeepSeek V4 Flash + Codex 辅助编写与调试。</p>

    <h3 data-i18n="h_bug">Bug 反馈</h3>
    <p data-i18n="bug_body">软件内点击「导出日志」打包日志后，发送至：gxgx3456@qq.com</p>

    <h3 data-i18n="h_disclaimer">免责声明</h3>
    <p data-i18n="disc_body">本人还是一名学生，代码可能存在不足，不好勿喷，欢迎友善的建议与改进。本项目免费开源，仅供学习交流。</p>
    <p data-i18n="license_p">开源协议：<b>MIT</b></p>
  </section>

  <section>
    <span class="sec-label" data-i18n="sec_app">软件「关于」窗口预览</span>
    <div class="appwin">
      <div class="app-titlebar" data-i18n="app_title">AI 检测工具箱 v1.0 · 关于</div>
      <div class="app-body">
        <div class="app-about"><pre id="appText" style="font-family:inherit;white-space:pre-wrap;"></pre></div>
        <div class="app-qr">
          <div class="item"><img src="__IMG_ALIPAY__" alt="支付宝"><p data-i18n="alipay">支付宝 Alipay</p></div>
          <div class="item"><img src="__IMG_WECHAT__" alt="微信支付"><p data-i18n="wechat">微信支付 WeChat Pay</p></div>
        </div>
        <div class="app-close"><button data-i18n="app_close">关闭</button></div>
      </div>
    </div>
  </section>

  <footer data-i18n="footer_note">预览页仅用于查看效果 · 实际内容以 README.md 与软件「关于」为准</footer>
</div>
<script>
const I18N = __I18N_JSON__;
const ABOUT_ZH = __APP_ZH__;
const ABOUT_EN = __APP_EN__;
let lang = 'zh';
try { lang = localStorage.getItem('aigc_lang') || 'zh'; } catch (e) {}
function t(k){ const o = I18N[k]; return o ? (o[lang] || o.zh) : k; }
function applyLang(){
  document.querySelectorAll('[data-i18n]').forEach(function(el){
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  document.getElementById('appText').textContent = lang === 'zh' ? ABOUT_ZH : ABOUT_EN;
  document.title = t('page_title');
  const lb = document.getElementById('langBtn');
  if (lb) lb.textContent = lang === 'zh' ? 'EN' : '中文';
}
function toggleLang(){
  lang = lang === 'zh' ? 'en' : 'zh';
  try { localStorage.setItem('aigc_lang', lang); } catch (e) {}
  applyLang();
}
applyLang();
</script>
</body>
</html>
"""


def main():
    out = HTML
    out = out.replace("__IMG_ALIPAY__", uri("alipay.jpg", "image/jpeg"))
    out = out.replace("__IMG_WECHAT__", uri("wechat_pay.jpg", "image/jpeg"))
    out = out.replace("__IMG_DEEPSEEK__", uri("deepseek_usage.png", "image/png"))
    t_en = dict(T)
    t_en["app_title"] = {"zh": "AI 检测工具箱 v1.0 · 关于", "en": "AIGC Detector Toolkit v1.0 · About"}
    out = out.replace("__I18N_JSON__", json.dumps(t_en, ensure_ascii=False))
    out = out.replace("__APP_ZH__", json.dumps(MOD.ABOUT_TEXT, ensure_ascii=False))
    out = out.replace("__APP_EN__", json.dumps(MOD.ABOUT_TEXT_EN, ensure_ascii=False))
    out = out.replace("__PAGE_TITLE__", t_en["page_title"]["zh"])
    dest = os.path.join(ROOT, "docs", "intro_preview.html")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    print("preview written:", dest, os.path.getsize(dest))


if __name__ == "__main__":
    main()
