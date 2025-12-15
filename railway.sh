#!/bin/bash
# Railway Deployment Helper Script
# This script ensures proper setup for Railway deployment

set -e

echo "🚀 RVX Backend - Railway Deployment Starting..."

# Step 1: Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt --no-cache-dir

# Step 2: Create necessary directories
echo "📁 Creating application directories..."
mkdir -p logs
mkdir -p backups

# Step 3: Verify critical files exist
echo "🔍 Verifying critical files..."
for file in api_server.py bot.py requirements.txt; do
    if [ ! -f "$file" ]; then
        echo "❌ ERROR: Required file not found: $file"
        exit 1
    fi
done

# Step 4: Check Python version
echo "🐍 Checking Python version..."
python --version

# Step 5: Verify key modules can be imported
echo "✅ Verifying module imports..."
python -c "
import sys
try:
    import fastapi
    import telegram
    import httpx
    import pydantic
    print('✅ All critical modules imported successfully')
except ImportError as e:
    print(f'❌ Import error: {e}')
    sys.exit(1)
"

# Step 6: Database initialization (for bot)
echo "📊 Checking database..."
if [ ! -f "rvx_bot.db" ]; then
    echo "📝 Database file not found - will be created on first bot run"
fi

# Step 7: API Keys initialization
echo "🔐 Checking API authentication database..."
if [ ! -f "auth_keys.db" ]; then
    echo "🔑 Auth database will be created on first API startup"
fi

# Step 8: Show environment summary
echo ""
echo "📋 Environment Summary:"
echo "  • Python: $(python --version 2>&1)"
echo "  • Railway: ${RAILWAY_ENVIRONMENT:-'not set'}"
echo "  • PORT: ${PORT:-'8080'}"
echo "  • API_URL: ${API_URL:-'not set'}"
echo ""

echo "✅ Deployment setup complete!"
echo "🎯 Ready to start services..."
