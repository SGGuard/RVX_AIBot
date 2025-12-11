#!/usr/bin/env python3
"""
RVX Deployment Diagnostic - Audit environment and code configuration
"""

import os
import sys

print("=" * 80)
print("🔍 RVX DEPLOYMENT AUDIT")
print("=" * 80)

# 1. Check environment variables
print("\n📋 ENVIRONMENT VARIABLES:")
print("-" * 80)

env_vars = [
    "TELEGRAM_BOT_TOKEN",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "API_URL",
    "API_URL_NEWS",
    "API_BASE_URL",
    "TEACH_API_URL",
    "RAILWAY_ENVIRONMENT",
    "PORT",
]

for var in env_vars:
    val = os.getenv(var)
    if val:
        # Mask secrets
        if "TOKEN" in var or "KEY" in var:
            display = f"{val[:4]}...{val[-4:]}"
        else:
            display = val
        print(f"  ✅ {var:25} = {display}")
    else:
        print(f"  ❌ {var:25} = NOT SET")

# 2. Check if running on Railway
print("\n🚀 DEPLOYMENT ENVIRONMENT:")
print("-" * 80)

if os.getenv("RAILWAY_ENVIRONMENT"):
    print(f"  🚂 Running on Railway (environment: {os.getenv('RAILWAY_ENVIRONMENT')})")
else:
    print("  💻 Running locally (not on Railway)")

# 3. Simulate URL resolution logic from teacher.py
print("\n🔗 TEACH_LESSON URL RESOLUTION (from teacher.py):")
print("-" * 80)

teach_api_url = os.getenv("TEACH_API_URL")
print(f"  Step 1: Check TEACH_API_URL env var = {teach_api_url}")

if not teach_api_url:
    api_base_url = os.getenv("API_BASE_URL")
    print(f"  Step 2: Check API_BASE_URL env var = {api_base_url}")
    
    if not api_base_url:
        api_url = os.getenv("API_URL")
        print(f"  Step 3: Check API_URL env var = {api_url}")
        
        if api_url:
            api_base_url = api_url.rstrip('/')
            print(f"    → Using API_URL: {api_base_url}")
        elif os.getenv("RAILWAY_ENVIRONMENT"):
            api_base_url = "http://localhost:8080"
            print(f"    → Fallback to Railway localhost: {api_base_url}")
        else:
            api_base_url = "http://localhost:8000"
            print(f"    → Fallback to local dev: {api_base_url}")
    
    teach_api_url = f"{api_base_url}/teach_lesson"

print(f"\n  ✅ FINAL TEACH_API_URL = {teach_api_url}")

# 4. Simulate URL resolution logic from bot.py
print("\n📰 EXPLAIN_NEWS URL RESOLUTION (from bot.py):")
print("-" * 80)

api_url_news = os.getenv("API_URL_NEWS")
print(f"  Step 1: Check API_URL_NEWS env var = {api_url_news}")

if not api_url_news:
    api_url = os.getenv("API_URL")
    print(f"  Step 2: Check API_URL env var = {api_url}")
    
    if api_url:
        api_url_news = api_url.rstrip('/') + "/explain_news"
        print(f"    → Using API_URL: {api_url_news}")
    elif os.getenv("API_BASE_URL"):
        api_base_url = os.getenv("API_BASE_URL")
        api_url_news = api_base_url.rstrip('/') + "/explain_news"
        print(f"    → Using API_BASE_URL: {api_url_news}")
    elif os.getenv("RAILWAY_ENVIRONMENT"):
        api_url_news = "http://localhost:8080/explain_news"
        print(f"    → Fallback to Railway localhost: {api_url_news}")
    else:
        api_url_news = "http://localhost:8000/explain_news"
        print(f"    → Fallback to local dev: {api_url_news}")

print(f"\n  ✅ FINAL API_URL_NEWS = {api_url_news}")

# 5. Diagnosis
print("\n🔍 DIAGNOSIS:")
print("-" * 80)

if teach_api_url.startswith("http://localhost"):
    print("  ⚠️  PROBLEM: Using localhost URL on Railway!")
    print("      Teaching feature will NOT work (separate containers)")
    print("\n  🔧 SOLUTION:")
    print("      1. Go to Railway Dashboard")
    print("      2. Click Bot Service → Variables")
    print("      3. Add: API_URL = https://rvx-api.railway.app")
    print("      4. Save and redeploy")
    sys.exit(1)
else:
    print("  ✅ Using proper public URL (should work)")
    print(f"     {teach_api_url}")
    sys.exit(0)

print("\n" + "=" * 80)
