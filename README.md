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

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/PCcoding666/youtube_download.git
   cd youtube_download
   ```

2. **Setup environment files**
   ```bash
   # Backend environment
   cp backend/.env.example backend/.env
   # Edit backend/.env with your API keys
   
   # Frontend environment
   cp frontend/.env.example frontend/.env
   ```

3. **Start services**
   
   **Option A: Complete Startup (Recommended - All Services)**
   ```bash
   # This script will start ALL services including PO Token Provider:
   # - PO Token Provider (Port 4416)
   # - Backend API (Port 8000)
   # - Frontend Dev Server (Port 5173)
   chmod +x start-all-services.sh
   ./start-all-services.sh
   ```
   
   **Option B: Quick Start (Backend + Frontend only)**
   ```bash
   # Start backend and frontend (requires manual PO Token Provider start)
   ./start-dev.sh
   
   # In a new terminal, start PO Token Provider:
   cd backend/bgutil-ytdlp-pot-provider/server
   node build/main.js
   ```
   
   **Option C: Docker Compose (Production-like)**
   ```bash
   docker-compose up -d
   ```

4. **Access the application**
   - Frontend: http://localhost:5173 (dev) or http://localhost (docker)
   - Backend: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - PO Token Provider: http://localhost:4416 (health check: /ping)

For detailed instructions, please refer to the **[Local Development Guide](docs/guides/local_development.md)** or **[Quick Start Guide](docs/guides/quick_start.md)**.

## 🔧 Configuration & Deployment

Please refer to the **[Deployment Guide](docs/guides/deployment_guide.md)** for detailed configuration variables and production deployment steps.

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is private. All rights reserved.