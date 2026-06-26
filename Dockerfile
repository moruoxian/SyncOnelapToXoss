# =============================================================================
# OneLap 多平台数据同步工具 — 带 VNC 的 Docker 镜像
#
# 基础镜像: selenium/standalone-chromium（官方维护，内置 Chrome + VNC 组件）
#
# 加速构建（国内）：
#   docker compose build --build-arg APT_MIRROR=mirrors.aliyun.com
#
# 如果拉取镜像失败（1panel 等镜像站未代理此镜像）：
#   docker pull docker.io/selenium/standalone-chromium:latest
#   如果仍然失败，临时绕过镜像站：
#   docker pull --registry-mirror= docker.io/selenium/standalone-chromium:latest
# =============================================================================
FROM selenium/standalone-chromium:latest

# 切换 root
USER root

# apt 镜像加速（可选，构建时传 --build-arg APT_MIRROR=mirrors.aliyun.com）
ARG APT_MIRROR=""
RUN if [ -n "$APT_MIRROR" ]; then \
        sed -i "s|http://archive.ubuntu.com|http://${APT_MIRROR}|g" /etc/apt/sources.list.d/*.sources 2>/dev/null || \
        sed -i "s|http://archive.ubuntu.com|http://${APT_MIRROR}|g" /etc/apt/sources.list 2>/dev/null || true ; \
        sed -i "s|http://security.ubuntu.com|http://${APT_MIRROR}|g" /etc/apt/sources.list.d/*.sources 2>/dev/null || \
        sed -i "s|http://security.ubuntu.com|http://${APT_MIRROR}|g" /etc/apt/sources.list 2>/dev/null || true ; \
        echo "[OK] apt 镜像已切换至 ${APT_MIRROR}" ; \
    fi

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    novnc \
    websockify \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# Python 依赖（传 PIP_INDEX 可加速，如 --build-arg PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/）
ARG PIP_INDEX=""
RUN if [ -n "$PIP_INDEX" ]; then \
        PIP_EXTRA="-i $PIP_INDEX" ; \
    fi ; \
    pip3 install --break-system-packages --no-cache-dir $PIP_EXTRA \
        DrissionPage>=4.0.0 \
        requests>=2.25.0 \
        bs4>=0.0.1 \
        beautifulsoup4

# 复制程序文件
COPY SyncOnelapToXoss.py /app/
COPY incremental_sync_v2.py /app/
COPY settings.ini.example /app/

# 复制启动脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 将 /app 所有权交给 seluser，方便 entrypoint 创建 symlink
RUN chown -R seluser:seluser /app

# 切回非 root
USER seluser

WORKDIR /app
EXPOSE 5900 6080

ENTRYPOINT ["/entrypoint.sh"]
