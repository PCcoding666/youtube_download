# YouTube Download & Transcription Service

A full-stack application for downloading YouTube videos and generating transcriptions with AI-powered summarization.

## 📚 Documentation Index

We have organized our documentation to help you find what you need quickly:

### 🚀 Guides & Tutorials (`docs/guides/`)
- **[Quick Start Guide](docs/guides/quick_start.md)**: 5-minute setup guide to get up and running.
- **[Deployment Guide](docs/guides/deployment_guide.md)**: Detailed CI/CD setup and production deployment instructions.
- **[Setup Summary](docs/guides/setup_summary.md)**: Overview of the setup process.
- **[Migration Guide](docs/guides/migration_guide.md)**: Guide for migrating core modules.

### 🏗️ Architecture (`docs/architecture/`)
- **[CI/CD Architecture](docs/architecture/cicd_architecture.md)**: Visual diagrams and explanation of our DevOps pipeline.

### 💻 Developer Resources (`docs/dev/`)
- **[Backend Documentation](docs/backend/README.md)**: Detailed API usage, configuration, and troubleshooting for the backend.
- **[Debug Log](docs/dev/debug_log.md)**: Logs and debugging history.
- **[AI Prompts](docs/dev/ai_assistant_prompt.md)**: System prompts used for AI assistance.
- **[Research Prompt](docs/dev/research_prompt.md)**: Prompts used for research tasks.

---

## 🚀 Key Features

- **YouTube Video Download**: Download videos with multiple quality options
- **AI Transcription**: Automatic speech-to-text with Qwen AI
- **Smart Summarization**: Generate concise summaries of video content
- **Proxy Support**: Built-in proxy rotation and AgentGo integration for reliable access
- **Cloud Storage**: Aliyun OSS integration for media storage
- **Modern UI**: React + TypeScript frontend with Vite

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

2. **Run with Docker Compose**
   ```bash
   # Setup environment files first (see Quick Start Guide)
   docker-compose up -d
   ```

3. **Access the application**
   - Frontend: http://localhost
   - Backend: http://localhost:8000
   - API Docs: http://localhost:8000/docs

For detailed instructions, please refer to the **[Quick Start Guide](docs/guides/quick_start.md)**.

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