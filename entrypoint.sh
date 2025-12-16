#!/bin/bash
# Railway entrypoint script that manages multiple services
# Starts API server and Telegram bot with proper signal handling

set -e

# Colors for logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting RVX Dual-Service EntryPoint${NC}"
echo -e "${GREEN}========================================${NC}"

# Create /var/run directory if it doesn't exist (for pidfiles)
mkdir -p /var/run

# Function to clean up child processes
cleanup() {
    echo -e "${YELLOW}⛔ Shutdown signal received${NC}"
    if [ ! -z "$API_PID" ]; then
        echo -e "${YELLOW}Stopping API Server (PID: $API_PID)...${NC}"
        kill $API_PID 2>/dev/null || true
        wait $API_PID 2>/dev/null || true
    fi
    if [ ! -z "$BOT_PID" ]; then
        echo -e "${YELLOW}Stopping Telegram Bot (PID: $BOT_PID)...${NC}"
        kill $BOT_PID 2>/dev/null || true
        wait $BOT_PID 2>/dev/null || true
    fi
    echo -e "${YELLOW}✅ All services stopped${NC}"
    exit 0
}

# Trap signals
trap cleanup SIGTERM SIGINT

# Start API Server
echo -e "${GREEN}🚀 Starting API Server...${NC}"
python -m uvicorn api_server:app --host 0.0.0.0 --port 8080 &
API_PID=$!
echo -e "${GREEN}✅ API Server started (PID: $API_PID)${NC}"

# Wait for API to be ready
sleep 2

# Start Telegram Bot
echo -e "${GREEN}🤖 Starting Telegram Bot...${NC}"
python bot.py &
BOT_PID=$!
echo -e "${GREEN}✅ Telegram Bot started (PID: $BOT_PID)${NC}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ All services started successfully!${NC}"
echo -e "${GREEN}💪 Monitoring processes...${NC}"

# Monitor both processes
while true; do
    if ! kill -0 $API_PID 2>/dev/null; then
        echo -e "${RED}❌ API Server crashed!${NC}"
        cleanup
        exit 1
    fi
    
    if ! kill -0 $BOT_PID 2>/dev/null; then
        echo -e "${RED}❌ Telegram Bot crashed!${NC}"
        cleanup
        exit 1
    fi
    
    sleep 5
done
