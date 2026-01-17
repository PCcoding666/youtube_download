# Local Development Guide

## 快速开始

本指南帮助你在本地环境快速启动完整的开发环境。

## 系统要求

### 必需软件

- **Python 3.10+**: 后端运行环境
- **Node.js 18+**: 前端和 PO Token Provider
- **FFmpeg**: 音频处理
- **Git**: 版本控制

### 安装必需软件

**macOS:**
```bash
# 使用 Homebrew
brew install python@3.10 node ffmpeg git
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.10 python3-pip nodejs npm ffmpeg git
```

**Windows:**
- Python: https://www.python.org/downloads/
- Node.js: https://nodejs.org/
- FFmpeg: https://ffmpeg.org/download.html
- Git: https://git-scm.com/download/win

## 项目设置

### 1. 克隆项目

```bash
git clone https://github.com/PCcoding666/youtube_download.git
cd youtube_download
```

### 2. 配置环境变量

#### 后端配置

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`，填入必需的配置：

```bash
# AI 服务（必需）
QWEN_API_KEY=sk-your-qwen-api-key
QWEN_API_BASE=https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions

# 阿里云 OSS（必需）
OSS_ACCESS_KEY_ID=your-access-key-id
OSS_ACCESS_KEY_SECRET=your-access-key-secret
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET=your-bucket-name

# AgentGo 服务（推荐）
AGENTGO_API_KEY=api_your-agentgo-key
AGENTGO_API_URL=https://api.datasea.network
YOUTUBE_EMAIL=your-youtube-email@gmail.com
YOUTUBE_PASSWORD=your-youtube-password

# 代理配置（可选但推荐）
YOUTUBE_PROXY=http://127.0.0.1:7890

# 应用配置
TEMP_DIR=/tmp/video_processing
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://localhost
```

#### 前端配置

```bash
cd ../frontend
cp .env.example .env
```

编辑 `frontend/.env`：

```bash
VITE_API_URL=http://localhost:8000/api
```

### 3. 安装依赖

#### 后端依赖

```bash
cd backend
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

#### 前端依赖

```bash
cd ../frontend
npm install
```

#### PO Token Provider 依赖

```bash
cd ../backend/bgutil-ytdlp-pot-provider/server
npm install
npx tsc  # 编译 TypeScript
```

## 启动服务

### 方法 1: 使用启动脚本（推荐）

**一键启动后端和前端：**

```bash
cd youtube_download
chmod +x start-dev.sh
./start-dev.sh
```

这会自动启动：
- ✅ 后端 API (http://localhost:8000)
- ✅ 前端开发服务器 (http://localhost:5173)

**在新终端启动 PO Token Provider：**

```bash
cd backend/bgutil-ytdlp-pot-provider/server
node build/main.js
```

### 方法 2: 手动启动（更多控制）

**终端 1 - PO Token Provider:**
```bash
cd backend/bgutil-ytdlp-pot-provider/server
node build/main.js
```

**终端 2 - 后端:**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**终端 3 - 前端:**
```bash
cd frontend
npm run dev
```

### 方法 3: 使用 Docker Compose

```bash
docker-compose up -d
```

这会启动所有服务，包括：
- 后端容器
- 前端容器
- 共享网络

## 验证服务

### 检查所有服务状态

```bash
# 后端健康检查
curl http://localhost:8000/api/v1/health
# 应返回: {"status":"healthy","version":"1.0.0","timestamp":"..."}

# PO Token Provider 健康检查
curl http://127.0.0.1:4416/ping
# 应返回: {"server_uptime":123.45,"version":"1.2.2"}

# 前端（浏览器访问）
open http://localhost:5173
```

### 服务端口总览

| 服务 | 端口 | URL | 说明 |
|------|------|-----|------|
| 前端开发服务器 | 5173 | http://localhost:5173 | Vite HMR |
| 后端 API | 8000 | http://localhost:8000 | FastAPI |
| API 文档 | 8000 | http://localhost:8000/docs | Swagger UI |
| PO Token Provider | 4416 | http://127.0.0.1:4416 | Token 生成 |

## 开发工作流

### 1. 修改代码

**后端代码修改：**
- 修改 `backend/app/` 下的文件
- Uvicorn 会自动重载（`--reload` 模式）
- 查看终端输出确认重载成功

**前端代码修改：**
- 修改 `frontend/src/` 下的文件
- Vite 会自动热更新（HMR）
- 浏览器自动刷新

### 2. 查看日志

**后端日志：**
- 直接在运行 uvicorn 的终端查看
- 设置 `LOG_LEVEL=DEBUG` 查看详细日志

**前端日志：**
- 浏览器开发者工具 Console
- Vite 终端输出

**PO Token Provider 日志：**
- Node.js 进程的终端输出

### 3. 测试 API

**使用 Swagger UI：**
```
http://localhost:8000/docs
```

**使用 curl：**
```bash
# 提取视频 URL
curl -X POST "http://localhost:8000/api/v1/extract" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

**使用 Postman/Insomnia：**
- 导入 API 端点
- 测试各个接口

### 4. 调试

**Python 调试：**
```python
# 在代码中添加断点
import pdb; pdb.set_trace()

# 或使用 VS Code 调试器
# 创建 .vscode/launch.json
```

**前端调试：**
- 使用浏览器开发者工具
- React DevTools 扩展
- VS Code 调试器

## 常见开发问题

### Q1: 端口已被占用

**错误：** `Address already in use`

**解决：**
```bash
# 查找占用端口的进程
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# 杀死进程
kill -9 <PID>  # macOS/Linux
taskkill /PID <PID> /F  # Windows
```

### Q2: Python 虚拟环境问题

**错误：** `ModuleNotFoundError`

**解决：**
```bash
# 确保虚拟环境已激活
source backend/venv/bin/activate

# 重新安装依赖
pip install -r backend/requirements.txt
```

### Q3: Node.js 依赖问题

**错误：** `Cannot find module`

**解决：**
```bash
# 清除缓存并重新安装
rm -rf node_modules package-lock.json
npm install
```

### Q4: FFmpeg 未找到

**错误：** `ffmpeg not found`

**解决：**
```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt install ffmpeg

# 验证安装
ffmpeg -version
```

### Q5: CORS 错误

**错误：** `Access-Control-Allow-Origin`

**解决：**
- 检查 `backend/.env` 中的 `CORS_ORIGINS`
- 确保包含前端开发服务器地址：`http://localhost:5173`

### Q6: PO Token Provider 连接失败

**错误：** `Error reaching GET http://127.0.0.1:4416/ping`

**解决：**
```bash
# 确保 PO Token Provider 正在运行
cd backend/bgutil-ytdlp-pot-provider/server
node build/main.js

# 验证服务
curl http://127.0.0.1:4416/ping
```

## 开发技巧

### 1. 使用环境变量

创建 `.env.local` 用于本地覆盖：
```bash
# 不提交到 Git
echo ".env.local" >> .gitignore

# 本地特定配置
cp .env .env.local
# 编辑 .env.local
```

### 2. 快速重启服务

创建别名（添加到 `~/.bashrc` 或 `~/.zshrc`）：
```bash
alias yt-backend="cd ~/youtube_download/backend && source venv/bin/activate && uvicorn app.main:app --reload"
alias yt-frontend="cd ~/youtube_download/frontend && npm run dev"
alias yt-pot="cd ~/youtube_download/backend/bgutil-ytdlp-pot-provider/server && node build/main.js"
```

### 3. 使用 tmux/screen 管理多个终端

```bash
# 安装 tmux
brew install tmux  # macOS
sudo apt install tmux  # Ubuntu

# 创建会话
tmux new -s youtube-dev

# 分割窗口
Ctrl+b %  # 垂直分割
Ctrl+b "  # 水平分割

# 在不同窗格运行服务
# 窗格 1: PO Token Provider
# 窗格 2: Backend
# 窗格 3: Frontend
```

### 4. 使用 VS Code 任务

创建 `.vscode/tasks.json`：
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Start Backend",
      "type": "shell",
      "command": "cd backend && source venv/bin/activate && uvicorn app.main:app --reload",
      "problemMatcher": []
    },
    {
      "label": "Start Frontend",
      "type": "shell",
      "command": "cd frontend && npm run dev",
      "problemMatcher": []
    },
    {
      "label": "Start PO Token Provider",
      "type": "shell",
      "command": "cd backend/bgutil-ytdlp-pot-provider/server && node build/main.js",
      "problemMatcher": []
    }
  ]
}
```

## 性能优化

### 开发环境优化

1. **使用 SSD**: 提高文件读写速度
2. **增加内存**: 至少 8GB RAM
3. **关闭不必要的服务**: 释放端口和资源
4. **使用代理**: 提高 YouTube 访问成功率

### 代码热重载

- 后端：Uvicorn `--reload` 自动重载
- 前端：Vite HMR 即时更新
- 无需手动重启服务

## 下一步

- 阅读 [系统架构文档](../architecture/system_architecture.md)
- 查看 [后端 API 文档](../backend/README.md)
- 了解 [部署流程](deployment_guide.md)
- 贡献代码前阅读 [贡献指南](../../CONTRIBUTING.md)

## 获取帮助

遇到问题？
1. 查看本文档的常见问题部分
2. 检查 GitHub Issues
3. 查看服务日志
4. 联系项目维护者

---

**Happy Coding! 🚀**
