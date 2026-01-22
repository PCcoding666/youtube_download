# GitHub Secrets 配置指南

为了让 CI/CD 流程正常工作，你需要在 GitHub 仓库中配置以下 Secrets。

## 🔐 必需的 Secrets

### 阿里云容器镜像服务
```
ALIYUN_REGISTRY_USERNAME=你的阿里云账号用户名
ALIYUN_REGISTRY_PASSWORD=你的阿里云账号密码或访问令牌
```

### 服务器连接信息
```
SERVER_HOST=你的服务器IP地址
SERVER_USER=服务器用户名（通常是root或ubuntu）
SERVER_PORT=SSH端口（通常是22）
SERVER_SSH_KEY=你的SSH私钥内容
```

### 通知服务（可选）
```
TELEGRAM_BOT_TOKEN=你的Telegram机器人Token
TELEGRAM_CHAT_ID=你的Telegram聊天ID
```

## 📋 配置步骤

### 1. 设置阿里云容器镜像服务

1. 登录 [阿里云容器镜像服务控制台](https://cr.console.aliyun.com/)
2. 创建命名空间：`youtube-download`
3. 创建镜像仓库：
   - `backend` (私有)
   - `frontend` (私有)
4. 获取访问凭据：
   - 用户名：你的阿里云账号
   - 密码：可以使用账号密码或创建访问令牌

### 2. 生成 SSH 密钥对

```bash
# 在本地生成SSH密钥对
ssh-keygen -t rsa -b 4096 -C "github-actions@yourdomain.com" -f ~/.ssh/github_actions

# 将公钥添加到服务器
ssh-copy-id -i ~/.ssh/github_actions.pub user@your-server-ip

# 测试连接
ssh -i ~/.ssh/github_actions user@your-server-ip

# 复制私钥内容（用于GitHub Secret）
cat ~/.ssh/github_actions
```

### 3. 设置 Telegram 通知（可选）

1. 创建 Telegram 机器人：
   - 与 [@BotFather](https://t.me/botfather) 对话
   - 发送 `/newbot` 创建新机器人
   - 获取 Bot Token

2. 获取聊天 ID：
   - 与你的机器人发送消息
   - 访问：`https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - 找到 `chat.id` 字段

### 4. 在 GitHub 中添加 Secrets

1. 进入你的 GitHub 仓库
2. 点击 `Settings` → `Secrets and variables` → `Actions`
3. 点击 `New repository secret`
4. 逐个添加上述 Secrets

## 🔧 服务器环境准备

### 安装 Docker 和 Docker Compose

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 重新登录以应用组权限
exit
```

### 创建部署目录

```bash
sudo mkdir -p /opt/youtube-download
sudo chown $USER:$USER /opt/youtube-download
cd /opt/youtube-download
```

### 创建生产环境配置

```bash
# 创建 .env.production 文件
cat > .env.production <<EOF
# 应用配置
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO

# API 配置
API_HOST=0.0.0.0
API_PORT=8000

# 外部服务配置
AGENTGO_API_URL=你的AgentGo服务URL
AGENTGO_API_KEY=你的AgentGo API密钥

# 其他配置...
EOF
```

## 🚀 测试部署

### 手动触发部署

1. 推送代码到 `main` 分支
2. 查看 GitHub Actions 执行情况
3. 检查服务器上的容器状态：

```bash
# 检查容器状态
docker ps

# 查看日志
docker-compose logs -f

# 健康检查
curl http://localhost:8000/api/v1/health
curl http://localhost
```

### 本地测试 CI/CD 流程

```bash
# 使用 act 在本地测试 GitHub Actions
# 安装 act: https://github.com/nektos/act

# 测试 CI 流程
act -j frontend-ci
act -j backend-ci

# 测试完整流程（需要配置 secrets）
act -s ALIYUN_REGISTRY_USERNAME=xxx -s ALIYUN_REGISTRY_PASSWORD=xxx
```

## 🔍 故障排除

### 常见问题

1. **SSH 连接失败**
   - 检查服务器防火墙设置
   - 确认 SSH 密钥格式正确
   - 验证服务器用户权限

2. **镜像推送失败**
   - 检查阿里云镜像服务配置
   - 确认命名空间和仓库已创建
   - 验证访问凭据

3. **部署健康检查失败**
   - 检查应用启动日志
   - 确认环境变量配置
   - 验证端口映射

### 调试命令

```bash
# 查看 GitHub Actions 日志
# 在 GitHub 仓库的 Actions 页面查看

# 服务器端调试
docker-compose logs backend
docker-compose logs frontend
docker exec -it youtube-download-backend bash

# 网络连接测试
curl -v http://localhost:8000/api/v1/health
telnet localhost 8000
```

## 📚 相关文档

- [Docker 官方文档](https://docs.docker.com/)
- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [阿里云容器镜像服务](https://help.aliyun.com/product/60716.html)
- [Telegram Bot API](https://core.telegram.org/bots/api)