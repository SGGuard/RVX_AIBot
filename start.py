#!/usr/bin/env python3
"""
Start Telegram bot on Railway deployment.
Railway is configured for BOT-ONLY execution.
API server must run in a separate service/container.
"""
import subprocess
import sys

def run_bot():
    """Run Telegram bot - the main service on Railway."""
    print("=" * 70)
    print("🤖 RVX Telegram Bot - Starting")
    print("=" * 70)
    print("📡 API Configuration:")
    print("   • API is in separate Railway service")
    print("   • Bot will connect to API_URL from environment")
    print("=" * 70)
    
    try:
        subprocess.run([sys.executable, "bot.py"], check=True)
    except KeyboardInterrupt:
        print("\n⏹️  Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Railway runs ONLY the bot
    run_bot()
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n⏹️  Shutting down services...")
        sys.exit(0)

