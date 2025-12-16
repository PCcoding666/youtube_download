# YouTube Download & Transcription Service

A full-stack application for downloading YouTube videos and generating transcriptions with AI-powered summarization.

## 📚 Documentation

### Quick Links
- **[Quick Start Guide](./QUICK_START.md)** - 5-minute setup guide
- **[Complete Deployment Guide](./DEPLOYMENT_GUIDE.md)** - Detailed CI/CD setup
- **[CI/CD Architecture](./CICD_ARCHITECTURE.md)** - Visual pipeline diagrams

## 🚀 Features

- **YouTube Video Download**: Download videos with multiple quality options
- **AI Transcription**: Automatic speech-to-text with Qwen AI
- **Smart Summarization**: Generate concise summaries of video content
- **Proxy Support**: Built-in Clash API integration for reliable access
- **Cloud Storage**: Aliyun OSS integration for media storage
- **Modern UI**: React + TypeScript frontend with Vite

## 🏗️ Tech Stack

### Frontend
- React 18
- TypeScript
- Vite
- CSS3

### Backend
- Python 3.11
- FastAPI
- yt-dlp
- OpenAI-compatible API (Qwen)
- Aliyun OSS

### DevOps
- Docker & Docker Compose
- GitHub Actions
- Aliyun Container Registry
- Zero-downtime deployment

## 📦 Project Structure

```
youtube_download/
├── frontend/                 # React frontend
│   ├── src/
│   │   ├── App.tsx          # Main application
│   │   ├── api.ts           # API client
│   │   └── ...
│   └── Dockerfile
├── backend/                  # FastAPI backend
│   ├── app/
│   │   ├── api/             # API routes
│   │   ├── services/        # Business logic
│   │   ├── utils/           # Utilities
│   │   └── main.py          # Entry point
│   └── Dockerfile
├── scripts/                  # Deployment scripts
│   ├── deploy.sh            # Zero-downtime deployment
│   └── setup-server.sh      # Server initialization
├── .github/
│   └── workflows/
│       └── ci-cd.yml        # GitHub Actions pipeline
├── docker-compose.yml        # Local development
└── docker-compose.prod.yml   # Production deployment
```

## 🎯 CI/CD Pipeline

```
Local Development → GitHub Push → GitHub Actions →
Tests → Build Images → Push to Aliyun → Deploy to Server →
Health Check → Notification
```

**Full pipeline time**: 8-12 minutes

### Pipeline Features
- ✅ Automated testing (Frontend + Backend)
- 🏗️ Docker image building and caching
- 📤 Push to Aliyun Container Registry
- 🚀 Zero-downtime rolling deployment
- 🏥 Automated health checks
- 🔄 Automatic rollback on failure
- 📢 Telegram notifications

## 🚦 Getting Started

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/PCcoding666/youtube_download.git
   cd youtube_download
   ```

2. **Setup environment**
   ```bash
   # Backend
   cp backend/.env.example backend/.env
   # Edit backend/.env with your API keys
   
   # Frontend
   cp frontend/.env.example frontend/.env
   # Edit frontend/.env with your API URL
   ```

3. **Run with Docker Compose**
   ```bash
   docker-compose up -d
   ```

4. **Access the application**
   - Frontend: http://localhost
   - Backend: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Production Deployment

Follow the **[Quick Start Guide](./QUICK_START.md)** for complete setup instructions.

## 🔧 Configuration

### Required Environment Variables

#### Backend
```bash
QWEN_API_KEY=your_qwen_api_key
ALIYUN_ACCESS_KEY_ID=your_aliyun_key_id
ALIYUN_ACCESS_KEY_SECRET=your_aliyun_secret
ALIYUN_OSS_BUCKET=your_bucket_name
```

#### Frontend
```bash
VITE_API_URL=https://your-api-url.com
```

### GitHub Secrets (for CI/CD)
```bash
ALIYUN_REGISTRY_USERNAME    # Aliyun container registry username
ALIYUN_REGISTRY_PASSWORD    # Aliyun container registry password
SERVER_HOST                 # Your server IP
SERVER_USER                 # SSH user (typically 'root')
SERVER_SSH_KEY             # Your SSH private key
TELEGRAM_BOT_TOKEN         # (Optional) For notifications
TELEGRAM_CHAT_ID           # (Optional) For notifications
```

## 📖 API Documentation

Once the backend is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Main Endpoints

- `POST /api/v1/download` - Download YouTube video
- `POST /api/v1/transcribe` - Generate transcription
- `GET /api/v1/health` - Health check
- `GET /api/v1/status/{task_id}` - Check task status

## 🧪 Testing

### Backend Tests
```bash
cd backend
pip install -r requirements.txt
pip install pytest pytest-asyncio
pytest tests/ -v
```

### Frontend Tests
```bash
cd frontend
npm install
npm run build
```

## 📊 Monitoring

### View Logs
```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Backend only
docker logs yt-transcriber-backend -f

# Frontend only
docker logs yt-transcriber-frontend -f
```

### Health Check
```bash
curl http://localhost:8000/api/v1/health
```

## 🛠️ Deployment Scripts

### Server Setup
```bash
# Run on server
sudo ./scripts/setup-server.sh
```

### Manual Deployment
```bash
# Run on server
cd /opt/youtube_download
./scripts/deploy.sh
```

### Rollback
```bash
cd /opt/youtube_download
# List backups
ls -lt backups/

# Restore from backup
cp backups/backup_YYYYMMDD_HHMMSS/* ./
docker-compose -f docker-compose.prod.yml up -d
```

## 🔐 Security

- API keys stored in GitHub Secrets
- SSH key-based authentication
- No credentials in code
- Environment variable injection at runtime
- Automatic backup before deployment

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is private. All rights reserved.

## 🙋 Support

For issues and questions:
1. Check the [Deployment Guide](./DEPLOYMENT_GUIDE.md)
2. Review GitHub Actions logs
3. Check server logs: `docker-compose logs`

## 📈 Performance

- **Build time**: ~5 minutes
- **Deployment time**: ~3 minutes
- **Total CI/CD**: ~8-12 minutes
- **Zero downtime**: ✅
- **Automatic rollback**: ✅

## 🎨 Screenshots

(Add screenshots of your application here)

---

**Made with ❤️ for seamless YouTube video processing**
