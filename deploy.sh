#!/bin/bash
# 飞牛 NAS 一键部署脚本
# 用法: curl -sSL <raw_url>/deploy.sh | bash
# 或者: ./deploy.sh

set -e

REPO_URL="${REPO_URL:-https://github.com/victoriousxia/telegram-ai-bot.git}"
INSTALL_DIR="${INSTALL_DIR:-/vol1/docker/telegram-ai-bot}"

echo "=== Telegram AI Bot 部署脚本 ==="
echo ""

# 检查 docker 和 docker compose
if ! command -v docker &> /dev/null; then
    echo "错误: 未找到 docker，请先在飞牛 NAS 中安装 Docker。"
    exit 1
fi

if ! docker compose version &> /dev/null 2>&1; then
    echo "错误: 未找到 docker compose，请确认 Docker 版本支持 compose 插件。"
    exit 1
fi

# 克隆或更新代码
if [ -d "$INSTALL_DIR" ]; then
    echo "检测到已有安装，正在更新..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "正在克隆仓库到 $INSTALL_DIR ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 检查 .env 是否存在
if [ ! -f .env ]; then
    echo ""
    echo "未检测到 .env 配置文件，正在从模板创建..."
    cp config.example.env .env
    echo ""
    echo "请编辑 .env 文件填入你的配置："
    echo "  nano $INSTALL_DIR/.env"
    echo ""
    echo "必填项："
    echo "  - TELEGRAM_BOT_TOKEN (从 @BotFather 获取)"
    echo "  - PROVIDERS 中的 api_key"
    echo ""
    echo "配置完成后重新运行此脚本即可启动。"
    exit 0
fi

# 构建并启动
echo ""
echo "正在构建并启动容器..."
docker compose down 2>/dev/null || true
docker compose up -d --build

echo ""
echo "=== 部署完成 ==="
echo ""
echo "查看日志: docker compose -f $INSTALL_DIR/docker-compose.yml logs -f"
echo "停止服务: docker compose -f $INSTALL_DIR/docker-compose.yml down"
echo "重启服务: docker compose -f $INSTALL_DIR/docker-compose.yml restart"
