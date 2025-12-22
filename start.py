#!/usr/bin/env python3
"""
Start Telegram bot and optionally API server.
This is the entry point for Railway deployment.
Supports both single-container (with API) and multi-container (Bot only) deployments.
"""
import subprocess
import sys
import time
import threading
from pathlib import Path

def run_api():
    """Run API server in a thread."""
    print("📡 Starting API Server on port 8000...")
    try:
        subprocess.run([sys.executable, "api_server.py"], check=True)
    except Exception as e:
        print(f"❌ API Server error: {e}")

def run_bot():
    """Run Telegram bot in main thread."""
    print("🤖 Starting Telegram Bot...")
    try:
        subprocess.run([sys.executable, "bot.py"], check=True)
    except Exception as e:
        print(f"❌ Bot error: {e}")

if __name__ == "__main__":
    print("=" * 70)
    print("🚀 RVX Backend - Starting Services")
    print("=" * 70)
    
    # Check if api_server.py exists (single-container deployment)
    api_exists = Path("/app/api_server.py").exists()
    
    if api_exists:
        print("✅ Single-container deployment detected (API + Bot)")
        
        # Start API in background thread
        api_thread = threading.Thread(target=run_api, daemon=False)
        api_thread.start()
        
        # Give API time to start
        print("⏳ Waiting for API to initialize...")
        time.sleep(3)
    else:
        print("✅ Multi-container deployment detected (Bot only, API in separate service)")
    
    # Start Bot in main thread (blocking)
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n⏹️  Shutting down services...")
        sys.exit(0)

