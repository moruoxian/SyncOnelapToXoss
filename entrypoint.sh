#!/bin/bash
set -e

# =============================================================================
# OneLap 多平台数据同步工具 — 容器启动脚本
#
# 环境变量:
#   ONELAP_MODE = sync (默认) | vnc
#     sync - 自动运行同步脚本，结束后容器保持 30 分钟供 VNC 查看
#     vnc  - 仅启动 VNC，不运行脚本，容器一直存活
#   VNC_PW      - VNC 密码（默认 onelap123）
# =============================================================================

# ----- 持久化数据目录（避免 Docker 把单个文件挂载创建成目录）-----
mkdir -p /app/data
for f in onelap_download_state.json strava_upload_state.json; do
    # 如果旧版本遗留了目录挂载（非 symlink），先移除
    if [ -d "/app/$f" ] && [ ! -L "/app/$f" ]; then
        echo "[FIX] /app/$f 是目录，移除并重建为 symlink"
        rm -rf "/app/$f"
    fi
    # 创建 symlink 指向持久化目录
    if [ ! -L "/app/$f" ]; then
        ln -sf "/app/data/$f" "/app/$f"
    fi
    # 确保目标文件存在
    if [ ! -f "/app/data/$f" ]; then
        touch "/app/data/$f"
    fi
done

# ----- 配置文件检查 -----
if [ ! -f /app/settings.ini ]; then
    cp /app/settings.ini.example /app/settings.ini
    echo "=========================================="
    echo "  [WARN] 已从模板创建 settings.ini"
    echo "  请编辑 ./settings.ini 填入真实账号密码后重新启动"
    echo "=========================================="
fi

# ----- 清理上一次运行残留 -----
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

# ----- VNC 密码（x11vnc -storepasswd 创建专用格式）-----
VNC_PW="${VNC_PW:-onelap123}"
mkdir -p /tmp/x11vnc
x11vnc -storepasswd "$VNC_PW" /tmp/x11vnc/passwd

# ----- Xvfb 虚拟显示 -----
Xvfb :99 -screen 0 1280x720x16 -ac +extension RANDR &
sleep 1

# ----- x11vnc（密码保护）-----
x11vnc -display :99 -forever -shared \
    -rfbauth /tmp/x11vnc/passwd \
    -rfbport 5900 -quiet &
sleep 1

# ----- noVNC（浏览器 → VNC 桥接）-----
NOVNC_WEB="${NOVNC_WEB:-/usr/share/novnc}"
if [ ! -d "$NOVNC_WEB" ]; then
    NOVNC_WEB=$(python3 -c "import novnc; print(novnc.__path__[0])" 2>/dev/null || echo "")
    [ -z "$NOVNC_WEB" ] && NOVNC_WEB=$(find / -path "*/site-packages/novnc" -type d 2>/dev/null | head -1)
fi
if [ -n "$NOVNC_WEB" ] && [ -d "$NOVNC_WEB" ]; then
    websockify --web "$NOVNC_WEB" 6080 localhost:5900 &
    NOVNC_STARTED=true
else
    echo "[WARN] noVNC 未找到，仅提供 VNC 端口 5900"
    NOVNC_STARTED=false
fi
sleep 1

echo "=========================================="
echo "  VNC 已启动: 端口 5900"
[ "$NOVNC_STARTED" = true ] && echo "  noVNC: http://<宿主机IP>:6080/vnc.html"
echo "  模式: ${ONELAP_MODE:-sync}"
echo "=========================================="

# ----- 根据模式决定行为 -----
ONELAP_MODE="${ONELAP_MODE:-sync}"

if [ "$ONELAP_MODE" = "vnc" ]; then
    echo "VNC 模式: 容器将持续运行，不会自动执行同步脚本。"
    echo "请通过 VNC 连接后手动操作浏览器。"
    exec sleep infinity
fi

# sync 模式: 跑同步脚本，结束后保持容器存活供 VNC 查看
echo "sync 模式: 开始执行同步脚本..."
cd /app
python3 SyncOnelapToXoss.py &
PY_PID=$!

# 等待脚本结束，同时处理 SIGTERM 优雅退出
cleanup() {
    echo "收到退出信号，清理中..."
    kill $PY_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

wait $PY_PID || true
PY_EXIT=$?

if [ $PY_EXIT -eq 0 ]; then
    echo "=========================================="
    echo "  同步脚本执行完毕。"
else
    echo "=========================================="
    echo "  同步脚本异常退出 (code=$PY_EXIT)。"
fi
echo "  容器将继续存活 30 分钟，可通过 VNC 查看浏览器状态。"
echo "  如需立即退出请按 Ctrl+C。"
echo "=========================================="

# 保活 30 分钟
sleep 1800 &
trap 'kill $! 2>/dev/null; cleanup' SIGTERM SIGINT
wait $! 2>/dev/null || true
