#!/bin/bash

###############################################
# Server Setup Script
# Run this script on your server to prepare for deployment
###############################################

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration
PROJECT_DIR="/opt/youtube_download"
REGISTRY="registry.cn-hangzhou.aliyuncs.com"

log_info "Starting server setup..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    log_error "Please run as root (use sudo)"
    exit 1
fi

# Install Docker
log_info "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    log_info "Docker installed successfully"
else
    log_info "Docker already installed"
fi

# Install Docker Compose
log_info "Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
    curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    log_info "Docker Compose installed successfully"
else
    log_info "Docker Compose already installed"
fi

# Create project directory
log_info "Creating project directory..."
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Create necessary directories
mkdir -p backups
mkdir -p storage
mkdir -p /tmp/video_processing
chmod 777 /tmp/video_processing

# Create .env.production template
log_info "Creating environment file template..."
cat > .env.production.example << 'EOF'
# API Keys
QWEN_API_KEY=your_qwen_api_key_here
TRANSCRIPT_SERVICE_API_KEY=your_transcript_service_api_key_here
HF_TOKEN=your_huggingface_token_here

# Aliyun OSS
ALIYUN_ACCESS_KEY_ID=your_aliyun_access_key_id_here
ALIYUN_ACCESS_KEY_SECRET=your_aliyun_access_key_secret_here
ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
ALIYUN_OSS_BUCKET=your-bucket-name

# Security
SECRET_KEY=your_secret_key_here

# Browser Runtime
AGENTGO_API_KEY=your_agentgo_api_key_here

# Application Settings
LOG_LEVEL=INFO
MAX_VIDEO_DURATION=600
TRANSCRIPTION_TIMEOUT=300
POLL_INTERVAL=5

# CORS
CORS_ORIGINS=https://yourdomain.com,http://localhost:5173

# Docker Images
BACKEND_IMAGE=registry.cn-hangzhou.aliyuncs.com/your-namespace/youtube-download-backend:latest
FRONTEND_IMAGE=registry.cn-hangzhou.aliyuncs.com/your-namespace/youtube-download-frontend:latest
EOF

log_info "Please edit .env.production with your actual values:"
log_info "  nano $PROJECT_DIR/.env.production"

# Setup firewall (if ufw is available)
if command -v ufw &> /dev/null; then
    log_info "Configuring firewall..."
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw allow 8000/tcp
    log_info "Firewall configured"
fi

# Create systemd service for auto-restart
log_info "Creating systemd service..."
cat > /etc/systemd/system/youtube-download.service << EOF
[Unit]
Description=YouTube Download Service
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/local/bin/docker-compose -f docker-compose.prod.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.prod.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable youtube-download.service

log_info "✅ Server setup completed!"
echo ""
log_info "Next steps:"
log_info "1. Edit $PROJECT_DIR/.env.production with your configuration"
log_info "2. Copy docker-compose.prod.yml to $PROJECT_DIR/"
log_info "3. Login to Aliyun Registry: docker login $REGISTRY"
log_info "4. Start the service: systemctl start youtube-download"
log_info ""
log_info "Deployment script location: $PROJECT_DIR/scripts/deploy.sh"
