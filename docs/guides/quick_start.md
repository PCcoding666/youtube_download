# CI/CD Quick Start Guide

## 🚀 5分钟快速配置指南

### 第一步：阿里云容器镜像服务配置（3分钟）

1. **创建命名空间**
   - 访问：https://cr.console.aliyun.com/
   - 选择地域：`华东1 (杭州)`
   - 创建命名空间：`youtube-download`（可自定义）

2. **创建镜像仓库**
   - 创建两个仓库：
     - `youtube-download-backend`
     - `youtube-download-frontend`
   - 代码源：本地仓库

3. **获取访问凭证**
   - 点击"访问凭证"
   - 设置固定密码
   - 记录：
     - 仓库地址：`registry.cn-hangzhou.aliyuncs.com`
     - 用户名：你的阿里云账号ID
     - 密码：刚设置的密码

### 第二步：GitHub Secrets 配置（2分钟）

进入你的 GitHub 仓库 → Settings → Secrets and variables → Actions → New repository secret

**必需配置（5个）：**

| Secret名称 | 值 | 说明 |
|-----------|-----|------|
| `ALIYUN_REGISTRY_USERNAME` | 阿里云账号ID | 容器镜像服务用户名 |
| `ALIYUN_REGISTRY_PASSWORD` | 你设置的密码 | 容器镜像服务密码 |
| `SERVER_HOST` | 1.2.3.4 | 服务器IP地址 |
| `SERVER_USER` | root | SSH登录用户名 |
| `SERVER_SSH_KEY` | 完整私钥内容 | SSH私钥（见下方生成方法） |

**可选配置（通知功能）：**

| Secret名称 | 值 | 说明 |
|-----------|-----|------|
| `TELEGRAM_BOT_TOKEN` | 你的Bot Token | Telegram通知 |
| `TELEGRAM_CHAT_ID` | 你的Chat ID | Telegram通知 |

**Variables 配置：**

进入 Variables 标签页添加：

| Variable名称 | 值 | 说明 |
|-----------|-----|------|
| `VITE_API_URL` | `https://yourdomain.com/api` | 前端API地址 |

### 第三步：SSH密钥生成和配置

**本地生成密钥：**
```bash
# 生成新密钥
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions

# 查看公钥（稍后添加到服务器）
cat ~/.ssh/github_actions.pub

# 查看私钥（添加到GitHub Secrets）
cat ~/.ssh/github_actions
```

**服务器添加公钥：**
```bash
# SSH登录服务器
ssh root@your-server-ip

# 添加公钥
mkdir -p ~/.ssh
echo "刚才复制的公钥内容" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

### 第四步：服务器初始化

**一键设置脚本：**
```bash
# SSH登录服务器
ssh root@your-server-ip

# 下载并运行设置脚本
curl -o setup-server.sh https://raw.githubusercontent.com/PCcoding666/youtube_download/main/scripts/setup-server.sh
chmod +x setup-server.sh
sudo ./setup-server.sh
```

**配置环境变量：**
```bash
cd /opt/youtube_download
cp .env.production.example .env.production
nano .env.production
```

填写所有必需的环境变量（API密钥等）

**复制配置文件：**

从本地复制或手动创建：
```bash
# 方法1：从本地复制
scp docker-compose.prod.yml root@your-server:/opt/youtube_download/
scp scripts/deploy.sh root@your-server:/opt/youtube_download/scripts/

# 方法2：手动创建
nano /opt/youtube_download/docker-compose.prod.yml
# 粘贴 docker-compose.prod.yml 内容
```

**登录阿里云镜像仓库：**
```bash
docker login registry.cn-hangzhou.aliyuncs.com
# 输入用户名和密码
```

### 第五步：更新 GitHub Actions 配置

编辑 `.github/workflows/ci-cd.yml`：

```yaml
env:
  REGISTRY: registry.cn-hangzhou.aliyuncs.com
  NAMESPACE: youtube-download  # 改成你的命名空间
  IMAGE_BACKEND: youtube-download-backend
  IMAGE_FRONTEND: youtube-download-frontend
```

### 第六步：测试部署！

```bash
# 提交更改
git add .
git commit -m "Configure CI/CD"
git push origin main
```

🎉 现在访问 GitHub Actions 查看自动部署进度！

## 📋 配置检查清单

在推送代码前，确保：

- [ ] 阿里云容器镜像服务已创建命名空间和仓库
- [ ] GitHub Secrets 已配置（至少5个必需项）
- [ ] SSH密钥已生成并添加到服务器
- [ ] 服务器已运行 setup-server.sh
- [ ] 服务器 .env.production 已配置
- [ ] docker-compose.prod.yml 已复制到服务器
- [ ] 服务器已登录阿里云镜像仓库
- [ ] ci-cd.yml 中的 NAMESPACE 已更新

## 🔍 验证部署

### 查看 GitHub Actions
1. 访问：`https://github.com/你的用户名/youtube_download/actions`
2. 查看最新的 workflow 运行状态
3. 等待所有步骤完成（约5-10分钟）

### 查看服务器状态
```bash
ssh root@your-server
cd /opt/youtube_download
docker-compose -f docker-compose.prod.yml ps
```

### 访问应用
```bash
# 健康检查
curl http://your-server-ip:8000/api/v1/health

# 访问前端
curl http://your-server-ip
```

## 🐛 常见问题

### Q1: GitHub Actions 在 "Push to registry" 步骤失败
**A**: 检查阿里云镜像仓库凭证
```bash
# 本地测试登录
docker login registry.cn-hangzhou.aliyuncs.com
```

### Q2: SSH连接失败
**A**: 
1. 确保私钥包含完整的头尾（`-----BEGIN ... KEY-----`）
2. 验证公钥已添加到服务器
3. 测试手动SSH连接

### Q3: 健康检查失败
**A**: 
```bash
# 查看后端日志
docker logs yt-transcriber-backend

# 检查环境变量
docker exec yt-transcriber-backend env | grep API
```

### Q4: 镜像拉取失败
**A**: 
```bash
# 服务器重新登录
docker login registry.cn-hangzhou.aliyuncs.com

# 手动拉取测试
docker pull registry.cn-hangzhou.aliyuncs.com/your-namespace/youtube-download-backend:latest
```

## 📞 获取帮助

如果遇到问题：
1. 查看 GitHub Actions 详细日志
2. SSH到服务器查看 Docker 日志
3. 检查 [完整部署指南](./DEPLOYMENT_GUIDE.md)

## 🎯 下一步

部署成功后，你可以：
- 配置域名和 SSL 证书
- 设置监控和告警
- 优化 Docker 镜像大小
- 添加更多测试

---

**提示**: 整个设置过程约10-15分钟。如果是第一次配置，建议预留30分钟时间。
