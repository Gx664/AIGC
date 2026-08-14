#!/data/data/com.termux/files/usr/bin/sh
# AIGC Dashboard - automated phone installer
# 每次运行都会先检查环境，只安装缺失的组件，带进度条

PROG=0
bar() {
    [ "$1" -lt "$PROG" ] && return
    PROG=$1
    W=30
    F=$((W * $1 / 100))
    B=$(printf '%*s' "$F" '' | tr ' ' '=')
    printf '\r[%-*s] %3d%% %s' "$W" "$B" "$1" "$2"
}
say() { printf '\n== %s ==\n' "$1"; }
ok()  { printf '  [OK] %s\n' "$1"; }
miss(){ printf '  [缺] %s\n' "$1"; }

clear
say "AI 数据看板 - 手机自动安装"
bar 2 "开始..."

# ---------- 1. 环境检查 ----------
say "第 1 步：检查环境（哪些有、哪些没有）"
MISSING=""

if command -v python3 >/dev/null 2>&1; then
    ok "Python 已安装 ($(python3 --version 2>&1))"
else
    miss "Python 未安装"
    MISSING="$MISSING python"
fi

if [ -d "$HOME/storage" ]; then
    ok "存储权限已开通"
else
    miss "存储权限未开通（将自动执行 termux-setup-storage）"
    MISSING="$MISSING storage"
fi

SRC=""
for d in "$(pwd)" "$HOME/storage/downloads" "$HOME/dashboard"; do
    if [ -f "$d/dashboard.py" ]; then
        SRC="$d"
        break
    fi
done
if [ -n "$SRC" ]; then
    ok "找到看板文件: $SRC"
else
    miss "找不到 dashboard.py（请把手机版压缩包解压到 Download）"
    MISSING="$MISSING files"
fi

bar 15 "环境检查完成"

# ---------- 2. 安装缺失组件 ----------
say "第 2 步：自动安装缺失组件"

if echo "$MISSING" | grep -q storage; then
    bar 18 "开通存储权限..."
    termux-setup-storage
fi

if echo "$MISSING" | grep -q python; then
    bar 25 "更新软件源..."
    pkg update -y || true
    bar 45 "下载安装 Python（pkg 自带进度）..."
    pkg install -y python || { printf '\nPython 安装失败\n'; exit 1; }
fi

bar 60 "组件安装完成"

# ---------- 3. 复制文件 ----------
say "第 3 步：准备看板文件"
mkdir -p "$HOME/dashboard"
if [ -n "$SRC" ]; then
    cp -f "$SRC/dashboard.py" "$SRC/dashboard_config.json" "$HOME/dashboard/" 2>/dev/null
fi
bar 75 "文件就绪"

# ---------- 4. 配置检查 ----------
say "第 4 步：检查配置"
KEY=""
if [ -f "$HOME/dashboard/dashboard_config.json" ]; then
    KEY=$(grep -o '"personal_api_key"[^,]*' "$HOME/dashboard/dashboard_config.json" \
        | sed 's/.*"personal_api_key"[[:space:]]*:[[:space:]]*"//; s/".*//' | head -1)
fi
if [ -n "$KEY" ]; then
    ok "个人密钥已配置"
else
    miss "personal_api_key 为空（请编辑 ~/dashboard/dashboard_config.json）"
fi
bar 85 "配置检查完成"

# ---------- 5. 启动并自检 ----------
say "第 5 步：启动看板并自检"
pkill -f "dashboard.py 8765" 2>/dev/null || true
cd "$HOME/dashboard"
nohup python3 dashboard.py 8765 0.0.0.0 > dashboard.log 2>&1 &
sleep 3

HTTP=$(python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8765', timeout=5).status)" 2>/dev/null)
if [ "$HTTP" = "200" ]; then
    ok "看板运行中（返回 200）"
else
    miss "看板未响应，请查看 ~/dashboard/dashboard.log"
fi
bar 100 "完成"

printf '\n\n==============================================\n'
printf '手机浏览器打开: http://127.0.0.1:8765\n'
printf '日志: ~/dashboard/dashboard.log\n'
printf '重启看板: 再次运行 sh termux_setup.sh\n'
printf '==============================================\n'
