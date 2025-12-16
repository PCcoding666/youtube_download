# CI/CD Deployment Guide

Complete guide for setting up automated deployment with GitHub Actions to Aliyun Container Registry and your server.

## 📋 Overview

```
Local Development
    ↓
Push to GitHub
    ↓
GitHub Actions Auto Trigger
    ↓
1. Run Tests (pytest)
    ↓
2. Build Docker Images
    ↓
3. Push to Aliyun Container Registry
    ↓
4. SSH to Server & Pull Images
    ↓
5. Rolling Update (Zero Downtime)
    ↓
6. Health Check
    ↓
7. Send Notification (Success/Failure)
```

## 🚀 Step-by-Step Setup

### 1. Aliyun Container Registry Setup

#### 1.1 Create Registry Namespace
1. Go to [Aliyun Container Registry Console](https://cr.console.aliyun.com/)
2. Select region (e.g., `cn-hangzhou`)
3. Create a namespace (e.g., `youtube-download`)
4. Create two repositories:
   - `youtube-download-backend`
   - `youtube-download-frontend`

#### 1.2 Get Access Credentials
1. Go to Access Credentials
2. Set a registry password
3. Note down:
   - Registry: `registry.cn-hangzhou.aliyuncs.com`
   - Username: Your Aliyun account ID
   - Password: Registry password you just set

### 2. GitHub Secrets Configuration

Go to your GitHub repository → Settings → Secrets and variables → Actions

Add the following secrets:

#### Aliyun Registry Secrets
```
ALIYUN_REGISTRY_USERNAME=<your-aliyun-account-id>
ALIYUN_REGISTRY_PASSWORD=<your-registry-password>
```

#### Server Secrets
```
SERVER_HOST=<your-server-ip>
SERVER_USER=root
SERVER_PORT=22
SERVER_SSH_KEY=<your-private-ssh-key>
SERVER_URL=https://your-domain.com
```

#### Notification Secrets (Optional)
```
TELEGRAM_BOT_TOKEN=<your-telegram-bot-token>
TELEGRAM_CHAT_ID=<your-telegram-chat-id>
```

#### Application Secrets
```
QWEN_API_KEY=<your-qwen-api-key>
OSS_ACCESS_KEY_ID=<your-oss-access-key>
OSS_ACCESS_KEY_SECRET=<your-oss-secret>
```

### 3. GitHub Variables Configuration

Go to Settings → Secrets and variables → Actions → Variables

Add the following variables:

```
VITE_API_URL=https://your-domain.com/api
```

### 4. Server Setup

#### 4.1 Initial Server Setup

SSH to your server and run:

```bash
# Download and run setup script
curl -o setup-server.sh https://raw.githubusercontent.com/PCcoding666/youtube_download/main/scripts/setup-server.sh
chmod +x setup-server.sh
sudo ./setup-server.sh
```

This script will:
- Install Docker & Docker Compose
- Create project directory `/opt/youtube_download`
- Setup firewall rules
- Create systemd service
- Generate environment template

#### 4.2 Configure Environment

Edit the production environment file:

```bash
cd /opt/youtube_download
nano .env.production
```

Fill in all required values (API keys, credentials, etc.)

#### 4.3 Copy Production Compose File

```bash
# Copy from your local machine or create manually
scp docker-compose.prod.yml root@your-server:/opt/youtube_download/
```

Or create it manually on server:

```bash
nano /opt/youtube_download/docker-compose.prod.yml
# Paste the content from docker-compose.prod.yml
```

#### 4.4 Login to Aliyun Registry

```bash
docker login registry.cn-hangzhou.aliyuncs.com
# Enter your username and password
```

### 5. Update GitHub Actions Workflow

Edit `.github/workflows/ci-cd.yml` and update:

```yaml
env:
  REGISTRY: registry.cn-hangzhou.aliyuncs.com
  NAMESPACE: your-namespace  # Change this to your namespace
  IMAGE_BACKEND: youtube-download-backend
  IMAGE_FRONTEND: youtube-download-frontend
```

### 6. SSH Key Setup

#### 6.1 Generate SSH Key (on your local machine)

```bash
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions
```

#### 6.2 Add Public Key to Server

```bash
# Copy public key
cat ~/.ssh/github_actions.pub

# On server
ssh root@your-server
mkdir -p ~/.ssh
echo "your-public-key-content" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

#### 6.3 Add Private Key to GitHub Secrets

```bash
# Copy private key
cat ~/.ssh/github_actions

# Add to GitHub Secrets as SERVER_SSH_KEY
```

### 7. Telegram Notification Setup (Optional)

#### 7.1 Create Telegram Bot

1. Talk to [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow instructions
3. Save the bot token

#### 7.2 Get Chat ID

1. Send a message to your bot
2. Visit: `https://api.telegram.org/bot<YourBOTToken>/getUpdates`
3. Find `chat.id` in response
4. Add both to GitHub Secrets

## 🎯 Deployment Process

### Automatic Deployment

Simply push to main branch:

```bash
git add .
git commit -m "Your changes"
git push origin main
```

GitHub Actions will automatically:
1. ✅ Run tests
2. 🏗️ Build Docker images
3. 📤 Push to Aliyun Registry
4. 🚀 Deploy to server with zero downtime
5. 🏥 Health check
6. 📢 Send notification

### Manual Deployment on Server

If needed, you can deploy manually:

```bash
ssh root@your-server
cd /opt/youtube_download
./scripts/deploy.sh
```

## 🔍 Monitoring & Debugging

### Check Deployment Status

```bash
# On server
cd /opt/youtube_download
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs -f
```

### Check Individual Service

```bash
# Backend logs
docker logs yt-transcriber-backend -f

# Frontend logs
docker logs yt-transcriber-frontend -f
```

### Health Check

```bash
# Backend
curl http://localhost:8000/api/v1/health

# Frontend
curl http://localhost
```

### Rollback

If deployment fails, automatic rollback is triggered. Manual rollback:

```bash
cd /opt/youtube_download
# List backups
ls -lt backups/

# Restore specific backup
cp backups/backup_YYYYMMDD_HHMMSS/docker-compose.prod.yml ./
cp backups/backup_YYYYMMDD_HHMMSS/.env.production ./
docker-compose -f docker-compose.prod.yml up -d
```

## 🛠️ Troubleshooting

### Issue: GitHub Actions fails at "Push to registry"

**Solution**: Check Aliyun registry credentials in GitHub Secrets

```bash
# Test locally
docker login registry.cn-hangzhou.aliyuncs.com
```

### Issue: SSH connection fails

**Solution**: 
1. Check SERVER_SSH_KEY is complete (including header/footer)
2. Verify SSH key is added to server's authorized_keys
3. Test SSH connection manually

### Issue: Health check fails

**Solution**: 
1. Check backend logs: `docker logs yt-transcriber-backend`
2. Verify all environment variables are set
3. Check if proxy is running (if required)

### Issue: Docker pull fails on server

**Solution**:
```bash
# Re-login to registry
docker login registry.cn-hangzhou.aliyuncs.com

# Check image exists
docker pull registry.cn-hangzhou.aliyuncs.com/your-namespace/youtube-download-backend:latest
```

## 📊 CI/CD Workflow Details

### Frontend CI
- Type check with TypeScript
- Build with Vite
- Upload artifacts

### Backend CI
- Install dependencies
- Run linting (ruff)
- Run tests (pytest)

### Build & Push
- Build multi-platform images
- Use Docker Buildx
- Cache layers for faster builds
- Tag with git SHA and 'latest'

### Deploy
- SSH to server
- Pull latest images
- Rolling update backend first
- Wait for health check
- Update frontend
- Clean up old images

## 🔐 Security Best Practices

1. **Never commit secrets**: Use GitHub Secrets
2. **Use SSH keys**: Not passwords for server access
3. **Limit SSH access**: Only allow specific IPs if possible
4. **Rotate credentials**: Regularly update passwords and keys
5. **Use HTTPS**: Always use SSL/TLS in production
6. **Keep backups**: Automatic backups before each deployment

## 📝 Environment Variables Reference

### Required
- `QWEN_API_KEY`: Qwen AI API key
- `ALIYUN_ACCESS_KEY_ID`: Aliyun OSS access key
- `ALIYUN_ACCESS_KEY_SECRET`: Aliyun OSS secret
- `ALIYUN_OSS_BUCKET`: OSS bucket name

### Optional
- `CLASH_API_SECRET`: If using Clash proxy
- `TELEGRAM_BOT_TOKEN`: For notifications
- `AGENTGO_API_KEY`: Browser automation

## 🎓 Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Aliyun Container Registry](https://www.alibabacloud.com/help/en/acr)
- [Docker Compose](https://docs.docker.com/compose/)
- [Telegram Bot API](https://core.telegram.org/bots/api)

## 💡 Tips

1. **Test locally first**: Use `docker-compose.yml` for local testing
2. **Small commits**: Easier to rollback if issues occur
3. **Monitor logs**: Keep an eye on GitHub Actions and server logs
4. **Use branches**: Test in feature branches before merging to main
5. **Health checks**: Ensure all services have proper health check endpoints

## 🎉 Success Criteria

Your CI/CD is working correctly when:
- ✅ Push to main triggers automatic deployment
- ✅ Tests pass before deployment
- ✅ Images build and push successfully
- ✅ Server pulls and updates automatically
- ✅ Zero downtime during updates
- ✅ Health checks pass
- ✅ Notifications received

---

**Need Help?** Check GitHub Actions logs and server logs first. Most issues are related to credentials or network connectivity.
