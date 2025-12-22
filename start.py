#!/usr/bin/env python3
"""
Start both API server and Telegram bot simultaneously.
This is the entry point for Railway deployment.
"""
import subprocess
import sys
import time
from pathlib import Path

def run_services():
    """Start both API server and bot."""
    
    # Ensure we're in the app directory
    app_dir = Path(__file__).parent
    
    print("=" * 60)
    print("🚀 RVX Backend - Starting Both Services")
    print("=" * 60)
    
    # Start API server in background
    print("\n📡 Starting API Server...")
    api_process = subprocess.Popen(
        [sys.executable, "api_server.py"],
        cwd=app_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Give API a moment to start
    time.sleep(2)
    
    print("🤖 Starting Telegram Bot...")
    # Start bot in foreground
    bot_process = subprocess.Popen(
        [sys.executable, "bot.py"],
        cwd=app_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    print("✅ Both services started!")
    print("\n" + "=" * 60)
    
    try:
        # Wait for bot (foreground process)
        bot_process.wait()
    except KeyboardInterrupt:
        print("\n⏹️  Shutting down services...")
        bot_process.terminate()
        api_process.terminate()
        time.sleep(1)
        bot_process.kill()
        api_process.kill()
        sys.exit(0)

if __name__ == "__main__":
    run_services()
