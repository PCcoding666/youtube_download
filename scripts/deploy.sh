#!/bin/bash

###############################################
# YouTube Download - Production Deployment Script
# This script handles zero-downtime deployment
###############################################

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="/opt/youtube_download"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.production"
BACKUP_DIR="$PROJECT_DIR/backups"
MAX_BACKUPS=5

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create backup of current deployment
create_backup() {
    log_info "Creating backup..."
    mkdir -p "$BACKUP_DIR"
    
    BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"
    BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
    
    mkdir -p "$BACKUP_PATH"
    
    # Backup docker-compose file and env
    cp "$COMPOSE_FILE" "$BACKUP_PATH/" 2>/dev/null || true
    cp "$ENV_FILE" "$BACKUP_PATH/" 2>/dev/null || true
    
    # Save current image tags
    docker-compose -f "$COMPOSE_FILE" images > "$BACKUP_PATH/images.txt"
    
    log_info "Backup created: $BACKUP_PATH"
    
    # Clean old backups
    cd "$BACKUP_DIR"
    ls -t | tail -n +$((MAX_BACKUPS + 1)) | xargs rm -rf 2>/dev/null || true
}

# Rollback to previous version
rollback() {
    log_error "Deployment failed! Rolling back..."
    
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR" | head -n 1)
    if [ -z "$LATEST_BACKUP" ]; then
        log_error "No backup found for rollback!"
        exit 1
    fi
    
    log_info "Rolling back to: $LATEST_BACKUP"
    
    cd "$PROJECT_DIR"
    docker-compose -f "$COMPOSE_FILE" down
    
    # Restore backup
    cp "$BACKUP_DIR/$LATEST_BACKUP/$COMPOSE_FILE" ./ 2>/dev/null || true
    cp "$BACKUP_DIR/$LATEST_BACKUP/$ENV_FILE" ./ 2>/dev/null || true
    
    docker-compose -f "$COMPOSE_FILE" up -d
    
    log_error "Rollback completed"
    exit 1
}

# Health check
health_check() {
    local service=$1
    local url=$2
    local max_attempts=30
    local attempt=1
    
    log_info "Checking health of $service..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f "$url" > /dev/null 2>&1; then
            log_info "$service is healthy!"
            return 0
        fi
        
        log_warn "Waiting for $service... ($attempt/$max_attempts)"
        sleep 2
        attempt=$((attempt + 1))
    done
    
    log_error "$service health check failed!"
    docker-compose -f "$COMPOSE_FILE" logs "$service" --tail=50
    return 1
}

# Main deployment process
main() {
    log_info "Starting deployment process..."
    
    # Navigate to project directory
    cd "$PROJECT_DIR" || {
        log_error "Project directory not found: $PROJECT_DIR"
        exit 1
    }
    
    # Load environment variables
    if [ -f "$ENV_FILE" ]; then
        set -a
        source "$ENV_FILE"
        set +a
        log_info "Environment variables loaded"
    else
        log_error "Environment file not found: $ENV_FILE"
        exit 1
    fi
    
    # Create backup
    create_backup
    
    # Pull latest images
    log_info "Pulling latest images..."
    docker-compose -f "$COMPOSE_FILE" pull || {
        log_error "Failed to pull images"
        exit 1
    }
    
    # Deploy backend with zero downtime
    log_info "Deploying backend..."
    docker-compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate backend
    
    # Wait for backend health check
    if ! health_check "backend" "http://localhost:8000/api/v1/health"; then
        rollback
    fi
    
    # Deploy frontend
    log_info "Deploying frontend..."
    docker-compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate frontend
    
    # Wait a bit for frontend to start
    sleep 5
    
    # Clean up
    log_info "Cleaning up old images..."
    docker image prune -f
    
    log_info "✅ Deployment completed successfully!"
    
    # Show running containers
    log_info "Running containers:"
    docker-compose -f "$COMPOSE_FILE" ps
}

# Trap errors and rollback
trap rollback ERR

# Run main function
main
