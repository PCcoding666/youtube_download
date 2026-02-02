# YouTube Download & Transcription Service

A full-stack application for downloading YouTube videos and generating transcriptions with AI-powered summarization.

## 📚 Documentation Index

We have organized our documentation to help you find what you need quickly:

### 🚀 Guides & Tutorials (`docs/guides/`)
- **[Local Development Guide](docs/guides/local_development.md)**: Complete guide for setting up local development environment.
- **[Quick Start Guide](docs/guides/quick_start.md)**: 5-minute setup guide to get up and running.
- **[Deployment Guide](docs/guides/deployment_guide.md)**: Detailed CI/CD setup and production deployment instructions.
- **[Setup Summary](docs/guides/setup_summary.md)**: Overview of the setup process.
- **[Migration Guide](docs/guides/migration_guide.md)**: Guide for migrating core modules.
- **[Proxy Consistency Guide](docs/guides/proxy-consistency-guide.md)**: Guide for maintaining proxy consistency.

### 🏗️ Architecture (`docs/architecture/`)
- **[System Architecture](docs/architecture/system_architecture.md)**: Complete system architecture overview with component details.
- **[CI/CD Architecture](docs/architecture/cicd_architecture.md)**: Visual diagrams and explanation of our DevOps pipeline.

### 💻 Developer Resources (`docs/`)
- **[Backend Documentation](docs/backend/README.md)**: Detailed API usage, configuration, and troubleshooting for the backend.
- **[Debug Log](docs/dev/debug_log.md)**: Logs and debugging history.
- **[AI Prompts](docs/dev/ai_assistant_prompt.md)**: System prompts used for AI assistance.
- **[Research Prompt](docs/dev/research_prompt.md)**: Prompts used for research tasks.

---

## 🚀 Key Features

- **YouTube Video Download**: Download videos with multiple quality options
- **AI Transcription**: Automatic speech-to-text with Qwen AI (Paraformer-v2)
- **Smart Summarization**: Generate concise summaries of video content
- **Anti-Bot Protection**: 
  - PO Token Provider (bgutil-ytdlp-pot-provider) for bypassing YouTube bot detection
  - AgentGo browser automation for cookie/token extraction
  - Multi-strategy fallback mechanism
- **Proxy Support**: Built-in proxy rotation and intelligent node switching
- **Cloud Storage**: Aliyun OSS integration for media storage
- **Modern UI**: React + TypeScript frontend with Vite
- **Zero Downtime Deployment**: Automated CI/CD with health checks and rollback

## 📦 Project Structure

```
youtube_download/
├── docs/                     # 📚 Project Documentation
│   ├── architecture/
│   ├── backend/
│   ├── dev/
│   └── guides/
├── frontend/                 # React frontend
├── backend/                  # FastAPI backend
├── scripts/                  # Deployment scripts
├── .github/                  # GitHub Actions
└── docker-compose.yml        # Local development
```

## 🚦 Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (>= 20.10)
- [Docker Compose](https://docs.docker.com/compose/install/) (>= 2.0)
- [Node.js](https://nodejs.org/) (>= 18.0) - for local development
- [Python](https://www.python.org/) (>= 3.11) - for local development

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/PCcoding666/youtube_download.git
   cd youtube_download
   ```

2. **Quick setup with npm scripts**
   ```bash
   # One-time setup
   npm run dev:setup
   
   # Start development environment
   npm run dev:start
   
   # View logs
   npm run dev:logs
   
   # Stop services
   npm run dev:stop
   ```

3. **Manual setup (alternative)**
   ```bash
   # Setup environment files
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   # Edit the .env files with your configuration
   
   # Start with Docker Compose
   docker-compose -f docker-compose.dev.yml up -d
   ```

4. **Access the application**
   - Frontend: http://localhost:5201 (dev) or http://localhost (production)
   - Backend: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Health Check: http://localhost:8000/api/v1/health

### Production Deployment

This project includes a complete CI/CD pipeline with GitHub Actions:

1. **Automatic Deployment**
   - Push to `main` branch triggers automatic deployment
   - Includes testing, building, and zero-downtime deployment
   - Automatic rollback on failure

2. **Manual Deployment**
   ```bash
   # Build and deploy manually
   npm run deploy:manual
   ```

3. **Setup CI/CD**
   - Configure GitHub Secrets (see [GitHub Secrets Setup Guide](docs/guides/github-secrets-setup.md))
   - Push to main branch to trigger deployment

For detailed instructions, see:
- **[Local Development Guide](docs/guides/local-development-guide.md)**
- **[GitHub Secrets Setup Guide](docs/guides/github-secrets-setup.md)**
- **[CI/CD Architecture](docs/architecture/cicd_architecture.md)**

## 🔧 Configuration & Deployment

### Development Scripts

```bash
# Environment setup
npm run dev:setup          # One-time development environment setup
npm run dev:start           # Start all development services
npm run dev:stop            # Stop all development services
npm run dev:restart         # Restart development services
npm run dev:logs            # View all service logs
npm run dev:logs:backend    # View backend logs only
npm run dev:logs:frontend   # View frontend logs only

# Code quality
npm run lint:backend        # Check backend code style
npm run lint:frontend       # Check frontend code style
npm run lint:fix:backend    # Auto-fix backend code style
npm run lint:fix:frontend   # Auto-fix frontend code style

# Testing
npm run test:backend        # Run backend tests
npm run test:frontend       # Run frontend tests
npm run health:check        # Check service health

# Deployment
npm run build:prod          # Build production images
npm run deploy:manual       # Manual deployment to server
```

### CI/CD Pipeline

The project includes a complete CI/CD pipeline with the following stages:

1. **Continuous Integration**
   - Frontend type checking and build
   - Backend linting and testing
   - Parallel execution for faster feedback

2. **Build & Push**
   - Multi-stage Docker builds
   - Push to Aliyun Container Registry
   - Image caching for faster builds

3. **Deployment**
   - Zero-downtime rolling updates
   - Health checks before traffic switch
   - Automatic rollback on failure
   - Backup system with 5-version history

4. **Monitoring**
   - Telegram notifications
   - Deployment status tracking
   - Real-time health monitoring

**Pipeline Features:**
- ⚡ **Fast**: ~8-12 minutes from push to production
- 🔒 **Secure**: SSH key authentication, secrets management
- 🛡️ **Reliable**: Health checks, automatic rollback
- 📊 **Observable**: Real-time logs, notifications

Please refer to the **[Deployment Guide](docs/guides/deployment_guide.md)** for detailed configuration variables and production deployment steps.

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is private. All rights reserved.