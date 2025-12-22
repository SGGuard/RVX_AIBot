#!/usr/bin/env python3
"""
Start both API server and Telegram bot simultaneously.
This is the entry point for Railway deployment.
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
    print("🚀 RVX Backend - Starting Both Services in Single Container")
    print("=" * 70)
    
    # Start API in background thread
    api_thread = threading.Thread(target=run_api, daemon=False)
    api_thread.start()
    
    # Give API time to start
    print("⏳ Waiting for API to initialize...")
    time.sleep(3)
    
    # Start Bot in main thread (blocking)
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n⏹️  Shutting down services...")
        sys.exit(0)

