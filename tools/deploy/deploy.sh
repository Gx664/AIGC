#!/bin/sh
# 在服务器上执行：先上传 dashboard.py 和 dashboard_config.json 到本目录
if ! command -v python3 >/dev/null 2>&1; then
  echo "服务器需要 Python3：apt install python3"
  exit 1
fi
pkill -f "dashboard.py 8765" 2>/dev/null
nohup python3 dashboard.py 8765 0.0.0.0 > dashboard.log 2>&1 &
sleep 1
echo "看板已启动：http://你的服务器IP:8765"
echo "防火墙请放行 TCP 8765 端口"
