# 本地开发指南

本指南将帮你快速搭建本地开发环境，实现与生产环境的无缝衔接。

## 🚀 快速开始

### 1. 环境准备

确保你的系统已安装：
- [Docker](https://docs.docker.com/get-docker/) (>= 20.10)
- [Docker Compose](https://docs.docker.com/compose/install/) (>= 2.0)
- [Node.js](https://nodejs.org/) (>= 18.0)
- [Python](https://www.python.org/) (>= 3.11)
- [Git](https://git-scm.com/)

### 2. 克隆项目

```bash
git clone https://github.com/PCcoding666/youtube_download.git
cd youtube_download
```

### 3. 一键设置开发环境

```bash
# 运行设置脚本
npm run dev:setup

# 或者手动执行
./scripts/dev-setup.sh
```

### 4. 配置环境变量

编辑配置文件：
```bash
# 后端配置
vim backend/.env

# 前端配置  
vim frontend/.env
```

### 5. 启动开发环境

```bash
# 启动所有服务
npm run dev:start

# 查看日志
npm run dev:logs
```

## 📁 项目结构

```
youtube_download/
├── backend/                 # 后端服务
│   ├── app/                # 应用代码
│   ├── tests/              # 测试文件
│   ├── .env                # 开发环境变量
│   ├── .env.example        # 环境变量模板
│   ├── Dockerfile          # 多阶段构建
│   └── requirements.txt    # Python依赖
├── frontend/               # 前端应用
│   ├── src/               # 源代码
│   ├── .env               # 开发环境变量
│   ├── .env.example       # 环境变量模板
│   └── Dockerfile         # 多阶段构建
├── docs/                  # 文档
├── scripts/               # 脚本文件
├── .github/workflows/     # CI/CD配置
├── docker-compose.yml     # 生产环境
├── docker-compose.dev.yml # 开发环境
└── package.json          # 项目脚本
```

## 🛠️ 开发工作流

### 日常开发

```bash
# 启动开发环境
npm run dev:start

# 实时查看日志
npm run dev:logs

# 重启服务
npm run dev:restart

# 停止服务
npm run dev:stop
```

### 代码质量检查

```bash
# 后端代码检查
npm run lint:backend

# 前端代码检查
npm run lint:frontend

# 自动修复格式问题
npm run lint:fix:backend
npm run lint:fix:frontend
```

### 运行测试

```bash
# 后端测试
npm run test:backend

# 前端测试
npm run test:frontend

# 健康检查
npm run health:check
```

### 进入容器调试

```bash
# 进入后端容器
npm run dev:shell:backend

# 进入前端容器
npm run dev:shell:frontend
```

## 🔧 开发环境特性

### 热重载
- **后端**：使用 `--reload` 参数，代码变更自动重启
- **前端**：Vite 开发服务器，支持 HMR

### 卷挂载
- 源代码实时同步到容器
- 数据持久化到本地目录

### 服务发现
- 后端：`http://localhost:8000`
- 前端：`http://localhost:3000`
- Redis：`localhost:6379`
- PostgreSQL：`localhost:5432`

### 开发工具
- 集成 Redis 用于缓存
- 可选 PostgreSQL 数据库
- 开发依赖预装（pytest, ruff, etc.）

## 🚀 部署测试

### 本地生产环境测试

```bash
# 构建生产镜像
npm run build:prod

# 使用生产配置启动
docker-compose -f docker-compose.prod.yml up -d

# 查看生产环境日志
docker-compose -f docker-compose.prod.yml logs -f
```

### 手动部署到服务器

```bash
# 构建并推送镜像
DOCKER_REGISTRY_USER=your_user \
DOCKER_REGISTRY_PASS=your_pass \
npm run deploy:manual
```

## 🔄 Git 工作流

### 分支策略

```bash
# 功能开发
git checkout -b feature/new-feature
git add .
git commit -m "feat: 添加新功能"
git push origin feature/new-feature

# 创建 Pull Request
# 合并到 main 分支后自动触发 CI/CD
```

### 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```bash
feat: 新功能
fix: 修复bug
docs: 文档更新
style: 代码格式
refactor: 重构
test: 测试相关
chore: 构建/工具相关
```

## 🐛 调试技巧

### 后端调试

```bash
# 查看后端日志
docker-compose -f docker-compose.dev.yml logs -f backend

# 进入后端容器
docker-compose -f docker-compose.dev.yml exec backend bash

# 手动运行测试
docker-compose -f docker-compose.dev.yml exec backend python -m pytest tests/ -v

# 检查API健康状态
curl http://localhost:8000/api/v1/health
```

### 前端调试

```bash
# 查看前端日志
docker-compose -f docker-compose.dev.yml logs -f frontend

# 进入前端容器
docker-compose -f docker-compose.dev.yml exec frontend sh

# 检查构建
docker-compose -f docker-compose.dev.yml exec frontend npm run build
```

### 网络调试

```bash
# 检查容器网络
docker network ls
docker network inspect youtube_download_youtube-download-dev

# 测试服务间连通性
docker-compose -f docker-compose.dev.yml exec frontend ping backend
docker-compose -f docker-compose.dev.yml exec backend ping frontend
```

## 📊 性能监控

### 资源使用

```bash
# 查看容器资源使用
docker stats

# 查看镜像大小
docker images | grep youtube-download

# 清理未使用资源
npm run dev:clean
```

### 日志管理

```bash
# 查看特定时间段日志
docker-compose -f docker-compose.dev.yml logs --since="2024-01-01T00:00:00" backend

# 限制日志行数
docker-compose -f docker-compose.dev.yml logs --tail=100 frontend

# 导出日志
docker-compose -f docker-compose.dev.yml logs > app.log
```

## 🔧 故障排除

### 常见问题

1. **端口冲突**
   ```bash
   # 检查端口占用
   lsof -i :8000
   lsof -i :3000
   
   # 修改端口映射
   vim docker-compose.dev.yml
   ```

2. **权限问题**
   ```bash
   # 修复文件权限
   sudo chown -R $USER:$USER .
   
   # Docker权限
   sudo usermod -aG docker $USER
   ```

3. **依赖安装失败**
   ```bash
   # 清理并重建
   npm run dev:clean
   npm run dev:build
   ```

4. **热重载不工作**
   ```bash
   # 检查卷挂载
   docker-compose -f docker-compose.dev.yml config
   
   # 重启服务
   npm run dev:restart
   ```

### 重置环境

```bash
# 完全重置开发环境
npm run dev:stop
npm run dev:clean
docker system prune -a -f
npm run dev:setup
npm run dev:start
```

## 📚 相关资源

- [Docker 开发最佳实践](https://docs.docker.com/develop/dev-best-practices/)
- [FastAPI 开发指南](https://fastapi.tiangolo.com/tutorial/)
- [React + Vite 开发指南](https://vitejs.dev/guide/)
- [项目 CI/CD 架构](../architecture/cicd_architecture.md)