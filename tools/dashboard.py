"""AI 检测工具箱 · 数据看板（本地运行，自动刷新）。

只依赖 Python 标准库。数据从 PostHog Query API 拉取，
页面每 30 秒自动刷新，打开浏览器即可查看。
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "dashboard_config.json")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


CFG = load_config()
PH = CFG.get("posthog", {})
API_KEY = PH.get("personal_api_key", "").strip()
PROJECT_ID = PH.get("project_id", 0)
HOST = (PH.get("host") or "https://us.posthog.com").rstrip("/")
GH = CFG.get("github", {})
GH_REPO = GH.get("repo", "").strip()
try:
    REFRESH_MS = max(1000, int(CFG.get("refresh_seconds", 1)) * 1000)
except Exception:
    REFRESH_MS = 1000
LISTEN = str(CFG.get("listen", "127.0.0.1"))
ACCESS_TOKEN = str(CFG.get("access_token", "") or "")


def ph_query(hogql):
    if not API_KEY or not PROJECT_ID:
        raise RuntimeError("未配置 PostHog 个人 API 密钥（见 dashboard_config.json）")
    url = "%s/api/projects/%s/query/" % (HOST, PROJECT_ID)
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": hogql}}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": "Bearer " + API_KEY,
            "Content-Type": "application/json",
            "User-Agent": "aigc-dashboard",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError("PostHog API 错误 %s：%s" % (e.code, detail))
    if "results" not in data:
        raise RuntimeError("PostHog 返回异常：" + str(data)[:300])
    return data["results"]


def _num(hogql):
    rows = ph_query(hogql)
    if not rows or not rows[0]:
        return 0
    v = rows[0][0]
    if v is None:
        return 0
    try:
        return round(float(v), 1)
    except Exception:
        return v


def _pairs(hogql):
    rows = ph_query(hogql)
    return [[str(r[0]) if r[0] is not None else "未知", r[1]] for r in rows]


def github_downloads():
    if not GH_REPO:
        return None
    url = "https://api.github.com/repos/%s/releases" % GH_REPO
    req = urllib.request.Request(url, headers={"User-Agent": "aigc-dashboard"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            releases = json.loads(r.read().decode("utf-8"))
    except Exception:
        return {"error": "GitHub 下载统计获取失败"}
    total = 0
    items = []
    for rel in releases:
        tag = rel.get("tag_name", "?")
        for asset in rel.get("assets", []):
            total += asset.get("download_count", 0)
        items.append({"tag": tag, "count": sum(a.get("download_count", 0) for a in rel.get("assets", []))})
    return {"total": total, "releases": items[:10]}


def overview():
    out = {
        "ok": True,
        "configured": bool(API_KEY and PROJECT_ID),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "error": None,
    }
    if not out["configured"]:
        out["ok"] = False
        out["error"] = "未配置 personal_api_key / project_id，请编辑 dashboard_config.json"
        return out
    try:
        out["total_starts"] = _num("SELECT count() FROM events WHERE event='app_start'")
        out["today_starts"] = _num(
            "SELECT count() FROM events WHERE event='app_start' AND timestamp >= today()"
        )
        out["week_active"] = _num(
            "SELECT uniqExact(distinct_id) FROM events WHERE event IN ('app_start','heartbeat','detection_done') "
            "AND timestamp >= now() - INTERVAL 7 DAY"
        )
        out["month_active"] = _num(
            "SELECT uniqExact(distinct_id) FROM events WHERE event IN ('app_start','heartbeat','detection_done') "
            "AND timestamp >= now() - INTERVAL 30 DAY"
        )
        out["total_detections"] = _num(
            "SELECT count() FROM events WHERE event='detection_done'"
        )
        out["avg_session"] = _num(
            "SELECT avg(toFloat64OrNull(properties.duration_sec)) FROM events "
            "WHERE event='app_close' AND toFloat64OrNull(properties.duration_sec) > 0"
        )
        out["online_now"] = _num(
            "SELECT uniqExact(distinct_id) FROM events "
            "WHERE event='heartbeat' AND timestamp >= now() - INTERVAL 5 MINUTE"
        )
        rows = ph_query(
            "SELECT toDate(timestamp) AS d, count() AS c FROM events "
            "WHERE event='app_start' AND timestamp >= now() - INTERVAL 30 DAY "
            "GROUP BY d ORDER BY d"
        )
        out["trend"] = [{"date": str(r[0]), "count": r[1]} for r in rows]
        out["engines"] = _pairs(
            "SELECT properties.engine, count() FROM events "
            "WHERE event='detection_done' AND properties.engine != '' "
            "GROUP BY properties.engine ORDER BY count() DESC LIMIT 8"
        )
        out["gpus"] = _pairs(
            "SELECT properties.gpu, count() FROM events "
            "WHERE event='app_start' AND properties.gpu != '' "
            "GROUP BY properties.gpu ORDER BY count() DESC LIMIT 8"
        )
        out["versions"] = _pairs(
            "SELECT properties.app_version, count() FROM events "
            "WHERE properties.app_version != '' "
            "GROUP BY properties.app_version ORDER BY count() DESC LIMIT 8"
        )
        out["downloads"] = github_downloads()
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)
    return out


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 检测工具箱 · 数据看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root { --glass: rgba(255,255,255,0.07); --border: rgba(255,255,255,0.12); }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Microsoft YaHei UI","PingFang SC",sans-serif; color:#e2e8f0;
    background:linear-gradient(135deg,#0b1220 0%,#101b3c 45%,#1e1445 100%);
    min-height:100vh; padding:28px; }
  .wrap { max-width:1200px; margin:0 auto; }
  header { display:flex; align-items:center; justify-content:space-between; margin-bottom:22px; flex-wrap:wrap; gap:10px; }
  h1 { font-size:24px; font-weight:700; letter-spacing:.5px; }
  h1 small { font-size:13px; color:#94a3b8; font-weight:400; margin-left:10px; }
  .hdr-right { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  .badge { padding:6px 14px; border-radius:999px; font-size:13px; background:var(--glass); border:1px solid var(--border); backdrop-filter:blur(12px); }
  .badge.live { color:#34d399; }
  button { background:rgba(59,130,246,.85); color:#fff; border:none; padding:8px 18px; border-radius:10px; cursor:pointer; font-size:14px; }
  button:hover { background:rgba(37,99,235,1); }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:16px; margin-bottom:20px; }
  .card { background:var(--glass); border:1px solid var(--border); border-radius:20px; padding:20px; backdrop-filter:blur(16px); box-shadow:0 10px 30px rgba(0,0,0,.25); }
  .card .num { font-size:32px; font-weight:800; margin-top:6px; color:#fff; }
  .card .lbl { font-size:13px; color:#94a3b8; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px; }
  .chart-box { background:var(--glass); border:1px solid var(--border); border-radius:20px; padding:18px; backdrop-filter:blur(16px); box-shadow:0 10px 30px rgba(0,0,0,.25); }
  .chart-box h3 { font-size:15px; margin-bottom:10px; color:#cbd5e1; }
  .err { background:rgba(220,38,38,.15); border:1px solid rgba(248,113,113,.4); color:#fca5a5; padding:14px 18px; border-radius:14px; margin-bottom:18px; font-size:14px; }
  canvas { max-height:280px; }
  footer { text-align:center; color:#64748b; font-size:12px; margin-top:26px; }
  #aboutModal { display:none; position:fixed; inset:0; z-index:200; background:rgba(5,10,22,.72);
    align-items:center; justify-content:center; padding:20px; }
  #aboutModal.show { display:flex; }
  .about-box { background:linear-gradient(160deg,#152044,#1e1445); border:1px solid var(--border);
    border-radius:20px; max-width:680px; width:100%; max-height:84vh; overflow:auto;
    padding:24px 28px; font-size:13px; line-height:1.8; }
  .about-box h2 { font-size:18px; margin-bottom:10px; color:#fff; }
  .about-box h3 { font-size:15px; margin:16px 0 6px; color:#93c5fd; }
  .about-box p, .about-box li { color:#cbd5e1; }
  .about-box ul { padding-left:22px; }
  .about-box a { color:#60a5fa; }
  .donate-row { display:flex; gap:18px; justify-content:center; flex-wrap:wrap; margin:12px 0 6px; }
  .donate-item { text-align:center; }
  .donate-item img { width:180px; height:auto; border-radius:14px; border:1px solid var(--border); }
  .donate-item p { font-size:13px; color:#94a3b8; margin-top:6px; }
  .about-close { margin-top:16px; text-align:right; }
  @media (max-width:800px){ .grid2{ grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1><span data-i18n="h1_main">AI 检测工具箱</span> <small data-i18n="h1_sub">使用数据看板</small></h1>
    <div class="hdr-right">
      <span class="badge live" id="online">在线 --</span>
      <span class="badge" id="updated">更新 --</span>
      <button onclick="refresh()" data-i18n="refresh">立即刷新</button>
      <button onclick="openAbout()" data-i18n="about">关于</button>
      <button id="langBtn" onclick="toggleLang()">EN</button>
    </div>
  </header>
  <div id="errbox" class="err" style="display:none"></div>
  <div class="cards">
    <div class="card"><div class="lbl" data-i18n="total_starts">总启动次数</div><div class="num" id="totalStarts">--</div></div>
    <div class="card"><div class="lbl" data-i18n="today_starts">今日启动</div><div class="num" id="todayStarts">--</div></div>
    <div class="card"><div class="lbl" data-i18n="week_active">本周活跃设备</div><div class="num" id="weekActive">--</div></div>
    <div class="card"><div class="lbl" data-i18n="month_active">本月活跃设备</div><div class="num" id="monthActive">--</div></div>
    <div class="card"><div class="lbl" data-i18n="total_detections">总检测次数</div><div class="num" id="totalDetections">--</div></div>
    <div class="card"><div class="lbl" data-i18n="avg_session">平均使用时长(秒)</div><div class="num" id="avgSession">--</div></div>
  </div>
  <div id="dlbox" class="cards" style="display:none"></div>
  <div class="grid2">
    <div class="chart-box"><h3 data-i18n="c_trend">近 30 天启动趋势</h3><canvas id="cTrend"></canvas></div>
    <div class="chart-box"><h3 data-i18n="c_engine">引擎使用分布</h3><canvas id="cEngine"></canvas></div>
  </div>
  <div class="grid2">
    <div class="chart-box"><h3 data-i18n="c_gpu">显卡分布</h3><canvas id="cGpu"></canvas></div>
    <div class="chart-box"><h3 data-i18n="c_ver">版本分布</h3><canvas id="cVer"></canvas></div>
  </div>
  <div id="aboutModal" onclick="if(event.target===this)closeAbout()">
    <div class="about-box">
      <h2 data-i18n="m_title">关于 AI 检测工具箱</h2>
      <p data-i18n="m_intro">免费、本地的 AI 率检测工具：拖入论文即可得到整篇 AI 生成占比与段落级报告，论文不上传任何平台。</p>
      <h3 data-i18n="m_inspire">灵感</h3>
      <p data-i18n="m_inspire_body">我的大学生朋友毕业论文要反复查 AI 率，学校官方入口次数有限还费钱。我想：宿舍里打游戏的同学电脑都有独立显卡，本地就跑得动；不够还能连室友电脑、Pad、手机合并算力。</p>
      <h3 data-i18n="m_authority">权威性依据</h3>
      <ul>
        <li data-i18n="m_a1">SimpleAI / HC3：arXiv:2301.07597，数据集、代码、模型全公开</li>
        <li data-i18n="m_a2">Fast-DetectGPT：arXiv:2310.05130，发表于 ICLR 2024</li>
        <li data-i18n="m_a3">GLTR：arXiv:1906.04043，来自 MIT，发表于 NeurIPS 2019</li>
        <li data-i18n="m_a4">DetectGPT：arXiv:2301.11305，ICML 2023（Oral），斯坦福</li>
        <li data-i18n="m_a5">Binoculars：arXiv:2401.12070，ICML 2024，代码开源</li>
        <li data-i18n="m_a6">RAID：arXiv:2401.09985，ACL 2024，最大评测基准（600 万+ 文本）</li>
        <li data-i18n="m_a7">MGTBench：arXiv:2303.14822，首个 LLM 检测基准框架</li>
      </ul>
      <p data-i18n="m_disclaimer">检测结果仅供自测参考，请以学校 / 期刊官方认定为准。</p>
      <h3 data-i18n="m_thanks">特别感谢（算力合并）</h3>
      <ul>
        <li data-i18n="m_exo">exo（exo-explore/exo，约 4.6 万 star）：P2P 分布式 AI 集群，手机 / Pad / 笔记本自动组网</li>
        <li data-i18n="m_llama">llama.cpp（ggml-org/llama.cpp）：RPC 异构设备分布式推理参考方案</li>
      </ul>
      <h3 data-i18n="m_support">支持与赞赏 · Support</h3>
      <p data-i18n="m_support_body">如果这个项目对你有一点帮助，可以请作者喝杯奶茶，支持继续开发：</p>
      <div class="donate-row">
        <div class="donate-item">
          <img src="__DATA_ALIPAY__" alt="支付宝赞赏码 / Alipay">
          <p data-i18n="alipay">支付宝 Alipay</p>
        </div>
        <div class="donate-item">
          <img src="__DATA_WECHAT__" alt="微信支付赞赏码 / WeChat Pay">
          <p data-i18n="wechat">微信支付 WeChat Pay</p>
        </div>
      </div>
      <p data-i18n="m_nopressure">想给就给，不想给就不给，绝非道德绑架。作者还是一名初中生，零花钱不多，但做这个项目本身已经很有意义。</p>
      <p data-i18n="m_intl">For international users: you can also gift any AI API key (model name, URL and port required) to gxgx3456@qq.com. Recommended: DeepSeek V4 Flash — platform.deepseek.com/api_keys</p>
      <h3 data-i18n="m_dev">开发声明</h3>
      <p data-i18n="m_dev_body">部分代码由 DeepSeek V4 Flash + Codex 辅助开发；作者还是学生，发布时 14 岁。</p>
      <p data-i18n="m_feedback">反馈 / Bug 报告：gxgx3456@qq.com（桌面端可导出运行日志）</p>
      <p data-i18n="m_license">开源协议：MIT</p>
      <div class="about-close"><button onclick="closeAbout()" data-i18n="close">关闭</button></div>
    </div>
  </div>
  <footer data-i18n="footer">数据来源 PostHog · 自动刷新 · 仅展示匿名元数据统计</footer>
</div>
<script>
const REFRESH_MS = __REFRESH_MS__;
const TOKEN = new URLSearchParams(location.search).get('token') || '';
const charts = {};
const I18N = {
  h1_main:{zh:'AI 检测工具箱',en:'AIGC Detector Toolkit'},
  h1_sub:{zh:'使用数据看板',en:'Usage Dashboard'},
  refresh:{zh:'立即刷新',en:'Refresh'},
  about:{zh:'关于',en:'About'},
  online:{zh:'在线',en:'Online'},
  updated:{zh:'更新',en:'Updated'},
  total_starts:{zh:'总启动次数',en:'Total Starts'},
  today_starts:{zh:'今日启动',en:'Today'},
  week_active:{zh:'本周活跃设备',en:'Active (7d)'},
  month_active:{zh:'本月活跃设备',en:'Active (30d)'},
  total_detections:{zh:'总检测次数',en:'Total Detections'},
  avg_session:{zh:'平均使用时长(秒)',en:'Avg. Session (s)'},
  c_trend:{zh:'近 30 天启动趋势',en:'Starts - Last 30 Days'},
  c_engine:{zh:'引擎使用分布',en:'Engine Usage'},
  c_gpu:{zh:'显卡分布',en:'GPU Distribution'},
  c_ver:{zh:'版本分布',en:'Version Distribution'},
  gh_downloads:{zh:'GitHub 累计下载',en:'GitHub Total Downloads'},
  conn_fail:{zh:'连接看板服务失败：',en:'Failed to connect to dashboard service: '},
  unknown_error:{zh:'未知错误',en:'Unknown error'},
  footer:{zh:'数据来源 PostHog · 自动刷新 · 仅展示匿名元数据统计',en:'Data: PostHog · Auto-refresh · Anonymous metadata only'},
  m_title:{zh:'关于 AI 检测工具箱',en:'About AIGC Detector Toolkit'},
  m_intro:{zh:'免费、本地的 AI 率检测工具：拖入论文即可得到整篇 AI 生成占比与段落级报告，论文不上传任何平台。',en:'A free, local AI-written ratio detector: drop in a paper and get the overall AI ratio plus a paragraph-level report. Your paper never leaves your device.'},
  m_inspire:{zh:'灵感',en:'Inspiration'},
  m_inspire_body:{zh:'我的大学生朋友毕业论文要反复查 AI 率，学校官方入口次数有限还费钱。我想：宿舍里打游戏的同学电脑都有独立显卡，本地就跑得动；不够还能连室友电脑、Pad、手机合并算力。',en:'My college-student friend had to re-check his thesis for AI-written ratio repeatedly; the official school service is limited and expensive. Dorm gaming PCs have GPUs that can run local detection, and you can pool roommates\' PCs, Pads and phones if needed.'},
  m_authority:{zh:'权威性依据',en:'Why You Can Trust It'},
  m_a1:{zh:'SimpleAI / HC3：arXiv:2301.07597，数据集、代码、模型全公开',en:'SimpleAI / HC3: arXiv:2301.07597 - dataset, code and models fully public'},
  m_a2:{zh:'Fast-DetectGPT：arXiv:2310.05130，发表于 ICLR 2024',en:'Fast-DetectGPT: arXiv:2310.05130, published at ICLR 2024'},
  m_a3:{zh:'GLTR：arXiv:1906.04043，来自 MIT，发表于 NeurIPS 2019',en:'GLTR: arXiv:1906.04043, from MIT, published at NeurIPS 2019'},
  m_a4:{zh:'DetectGPT：arXiv:2301.11305，ICML 2023（Oral），斯坦福',en:'DetectGPT: arXiv:2301.11305, ICML 2023 (Oral), Stanford'},
  m_a5:{zh:'Binoculars：arXiv:2401.12070，ICML 2024，代码开源',en:'Binoculars: arXiv:2401.12070, ICML 2024, open source'},
  m_a6:{zh:'RAID：arXiv:2401.09985，ACL 2024，最大评测基准（600 万+ 文本）',en:'RAID: arXiv:2401.09985, ACL 2024, largest benchmark (6M+ texts)'},
  m_a7:{zh:'MGTBench：arXiv:2303.14822，首个 LLM 检测基准框架',en:'MGTBench: arXiv:2303.14822, first LLM detection benchmark'},
  m_disclaimer:{zh:'检测结果仅供自测参考，请以学校 / 期刊官方认定为准。',en:'Results are for self-checking only - the official verdict of your school/journal always wins.'},
  m_thanks:{zh:'特别感谢（算力合并）',en:'Special Thanks (Compute Pooling)'},
  m_exo:{zh:'exo（exo-explore/exo，约 4.6 万 star）：P2P 分布式 AI 集群，手机 / Pad / 笔记本自动组网',en:'exo (exo-explore/exo, ~46k stars): P2P distributed AI cluster with auto-discovery across phones, Pads and laptops'},
  m_llama:{zh:'llama.cpp（ggml-org/llama.cpp）：RPC 异构设备分布式推理参考方案',en:'llama.cpp (ggml-org/llama.cpp): RPC distributed inference across heterogeneous devices'},
  m_support:{zh:'支持与赞赏 · Support',en:'Support & Donate'},
  m_support_body:{zh:'如果这个项目对你有一点帮助，可以请作者喝杯奶茶，支持继续开发：',en:'If this project helped you a little, buy the author a milk tea to support further development:'},
  alipay:{zh:'支付宝 Alipay',en:'Alipay'},
  wechat:{zh:'微信支付 WeChat Pay',en:'WeChat Pay'},
  m_nopressure:{zh:'想给就给，不想给就不给，绝非道德绑架。作者还是一名初中生，零花钱不多，但做这个项目本身已经很有意义。',en:'No pressure at all - give only if you want to. The author is a middle-school student; building this project is already meaningful on its own.'},
  m_intl:{zh:'For international users: you can also gift any AI API key (model name, URL and port required) to gxgx3456@qq.com. Recommended: DeepSeek V4 Flash — platform.deepseek.com/api_keys',en:'For international users: you can also gift any AI API key (model name, URL and port required) to gxgx3456@qq.com. Recommended: DeepSeek V4 Flash - platform.deepseek.com/api_keys'},
  m_dev:{zh:'开发声明',en:'Development Note'},
  m_dev_body:{zh:'部分代码由 DeepSeek V4 Flash + Codex 辅助开发；作者还是学生，发布时 14 岁。',en:'Partly written and debugged with DeepSeek V4 Flash + Codex; the author was 14 when this project was released.'},
  m_feedback:{zh:'反馈 / Bug 报告：gxgx3456@qq.com（桌面端可导出运行日志）',en:'Feedback / Bug reports: gxgx3456@qq.com (export logs from the desktop app)'},
  m_license:{zh:'开源协议：MIT',en:'License: MIT'},
  close:{zh:'关闭',en:'Close'}
};
let lang = 'zh';
try { lang = localStorage.getItem('aigc_lang') || 'zh'; } catch (e) {}
function t(k){ const o = I18N[k]; return o ? (o[lang] || o.zh) : k; }
function applyLang(){
  document.querySelectorAll('[data-i18n]').forEach(function(el){
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  const lb = document.getElementById('langBtn');
  if (lb) lb.textContent = lang === 'zh' ? 'EN' : '中文';
}
function toggleLang(){
  lang = lang === 'zh' ? 'en' : 'zh';
  try { localStorage.setItem('aigc_lang', lang); } catch (e) {}
  applyLang();
  refresh();
}
function openAbout(){ document.getElementById('aboutModal').classList.add('show'); }
function closeAbout(){ document.getElementById('aboutModal').classList.remove('show'); }
function mkChart(id, cfg) {
  const el = document.getElementById(id);
  if (charts[id]) { charts[id].destroy(); }
  charts[id] = new Chart(el, cfg);
}
const GRID = 'rgba(255,255,255,0.08)';
const PALETTE = ['#3b82f6','#8b5cf6','#f59e0b','#10b981','#ef4444','#ec4899','#06b6d4','#84cc16'];
function labelsAndData(pairs) {
  const labels = pairs.map(p => p[0].length > 14 ? p[0].slice(0,13)+'…' : p[0]);
  const data = pairs.map(p => p[1]);
  return {labels, data};
}
function fmt(n) {
  if (n === null || n === undefined) return '--';
  return Number(n).toLocaleString();
}
async function refresh() {
  try {
    const res = await fetch('/api/overview' + (TOKEN ? '?token=' + encodeURIComponent(TOKEN) : ''));
    const d = await res.json();
    document.getElementById('updated').textContent = t('updated') + ' ' + d.updated;
    const err = document.getElementById('errbox');
    if (!d.ok) {
      err.style.display = 'block';
      err.textContent = '⚠ ' + (d.error || t('unknown_error'));
      return;
    }
    err.style.display = 'none';
    document.getElementById('totalStarts').textContent = fmt(d.total_starts);
    document.getElementById('todayStarts').textContent = fmt(d.today_starts);
    document.getElementById('weekActive').textContent = fmt(d.week_active);
    document.getElementById('monthActive').textContent = fmt(d.month_active);
    document.getElementById('totalDetections').textContent = fmt(d.total_detections);
    document.getElementById('avgSession').textContent = fmt(d.avg_session);
    document.getElementById('online').textContent = t('online') + ' ' + fmt(d.online_now);
    mkChart('cTrend', { type:'line', data:{ labels:d.trend.map(t=>t.date), datasets:[{ label:'启动次数', data:d.trend.map(t=>t.count), borderColor:'#3b82f6', backgroundColor:'rgba(59,130,246,0.15)', fill:true, tension:0.35 }] }, options:{ plugins:{legend:{display:false}}, scales:{ x:{grid:{color:GRID}}, y:{grid:{color:GRID}} } } });
    const eng = labelsAndData(d.engines);
    mkChart('cEngine', { type:'doughnut', data:{ labels:eng.labels, datasets:[{ data:eng.data, backgroundColor:PALETTE }] }, options:{ plugins:{legend:{position:'bottom'}} } });
    const gpu = labelsAndData(d.gpus);
    mkChart('cGpu', { type:'bar', data:{ labels:gpu.labels, datasets:[{ label:'设备数', data:gpu.data, backgroundColor:'#8b5cf6' }] }, options:{ plugins:{legend:{display:false}}, scales:{ x:{grid:{color:GRID}}, y:{grid:{color:GRID}} } } });
    const ver = labelsAndData(d.versions);
    mkChart('cVer', { type:'bar', data:{ labels:ver.labels, datasets:[{ label:'次数', data:ver.data, backgroundColor:'#10b981' }] }, options:{ plugins:{legend:{display:false}}, scales:{ x:{grid:{color:GRID}}, y:{grid:{color:GRID}} } } });
    if (d.downloads) {
      const box = document.getElementById('dlbox');
      box.style.display = 'grid';
      box.innerHTML = '<div class="card"><div class="lbl">' + t('gh_downloads') + '</div><div class="num">' + fmt(d.downloads.total) + '</div></div>';
      if (d.downloads.releases) {
        const html = d.downloads.releases.map(r => '<div class="card"><div class="lbl">' + r.tag + '</div><div class="num">' + fmt(r.count) + '</div></div>').join('');
        box.innerHTML += html;
      }
    }
  } catch (e) {
    const err = document.getElementById('errbox');
    err.style.display = 'block';
    err.textContent = '⚠ ' + t('conn_fail') + e;
  }
}
applyLang();
refresh();
setInterval(refresh, REFRESH_MS);
</script>
</body>
</html>
"""

HTML = HTML.replace("__REFRESH_MS__", str(REFRESH_MS))

try:
    from dashboard_assets import ALIPAY_URI, WECHAT_URI
except Exception:
    ALIPAY_URI = WECHAT_URI = ""
if not ALIPAY_URI:
    ALIPAY_URI = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
if not WECHAT_URI:
    WECHAT_URI = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
HTML = HTML.replace("__DATA_ALIPAY__", ALIPAY_URI)
HTML = HTML.replace("__DATA_WECHAT__", WECHAT_URI)

LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>数据看板</title>
<style>body{background:#0b1220;color:#e2e8f0;font-family:"Microsoft YaHei UI",sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-radius:20px;padding:36px;width:300px;box-shadow:0 10px 30px rgba(0,0,0,.3)}
h2{margin:0 0 8px;font-size:20px} p{color:#94a3b8;font-size:13px;margin:0 0 12px}
input{width:100%;padding:11px;border-radius:10px;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.08);color:#fff;margin:10px 0;box-sizing:border-box;outline:none}
button{width:100%;padding:11px;background:#3b82f6;color:#fff;border:none;border-radius:10px;cursor:pointer;font-size:15px}</style>
</head><body><div class="card"><h2>数据看板</h2><p>请输入访问密码</p>
<input id="p" type="password" placeholder="访问密码" onkeydown="if(event.key==='Enter')go()">
<button onclick="go()">进入</button></div>
<script>function go(){location.href='/?token='+encodeURIComponent(document.getElementById('p').value)}</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path, _, query = self.path.partition("?")
        params = {}
        if query:
            for kv in query.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[k] = v
        authed = (not ACCESS_TOKEN) or params.get("token") == ACCESS_TOKEN
        if path.startswith("/api/overview"):
            if not authed:
                self._send(403, "application/json", json.dumps(
                    {"ok": False, "error": "访问密码错误"}, ensure_ascii=False).encode("utf-8"))
                return
            body = json.dumps(overview(), ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json", body)
        else:
            body = (HTML if authed else LOGIN_HTML).encode("utf-8")
            self._send(200, "text/html", body)

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    host = sys.argv[2] if len(sys.argv) > 2 else LISTEN
    srv = ThreadingHTTPServer((host, port), Handler)
    print("数据看板已启动：http://127.0.0.1:%d" % port)
    if ACCESS_TOKEN:
        print("已启用访问密码（公网部署请保留）")
    if host != "127.0.0.1":
        try:
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            print("手机/其他设备（同一 Wi-Fi）访问：http://%s:%d" % (ip, port))
        except Exception:
            pass
    print("按 Ctrl+C 停止。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
