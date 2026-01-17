#!/bin/bash
# Service health check script for YouTube Transcriber

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "=========================================="
echo "  YouTube Transcriber - Service Check"
echo "=========================================="
echo ""

# Function to check service
check_service() {
    local name=$1
    local url=$2
    local expected=$3
    
    echo -n "Checking $name... "
    
    response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)
    
    if [ "$response" = "$expected" ]; then
        echo -e "${GREEN}✅ OK${NC} (HTTP $response)"
        return 0
    else
        echo -e "${RED}❌ FAILED${NC} (HTTP $response)"
        return 1
    fi
}

# Function to check if port is listening
check_port() {
    local name=$1
    local port=$2
    
    echo -n "Checking $name port... "
    
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Listening on port $port${NC}"
        return 0
    else
        echo -e "${RED}❌ Not listening on port $port${NC}"
        return 1
    fi
}

# Check services
echo -e "${BLUE}=== Port Status ===${NC}"
check_port "PO Token Provider" 4416
check_port "Backend API" 8000
check_port "Frontend Dev" 5173

echo ""
echo -e "${BLUE}=== Health Checks ===${NC}"

# Check PO Token Provider
if check_service "PO Token Provider" "http://127.0.0.1:4416/ping" "200"; then
    version=$(curl -s http://127.0.0.1:4416/ping 2>/dev/null | grep -o '"version":"[^"]*"' | cut -d'"' -f4)
    uptime=$(curl -s http://127.0.0.1:4416/ping 2>/dev/null | grep -o '"server_uptime":[0-9.]*' | cut -d':' -f2)
    echo "   Version: $version, Uptime: ${uptime}s"
fi

# Check Backend API
if check_service "Backend API" "http://localhost:8000/api/v1/health" "200"; then
    status=$(curl -s http://localhost:8000/api/v1/health 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    version=$(curl -s http://localhost:8000/api/v1/health 2>/dev/null | grep -o '"version":"[^"]*"' | cut -d'"' -f4)
    echo "   Status: $status, Version: $version"
fi

# Check Frontend
check_service "Frontend" "http://localhost:5173" "200"

echo ""
echo -e "${BLUE}=== Service URLs ===${NC}"
echo "  Frontend:     http://localhost:5173"
echo "  Backend API:  http://localhost:8000"
echo "  API Docs:     http://localhost:8000/docs"
echo "  PO Token:     http://127.0.0.1:4416"

echo ""
echo "=========================================="

# Check if all services are running
if lsof -Pi :4416 -sTCP:LISTEN -t >/dev/null 2>&1 && \
   lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 && \
   lsof -Pi :5173 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${GREEN}✅ All services are running!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  Some services are not running${NC}"
    echo ""
    echo "To start all services, run:"
    echo "  ./start-all-services.sh"
    exit 1
fi
