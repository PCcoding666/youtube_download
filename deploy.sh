#!/bin/bash

set -e

echo "=========================================="
echo "部署 u2foru.site"
echo "=========================================="

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 解析参数
BUILD_FLAG=""
QUICK_MODE=false
NO_MAINTENANCE=false

for arg in "$@"; do
    case $arg in
        --build|-b)
            BUILD_FLAG="--build"
            ;;
        --quick|-q)
            QUICK_MODE=true
            ;;
        --no-maintenance)
            NO_MAINTENANCE=true
            ;;
        --help|-h)
            echo "用法: ./deploy.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --build, -b       重新构建镜像（默认不构建）"
            echo "  --quick, -q       快速模式：只重启容器，不停止"
            echo "  --no-maintenance  不显示维护页面"
            echo "  --help, -h        显示帮助"
            echo ""
            echo "示例:"
            echo "  ./deploy.sh           # 只重启，不重新构建"
            echo "  ./deploy.sh --build   # 重新构建并部署（显示维护页面）"
            echo "  ./deploy.sh -q        # 快速重启"
            exit 0
            ;;
    esac
done

PROJECT_DIR="/home/yt-final"
cd "$PROJECT_DIR"

# 维护模式函数
enable_maintenance() {
    if [ "$NO_MAINTENANCE" = false ]; then
        echo -e "${BLUE}🔧 启用维护模式...${NC}"
        touch "$PROJECT_DIR/.maintenance"
        # 重载 Nginx 让维护模式生效
        /etc/init.d/nginx reload 2>/dev/null || nginx -s reload 2>/dev/null || true
        echo -e "${GREEN}✓ 维护页面已启用${NC}"
    fi
}

disable_maintenance() {
    if [ -f "$PROJECT_DIR/.maintenance" ]; then
        echo -e "${BLUE}🔧 禁用维护模式...${NC}"
        rm -f "$PROJECT_DIR/.maintenance"
        # 重载 Nginx 恢复正常服务
        /etc/init.d/nginx reload 2>/dev/null || nginx -s reload 2>/dev/null || true
        echo -e "${GREEN}✓ 网站已恢复正常${NC}"
    fi
}

# 确保脚本退出时禁用维护模式（即使出错）
trap disable_maintenance EXIT

if [ "$QUICK_MODE" = true ]; then
    echo -e "${YELLOW}[快速模式] 重启容器...${NC}"
    docker-compose -f docker-compose.prod.yml restart
    echo -e "${GREEN}✓ 完成${NC}"
else
    # 启用维护模式（仅在需要构建或完整重启时）
    enable_maintenance
    
    echo -e "${YELLOW}[1/5] 停止现有容器...${NC}"
    docker-compose -f docker-compose.prod.yml down 2>/dev/null || true
    echo -e "${GREEN}✓ 完成${NC}"

    if [ -n "$BUILD_FLAG" ]; then
        echo -e "${YELLOW}[2/5] 重新构建镜像...${NC}"
        docker-compose -f docker-compose.prod.yml build
        echo -e "${GREEN}✓ 完成${NC}"
    else
        echo -e "${YELLOW}[2/5] 跳过构建（使用 --build 强制重新构建）${NC}"
    fi

    echo -e "${YELLOW}[3/5] 启动服务...${NC}"
    docker-compose -f docker-compose.prod.yml up -d
    echo -e "${GREEN}✓ 完成${NC}"
fi

echo -e "${YELLOW}[4/5] 等待服务就绪...${NC}"
sleep 10
for i in {1..30}; do
    if curl -sf http://127.0.0.1:9001/api/v1/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 服务已就绪${NC}"
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

echo -e "${YELLOW}[5/5] 重新加载 Nginx...${NC}"
# 禁用维护模式会在 trap 中自动执行，这里只是确保 Nginx 配置正确
/etc/init.d/nginx reload 2>/dev/null || nginx -s reload 2>/dev/null || true
echo -e "${GREEN}✓ 完成${NC}"

echo ""
echo "=========================================="
echo "测试结果"
echo "=========================================="
echo -n "前端: "
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9000/
echo -n "后端: "
curl -s http://127.0.0.1:9001/api/v1/health
echo ""
echo -n "HTTPS: "
curl -k -s -o /dev/null -w "%{http_code}\n" https://u2foru.site

echo ""
echo "访问地址: https://u2foru.site"
echo "=========================================="
