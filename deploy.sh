#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="/home/yt-final"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
cd "$PROJECT_DIR"

show_help() {
    echo "用法: ./deploy.sh [选项]"
    echo ""
    echo "选项:"
    echo "  (无参数)          智能部署: 重建前后端镜像并重启"
    echo "  --frontend, -f    只重建前端"
    echo "  --backend, -b     只重建后端"
    echo "  --restart, -r     只重启容器（不重建镜像）"
    echo "  --full            完整重建所有服务（含 postgres/bgutil）"
    echo "  --help, -h        显示帮助"
    exit 0
}

# 解析参数
MODE="smart"  # smart | frontend | backend | restart | full
for arg in "$@"; do
    case $arg in
        --frontend|-f) MODE="frontend" ;;
        --backend|-b)  MODE="backend" ;;
        --restart|-r)  MODE="restart" ;;
        --full)        MODE="full" ;;
        --help|-h)     show_help ;;
    esac
done

# ========== 维护模式 ==========
enable_maintenance() {
    touch "$PROJECT_DIR/.maintenance"
    nginx -s reload 2>/dev/null || /etc/init.d/nginx reload 2>/dev/null || true
}
disable_maintenance() {
    rm -f "$PROJECT_DIR/.maintenance"
    nginx -s reload 2>/dev/null || /etc/init.d/nginx reload 2>/dev/null || true
}
trap disable_maintenance EXIT

echo ""
echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE}  部署 u2foru.site  [模式: ${YELLOW}${MODE}${BLUE}]${NC}"
echo -e "${BLUE}===========================================${NC}"
echo ""

# ========== 启用维护页面 ==========
echo -e "${YELLOW}[1/4] 启用维护页面...${NC}"
enable_maintenance
echo -e "${GREEN}  ✓ 维护页面已启用${NC}"

# ========== 确保基础服务运行 ==========
echo -e "${YELLOW}[2/4] 检查基础服务...${NC}"
# 确保 postgres 和 bgutil 在运行
POSTGRES_RUNNING=$(docker ps --filter "name=yt-postgres" --filter "status=running" -q)
BGUTIL_RUNNING=$(docker ps --filter "name=yt-bgutil" --filter "status=running" -q)

if [ -z "$POSTGRES_RUNNING" ] || [ -z "$BGUTIL_RUNNING" ]; then
    echo -e "  基础服务未运行，启动 postgres + bgutil..."
    docker-compose -f "$COMPOSE_FILE" up -d postgres bgutil 2>&1 | grep -v "^WARN"
    echo -e "  等待健康检查..."
    sleep 5
    for i in {1..20}; do
        PG_OK=$(docker inspect --format='{{.State.Health.Status}}' yt-postgres 2>/dev/null || echo "none")
        BG_OK=$(docker inspect --format='{{.State.Health.Status}}' yt-bgutil 2>/dev/null || echo "none")
        if [ "$PG_OK" = "healthy" ] && [ "$BG_OK" = "healthy" ]; then
            break
        fi
        sleep 2
    done
fi
echo -e "${GREEN}  ✓ postgres + bgutil 运行中${NC}"

# ========== 构建 + 重启 ==========
echo -e "${YELLOW}[3/4] 构建 & 部署...${NC}"

case $MODE in
    smart)
        # 只重建 frontend + backend，不碰 postgres/bgutil
        docker-compose -f "$COMPOSE_FILE" build --parallel frontend backend 2>&1 | tail -5
        docker-compose -f "$COMPOSE_FILE" up -d --no-deps frontend backend 2>&1 | grep -v "^WARN"
        ;;
    frontend)
        docker-compose -f "$COMPOSE_FILE" build frontend 2>&1 | tail -5
        docker-compose -f "$COMPOSE_FILE" up -d --no-deps frontend 2>&1 | grep -v "^WARN"
        ;;
    backend)
        docker-compose -f "$COMPOSE_FILE" build backend 2>&1 | tail -5
        docker-compose -f "$COMPOSE_FILE" up -d --no-deps backend 2>&1 | grep -v "^WARN"
        ;;
    restart)
        docker-compose -f "$COMPOSE_FILE" restart frontend backend
        ;;
    full)
        docker-compose -f "$COMPOSE_FILE" down 2>/dev/null || true
        docker-compose -f "$COMPOSE_FILE" build --parallel 2>&1 | tail -10
        docker-compose -f "$COMPOSE_FILE" up -d 2>&1 | grep -v "^WARN"
        ;;
esac
echo -e "${GREEN}  ✓ 构建完成${NC}"

# ========== 等待服务就绪 ==========
echo -e "${YELLOW}[4/4] 等待服务就绪...${NC}"
for i in {1..30}; do
    if curl -sf http://127.0.0.1:9001/api/v1/health > /dev/null 2>&1; then
        echo -e "${GREEN}  ✓ 后端就绪${NC}"
        break
    fi
    [ $i -eq 30 ] && echo -e "${RED}  ✗ 后端超时${NC}"
    sleep 2
done

if curl -sf http://127.0.0.1:9000/ > /dev/null 2>&1; then
    echo -e "${GREEN}  ✓ 前端就绪${NC}"
else
    echo -e "${RED}  ✗ 前端未响应${NC}"
fi

# ========== 测试结果 ==========
echo ""
echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE}  测试结果${NC}"
echo -e "${BLUE}===========================================${NC}"
echo -n "  前端: "; curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9000/ ; echo ""
echo -n "  后端: "; curl -s http://127.0.0.1:9001/api/v1/health 2>/dev/null | head -c 80; echo ""
echo -n "  HTTPS: "; curl -k -s -o /dev/null -w "%{http_code}" https://u2foru.site 2>/dev/null; echo ""
echo ""
echo -e "${GREEN}  ✓ 部署完成! https://u2foru.site${NC}"
echo -e "${BLUE}===========================================${NC}"
