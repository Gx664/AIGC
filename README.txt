AI 检测工具箱 v1.0
==================

一、这是什么
一个本地运行的 AIGC 检测桌面工具：拖入论文（PDF/DOCX/TXT），选择检测引擎，
得到整篇 AI 占比和段落级报告。

二、主要功能
1. 多引擎：SimpleAI（中文，默认）、GLTR（困惑度）、Fast-DetectGPT（重）、
   以及自定义引擎（任意 HuggingFace 模型 ID）
2. 参数自定义：阈值、段落长度、并行数、GPU/CPU 开关等，可保存多套预设，
   支持导出/导入
3. 多卡/多设备：同一台机器多张显卡自动并行；局域网内多台电脑可组集群
   （主节点 + 工作节点，参考 exo 的自动发现思路）
4. 免费使用，预留收费授权接口（专业版激活逻辑已写好，接上服务器即可）

三、安装
1. 运行 AIGC_Toolkit_Setup.exe（小体积安装器，不打包 AI 环境）
2. 选择安装目录（默认 D:\AIGC_Detector）
3. 安装器自动下载 Python 运行时和 AI 依赖（含 CUDA 版 PyTorch，约 3~4GB，
   自动使用国内镜像），实时显示进度
4. 完成后桌面出现快捷方式

四、多设备集群
- 所有电脑装上同一版本软件
- 其中一台点"作为工作节点加入集群"，其他电脑点"扫描设备"即可自动发现
- 主节点检测时勾选"使用集群"，论文段落会分发给各设备并行计算
- 同一台电脑多张显卡无需设置，自动并行（段落级数据并行）

五、收费接口说明
app/core/license.py 中已预留：
- 免费版：全部功能可用
- 专业版：在设置里输入授权码（AIGC-PRO- 开头）即可激活
- 后续接在线激活服务器时，替换 _validate 即可

六、开发与打包
- 源码在 app/ 目录
- 修改后运行 sync_to_d.bat 同步到 D 盘开发目录
- 再运行 build_installer.bat 重新打包安装器（小体积 exe）

七、联系方式
作者邮箱：gxgx3456@qq.com

八、遥测与日志（隐私说明）
- 默认开启匿名使用统计：仅包含版本、系统、显卡、使用次数与时长、错误类型，
  不含论文内容和个人信息；首次运行会弹窗说明，可随时在界面
  "允许匿名使用统计"处关闭，关闭后立即清空本地缓存
- 数据通过 PostHog 分析；默认未配置 Key 时不启用任何上报
- 配置方法：在软件安装目录放 posthog_config.json，内容：
  {"api_key": "你的 Project API Key", "host": "https://us.i.posthog.com"}
- 运行日志保存在 logs/ 目录（滚动保留），界面点"导出日志"可打包成 zip
  发送给作者，用于排查问题

九、数据看板（怎么看统计数据）
- 在 PostHog 后台 Settings → Personal API keys 新建一个个人 API 密钥
- 编辑 tools/dashboard_config.json，填入 personal_api_key（和你的 github repo 可选）
- 双击 tools/run_dashboard.bat，浏览器自动打开精美数据看板：
  总启动/今日/周活跃/月活跃/总检测/平均时长/实时在线 + 30 天趋势、引擎/显卡/版本分布
- 页面默认每秒自动刷新（可在 dashboard_config.json 改 refresh_seconds）
- Windows 独立版：tools/dist/AIGC_Dashboard.exe（免安装，配置放 exe 同目录）
- 手机查看（同一 Wi-Fi）：双击 run_dashboard_lan.bat，
  用手机浏览器打开电脑上显示的 http://电脑IP:8765 即可，无需装 APK
- 数据全部来自 PostHog
