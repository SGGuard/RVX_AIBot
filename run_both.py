#!/usr/bin/env python3
"""
Main entry point for Railway deployment
Starts both API server and Telegram bot using subprocess (parallel processes)
"""

import sys
import subprocess
import logging
import time
import os
import signal

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Track child processes
processes = []

def signal_handler(signum, frame):
    """Handle graceful shutdown"""
    logger.info("⛔ Shutdown signal received, terminating services...")
    for proc in processes:
        try:
            if proc and proc.poll() is None:  # Process still running
                proc.terminate()
                proc.wait(timeout=5)
        except Exception as e:
            logger.warning(f"Error terminating process: {e}")
    sys.exit(0)

def run_api_server():
    """Run FastAPI server in subprocess"""
    logger.info("🚀 Starting API Server...")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "api_server:app",
        "--host", "0.0.0.0",
        "--port", "8080",
        "--workers", "1",
        "--log-level", "info"
    ]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
            bufsize=1
        )
        logger.info(f"✅ API Server started (PID: {proc.pid})")
        return proc
    except Exception as e:
        logger.error(f"❌ Failed to start API Server: {e}")
        return None

def run_bot_service():
    """Run Telegram bot in subprocess"""
    logger.info("🤖 Starting Telegram Bot...")
    cmd = [
        sys.executable,
        "bot.py"
    ]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
            bufsize=1
        )
        logger.info(f"✅ Telegram Bot started (PID: {proc.pid})")
        return proc
    except Exception as e:
        logger.error(f"❌ Failed to start Telegram Bot: {e}")
        return None

def main():
    """Start both services and monitor them"""
    logger.info("⏳ Initializing dual-service startup...")
    logger.info(f"📍 Environment: {'Railway' if os.getenv('RAILWAY_ENVIRONMENT') else 'Local'}")
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Start API server
        api_proc = run_api_server()
        if not api_proc:
            logger.error("Failed to start API Server")
            sys.exit(1)
        processes.append(api_proc)
        
        # Give API server time to start
        time.sleep(2)
        
        # Start bot service
        bot_proc = run_bot_service()
        if not bot_proc:
            logger.error("Failed to start Bot Service")
            if api_proc:
                api_proc.terminate()
            sys.exit(1)
        processes.append(bot_proc)
        
        logger.info("✅ Both services started successfully!")
        logger.info("💪 Monitoring services...")
        
        # Monitor processes - if either dies, terminate all
        while True:
            # Check if API is still running
            if api_proc.poll() is not None:
                logger.error("❌ API Server crashed!")
                signal_handler(None, None)
                sys.exit(1)
            
            # Check if Bot is still running
            if bot_proc.poll() is not None:
                logger.error("❌ Telegram Bot crashed!")
                signal_handler(None, None)
                sys.exit(1)
            
            time.sleep(5)
            
    except KeyboardInterrupt:
        logger.info("⛔ Keyboard interrupt received")
        signal_handler(None, None)
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}", exc_info=True)
        signal_handler(None, None)
        sys.exit(1)

if __name__ == "__main__":
    main()
