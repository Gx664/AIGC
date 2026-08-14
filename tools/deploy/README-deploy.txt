数据看板 · 公网部署说明（联网即用）
====================================

目标：手机在任何网络下都能打开看板，不需要电脑开机。
方法：把看板放到一台公网服务器上跑。

方案 A：轻量服务器（推荐，约 30~60 元/月）
1. 买一台香港轻量服务器（腾讯云/阿里云都行，香港免备案）
2. 用 SSH 登录服务器，把 tools/dashboard.py 和
   tools/dashboard_config.json 上传上去（可用 WinSCP/宝塔面板）
3. 服务器上执行：sh deploy.sh
4. 控制台/安全组放行 TCP 8765 端口
5. 手机浏览器打开 http://服务器IP:8765 即用（填访问密码）

方案 B：Docker（服务器装了 Docker 时）
1. 上传 dashboard.py、dashboard_config.json、Dockerfile
2. 执行：
   docker build -t aigc-dashboard .
   docker run -d --name aigc-dashboard -p 8765:8765 aigc-dashboard
3. 放行 8765 端口，访问同上

方案 C：免费托管平台（Railway / Render / Fly.io）
上传本项目后按平台向导部署，免费额度通常够个人使用。

安全必做：
- dashboard_config.json 里必须设置 access_token（访问密码），
  否则任何人都能看你的统计数据
- PostHog 个人密钥放在服务器端，不要放进手机 APK

部署完成后：
- 把公网地址（如 http://你的IP:8765?token=xxx）告诉作者，
  作者会把地址内置进 APK，手机装好打开即看，零配置
