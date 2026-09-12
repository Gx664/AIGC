# AI 检测工具箱 (AIGC Detector Toolkit) - 项目交接文档

> **版本**: v1.2.0 → v1.3.0  
> **作者**: gxgx3456   
> **邮箱**: gxgx3456@qq.com  
> **GitHub**: https://github.com/Gx664/AIGC  
> **最后更新**: 2026-09-12

---

## 一、项目概述

### 1.1 是什么

一个**完全离线**的 AIGC（AI Generated Content）检测工具，用于检测学术论文中 AI 生成的文本。核心功能：

- **检测**：判断文本是否由 AI 生成（基于深度学习模型）
- **诊断**：分析 AI 写作痕迹模式（9维特征 + 11种深度模式）
- **治疗**：自动降重改写（确定性改写，不编造事实）

### 1.2 技术栈

| 层级 | 技术 |
|------|------|
| UI | PySide6 (Qt for Python) |
| 检测引擎 | transformers (HuggingFace) |
| 诊断引擎 | 纯正则 + 标准库（无依赖） |
| 治疗引擎 | 纯正则 + 标准库（无依赖） |
| 打包 | PyInstaller |
| 安装器 | tkinter + Python |

### 1.3 目录结构

```
AIGC_Toolkit/
├── app/                          # 主程序
│   ├── main.py                   # 入口（读取镜像配置）
│   ├── core/                     # 核心逻辑
│   │   ├── settings.py           # 设置管理（JSON持久化）
│   │   ├── i18n.py               # 中英双语
│   │   ├── meta.py               # 版本号、作者信息
│   │   ├── doc_reader.py         # 文档解析（PDF/DOCX/TXT）
│   │   ├── detector.py           # 检测调度
│   │   ├── diagnosis.py          # 诊断引擎（588行）
│   │   ├── therapy.py            # 治疗引擎（382行）
│   │   ├── aigc_rules.py         # 规则库（557行）
│   │   ├── report.py             # 报告生成
│   │   ├── cluster.py            # 局域网集群
│   │   ├── license.py            # 授权系统
│   │   ├── logging_setup.py      # 日志系统
│   │   ├── about_text.py         # 关于页面
│   │   └── engines/              # 检测引擎
│   │       ├── __init__.py       # 引擎工厂
│   │       ├── manager.py        # 引擎注册表
│   │       ├── simpleai_engine.py    # SimpleAI 中文检测
│   │       └── perplexity_engine.py  # GLTR/Fast-DetectGPT
│   └── ui/                       # 界面
│       ├── main_window.py        # 主窗口（722行）
│       ├── glass.py              # 毛玻璃UI组件
│       ├── engine_dialog.py      # 引擎管理
│       ├── settings_dialog.py    # 下载设置（新增）
│       └── rewrite_dialog.py     # 降重对话框
├── installer/
│   └── installer.py              # 安装器（377行）
├── tools/                        # 开发工具
│   ├── fusion_selftest.py        # 融合自测
│   ├── test_detect.py            # 检测测试
│   └── patch_offline_fix.py      # 通用补丁脚本
├── dist/                         # 产物
│   └── AIGC_Toolkit_Setup.exe    # 安装包（~11MB）
└── 聊天记录/                      # 历史会话记录
```

---

## 二、核心算法

### 2.1 检测引擎

| 引擎 | 模型 | 大小 | 用途 |
|------|------|------|------|
| SimpleAI | Hello-SimpleAI/chatgpt-detector-roberta-chinese | ~400MB | 中文论文检测（推荐） |
| GLTR | gpt2 | ~500MB | 英文困惑度检测（实验） |
| Fast-DetectGPT | EleutherAI/gpt-neo-2.7B | ~5.4GB | 高精度检测（需显卡） |

**关键代码**：`app/core/engines/simpleai_engine.py`
- 优先本地缓存（`local_files_only=True`）
- 支持 GPU 加速
- 线程安全（threading.Lock）

### 2.2 诊断引擎

**9维特征扫描**（`scan_9dim`）：
1. 模板句式密度
2. 被动语态比例
3. 句法节奏可预测性（CV值）
4. 段落对称性
5. 嵌套编号
6. 冒号并列
7. 逗号密度
8. 口语化用语
9. 破折号密度

**11种深度AI痕迹**（`_analyze_deep_11`）：
1. 重要性膨胀（significance inflation）
2. 同义词轮换（synonym cycling）
3. 三板斧强迫症（rule of three）
4. 系词回避（copula avoidance）
5. 模糊归因（vague attribution）
6. 公式化挑战段（formulaic challenges）
7. 悬浮式分析（suspended analysis）
8. 空洞结论（generic conclusions）
9. 破折号过度（em-dash overuse）
10. 虚假范围（false ranges）
11. 成对转折收束（paired contrast closures）

**知网5种语言模式**（`_analyze_cnki_5`）：
1. 句法节奏可预测性
2. 信息密度均匀性
3. 术语句法位置固定
4. 连接词功能重叠
5. 模板段功能全等性

### 2.3 治疗引擎

确定性改写（`therapy.py`）：
- 词级替换：AI高频词 → 同义替换
- 句级重构：拆分长句、调整语序
- 排比拆解：三/四项并列 → 自然表达
- 破折号修正：多余破折号 → 逗号/句号
- 语体守门：防止改写后出现口语化

**原则**：不编造事实、不改变数据、不伪造引用

---

## 三、已知问题与修复记录

### 3.1 HuggingFace 离线问题（已修复）

**问题**：模型下载需VPN，国内用户无法使用  
**修复**：
1. 引擎优先本地缓存（`local_files_only=True`）
2. 添加国内镜像源（`hf-mirror.com`）
3. 设置页面可切换下载源

### 3.2 安装器 Python 检测问题（已修复）

**问题**：`InstallAllUsers=0` 忽略 `TargetDir`，Python 装到 AppData  
**修复**：
1. 优先检测系统已安装的 Python 3.12
2. 找到则直接复制，无需下载
3. 找不到再下载安装

### 3.3 控制台 emoji 崩溃（已修复）

**问题**：Windows GBK 控制台遇到 emoji 崩溃  
**修复**：`sys.stdout.reconfigure(errors="replace")`

---

## 四、构建流程

### 4.1 开发环境

```
Python 3.12.10 (D:\开发工具\Dev\Python312\)
Git (D:\开发工具\Dev\Git\)
venv (D:\开发工具\Dev\AIGC_Detector\.venv\)
```

### 4.2 重新打包 exe

```powershell
cd D:\AIGC\outputs\AIGC_Toolkit
D:\开发工具\Dev\AIGC_Detector\.venv\Scripts\python.exe -m PyInstaller `
    --noconfirm --clean --onefile --noconsole `
    --name "AIGC_Toolkit_Setup" `
    --add-data "app;app" `
    installer\installer.py
```

### 4.3 自测

```bash
# 融合自测（4项）
D:\开发工具\Dev\Python312\python.exe tools\fusion_selftest.py

# 检测测试
D:\开发工具\Dev\Python312\python.exe tools\test_detect.py
```

---

## 五、Git 提交记录

```
bcae7f4 fix: installer detect system Python first, skip download if found
e1f6475 fix: installer check exit code 1603 = needs admin rights
1b50623 fix: installer use InstallAllUsers=1 + fallback to system Python
31bc8eb fix: installer comprehensive Python search with detailed logging
2888799 fix: installer add diagnostic logging for Python install failure
4cdc7ca feat: add download settings page with mirror selection + model management
e0577fe build: rebuild exe v1.2.1 with offline fix + hf-mirror
26fd078 feat: add offline patch script for existing exe users
ceff671 fix: use hf-mirror.com for model downloads (no VPN needed in China)
2c4a64b fix: engines try local cache first before downloading (offline mode)
```

---

## 六、给接手者的建议

### 6.1 立即要做的

1. **运行安装器测试**：右键以管理员身份运行 `AIGC_Toolkit_Setup.exe`
2. **检查日志**：安装器会打印详细的检测和安装过程
3. **验证检测功能**：导入一篇论文，选择 SimpleAI 引擎检测

### 6.2 需要深入了解的

1. **诊断引擎**：`diagnosis.py` 是核心，理解9维特征和11种模式
2. **治疗引擎**：`therapy.py` 的改写逻辑，确保不破坏原意
3. **规则库**：`aigc_rules.py` 可能需要根据新的AI写作模式更新

### 6.3 潜在改进方向

1. **模型更新**：跟踪 HuggingFace 上新的检测模型
2. **规则更新**：根据AI写作能力提升，更新检测规则
3. **批量检测**：支持多文件批量处理
4. **云端API**：可选接入云端大模型做更精准检测

### 6.4 注意事项

- **完全离线**：所有检测、诊断、治疗都在本地完成
- **不上传数据**：用户论文不会上传到任何服务器
- **确定性改写**：治疗引擎不使用AI，纯规则改写
- **作者是学生**：代码风格可能不够专业，但功能完整

---

## 七、技术债务

1. **测试覆盖**：目前只有手动测试，需要添加单元测试
2. **类型注解**：部分函数缺少类型注解
3. **错误处理**：部分异常处理可以更细致
4. **文档注释**：关键函数需要更详细的文档

---

## 八、资源链接

- **GitHub**: https://github.com/Gx664/AIGC
- **模型下载**: https://hf-mirror.com（国内镜像）
- **PyTorch**: https://pytorch.org/
- **transformers**: https://huggingface.co/docs/transformers

---

*本文档由 opencode 自动生成，最后更新于 2026-09-12*
