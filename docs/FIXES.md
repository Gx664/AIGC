# 审查与修复记录

- 基线：原作者 v1.3.0（upstream `3888dac`）
- 审查与修复：yinlb，2026-09
- 环境：torch 2.8.0+cu129 / transformers 5.17.0 / RTX 4080 SUPER 16GB

文中数值均实测；未实测的一律标「未标定」。复现与重打包命令见 §4。

---

## 1. 修的缺陷

| # | 问题 | 位置 | 效果 |
|---|---|---|---|
| 1 | **Binoculars 恒判 AI**：分母跑出 log 域 + 缺交叉项 + 量纲混用 | `binoculars_engine.py` | 准确率 46.7% → **94.17%** |
| 2 | **`avg_logprob` 分块口径错**（binoculars / perplexity / curvature 的公共基座）| `base.py` | 偏差 34~67% → **0.000%** |
| 3 | 设置保存写坏 `hf_endpoint`（丢协议头）→ 模型下载全失败 | `settings_dialog.py` | 下载恢复 |
| 4 | 集群发现被端口绑定竞争掐死 | `cluster.py` | 恒为空 → 4 秒发现节点 |
| 5 | detectgpt / fastdetectgpt 缺 σ 归一化 | `curvature_engine.py` | 补上（实测效果见 §2.3）|
| 6 | 引擎清单参数覆盖用户参数 | `main_window.py` | 顺序修正 |
| 7 | 中文长文本超 `n_positions` 崩溃 | `base.py` | 新增 `_encode_capped()` |
| 8 | 显存不足静默降速（fp32 溢出）| `base.py` | fp16 加载 + 显存预检三档 |
| 9 | T5 输入超 512 token | `curvature_engine.py` | 两侧截断 |
| 10 | 报告文件名未转义 | `report.py` | 修 |
| 11 | 引擎无语言标注 → 用户误用（detectgpt 中文判定**反向**）| `engine_dialog.py` | 加 ✅ / ⚠️ / ❌ / ❔ 标注 |
| 12 | 阈值不可移植 | `catalog.py` | 重标（见 §3）|
| 13 | `zh_perplexity` 阈值错（FPR 95%）| 标定数据 | FPR 降至 4% |
| 14 | 工程清理：17 处未用导入 | 11 个文件 | 删（行长 / 编码声明按作者风格**不动**）|

**模型大小不是决定性的** —— 决定性的是「代码对 + 阈值标定 + 语言匹配」：

| 引擎 | 规模 | 结果 |
|---|---|---|
| simpleai | ~0.1B | 中文 acc **99.02%** |
| binoculars | ~0.4B | 英文 acc 94.17% |
| binoculars 修前 → 修后（**模型未变**）| — | 46.7% → **94.17%** |

故**不换**论文的 Falcon-7B / T5-3B（非英语扰动模型除外，见 §2.4）。

---

## 2. 与论文的差异

### 2.1 数据语言（最影响结论）

论文（arXiv:2401.12070v3 §5.2）承认多语言是弱项，其检测器**只针对英文**。
本项目用英文模型处理中文 → 中文侧只有 `simpleai` 可交付（见 §3.3）。

### 2.2 公式（已按论文修）

| 论文 | 修复前 | 现状 |
|---|---|---|
| Binoculars §3.3 式 (3)(4)：分母留 log 域 + 交叉项 + 同量纲比 | `exp()` 出域、无交叉项、log 比实数 | ✅ 按论文 |
| DetectGPT / Fast §2.3：σ 归一化 | 缺 | ✅ 补上（效果见 §2.3）|
| GLTR §3 Test-2：逐 token rank 四档 | 只做整段 PPL | ✅ 实现为 `method="rank"` 可选路线 |

### 2.3 σ 归一化：实测与论文相悖

论文 §5.3 的扰动数 k=100 才收敛；本项目 k=5~10 → σ 估不稳，**归一化反而有害**：
detectgpt 英文未归一化 acc 90%，加 σ 后 AUC 降到 0.7100（论文 0.9554）。

### 2.4 非英语扰动模型：**未换（待办）**

DetectGPT 论文 §6 明确：非英语用 **mT5**（本项目仍用英文 t5-base）——
这是 detectgpt 中文 AUC 0.2800（**排序反向**）的成因之一。
`curvature_engine._mask_perturb` 用的是 `<extra_id_N>` 哨兵，**mT5 同格式，换模型只需改清单的 `models` 字段**。

### 2.5 标定数据与样本量

| | 论文 | 本项目 |
|---|---|---|
| 数据 | CC News + CNN + PubMed（需自建，含 13B 模型生成）| HC3（中）+ Ghostbuster（英），公开可下载 |
| 样本量 | 每数据集 500 条 | 15,216（中）/ 5,984（英）|
| 留出集 | 明确区分标定集与 out-of-domain 评测集 | 同批数据既标定又评测 → **指标偏乐观** |

**数据集不同则指标不可直接比**：实测同引擎同阈值换数据集，93.67% → 52.33%。

### 2.6 无影响项

`max_tokens` 差异、阈值搜索步长与候选数。

---

## 3. 阈值标定（改阈值前必看）

**判据**：查重工具**误报比漏报严重** → 一律看 **FPR≤5%** 约束下的 acc，不看「最优 acc」。
（旧阈值多为未约束的「最优 acc」，看着高，实则误报超标。）

标定值不写死在代码里：

```
tools/probes/ 标定探针 → tools/export_calibration.py → app/core/engines/engines_calibration.json
                                                              ↓ 启动时读取覆盖
                                                       manager.py
```

优先级：`catalog.py 出厂值 < 标定值 < 远端 < 用户覆盖`。改阈值请改 json，不要写进 `catalog.py`。

### 3.1 中文（HC3）

数据：`HC3_zh_all.jsonl`（12,853 问）→ 展开成 pair 并按问题配平 **15,216 条 1:1**（论文 §4.1 口径）。

| 引擎 | 阈值 | FPR≤5% acc | AUC | 判定 |
|---|---|---|---|---|
| **simpleai** | 判定点 0.50（分类器无阈值可调）| **0.9902** | **0.9998** | ✅ **唯一可交付** |
| zh_perplexity | 4.33 / 11.55 | 0.8623 | — | ⚠️ 弱 |
| gltr | 5.22 / 17.31 | 0.6096 | 0.7816 | ❌ 不可交付 |
| binoculars | 0.1494 | 0.5900 | 0.7728 | ⚠️ 弱 |
| detectgpt | — | — | **0.2800** | ❌ 排序反向 |
| fastdetectgpt | **未标定** | — | — | ❔ |

- **gltr 中文**：旧值 (11.35, 18.72) 实测 **FPR 23.74% 严重超标**（acc 0.7250 是「宁可错杀」换来的）；
  按 FPR≤5% 重标 (5.22, 17.31) 后 FPR 4.85% 合格，但 **FNR 73%** —— 检出能力不足，
  **确认不可交付**（界面标「中文勿用」，建议改用 `zh_perplexity`）。新旧 acc **不可直接比**。
- **阈值未收敛**：`zh_perplexity` 在 200 条 (2.88, 7.68) / 400 条 (3.72, 9.92) /
  15,216 条 **(4.33, 11.55)** 上单调右移，acc 涨 7~16 点 → **扩样本后必须重标**。
- **detectgpt 排序反向**（AUC < 0.5）：人写得分高于 AI，任何阈值都救不了，成因见 §2.4。
- gltr / binoculars 中文两侧分布重叠 —— 调阈值救不了，属模型不匹配。

### 3.2 英文（Ghostbuster）

数据：`ghostbuster-data/`（essay / wp / reuter，21,268 条 → 配平后 5,984 条）。
**读原件须跳过** `logprobs/`（token + 概率，非文本）、`other/`（只有人写）、`perturb/`、`prompts/`。

| 引擎 | 阈值 | **FPR≤5% acc** | AUC | 判定 |
|---|---|---|---|---|
| **gltr** | **8.69 / 25.64** | **0.7659** | 0.9664 | ✅ 可用 |
| **binoculars** | **0.8152** | **0.8422** | **0.9727** | ✅ 可用 |
| simpleai | — | 0.5015 | 0.4397 | ❌ 等于抛硬币 |

两者的旧值都不可交付：

| 引擎 | 旧值 | 旧 acc / FPR | 新值 | 新 acc / FPR |
|---|---|---|---|---|
| gltr | (12, 25) | 0.7975 / **0.0799 超标** | (8.69, 25.64) | 0.7659 / **0.0488 ✅** |
| binoculars | 0.615 | 0.5010 / 0.0000（**FNR 0.998**）| 0.8152 | 0.8422 / **0.0498 ✅** |

- **AUC 高 ≠ 可交付**：binoculars 英文 AUC 最高（0.9727），但 FPR≤5% 下的 acc 反而略低于
  gltr —— **两个指标必须一起看**。
- **小样本阈值漂移**：binoculars 的 0.615 标自 essay 120 条，换到前 200 条时最优阈值掉到
  **0.1288**（差 4.5 倍），0.615 下 **FNR=1.0000**（一条 AI 都抓不出）。
- **数据集效应**：同一引擎同一阈值，只换数据集 —— `essay-only` n=300 acc 93.67%，
  `essay+reuter+wp` n=300 acc **52.33%**（差 41 个百分点）→ **引用指标必须说明数据集**。

### 3.3 语言适配（界面标注依据）

| 引擎 | 界面标注 | 依据 |
|---|---|---|
| SimpleAI | `🌐 中文 ✅ 可用` | 中文 AUC 0.9998 |
| zh_perplexity | `🌐 中文 ⚠️ 中文弱` | FPR≤5% acc 0.8623 |
| GLTR | `🌐 中文 / 英文 ⚠️ 中文勿用` | 英文 0.7659；中文无可行阈值 |
| Binoculars | `🌐 中文 / 英文 ⚠️ 中文弱` | 英文 0.8422；中文 0.5900 |
| DetectGPT | `🌐 中文 / 英文 ❌ 中文勿用` | 中文 AUC 反向（成因见 §2.4）|
| Fast-DetectGPT | `❔` | 无实测数据 |

**原则**：没有实测数据的引擎不得标可用性；语言无关的引擎（规则降重、评测基准）不标语言。
`❔` 只给一个符号、含义放在该行悬停提示里 —— 「未标定」与「测出来差」（⚠️）语义相反，
标语言反而等于编造。

**过拟合检查**（`holdout` 探针）：留出集按**问题**拆分（同一 question 下的人机答案是一对
对照样本，按条拆等于变相泄漏）—— 标定集 0.8615 / 留出集 0.8673，落差 **−0.58 点**。

---

## 4. 复现与重打包

```powershell
# 解释器（torch 2.8.0+cu129 / transformers 5.17.0）
C:\ProgramData\miniconda3\envs\pytorch\python.exe

# 回归（改动后必跑；全绿是必要不充分条件）
python tools\smoke_test.py            # 10/10
python tools\test_engines.py          # 13/13
python tools\test_detect.py
python tools\fusion_selftest.py

# 探针：--list 看全部（29 个；safe 组默认跑，heavy 需显式指定）
python tools\audit_probes.py                      # safe 组
python tools\audit_probes.py --only ui_flow       # 界面真跑一次检测
python tools\audit_probes.py --only package_flow  # 装机必需文件、标定数据位置
python tools\audit_probes.py --only env_setup     # 首次启动 / 卸载器
python tools\audit_probes.py --only bino_cal      # 阈值标定（跑完写回 json）

# 静态检查
npx --yes pyright                     # 期望 0 errors（现存 5 条 reportUnusedImport，见 §6）
```

**数据集不在仓库内**（HC3 中文 / Ghostbuster 英文，数 GB）—— 路径是
`tools/prepare_datasets.py` 顶部的常量，按自己环境改；标定探针会用到它们。

**改了 `app/` 或 `installer/` 必须重打 exe**（安装器把 `app/` 当数据打在自己里面，
不重打包，用户装到的还是旧代码 —— 实测踩过）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

三步、**顺序不可反**：`dist\uninstaller.exe` → `app\first_run_gui.exe` → `dist\AIGC_Toolkit_Setup.exe`。

探针是「主程序 + 探针函数」两层结构：`audit_probes.py` 是入口（分组隔离、统一
`sys.path` 与汇总），各探针的验证逻辑原样保留 —— §1 的结论由它们复现。

---

## 5. 改动约束

1. **风格跟随原作者，不要「修正」**：中文注释 / docstring / 异常消息、`os.path.join()`、
   双引号、`[]`、行长不限、不加文件头 —— 13 项里 9 项与通行规范**相反**，是有意为之。
   核验：`python tools\audit_probes.py --only style_report`
2. **标定值必须外置**（见 §3）；改完跑 `python tools\export_calibration.py --audit` 查硬编码漏网。
3. **路径**：用户数据放**安装目录**（`core.settings.base_dir()` 是唯一真源）——
   放 `app\` 下会被重装的 `rmtree` 清掉。
4. **依赖**：`transformers` / `PySide6` 必须锁主版本（本项目用 5.x / 6.x 的 API）；
   导入名 ≠ pip 名 —— `docx` 的包名是 `python-docx`（PyPI 上的 `docx` 是 2014 年的另一个库）。
5. **显存不足不报错、只变慢约 10 倍**（Windows WDDM 换页）：看**温度与功耗**判断，
   别只看利用率。
6. 改完跑 §4 的回归，并**按需重打包**。

---

## 6. 未做

| 优先级 | 事项 | 耗时（实测）| 说明 |
|---|---|---|---|
| 高 | `fastdetectgpt` 中英标定 | **~5.5h** | 中 15,216×1.01s + 英 5,984×0.65s；**未标定前别下结论**（阈值 0.0 / scale 0.6 是默认值）|
| 高 | 用新 exe 真装一次复核 | ~30min | 装机端到端是最终判据；本轮只做完静态与探针验证 |
| 中 | `detectgpt` 中文换 `google/mt5-xl` 后重标 | 下载 ~1h + 标定 ~1.8h | 论文要求非英语用 mT5，见 §2.4 |
| 低 | pyright 剩 5 条 `reportUnusedImport` | 分钟级 | 4 条对外接口导入 + 1 条 `try: import torch` 探测导入；**如实记录、不做抑制** |

**不做**：换论文的 Falcon-7B / T5-3B、抓论文数据集（见 §1、§2.5）；改原作者文档
（`README` / `使用手册` / `CHANGELOG` 一字未动）；行长与编码声明；并行数改下拉。

**方法局限（不是缺陷）**：gltr 在长文 / 新闻类判别力弱；GLTR 四档聚合后与 PPL 路线基本
打平 —— 论文的 AUC 0.87 来自「四档 + 逻辑回归」，需训练才能复现。
