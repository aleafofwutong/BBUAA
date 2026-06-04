#!/usr/bin/env bash
# ============================================================
#  BBUAA (Break-Boundary Ur Academic Archive) 一键安装脚本
#  北航 classroom 课程回放浏览器
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# ---- 颜色 ----
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[x]${NC} $*"; }
step()  { echo -e "\n${BLUE}==>${NC} $*"; }

# ---- 配置 ----
VENV_DIR="$ROOT_DIR/.venv"
REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=10

step "检查 Python 环境"

# 找 Python
PYTHON=""
for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge "$REQUIRED_PYTHON_MAJOR" ] && [ "$minor" -ge "$REQUIRED_PYTHON_MINOR" ]; then
            PYTHON="$candidate"
            info "找到 Python $ver ($candidate)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    err "需要 Python >= 3.10，未找到可用版本"
    echo "  安装方法:"
    echo "    Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "    macOS:         brew install python@3.12"
    echo "    Conda:         conda create -n bbuaa python=3.12"
    exit 1
fi

# ---- 虚拟环境（可选） ----
USE_VENV=""
if [ "${1:-}" = "--venv" ] || [ "${1:-}" = "-v" ]; then
    USE_VENV="1"
    shift || true
fi

if [ -n "$USE_VENV" ]; then
    step "创建虚拟环境"
    if [ ! -d "$VENV_DIR" ]; then
        "$PYTHON" -m venv "$VENV_DIR"
        info "虚拟环境: $VENV_DIR"
    else
        info "虚拟环境已存在: $VENV_DIR"
    fi
    source "$VENV_DIR/bin/activate"
    PYTHON="$VENV_DIR/bin/python"
    PIP="$VENV_DIR/bin/pip"
else
    PIP="$PYTHON -m pip"
fi

# ---- 安装依赖 ----
step "安装 Python 依赖"

$PIP install --upgrade pip -q 2>/dev/null || true

PACKAGES=(
    "flask>=3.0"
    "requests>=2.31"
    "pillow>=9.0"
    "python-pptx>=0.6"
)

for pkg in "${PACKAGES[@]}"; do
    pkg_name="${pkg%%>=*}"
    if "$PYTHON" -c "import ${pkg_name//-/_}" 2>/dev/null; then
        info "$pkg_name 已安装"
    else
        info "安装 $pkg ..."
        $PIP install "$pkg"
    fi
done

# ---- 验证 ----
step "验证依赖"
"$PYTHON" <<'PYEOF'
import sys
errors = []
for mod, pkg in [
    ("flask", "flask"),
    ("requests", "requests"),
    ("PIL", "pillow"),
    ("pptx", "python-pptx"),
]:
    try:
        __import__(mod)
        print(f"  ✓ {pkg}")
    except ImportError:
        print(f"  ✗ {pkg} — 未安装")
        errors.append(pkg)
if errors:
    print(f"\n缺少依赖: {', '.join(errors)}")
    print("请手动安装: pip install " + " ".join(errors))
    sys.exit(1)
print("\n所有依赖就绪！")
PYEOF

# ---- 配置代理 ----
step "配置网络代理"

PROXY_HOST="${BBUAA_PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${BBUAA_PROXY_PORT:-7897}"

if [ -z "${BBUAA_PROXY:-}" ]; then
    warn "未设置 BBUAA_PROXY 环境变量"
    echo "  BUA 服务器可能需要代理访问。如果你已运行代理软件（如 clash/v2ray）"
    echo "  在 ${PROXY_HOST}:${PROXY_PORT}，请设置环境变量:"
    echo ""
    echo "    export BBUAA_PROXY=http://${PROXY_HOST}:${PROXY_PORT}"
    echo ""
    echo "  如果不需要代理，设置:"
    echo ""
    echo "    export BBUAA_PROXY=none"
    echo ""
    echo "  （可写入 ~/.bashrc 永久生效）"
else
    info "代理已配置: $BBUAA_PROXY"
fi

# ---- 创建 .env 文件（可选） ----
if [ ! -f "$ROOT_DIR/.env" ]; then
    cat > "$ROOT_DIR/.env" <<EOF
# BBUAA 环境配置
# 代理设置: http://host:port 或 none 禁用
BBUAA_PROXY=${BBUAA_PROXY:-http://127.0.0.1:7897}

# 北航 SSO 账号（可选，避免每次输入）
# BBUAA_USERNAME=你的学号
# BBUAA_PASSWORD=你的密码
EOF
    info "已创建 .env 模板: $ROOT_DIR/.env"
fi

# ---- 确保启动脚本可执行 ----
chmod +x "$ROOT_DIR/start_bbuaa.sh"

# ---- 完成 ----
echo ""
echo "============================================"
echo -e "  ${GREEN}BBUAA 安装完成！${NC}"
echo "============================================"
echo ""
echo "  启动方法:"
echo "    bash start_bbuaa.sh              # 默认端口 8765"
echo "    bash start_bbuaa.sh 9000         # 指定端口"
echo ""
if [ -n "$USE_VENV" ]; then
    echo "  使用虚拟环境（下次启动时）:"
    echo "    source .venv/bin/activate"
    echo "    bash start_bbuaa.sh"
    echo ""
fi
echo "  首次使用:"
echo "    1. 打开浏览器访问显示的地址"
echo "    2. 输入北航学号/工号和密码登录"
echo "    3. 搜索课程，点击 ▶ 进入播放器"
echo ""
echo "  可选环境变量 (写入 ~/.bashrc):"
echo "    export BBUAA_PROXY=http://127.0.0.1:7897"
echo "    export BBUAA_USERNAME=你的学号"
echo "    export BBUAA_PASSWORD=你的密码"
echo ""
