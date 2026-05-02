#!/bin/bash
# Gcode 部署脚本 — 麒麟OS
# 用法: sudo bash deploy/setup.sh

set -e

# 自动检测项目根目录（脚本所在目录的上一级）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

GCODE_DIR="/opt/gcode"
GCODE_USER="gcode"
SOCKET_DIR="/run/gcode"
DATA_DIR="${GCODE_DIR}/data"

echo "=== Gcode 智能运维Agent 部署 ==="
echo "源码目录: ${PROJECT_DIR}"
echo "安装目录: ${GCODE_DIR}"

# 1. 创建用户
if ! id -u ${GCODE_USER} &>/dev/null; then
    echo "[1/7] 创建用户 ${GCODE_USER}..."
    useradd -r -s /sbin/nologin -d ${GCODE_DIR} ${GCODE_USER}
else
    echo "[1/7] 用户 ${GCODE_USER} 已存在"
fi

# 2. 创建目录
echo "[2/7] 创建目录..."
mkdir -p ${GCODE_DIR}
mkdir -p ${SOCKET_DIR}
mkdir -p ${DATA_DIR}
mkdir -p ${DATA_DIR}/audit
mkdir -p ${DATA_DIR}/logs

# 3. 复制代码（排除 .git、缓存等）
echo "[3/7] 复制代码到 ${GCODE_DIR}..."
rsync -a --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
      --exclude '.pytest_cache' --exclude '*.egg-info' \
      "${PROJECT_DIR}/" "${GCODE_DIR}/"

# 4. 安装依赖
echo "[4/7] 安装 Python 依赖..."
cd ${GCODE_DIR}
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[reasoner-openai]" 2>/dev/null || pip install -e .

# 5. 安装 gcode CLI 命令（pip install 自动创建）
echo "[5/7] 安装 gcode 命令..."
# entry_points 会自动创建 gcode 命令到 .venv/bin/
ln -sf /opt/gcode/.venv/bin/gcode /usr/local/bin/gcode 2>/dev/null || true

# 6. 设置权限
echo "[6/7] 设置权限..."
chown -R ${GCODE_USER}:${GCODE_USER} ${GCODE_DIR}
chown -R ${GCODE_USER}:${GCODE_USER} ${SOCKET_DIR}
chown -R ${GCODE_USER}:${GCODE_USER} ${DATA_DIR}
chmod 750 ${GCODE_DIR}
chmod 770 ${SOCKET_DIR}
chmod 750 ${DATA_DIR}
chmod +x /usr/local/bin/gcode

# 7. 安装 systemd 服务
echo "[7/7] 安装 systemd 服务..."
cp ${GCODE_DIR}/deploy/gcode-security-guard.service /etc/systemd/system/
cp ${GCODE_DIR}/deploy/gcode-mcp-server.service /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "=== 部署完成 ==="
echo ""
echo "现在直接输入:  gcode"
echo ""
echo "服务状态:"
systemctl status gcode-security-guard --no-pager -l 2>/dev/null || true
echo ""
systemctl status gcode-mcp-server --no-pager -l 2>/dev/null || true
echo ""
echo "Socket: ${SOCKET_DIR}/gcode.sock"
echo "数据目录: ${DATA_DIR}"
echo "日志: journalctl -u gcode-security-guard -u gcode-mcp-server -f"
