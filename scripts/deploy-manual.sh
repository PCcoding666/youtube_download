#!/bin/bash

# 手动部署脚本（用于紧急部署或本地测试）
set -e

# 配置变量
REGISTRY="registry.cn-hangzhou.aliyuncs.com"
NAMESPACE="youtube-download"
BACKEND_IMAGE="backend"
FRONTEND_IMAGE="frontend"
TAG=${1:-latest}

echo "🚀 开始手动部署 - Tag: $TAG"

# 检查必要工具
check_tool() {
    if ! command -v $1 &> /dev/null; then
        echo "❌ $1 未安装，请先安装"
        exit 1
    fi
}

echo "🔍 检查必要工具..."
check_tool docker
check_tool docker-compose

# 构建镜像
echo "🏗️ 构建镜像..."

# 构建后端镜像
echo "📦 构建后端镜像..."
docker build -t $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$TAG \
    --target production \
    backend/

# 构建前端镜像
echo "🎨 构建前端镜像..."
docker build -t $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$TAG \
    --target production \
    frontend/

# 推送镜像（如果提供了注册表凭据）
if [ ! -z "$DOCKER_REGISTRY_USER" ] && [ ! -z "$DOCKER_REGISTRY_PASS" ]; then
    echo "🔐 登录镜像仓库..."
    echo $DOCKER_REGISTRY_PASS | docker login $REGISTRY -u $DOCKER_REGISTRY_USER --password-stdin
    
    echo "📤 推送镜像..."
    docker push $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$TAG
    docker push $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$TAG
    
    echo "✅ 镜像推送完成"
else
    echo "⚠️ 未提供镜像仓库凭据，跳过推送步骤"
    echo "💡 设置 DOCKER_REGISTRY_USER 和 DOCKER_REGISTRY_PASS 环境变量以启用推送"
fi

# 生成生产环境 docker-compose 文件
echo "📝 生成生产环境配置..."
cat > docker-compose.prod.yml <<EOF
version: '3.8'

services:
  backend:
    image: $REGISTRY/$NAMESPACE/$BACKEND_IMAGE:$TAG
    container_name: youtube-download-backend
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env.production
    volumes:
      - ./downloads:/app/downloads
      - ./logs:/app/logs
    networks:
      - youtube-download
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  frontend:
    image: $REGISTRY/$NAMESPACE/$FRONTEND_IMAGE:$TAG
    container_name: youtube-download-frontend
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - youtube-download

networks:
  youtube-download:
    driver: bridge

volumes:
  downloads:
  logs:
EOF

echo "✅ 手动部署准备完成！"
echo ""
echo "📋 接下来的步骤："
echo "1. 将 docker-compose.prod.yml 上传到服务器"
echo "2. 在服务器上创建 .env.production 文件"
echo "3. 运行 'docker-compose -f docker-compose.prod.yml up -d'"
echo ""
echo "🔧 本地测试命令："
echo "docker-compose -f docker-compose.prod.yml up -d"