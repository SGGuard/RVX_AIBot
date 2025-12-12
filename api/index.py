"""
Vercel serverless function entry point for RVX API.
This wraps the FastAPI app for Vercel deployment.
"""
import sys
from pathlib import Path

# Add parent directory to path to import api_server
sys.path.insert(0, str(Path(__file__).parent.parent))

from api_server import app

# Vercel expects the app to be named 'app' or exported as 'handler'
handler = app
