# CI/CD Setup Summary

## ✅ 已完成的工作

### 1. GitHub Actions CI/CD Pipeline
已创建完整的自动化部署流程：`.github/workflows/ci-cd.yml`

**流程包括：**
- ✅ Frontend CI (类型检查、构建)
- ✅ Backend CI (代码检查、测试)
- ✅ Docker 镜像构建
- ✅ 推送到阿里云容器镜像服务
- ✅ SSH 部署到服务器
- ✅ 零停机滚动更新
- ✅ 健康检查
- ✅ Telegram 通知

### 2. 部署脚本

**服务器设置脚本** (`scripts/setup-server.sh`)
- 自动安装 Docker 和 Docker Compose
- 创建项目目录结构
- 配置防火墙
- 创建 systemd 服务

**部署脚本** (`scripts/deploy.sh`)
- 自动备份当前部署
- 拉取最新镜像
- 零停机滚动更新
- 健康检查
- 失败自动回滚

**配置检查脚本** (`scripts/check-config.sh`)
- 验证所有配置文件
- 检查敏感信息泄露
- 提供下一步指引

### 3. Docker 配置

**本地开发** (`docker-compose.yml`)
- Backend + Frontend 服务
- 本地开发环境配置

**生产环境** (`docker-compose.prod.yml`)
- 优化的生产配置
- 健康检查
- 自动重启
- Volume 持久化

### 4. 完整文档

| 文档 | 用途 |
|------|------|
| `README.md` | 项目总览和快速开始 |
| `QUICK_START.md` | 5分钟快速配置指南 |
| `DEPLOYMENT_GUIDE.md` | 详细部署指南 |
| `CICD_ARCHITECTURE.md` | CI/CD 架构和流程图 |
| `SETUP_SUMMARY.md` | 本文档，配置总结 |

## 📋 你需要完成的配置

### 步骤 1: 阿里云容器镜像服务（3分钟）

1. 访问 https://cr.console.aliyun.com/
2. 创建命名空间（例如：`youtube-download`）
3. 创建两个镜像仓库：
   - `youtube-download-backend`
   - `youtube-download-frontend`
4. 设置访问凭证（固定密码）

### 步骤 2: 配置 GitHub Secrets（5分钟）

进入 GitHub 仓库 → Settings → Secrets and variables → Actions

**必需的 Secrets：**
```
ALIYUN_REGISTRY_USERNAME    # 阿里云账号 ID
ALIYUN_REGISTRY_PASSWORD    # 容器镜像服务密码
SERVER_HOST                 # 服务器 IP
SERVER_USER                 # SSH 用户（通常是 root）
SERVER_SSH_KEY             # SSH 私钥（完整内容）
```

**可选的 Secrets（用于通知）：**
```
TELEGRAM_BOT_TOKEN         # Telegram Bot Token
TELEGRAM_CHAT_ID           # Telegram Chat ID
```

**Variables：**
```
VITE_API_URL               # 前端 API 地址，例如：https://yourdomain.com/api
```

### 步骤 3: 生成和配置 SSH 密钥（3分钟）

```bash
# 本地执行
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions

# 查看公钥（添加到服务器）
cat ~/.ssh/github_actions.pub

# 查看私钥（添加到 GitHub Secrets）
cat ~/.ssh/github_actions
```

**在服务器上：**
```bash
mkdir -p ~/.ssh
echo "你的公钥内容" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

### 步骤 4: 更新配置文件（1分钟）

编辑 `.github/workflows/ci-cd.yml`，更新：

```yaml
env:
  NAMESPACE: youtube-download  # 改成你的阿里云命名空间
```

### 步骤 5: 服务器初始化（5分钟）

```bash
# SSH 登录服务器
ssh root@your-server-ip

# 下载设置脚本
curl -o setup-server.sh https://raw.githubusercontent.com/PCcoding666/youtube_download/main/scripts/setup-server.sh

# 运行设置
chmod +x setup-server.sh
sudo ./setup-server.sh

# 配置环境变量
cd /opt/youtube_download
nano .env.production
# 填写所有必需的环境变量

# 复制生产配置
nano docker-compose.prod.yml
# 粘贴 docker-compose.prod.yml 的内容

# 登录阿里云镜像仓库
docker login registry.cn-hangzhou.aliyuncs.com
```

### 步骤 6: 首次部署（1分钟）

```bash
# 本地执行
git add .
git commit -m "Configure CI/CD for production"
git push origin main
```

访问 GitHub Actions 查看部署进度：
`https://github.com/PCcoding666/youtube_download/actions`

## 🔍 验证配置

运行配置检查脚本：

```bash
./scripts/check-config.sh
```

这将检查：
- GitHub 仓库配置
- GitHub Actions 工作流
- Docker 配置文件
- 部署脚本
- 环境文件
- 安全性（敏感信息检查）

## 📊 完整的 CI/CD 流程

```
开发人员推送代码
    ↓
GitHub Actions 自动触发
    ↓
1️⃣ 运行测试
   - Frontend: 类型检查 + 构建
   - Backend: Linting + Pytest
    ↓
2️⃣ 构建 Docker 镜像
   - Backend image
   - Frontend image
    ↓
3️⃣ 推送到阿里云容器镜像服务
   - registry.cn-hangzhou.aliyuncs.com
    ↓
4️⃣ SSH 连接到服务器
   - 登录镜像仓库
   - 拉取最新镜像
    ↓
5️⃣ 滚动更新（零停机）
   - 创建备份
   - 更新 Backend
   - 健康检查（30次，每2秒）
   - 更新 Frontend
    ↓
6️⃣ 最终健康检查
   - 验证服务可访问
    ↓
7️⃣ 发送通知
   - ✅ 成功：发送成功消息
   - ❌ 失败：自动回滚 + 发送失败消息
```

**总耗时：** 约 8-12 分钟

## 🎯 配置清单

在推送代码前，确保完成以下所有项：

- [ ] **阿里云容器镜像服务**
  - [ ] 创建命名空间
  - [ ] 创建 backend 镜像仓库
  - [ ] 创建 frontend 镜像仓库
  - [ ] 设置访问凭证

- [ ] **GitHub Secrets**
  - [ ] ALIYUN_REGISTRY_USERNAME
  - [ ] ALIYUN_REGISTRY_PASSWORD
  - [ ] SERVER_HOST
  - [ ] SERVER_USER
  - [ ] SERVER_SSH_KEY
  - [ ] (可选) TELEGRAM_BOT_TOKEN
  - [ ] (可选) TELEGRAM_CHAT_ID

- [ ] **GitHub Variables**
  - [ ] VITE_API_URL

- [ ] **SSH 密钥**
  - [ ] 生成 SSH 密钥对
  - [ ] 公钥添加到服务器
  - [ ] 私钥添加到 GitHub Secrets

- [ ] **工作流配置**
  - [ ] 更新 NAMESPACE 为实际命名空间

- [ ] **服务器配置**
  - [ ] 运行 setup-server.sh
  - [ ] 配置 .env.production
  - [ ] 复制 docker-compose.prod.yml
  - [ ] 登录阿里云镜像仓库

- [ ] **验证**
  - [ ] 运行 check-config.sh
  - [ ] 测试 SSH 连接
  - [ ] 测试阿里云镜像仓库登录

## 🚀 首次部署后

部署成功后，你可以：

1. **访问应用**
   - Frontend: `http://your-server-ip`
   - Backend: `http://your-server-ip:8000`
   - API 文档: `http://your-server-ip:8000/docs`

2. **查看日志**
   ```bash
   # 所有服务
   docker-compose -f docker-compose.prod.yml logs -f
   
   # 单个服务
   docker logs yt-transcriber-backend -f
   ```

3. **监控状态**
   ```bash
   docker-compose -f docker-compose.prod.yml ps
   ```

4. **健康检查**
   ```bash
   curl http://your-server-ip:8000/api/v1/health
   ```

## 🔄 日常工作流

配置完成后，日常开发非常简单：

```bash
# 1. 开发功能
# 编辑代码...

# 2. 本地测试
docker-compose up -d

# 3. 提交并推送
git add .
git commit -m "Add new feature"
git push origin main

# 4. GitHub Actions 自动完成部署！
# 5. 收到 Telegram 通知
```

## 🆘 故障排除

### GitHub Actions 失败

1. 查看 Actions 日志详情
2. 检查 Secrets 配置是否正确
3. 验证服务器 SSH 连接

### 部署失败

```bash
# 查看部署日志
ssh root@your-server
cd /opt/youtube_download
docker-compose -f docker-compose.prod.yml logs

# 手动回滚
ls -lt backups/
cp backups/backup_YYYYMMDD_HHMMSS/* ./
docker-compose -f docker-compose.prod.yml up -d
```

### 健康检查失败

```bash
# 检查后端日志
docker logs yt-transcriber-backend --tail=100

# 检查环境变量
docker exec yt-transcriber-backend env

# 重启服务
docker-compose -f docker-compose.prod.yml restart backend
```

## 📞 需要帮助？

1. 查看 [QUICK_START.md](./QUICK_START.md) - 快速开始指南
2. 查看 [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) - 详细部署指南
3. 查看 [CICD_ARCHITECTURE.md](./CICD_ARCHITECTURE.md) - 架构说明
4. 检查 GitHub Actions 日志
5. 检查服务器 Docker 日志

## 🎉 完成！

配置完成后，你将拥有：

- ✅ 全自动 CI/CD 流程
- ✅ 零停机部署
- ✅ 自动健康检查
- ✅ 失败自动回滚
- ✅ Telegram 通知
- ✅ 完整的备份系统

**开始享受自动化部署的乐趣吧！** 🚀
