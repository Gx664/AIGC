把看板程序装进手机（Termux 方案）
====================================

原理：在手机里用 Termux 跑一个 Python 环境，把看板程序本身装进手机。
手机自己就是"服务器"：打开手机浏览器访问本机地址就能看，
走到哪都能看（数据在 PostHog 云端，只需手机有网）。

第一步：安装 Termux
1. 手机浏览器打开 https://f-droid.org 下载并安装 F-Droid（应用商店）
2. 在 F-Droid 里搜索 Termux，安装
   （注意：不要用应用商店里的 Termux，那是旧版）

第二步：把压缩包传到手机
把 AIGC_Dashboard_phone.zip 传到手机（微信文件传输/网盘/数据线均可），
放到 Download 目录并解压。压缩包里已带好 dashboard.py、dashboard_config.json、
termux_setup.sh，配置文件已内置查看密钥，无需再手动配置。

第三步：在 Termux 里一键启动（全自动）
把 AIGC_Dashboard_phone.zip 传到手机 Download 目录并解压，
然后打开 Termux，依次输入（每行回车）：

  termux-setup-storage
  cd storage/downloads
  sh termux_setup.sh

脚本会自动：
1. 检查环境：Python 装了没有、存储权限开了没有、文件在不在，
   逐项显示 [OK] 或 [缺]
2. 只安装缺失的组件（自动更新源 + 装 Python，pkg 自带下载进度）
3. 复制文件、检查查看密钥是否已配置
4. 启动看板并自检（返回 200 才算成功）
全程带进度条 [====]。

看到"看板运行中"后，
手机浏览器打开 http://127.0.0.1:8765 就能看数据了。

第四步（可选）：保持后台运行
- 首次运行时输入：termux-wake-lock
  锁屏后程序也继续跑
- 想开机自启：再装 Termux:Boot（F-Droid 里），
  把上面的启动命令写进 ~/.termux/boot/start.sh

安全说明：
- 压缩包内置的是作者项目的"查看密钥"（仅供查看公开的匿名统计）；
  如果你 fork 自建，请把 dashboard_config.json 里的密钥换成你自己的
  PostHog personal_api_key，不要沿用预编译包里的密钥。
- dashboard_config.json 里是读取数据的密钥，只放在你自己手机
- 建议设置 access_token（访问密码），并只在本机/可信设备使用
- 如果只是自己手机看，地址 http://127.0.0.1:8765 只有本机能访问，很安全

其它设备想在任何网络看：仍需要把看板部署到公网服务器
（见 tools/deploy/README-deploy.txt），手机方案解决的是"自己手机看"。
