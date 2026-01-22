#!/bin/bash

# 开发环境设置脚本
set -e

echo "🚀 设置 YouTube 下载项目开发环境..."

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
check_tool git

# 创建必要目录
echo "📁 创建项目目录..."
mkdir -p downloads logs

# 复制环境变量文件
echo "⚙️ 设置环境变量..."
if [ ! -f backend/.env ]; then
    if [ -f backend/.env.example ]; then
        cp backend/.env.example backend/.env
        echo "✅ 已创建 backend/.env，请根据需要修改配置"
    else
        echo "⚠️ backend/.env.example 不存在，请手动创建 backend/.env"
    fi
fi

if [ ! -f frontend/.env ]; then
    if [ -f frontend/.env.example ]; then
        cp frontend/.env.example frontend/.env
        echo "✅ 已创建 frontend/.env，请根据需要修改配置"
    else
        echo "⚠️ frontend/.env.example 不存在，请手动创建 frontend/.env"
    fi
fi

# 构建开发镜像
echo "🏗️ 构建开发环境镜像..."
docker-compose -f docker-compose.dev.yml build

echo "✅ 开发环境设置完成！"
echo ""
echo "📋 接下来的步骤："
echo "1. 编辑 backend/.env 和 frontend/.env 配置文件"
echo "2. 运行 'npm run dev:start' 启动开发环境"
echo "3. 运行 'npm run dev:logs' 查看日志"
echo "4. 运行 'npm run dev:stop' 停止开发环境"