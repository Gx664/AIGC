# AIGC 检测工具箱 {{TAG}}

中文 AI 生成文本检测工具，**完全离线运行**，个人免费使用。

## ✨ 本版更新（v1.4.0）

模型仓库扩容 + 联系方式清理：新增 **Humanizer** 与 **humanize-zh** 两个可预下载的
开源改写模型，下载层支持 GGUF 与子目录权重；**内置规则降重引擎保持原样、仍是默认**。
同时按要求从软件本体移除打款码与 Telegram 联系方式。

**📦 引擎管理里新增 2 个可下载的改写模型**

| 条目 | 语言 | 体积 | 说明 |
|---|---|---|---|
| Humanizer | 中文 / 英文 | 约 7.6 GB（GGUF Q4_K_M） | Gemma-4-12B + SFT+DPO 真微调，Apache-2.0 |
| humanize-zh | **中文专用** | adapter 0.116 GB + 约 19.3 GB 底座 | Qwen3.5-9B + 1.8 万条 SFT + 两轮 DPO，Apache-2.0 |

**⚠️ 这 2 个条目与 v1.3.9 的 4 条一样，只用于「提前把模型下到本地」，本版不参与降重** ——
选中它们点「开始降重」会直接报错提示改用规则引擎，这是有意为之。
**默认降重引擎没变**，仍是内置的规则引擎，本版一行都没碰它，中英文降重效果与 v1.3.9 完全一致。

**🔧 下载层支持 GGUF 与子目录权重** —— 按条目 `files` / `subfolder` 声明逐文件下载，
`.gguf` 也能落盘到模型目录（供外部工具加载），体积统计已纳入 `.gguf`。
humanize-zh 的 adapter 与底座分离下载就靠这个机制。

**🗑️ 联系方式清理** —— 关于窗口不再显示支付宝 / 微信支付二维码，主界面联系栏只留邮箱
`gxgx3456@qq.com`；Telegram 账号从软件内彻底移除（历史版本记录里的账号已脱敏）。

> 降重仍然是**纯规则引擎**，不吃显卡 —— 任务管理器里 GPU 显存为 0 属于正常，不是 bug。

## 📦 按你的系统下载

| 你的系统 | 下载这个文件 | 体积 | 怎么装 |
|---|---|---|---|
| **Windows 10 / 11** | `AIGC_Toolkit_Setup.exe` | 32 MB | 双击 → 选安装目录 → 开始安装 |
| **Linux（x86_64）** | `AIGC_Toolkit-{{VER}}-x86_64.AppImage` | 88 MB | 先 `chmod +x`，再双击（或命令行运行） |
| **macOS（Apple 芯片）** | `AIGC_Toolkit-{{VER}}-macos-arm64.dmg` | 62 MB | 打开 dmg → 拖进「应用程序」→ **首次要手动放行一次**，见下方说明 |

三个平台的功能完全一致。首次启动都会弹引导窗口，自动下载运行组件（约 0.2 GB，国内镜像加速，不需要 VPN）；
有 NVIDIA 显卡会问你要 CUDA 还是 CPU 版，没有则自动用 CPU 版。装好之后完全离线可用。

## 🐧 Linux 用户注意

- AppImage 需要 `libfuse2`（Ubuntu 22.04+：`sudo apt install libfuse2`）。
  装不了也没关系，加环境变量照样跑：`APPIMAGE_EXTRACT_AND_RUN=1 ./AIGC_Toolkit-*.AppImage`
- 首次运行会把运行时**复制到你的用户目录**再装依赖 —— AppImage 每次挂载点都不一样，
  而且镜像是只读的，就地装依赖下次启动就失效。桌面快捷方式会自动创建。

## 🍎 macOS 用户注意

本项目没有购买苹果开发者签名证书，产物是**未签名**的，第一次打开会被系统拦下。放行一次就好。

**macOS 15 Sequoia / 26 Tahoe 及更新**：双击 App → 出现拦截提示时点「完成」（**别点「移到废纸篓」**）
→ 打开 **系统设置 → 隐私与安全性** → 拉到最下面「安全性」→ 点「**仍要打开**」→ 输密码确认 → 再启动一次。

> ⚠️ 「仍要打开」按钮只在启动失败后的**约 1 小时内**出现，看不到就再双击一次 App，然后再回设置页。

**macOS 14 及更早**：按住 Control 点 App（或右键）→「打开」→ 再点一次「打开」。

**任何版本通用（终端，最省事）**：

```bash
xattr -dr com.apple.quarantine /Applications/AIGC_Toolkit.app
```

看到「**已损坏，应该移到废纸篓**」是**误导性提示**，文件没坏，别删。

- 目前只发布 **Apple 芯片（arm64）** 版；Intel 芯片的 Mac 请从源码运行。

## 🗑️ 卸载

- **Windows**：从「设置 → 应用」或安装目录里的卸载程序卸载。
- **Linux / macOS**：删掉 App 本体，再删掉用户目录下的数据目录
  （Linux `~/.local/share/AIGC_Toolkit`，macOS `~/Library/Application Support/AIGC_Toolkit`）。

## ⚖️ 许可与说明

本项目采用 [PolyForm Noncommercial License 1.0.0](https://github.com/Gx664/AIGC/blob/main/LICENSE)：
**个人免费使用、源码公开，禁止任何商业用途。**

检测结果由模型估算得出，**仅供参考**，不构成任何保证。

---

有问题或想反馈：gxgx3456@qq.com ｜ 详细文档见 [README](https://github.com/Gx664/AIGC#readme)
