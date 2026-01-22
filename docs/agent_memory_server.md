# YouTube Transcriber - 服务器端 Agent Memory

> 本文档是服务器端 AI Agent 的完整记忆文档，包含项目架构、部署、运维、故障排查等所有关键信息。

---

## 📋 项目概述

### 项目名称
YouTube Download & Transcription Service

### 核心功能
1. **YouTube 视频下载** - 支持多分辨率 (360p-4K)
2. **AI 语音转录** - 使用阿里云 Paraformer-v2
3. **智能摘要生成** - 基于 Qwen AI
4. **云存储** - 阿里云 OSS 集成
5. **反机器人检测** - PO Token + AgentGo 双重认证
6. **智能地理路由** - 基于用户 IP 自动选择最优区域

### 技术栈
| 层级 | 技术 |
|------|------|
| 前端 | React 19 + TypeScript + Vite 7 |
| 后端 | Python 3.11 + FastAPI + Uvicorn |
| 视频处理 | yt-dlp + FFmpeg |
| AI 服务 | 阿里云 DashScope (Qwen/Paraformer) |
| 存储 | 阿里云 OSS |
| 容器化 | Docker + Docker Compose |
| 反检测 | bgutil-ytdlp-pot-provider + AgentGo |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        YouTube Transcriber                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │   Frontend   │───▶│   Backend    │───▶│      yt-dlp          │   │
│  │   (React)    │    │  (FastAPI)   │    │  + bgutil plugin     │   │
│  │   Port: 80   │    │  Port: 8000  │    └──────────┬───────────┘   │
│  └──────────────┘    └──────────────┘               │               │
│                             │                        │               │
│                             ▼                        ▼               │
│                    ┌──────────────┐    ┌──────────────────────┐     │
│                    │  Aliyun OSS  │    │  bgutil PO Token     │     │
│                    │  (存储)       │    │  Provider (Docker)   │     │
│                    └──────────────┘    │  Port: 4416          │     │
│                             │          └──────────────────────┘     │
│                             ▼                        │               │
│                    ┌──────────────┐                  │               │
│                    │  Paraformer  │    ┌─────────────▼──────────┐   │
│                    │  (转录服务)   │    │  AgentGo (云端浏览器)   │   │
│                    └──────────────┘    │  Cookies + Visitor Data│   │
│                                        └────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 认证机制说明
| 组件 | 来源 | 作用 |
|------|------|------|
| **PO Token** | bgutil 服务 (本地 Docker, 端口 4416) | 绕过 YouTube 机器人检测 |
| **Cookies + Visitor Data** | AgentGo (云端浏览器 API) | 提供登录状态和访客标识 |

---

## 📁 项目结构

```
youtube_download/
├── backend/                          # 后端服务
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI 入口
│   │   ├── config.py                 # 配置管理
│   │   ├── models.py                 # Pydantic 模型
│   │   ├── api/
│   │   │   └── routes.py             # API 路由
│   │   ├── services/
│   │   │   ├── downloader.py         # YouTube 下载服务
│   │   │   ├── agentgo_service.py    # AgentGo 认证服务
│   │   │   ├── transcriber.py        # 转录服务
│   │   │   ├── storage.py            # OSS 存储服务
│   │   │   ├── url_extractor.py      # URL 提取服务
│   │   │   ├── geo_service.py        # 地理路由服务
│   │   │   └── stream_converter.py   # 流转换服务
│   │   └── utils/
│   │       └── ffmpeg_tools.py       # FFmpeg 工具
│   ├── bgutil-ytdlp-pot-provider/    # PO Token Provider
│   │   └── server/
│   │       ├── src/
│   │       ├── build/
│   │       └── package.json
│   ├── tests/                        # 测试文件
│   ├── .env                          # 环境变量
│   ├── .env.example                  # 环境变量示例
│   ├── requirements.txt              # Python 依赖
│   ├── Dockerfile                    # Docker 构建文件
│   └── pytest.ini                    # 测试配置
│
├── frontend/                         # 前端服务
│   ├── src/
│   │   ├── App.tsx                   # 主组件
│   │   ├── api.ts                    # API 客户端
│   │   ├── App.css                   # 样式
│   │   └── main.tsx                  # 入口
│   ├── .env                          # 环境变量
│   ├── package.json                  # Node 依赖
│   ├── Dockerfile                    # Docker 构建文件
│   ├── nginx.conf                    # Nginx 配置
│   └── vite.config.ts                # Vite 配置
│
├── docs/                             # 文档
│   ├── architecture/
│   ├── guides/
│   └── backend/
│
├── scripts/                          # 部署脚本
│   ├── deploy.sh                     # 部署脚本
│   └── setup-server.sh               # 服务器初始化
│
├── docker-compose.yml                # 开发环境
├── docker-compose.prod.yml           # 生产环境
├── start-all-services.sh             # 完整启动脚本
├── start-dev.sh                      # 开发启动脚本
└── check-services.sh                 # 服务检查脚本
```

---

## 🔧 环境配置

### 后端环境变量 (backend/.env)

```bash
# ====================================
# 必需配置
# ====================================

# Qwen API (AI 转录和摘要)
QWEN_API_KEY=sk-your-qwen-api-key
QWEN_API_BASE=https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions

# 阿里云 OSS (文件存储)
OSS_ACCESS_KEY_ID=your-access-key-id
OSS_ACCESS_KEY_SECRET=your-access-key-secret
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET=your-bucket-name

# ====================================
# AgentGo 配置 (YouTube 访问)
# ====================================
AGENTGO_API_KEY=api_your-agentgo-key
AGENTGO_API_URL=https://api.browsers.live
AGENTGO_REGION=us  # 支持: us, uk, de, fr, jp, sg, in, au, ca

# YouTube 账号 (用于获取 cookies)
YOUTUBE_EMAIL=your-youtube-email@gmail.com
YOUTUBE_PASSWORD=your-youtube-password

# ====================================
# 应用配置
# ====================================
SECRET_KEY=your-random-secret-key
STORAGE_DIR=./storage
LOG_LEVEL=INFO
TEMP_DIR=/tmp/video_processing

# 视频处理限制
MAX_VIDEO_DURATION=600      # 最大视频时长(秒)
TRANSCRIPTION_TIMEOUT=300   # 转录超时(秒)
POLL_INTERVAL=5             # 轮询间隔(秒)

# CORS 配置
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://your-domain.com

# ====================================
# 可选配置
# ====================================

# HTTP 代理 (用于 yt-dlp)
# HTTP_PROXY=http://127.0.0.1:7890

# GeoIP 数据库路径
# GEOIP_DB_PATH=/path/to/GeoLite2-Country.mmdb

# 启用地理路由
ENABLE_GEO_ROUTING=true
```

### 前端环境变量 (frontend/.env)

```bash
# API 地址
VITE_API_URL=http://localhost:8000

# 生产环境
# VITE_API_URL=https://your-domain.com
```

---

## 🚀 部署指南

### 方式一：Docker Compose 部署 (推荐)

#### 1. 准备服务器
```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# 安装 Docker Compose
DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
```

#### 2. 克隆项目
```bash
cd /opt
git clone https://github.com/your-username/youtube_download.git
cd youtube_download
```

#### 3. 配置环境变量
```bash
# 后端
cp backend/.env.example backend/.env
nano backend/.env  # 编辑配置

# 前端
cp frontend/.env.example frontend/.env
nano frontend/.env  # 编辑配置
```

#### 4. 启动服务
```bash
# 开发环境
docker-compose up -d --build

# 生产环境
docker-compose -f docker-compose.prod.yml up -d --build
```

#### 5. 验证部署
```bash
# 检查容器状态
docker-compose ps

# 健康检查
curl http://localhost:8000/api/v1/health
curl http://localhost:4416/ping
```

### 方式二：手动部署

#### 1. 安装依赖
```bash
# 系统依赖
apt update && apt install -y python3.11 python3-pip nodejs npm ffmpeg

# 后端依赖
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 前端依赖
cd ../frontend
npm install
npm run build

# PO Token Provider
cd ../backend/bgutil-ytdlp-pot-provider/server
npm install
npx tsc
```

#### 2. 启动服务
```bash
# 使用启动脚本
chmod +x start-all-services.sh
./start-all-services.sh

# 或手动启动各服务
# 终端1: PO Token Provider
cd backend/bgutil-ytdlp-pot-provider/server && node build/main.js

# 终端2: 后端
cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000

# 终端3: 前端 (开发)
cd frontend && npm run dev

# 前端 (生产) - 使用 Nginx
npm run build
# 将 dist 目录部署到 Nginx
```

---

## 📊 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Frontend | 80 (prod) / 5173 (dev) | 前端 Web 界面 |
| Backend API | 8000 | FastAPI 后端 |
| API Docs | 8000/docs | Swagger UI |
| PO Token Provider | 4416 | bgutil 服务 |

---

## 🔍 日志查看

### Docker 环境
```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f bgutil

# 查看最近 100 行
docker-compose logs --tail 100 backend
```

### 手动部署环境
```bash
# 日志文件位置
tail -f logs/backend.log
tail -f logs/frontend.log
tail -f logs/pot-provider.log

# 或直接查看终端输出
```

### 日志级别配置
```bash
# 在 backend/.env 中设置
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

---

## 🛠️ 常用运维命令

### 服务管理
```bash
# 启动所有服务
docker-compose up -d

# 停止所有服务
docker-compose down

# 重启单个服务
docker-compose restart backend

# 重建并启动
docker-compose up -d --build --force-recreate

# 查看服务状态
docker-compose ps
```

### 健康检查
```bash
# 后端健康检查
curl http://localhost:8000/api/v1/health

# PO Token Provider 检查
curl http://localhost:4416/ping

# 系统信息
curl http://localhost:8000/api/v1/system/info

# 地理检测
curl http://localhost:8000/api/v1/geo/detect
```

### 容器调试
```bash
# 进入后端容器
docker exec -it yt-transcriber-backend bash

# 查看环境变量
docker exec yt-transcriber-backend env | grep -E "(QWEN|OSS|AGENTGO)"

# 查看进程
docker exec yt-transcriber-backend ps aux
```

### 清理操作
```bash
# 清理临时文件
rm -rf /tmp/video_processing/*

# 清理 Docker 缓存
docker system prune -a

# 清理未使用的镜像
docker image prune -a

# 完全重置
docker-compose down -v
docker system prune -a
docker-compose up -d --build
```

---

## 🔧 故障排查

### 问题1: 容器启动失败
```bash
# 查看详细日志
docker-compose logs backend

# 检查配置
docker exec yt-transcriber-backend env

# 重新构建
docker-compose down
docker-compose up -d --build --force-recreate
```

### 问题2: YouTube 下载失败
```bash
# 1. 检查 PO Token Provider
curl http://localhost:4416/ping

# 2. 检查 AgentGo 配置
docker exec yt-transcriber-backend env | grep AGENTGO

# 3. 测试认证
curl -X POST http://localhost:8000/api/v1/auth/test/us

# 4. 查看详细错误日志
docker logs yt-transcriber-backend --tail 200 | grep -i "error\|fail"
```

### 问题3: OSS 上传失败
```bash
# 检查 OSS 配置
docker exec yt-transcriber-backend env | grep -E "(OSS|ALIYUN)"

# 测试网络连接
docker exec yt-transcriber-backend curl -I https://oss-cn-hangzhou.aliyuncs.com
```

### 问题4: 转录失败
```bash
# 检查 Qwen API 配置
docker exec yt-transcriber-backend env | grep QWEN

# 检查音频文件是否生成
docker exec yt-transcriber-backend ls -la /tmp/video_processing/
```

### 问题5: CORS 错误
```bash
# 检查 CORS 配置
docker exec yt-transcriber-backend env | grep CORS

# 确保包含前端域名
# CORS_ORIGINS=http://localhost:5173,http://your-domain.com
```

### 问题6: 端口被占用
```bash
# 查看端口占用
lsof -i :8000
lsof -i :4416
lsof -i :80

# 杀死占用进程
kill -9 <PID>
```

### 问题7: 磁盘空间不足
```bash
# 查看磁盘使用
df -h

# 清理临时文件
rm -rf /tmp/video_processing/*

# 清理 Docker
docker system prune -a
```

---

## 📡 API 端点参考

### 核心端点
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| POST | `/api/v1/process` | 提交视频处理任务 |
| GET | `/api/v1/status/{task_id}` | 查询任务状态 |
| GET | `/api/v1/result/{task_id}` | 获取任务结果 |
| POST | `/api/v1/extract` | 提取直接下载链接 |

### 系统端点
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/system/info` | 系统信息 |
| GET | `/api/v1/geo/detect` | 地理位置检测 |
| GET | `/api/v1/geo/cookies` | 缓存的认证信息 |
| POST | `/api/v1/auth/test/{region}` | 测试区域认证 |
| POST | `/api/v1/geo/prefetch/{region}` | 预取区域认证 |

### 任务管理
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/tasks` | 列出所有任务 |
| DELETE | `/api/v1/tasks/{task_id}` | 删除任务 |
| GET | `/api/v1/download/{task_id}/subtitle` | 下载字幕 |

---

## 🔐 安全配置

### 防火墙配置
```bash
# Ubuntu (ufw)
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw enable

# CentOS (firewalld)
firewall-cmd --permanent --add-service=ssh
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https
firewall-cmd --reload
```

### Nginx + SSL 配置
```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

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

### SSL 证书申请
```bash
apt install certbot python3-certbot-nginx -y
certbot --nginx -d your-domain.com
```

---

## 📈 监控和告警

### 健康检查脚本
```bash
#!/bin/bash
# /opt/youtube_download/scripts/health_check.sh

BACKEND_HEALTH=$(curl -s http://localhost:8000/api/v1/health | grep -c "healthy")
POT_HEALTH=$(curl -s http://localhost:4416/ping | grep -c "server_uptime")

if [ "$BACKEND_HEALTH" -eq 0 ]; then
    echo "$(date): Backend unhealthy, restarting..."
    cd /opt/youtube_download && docker-compose restart backend
fi

if [ "$POT_HEALTH" -eq 0 ]; then
    echo "$(date): PO Token Provider unhealthy, restarting..."
    cd /opt/youtube_download && docker-compose restart bgutil
fi
```

### Crontab 配置
```bash
# 每5分钟健康检查
*/5 * * * * /opt/youtube_download/scripts/health_check.sh >> /var/log/youtube-health.log 2>&1

# 每天清理临时文件
0 3 * * * rm -rf /tmp/video_processing/* >> /var/log/youtube-cleanup.log 2>&1

# 每周清理 Docker
0 4 * * 0 docker system prune -f >> /var/log/docker-cleanup.log 2>&1
```

---

## 🔄 更新部署

### 代码更新
```bash
cd /opt/youtube_download

# 拉取最新代码
git pull origin main

# 重新构建并部署
docker-compose down
docker-compose up -d --build
```

### 零停机更新
```bash
# 使用部署脚本
./scripts/deploy.sh
```

---

## 📝 开机自启配置

### Systemd 服务
```bash
# 创建服务文件
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

# 启用服务
systemctl daemon-reload
systemctl enable youtube-download
```

---

## 🎯 快速命令速查

```bash
# === 服务管理 ===
docker-compose up -d                    # 启动
docker-compose down                     # 停止
docker-compose restart backend          # 重启后端
docker-compose logs -f backend          # 查看日志

# === 健康检查 ===
curl localhost:8000/api/v1/health       # 后端
curl localhost:4416/ping                # PO Token

# === 调试 ===
docker exec -it yt-transcriber-backend bash
docker logs yt-transcriber-backend --tail 100

# === 清理 ===
rm -rf /tmp/video_processing/*
docker system prune -a

# === 更新 ===
git pull && docker-compose up -d --build
```

---

## 📚 相关文档

- [本地开发指南](./local_development.md)
- [服务器部署完整指南](./server_deployment_complete.md)
- [系统架构文档](../architecture/system_architecture.md)
- [后端 API 文档](../backend/README.md)
- [CI/CD 架构](../architecture/cicd_architecture.md)

---

*最后更新: 2026-01-21*


---

## 🔗 服务依赖关系

### 启动顺序
```
1. bgutil (PO Token Provider) - 必须首先启动
   ↓
2. backend (FastAPI) - 依赖 bgutil 健康
   ↓
3. frontend (React/Nginx) - 依赖 backend
```

### 依赖检查
```bash
# bgutil 必须先启动并健康
curl http://localhost:4416/ping
# 返回: {"server_uptime":...,"version":"..."}

# 然后 backend 才能正常工作
curl http://localhost:8000/api/v1/health
# 返回: {"status":"healthy",...}
```

---

## 🗄️ 数据存储

### 临时文件
- 位置: `/tmp/video_processing/`
- 内容: 下载的视频、提取的音频
- 清理: 任务完成后自动清理，或手动 `rm -rf /tmp/video_processing/*`

### 持久化存储
- 阿里云 OSS: 视频、音频、字幕文件
- 路径格式:
  - 视频: `videos/{task_id}/{filename}.mp4`
  - 音频: `audio/{task_id}/{filename}.wav`

### 任务数据
- 当前: 内存存储 (重启后丢失)
- 生产建议: 使用 Redis 或数据库持久化

---

## 🌍 地理路由配置

### 支持的 AgentGo 区域
| 区域代码 | 覆盖国家/地区 |
|---------|--------------|
| us | 美国、加拿大、墨西哥、南美 |
| uk | 英国、爱尔兰、北欧 |
| de | 德国、中欧、东欧 |
| fr | 法国、比利时、南欧 |
| jp | 日本、韩国、台湾 |
| sg | 新加坡、东南亚、中国、香港 |
| in | 印度、南亚 |
| au | 澳大利亚、新西兰 |
| ca | 加拿大 |

### 国家到区域映射
```python
# 主要映射规则
'CN': 'sg',  # 中国 -> 新加坡
'HK': 'sg',  # 香港 -> 新加坡
'TW': 'jp',  # 台湾 -> 日本
'KR': 'jp',  # 韩国 -> 日本
'RU': 'de',  # 俄罗斯 -> 德国
```

---

## 🔄 下载策略

### 策略优先级
1. **Strategy 1**: Web 客户端 (bgutil 提供 PO Token)
2. **Strategy 2**: iOS 客户端 (备用)
3. **Strategy 3**: TV Embedded 客户端 (最后手段，仅 360p)

### 格式选择
- 优先: MP4 容器 + H.264 编码
- 备选: WebM 容器 + VP9 编码
- 音频: M4A (AAC) 优先

### 超时配置
| 操作 | 超时时间 |
|------|---------|
| 认证获取 | 90 秒 |
| 视频下载 | 600 秒 (10分钟) |
| 音频提取 | 60 秒 |
| 转录 | 300 秒 (5分钟) |
| OSS 上传 | 120 秒 |

---

## 📊 性能调优

### 后端配置
```python
# uvicorn 配置
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \           # 生产环境增加 worker 数
    --limit-concurrency 100 \
    --timeout-keep-alive 30
```

### Docker 资源限制
```yaml
# docker-compose.prod.yml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

### Nginx 优化
```nginx
# 增加超时时间
proxy_read_timeout 300s;
proxy_connect_timeout 60s;
proxy_send_timeout 300s;

# 增加缓冲区
proxy_buffer_size 128k;
proxy_buffers 4 256k;
proxy_busy_buffers_size 256k;
```

---

## 🧪 测试命令

### API 测试
```bash
# 健康检查
curl http://localhost:8000/api/v1/health

# 提取视频 URL
curl -X POST http://localhost:8000/api/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "resolution": "720"}'

# 提交处理任务
curl -X POST http://localhost:8000/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "enable_transcription": true, "resolution": "720"}'

# 查询任务状态
curl http://localhost:8000/api/v1/status/{task_id}

# 获取任务结果
curl http://localhost:8000/api/v1/result/{task_id}
```

### 认证测试
```bash
# 测试特定区域认证
curl -X POST http://localhost:8000/api/v1/auth/test/us
curl -X POST http://localhost:8000/api/v1/auth/test/sg

# 预取认证
curl -X POST http://localhost:8000/api/v1/geo/prefetch/us

# 查看缓存的认证
curl http://localhost:8000/api/v1/geo/cookies
```

---

## 🔒 敏感信息处理

### 日志脱敏
后端自动脱敏以下信息:
- API Keys
- Tokens (PO Token, Visitor Data)
- 密码
- 长字符串 (>20字符)

### 环境变量安全
```bash
# 不要在日志中打印敏感变量
# 使用 docker secrets 或 vault 管理生产密钥
```

---

## 📋 部署检查清单

### 部署前
- [ ] 服务器满足最低配置 (2核4G)
- [ ] Docker 和 Docker Compose 已安装
- [ ] 项目代码已克隆
- [ ] 所有环境变量已配置
- [ ] 防火墙已配置 (80, 443, 8000)

### 部署后
- [ ] 所有容器正常运行 (`docker-compose ps`)
- [ ] 后端健康检查通过
- [ ] PO Token Provider 健康检查通过
- [ ] 前端可以正常访问
- [ ] API 文档可以访问 (/docs)
- [ ] 测试视频下载功能
- [ ] 测试转录功能

### 生产环境
- [ ] SSL 证书已配置
- [ ] Nginx 反向代理已配置
- [ ] 开机自启已设置
- [ ] 监控脚本已配置
- [ ] 日志轮转已配置
- [ ] 备份策略已制定

---

## 🆘 紧急恢复

### 服务完全不可用
```bash
# 1. 停止所有服务
docker-compose down

# 2. 清理 Docker
docker system prune -a

# 3. 重新构建
docker-compose up -d --build --force-recreate

# 4. 检查日志
docker-compose logs -f
```

### 回滚到上一版本
```bash
# 1. 查看 git 历史
git log --oneline -10

# 2. 回滚到指定版本
git checkout <commit-hash>

# 3. 重新部署
docker-compose up -d --build
```

### 数据恢复
```bash
# OSS 数据: 通过阿里云控制台恢复
# 任务数据: 当前为内存存储，无法恢复
```

---

*Agent Memory 文档 - 版本 1.0*
