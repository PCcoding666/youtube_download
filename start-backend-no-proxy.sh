#!/bin/bash

# Start backend without proxy settings that interfere with AgentGo browser
echo "Starting backend without proxy settings..."

# Unset proxy environment variables
unset https_proxy
unset http_proxy  
unset all_proxy
unset HTTPS_PROXY
unset HTTP_PROXY
unset ALL_PROXY

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to the project root directory
cd "$SCRIPT_DIR"

# Initialize conda for this shell session
eval "$(conda shell.bash hook)"

# Activate conda environment and start backend
conda activate youtube_download
cd backend
uvicorn app.main:app --reload --port 8000