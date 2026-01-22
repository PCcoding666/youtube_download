# 服务器部署完整指南

本指南将帮助你从零开始在服务器上部署 YouTube Transcriber 项目。

## 目录

1. [架构说明](#架构说明)
2. [前置准备](#1-前置准备)
3. [服务器环境配置](#2-服务器环境配置)
4. [项目部署](#3-项目部署)
5. [服务验证](#4-服务验证)
6. [常见问题排查](#5-常见问题排查)
7. [生产环境优化](#6-生产环境优化)

---

## 架构说明

你的项目使用 **双重认证机制** 来访问 YouTube：

```
┌─────────────────────────────────────────────────────────────┐
│                     YouTube Transcriber                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │   Frontend   │───▶│   Backend    │───▶│   yt-dlp     │   │
│  │   (React)    │    │  (FastAPI)   │    │              │   │
│  └──────────────┘    └──────────────┘    └──────┬───────┘   │
│                                                  │           │
│                           ┌──────────────────────┼───────┐   │
│                           │                      ▼       │   │
│                           │  ┌──────────────────────┐    │   │
│                           │  │  bgutil PO Token     │    │   │
│                           │  │  Provider (Docker)   │    │   │
│                           │  │  localhost:4416      │    │   │
│                           │  └──────────────────────┘    │   │
│                           │         提供 PO Token        │   │
│                           └──────────────────────────────┘   │
│                                                              │
│                           ┌──────────────────────────────┐   │
│                           │  AgentGo (云端浏览器)         │   │
│                           │  提供 Cookies + Visitor Data │   │
│                           └──────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

| 组件 | 来源 | 作用 |
|------|------|------|
| **PO Token** | bgutil 服务 (本地 Docker, 端口 4416) | 绕过 YouTube 机器人检测 |
| **Cookies + Visitor Data** | AgentGo (云端浏览器 API) | 提供登录状态和访客标识 |

**工作流程：**
1. `bgutil-ytdlp-pot-provider` 作为 Docker sidecar 运行，yt-dlp 通过插件自动调用它获取 PO Token
2. `AgentGo` 是云端浏览器服务，用于提取 YouTube Cookies 和 Visitor Data
3. 两者配合使用，确保 YouTube 下载的稳定性

---

## 1. 前置准备

### 1.1 服务器要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2核 | 4核+ |
| 内存 | 4GB | 8GB+ |
| 硬盘 | 40GB SSD | 100GB SSD |
| 系统 | Ubuntu 20.04+ / CentOS 7+ | Ubuntu 22.04 |
| 网络 | 公网IP | 公网IP + 域名 |

### 1.2 需要准备的账号和密钥

在开始之前，请确保你已经获取以下信息：

```
□ 阿里云 OSS 配置
  - Access Key ID
  - Access Key Secret
  - OSS Endpoint (如: oss-cn-hangzhou.aliyuncs.com)
  - Bucket 名称

□ Qwen API 配置
  - API Key (从 DashScope 获取)

□ AgentGo 配置 (用于 YouTube 访问)
  - API Key (从 https://docs.agentgo.live/ 获取)
  - YouTube 账号邮箱和密码 (可选，用于登录获取 cookies)

□ 服务器访问
  - 服务器 IP 地址
  - SSH 登录凭证 (用户名/密码 或 SSH 密钥)
```

---

## 2. 服务器环境配置

### 2.1 SSH 连接到服务器

```bash
ssh root@你的服务器IP
# 或使用密钥
ssh -i ~/.ssh/your_key root@你的服务器IP
```

### 2.2 系统更新

**Ubuntu/Debian:**
```bash
apt update && apt upgrade -y
```

**CentOS/RHEL:**
```bash
yum update -y
```

### 2.3 安装 Docker

```bash
# 一键安装 Docker
curl -fsSL https://get.docker.com | sh

# 启动并设置开机自启
systemctl enable docker
systemctl start docker

# 验证安装
docker --version
```

### 2.4 安装 Docker Compose

```bash
# 获取最新版本
DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)

# 下载并安装
curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

chmod +x /usr/local/bin/docker-compose

# 验证安装
docker-compose --version
```

### 2.5 创建项目目录

```bash
mkdir -p /opt/youtube_download
cd /opt/youtube_download

# 创建必要的子目录
mkdir -p backups storage scripts
mkdir -p /tmp/video_processing
chmod 777 /tmp/video_processing
```

---

## 3. 项目部署

### 3.1 方式一：直接从 GitHub 克隆（推荐）

```bash
cd /opt
git clone https://github.com/你的用户名/youtube_download.git
cd youtube_download
```

### 3.2 方式二：手动上传文件

如果无法访问 GitHub，可以从本地上传：

```bash
# 在本地执行
scp -r ./backend ./frontend ./docker-compose.yml root@服务器IP:/opt/youtube_download/
```

### 3.3 配置环境变量

创建后端环境变量文件：

```bash
cd /opt/youtube_download/backend
cp .env.example .env
nano .env
```

填入以下配置（根据你的实际情况修改）：

```bash
# ====================================
# 必需配置
# ====================================

# Qwen API (AI 转录服务)
QWEN_API_KEY=sk-你的qwen_api_key
QWEN_API_BASE=https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions

# 阿里云 OSS (文件存储)
ALIYUN_ACCESS_KEY_ID=你的access_key_id
ALIYUN_ACCESS_KEY_SECRET=你的access_key_secret
ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
ALIYUN_OSS_BUCKET=你的bucket名称

# ====================================
# AgentGo 配置 (YouTube 访问方案)
# ====================================
AGENTGO_API_KEY=api_你的agentgo_key
AGENTGO_API_URL=https://api.browsers.live
AGENTGO_REGION=us

# YouTube 账号 (可选，用于获取 cookies)
YOUTUBE_EMAIL=你的youtube邮箱
YOUTUBE_PASSWORD=你的youtube密码

# ====================================
# 应用配置
# ====================================
SECRET_KEY=生成一个随机字符串作为密钥
STORAGE_DIR=./storage
LOG_LEVEL=INFO
TEMP_DIR=/tmp/video_processing

# 视频处理限制
MAX_VIDEO_DURATION=600
TRANSCRIPTION_TIMEOUT=300
POLL_INTERVAL=5

# CORS 配置 (根据你的域名修改)
CORS_ORIGINS=http://你的域名,http://localhost:5173,http://localhost:3000

# ====================================
# 可选：代理配置
# ====================================
# 如果服务器在国内，可能需要代理访问 YouTube
# YOUTUBE_PROXY=http://127.0.0.1:7890
```

创建前端环境变量文件：

```bash
cd /opt/youtube_download/frontend
cp .env.example .env
nano .env
```

```bash
# 后端 API 地址
VITE_API_URL=http://你的服务器IP:8000
# 如果有域名
# VITE_API_URL=https://你的域名/api
```

### 3.4 构建并启动服务

```bash
cd /opt/youtube_download

# 构建镜像并启动
docker-compose up -d --build

# 查看启动状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 3.5 服务端口说明

| 服务 | 端口 | 说明 |
|------|------|------|
| Frontend | 80 | 前端 Web 界面 |
| Backend | 8000 | 后端 API 服务 |
| bgutil | 4416 | PO Token Provider |

---

## 4. 服务验证

### 4.1 检查容器状态

```bash
docker-compose ps
```

预期输出：
```
NAME                    STATUS              PORTS
bgutil-pot-provider     Up (healthy)        0.0.0.0:4416->4416/tcp
yt-transcriber-backend  Up (healthy)        0.0.0.0:8000->8000/tcp
yt-transcriber-frontend Up                  0.0.0.0:80->80/tcp
```

### 4.2 健康检查

```bash
# 后端健康检查
curl http://localhost:8000/api/v1/health
# 预期返回: {"status":"healthy","version":"1.0.0",...}

# PO Token Provider 检查
curl http://localhost:4416/ping
# 预期返回: {"server_uptime":...,"version":"..."}

# 前端检查
curl -I http://localhost
# 预期返回: HTTP/1.1 200 OK
```

### 4.3 API 文档访问

在浏览器中访问：
- Swagger UI: `http://你的服务器IP:8000/docs`
- ReDoc: `http://你的服务器IP:8000/redoc`

### 4.4 前端访问

在浏览器中访问：`http://你的服务器IP`

---

## 5. 常见问题排查

### 5.1 容器启动失败

```bash
# 查看详细日志
docker-compose logs backend
docker-compose logs frontend
docker-compose logs bgutil

# 重新构建
docker-compose down
docker-compose up -d --build --force-recreate
```

### 5.2 后端无法连接 OSS

检查环境变量是否正确：
```bash
docker exec yt-transcriber-backend env | grep ALIYUN
```

### 5.3 YouTube 下载失败

1. 检查 AgentGo 配置：
```bash
docker exec yt-transcriber-backend env | grep AGENTGO
```

2. 检查 PO Token Provider 是否正常：
```bash
curl http://localhost:4416/ping
```

3. 查看后端日志中的具体错误：
```bash
docker logs yt-transcriber-backend --tail 100
```

### 5.4 CORS 错误

确保 `CORS_ORIGINS` 包含前端访问的域名：
```bash
# 编辑环境变量
nano /opt/youtube_download/backend/.env

# 重启后端
docker-compose restart backend
```

### 5.5 端口被占用

```bash
# 查看端口占用
lsof -i :80
lsof -i :8000
lsof -i :4416

# 杀死占用进程
kill -9 <PID>
```

### 5.6 磁盘空间不足

```bash
# 查看磁盘使用
df -h

# 清理 Docker 缓存
docker system prune -a

# 清理临时文件
rm -rf /tmp/video_processing/*
```

---

## 6. 生产环境优化

### 6.1 配置 Nginx 反向代理 + SSL

安装 Nginx 和 Certbot：
```bash
apt install nginx certbot python3-certbot-nginx -y
```

创建 Nginx 配置：
```bash
nano /etc/nginx/sites-available/youtube-download
```

```nginx
server {
    listen 80;
    server_name 你的域名;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }
}
```

启用配置并申请 SSL：
```bash
ln -s /etc/nginx/sites-available/youtube-download /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# 申请 SSL 证书
certbot --nginx -d 你的域名
```

### 6.2 配置防火墙

```bash
# Ubuntu (ufw)
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# CentOS (firewalld)
firewall-cmd --permanent --add-service=ssh
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https
firewall-cmd --reload
```

### 6.3 设置开机自启

```bash
# 创建 systemd 服务
cat > /etc/systemd/system/youtube-download.service << EOF
[Unit]
Description=YouTube Download Service
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/youtube_download
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable youtube-download
```

### 6.4 日志管理

配置日志轮转：
```bash
cat > /etc/logrotate.d/youtube-download << EOF
/opt/youtube_download/backend/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
EOF
```

### 6.5 监控和告警

使用 Docker 内置的健康检查：
```bash
# 查看容器健康状态
docker inspect --format='{{.State.Health.Status}}' yt-transcriber-backend
```

创建简单的监控脚本：
```bash
cat > /opt/youtube_download/scripts/health_check.sh << 'EOF'
#!/bin/bash
BACKEND_HEALTH=$(curl -s http://localhost:8000/api/v1/health | grep -c "healthy")
if [ "$BACKEND_HEALTH" -eq 0 ]; then
    echo "Backend unhealthy, restarting..."
    cd /opt/youtube_download && docker-compose restart backend
fi
EOF

chmod +x /opt/youtube_download/scripts/health_check.sh

# 添加到 crontab (每5分钟检查一次)
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/youtube_download/scripts/health_check.sh") | crontab -
```

---

## 快速命令参考

```bash
# 启动所有服务
docker-compose up -d

# 停止所有服务
docker-compose down

# 重启单个服务
docker-compose restart backend

# 查看日志
docker-compose logs -f backend

# 进入容器调试
docker exec -it yt-transcriber-backend bash

# 更新代码后重新部署
git pull
docker-compose up -d --build

# 清理所有数据重新开始
docker-compose down -v
docker system prune -a
docker-compose up -d --build
```

---

## 部署检查清单

- [ ] 服务器满足最低配置要求
- [ ] Docker 和 Docker Compose 已安装
- [ ] 项目代码已上传/克隆
- [ ] 后端 `.env` 已配置所有必需项
- [ ] 前端 `.env` 已配置 API 地址
- [ ] 所有容器正常运行 (docker-compose ps)
- [ ] 后端健康检查通过
- [ ] 前端可以正常访问
- [ ] 防火墙已配置
- [ ] (可选) SSL 证书已配置
- [ ] (可选) 开机自启已设置

---

如有问题，请查看日志或联系项目维护者。
