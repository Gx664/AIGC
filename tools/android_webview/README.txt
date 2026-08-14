AIGC 数据看板 · 安卓壳工程
============================

这个工程是一个极简安卓 App：打开后全屏显示电脑上的数据看板网页。

打包步骤（需要一台装有 Android Studio 的电脑，本机无安卓工具链）：
1. 用 Android Studio 打开本文件夹（android_webview）
2. 修改 MainActivity.kt 顶部的 DEFAULT_URL 为你电脑的局域网地址
   （例如 "http://192.168.1.100:8765"，看板启动时控制台会显示这个地址）
   填了它，APK 装到手机打开就直接显示数据，零设置
   不填也没关系：首次打开会出现地址输入框，输入一次自动记住
3. 菜单 Build → Build APK(s)，等几分钟
4. 生成的 APK 在 app/build/outputs/apk/debug/ 下，安装到手机即可

关于"配置数据放里面"：
- PostHog 密钥不放 APK（那是管理员级密钥，放进去等于公开后台管理权）
- APK 打开的是电脑上的数据看板页面，看板已配好所有密钥，
  所以 App 打开就能直接看到数据

注意：
- 手机和电脑必须连同一个 Wi-Fi
- 电脑上要看板以局域网模式运行：双击 run_dashboard_lan.bat
- 想"随时随地、免开电脑"看数据：把看板部署到公网服务器，
  把 DEFAULT_URL 改成公网地址再打包，即可实现

关于 PostHog 密钥（重要）：
- 仓库里预编译的看板 APK / exe（见根目录 README.md）已内置作者项目的"查看密钥"，
  仅用于查看公开的匿名使用统计，下载安装后打开即可直接看数据。
- 源码中的密钥文件保持占位符：APK 的查询密钥位于 tools/apk_self/assets/posthog_key.txt（仓库内为占位符）。
- fork 自建时：把 tools/apk_self/assets/posthog_key.txt 替换成你自己的 PostHog personal_api_key，
  运行 tools/apk_self/build_apk.bat（javac + d8 + zipalign + apksigner）重新打包；
  不要沿用预编译包里的密钥。
- 注意：personal_api_key 属于账号级钥匙，公开它等于把后台数据公开给所有人。
  本项目作者有意公开这份匿名统计，因此预编译包内置了查看密钥；fork 请自行判断。
