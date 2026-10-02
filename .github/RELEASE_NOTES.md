# AIGC 检测工具箱 {{TAG}}

中文 AI 生成文本检测工具，**完全离线运行**，个人免费使用。

## 📦 按你的系统下载

| 你的系统 | 下载这个文件 | 体积 | 怎么装 |
|---|---|---|---|
| **Windows 10 / 11** | `AIGC_Toolkit_Setup.exe` | 22 MB | 双击 → 选安装目录 → 开始安装 |
| **Linux（x86_64）** | `AIGC_Toolkit-{{VER}}-x86_64.AppImage` | 88 MB | 先 `chmod +x`，再双击（或命令行运行） |
| **macOS（Apple 芯片）** | `AIGC_Toolkit-{{VER}}-macos-arm64.dmg` | 62 MB | 打开 dmg → 把 App 拖进「应用程序」→ **右键「打开」** |

三个平台的功能完全一致。首次启动都会弹引导窗口，自动下载运行组件（约 0.2 GB，国内镜像加速，不需要 VPN）；
有 NVIDIA 显卡会问你要 CUDA 还是 CPU 版，没有则自动用 CPU 版。装好之后完全离线可用。

## 🐧 Linux 用户注意

- AppImage 需要 `libfuse2`（Ubuntu 22.04+：`sudo apt install libfuse2`）。
  装不了也没关系，加环境变量照样跑：`APPIMAGE_EXTRACT_AND_RUN=1 ./AIGC_Toolkit-*.AppImage`
- 首次运行会把运行时**复制到你的用户目录**再装依赖 —— AppImage 每次挂载点都不一样，
  而且镜像是只读的，就地装依赖下次启动就失效。桌面快捷方式会自动创建。

## 🍎 macOS 用户注意

- 本项目没有购买苹果开发者签名证书，产物是**未签名**的。第一次打开必须
  **按住 Control 点它（或右键）→ 选「打开」→ 再点一次「打开」**，只需做一次。
- 若提示「已损坏」或「无法打开」，打开「终端」执行：
  `xattr -dr com.apple.quarantine /Applications/AIGC_Toolkit.app`
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

有问题或想反馈，Telegram：[@A9100010](https://t.me/A9100010) ｜ 详细文档见 [README](https://github.com/Gx664/AIGC#readme)
