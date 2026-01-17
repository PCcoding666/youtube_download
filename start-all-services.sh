#!/bin/bash
# Complete startup script for YouTube Transcriber
# Starts all required services: Backend, Frontend, and PO Token Provider

set -e

echo "=========================================="
echo "  YouTube Transcriber - Complete Startup"
echo "=========================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if ffmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${RED}❌ FFmpeg not found. Please install FFmpeg first:${NC}"
    echo "   macOS: brew install ffmpeg"
    echo "   Ubuntu: sudo apt-get install ffmpeg"
    exit 1
fi
echo -e "${GREEN}✅ FFmpeg found${NC}"

# Check if node is installed
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js not found. Please install Node.js first:${NC}"
    echo "   macOS: brew install node"
    echo "   Ubuntu: sudo apt-get install nodejs npm"
    exit 1
fi
echo -e "${GREEN}✅ Node.js found ($(node --version))${NC}"

# Check for backend .env file
if [ ! -f "backend/.env" ]; then
    echo -e "${YELLOW}⚠️  No backend/.env file found. Copying from .env.example...${NC}"
    cp backend/.env.example backend/.env
    echo -e "${YELLOW}📝 Please edit backend/.env with your API keys${NC}"
fi

# Check for frontend .env file
if [ ! -f "frontend/.env" ]; then
    echo -e "${YELLOW}⚠️  No frontend/.env file found. Copying from .env.example...${NC}"
    cp frontend/.env.example frontend/.env
fi

# Create Python virtual environment if not exists
if [ ! -d "backend/venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv backend/venv
fi

# Activate virtual environment and install dependencies
echo "📦 Installing Python dependencies..."
source backend/venv/bin/activate
pip install -q -r backend/requirements.txt

# Install frontend dependencies if needed
if [ ! -d "frontend/node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    cd frontend && npm install && cd ..
fi

# Check if PO Token Provider is built
if [ ! -f "backend/bgutil-ytdlp-pot-provider/server/build/main.js" ]; then
    echo "📦 Building PO Token Provider..."
    cd backend/bgutil-ytdlp-pot-provider/server
    npm install
    npx tsc
    cd ../../..
fi

echo ""
echo "=========================================="
echo "  Starting services..."
echo "=========================================="

# Create log directory
mkdir -p logs

# Start PO Token Provider in background
echo -e "${GREEN}🚀 Starting PO Token Provider on http://127.0.0.1:4416${NC}"
cd backend/bgutil-ytdlp-pot-provider/server
node build/main.js > ../../../logs/pot-provider.log 2>&1 &
POT_PID=$!
cd ../../..

# Wait for PO Token Provider to start
echo "⏳ Waiting for PO Token Provider to start..."
for i in {1..10}; do
    if curl -s http://127.0.0.1:4416/ping > /dev/null 2>&1; then
        echo -e "${GREEN}✅ PO Token Provider is ready${NC}"
        break
    fi
    if [ $i -eq 10 ]; then
        echo -e "${RED}❌ PO Token Provider failed to start${NC}"
        echo "Check logs/pot-provider.log for details"
        kill $POT_PID 2>/dev/null
        exit 1
    fi
    sleep 1
done

# Start backend in background
echo -e "${GREEN}🚀 Starting backend on http://localhost:8000${NC}"
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000 > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# Wait for backend to start
echo "⏳ Waiting for backend to start..."
for i in {1..15}; do
    if curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend is ready${NC}"
        break
    fi
    if [ $i -eq 15 ]; then
        echo -e "${RED}❌ Backend failed to start${NC}"
        echo "Check logs/backend.log for details"
        kill $POT_PID $BACKEND_PID 2>/dev/null
        exit 1
    fi
    sleep 1
done

# Start frontend
echo -e "${GREEN}🚀 Starting frontend on http://localhost:5173${NC}"
cd frontend
npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

# Wait for frontend to start
sleep 3

echo ""
echo "=========================================="
echo -e "${GREEN}  ✅ All services are running!${NC}"
echo "=========================================="
echo ""
echo "  📱 Frontend:        http://localhost:5173"
echo "  🔧 Backend API:     http://localhost:8000"
echo "  📚 API Docs:        http://localhost:8000/docs"
echo "  🔑 PO Token:        http://127.0.0.1:4416"
echo ""
echo "  📋 Logs:"
echo "     Backend:         tail -f logs/backend.log"
echo "     Frontend:        tail -f logs/frontend.log"
echo "     PO Token:        tail -f logs/pot-provider.log"
echo ""
echo "=========================================="
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo "=========================================="

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping all services..."
    kill $POT_PID $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "✅ All services stopped"
    exit 0
}

# Trap Ctrl+C and call cleanup
trap cleanup INT TERM

# Wait for interrupt
wait
