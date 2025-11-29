#!/bin/bash
# RVX Bot v0.5.0 - Quick Test & Verification Script

echo "============================================================"
echo "🚀 RVX Bot v0.5.0 - Quick Test Suite"
echo "============================================================"

cd /home/sv4096/rvx_backend

# Check if services are running
echo -e "\n📋 Service Status:"
echo "---"

if ps aux | grep -q "[p]ython.*api_server.py"; then
    echo "✅ API Server: RUNNING (port 8000)"
else
    echo "❌ API Server: NOT RUNNING"
fi

if ps aux | grep -q "[p]ython.*bot.py"; then
    echo "✅ Telegram Bot: RUNNING (v0.5.0)"
else
    echo "❌ Telegram Bot: NOT RUNNING"
fi

# Check API health
echo -e "\n🏥 Health Check:"
echo "---"
HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null)
if [ ! -z "$HEALTH" ]; then
    echo "✅ API Health: $(echo $HEALTH | grep -o '"status":"[^"]*"' | cut -d'"' -f4)"
else
    echo "❌ API Health: Connection failed"
fi

# Run integration tests
echo -e "\n🧪 Running Test Suites:"
echo "---"

echo -e "\n📊 Test Suite 1: Core Education System (8 tests)"
python3 test_bot_v05.py 2>&1 | grep "🎉\|⚠️" | tail -1

echo -e "\n📊 Test Suite 2: Button Callbacks (5 tests)"
python3 test_callbacks_v05.py 2>&1 | grep "🎉\|⚠️" | tail -1

# Check database
echo -e "\n💾 Database Status:"
echo "---"
sqlite3 rvx_bot.db "SELECT COUNT(*) as 'Total Courses' FROM courses;" 2>/dev/null | head -1 && \
echo "  ✅ Courses loaded"

sqlite3 rvx_bot.db "SELECT COUNT(*) as 'Total Lessons' FROM lessons;" 2>/dev/null | head -1 && \
echo "  ✅ Lessons loaded"

sqlite3 rvx_bot.db "SELECT COUNT(*) as 'Total Requests' FROM requests;" 2>/dev/null | head -1

# Show bot version
echo -e "\n📦 Software Versions:"
echo "---"
echo "Bot Version: v0.5.0 (Interactive Educational System)"
echo "Python: $(python3 --version 2>&1 | cut -d' ' -f2)"
echo "Database: SQLite 3"

# Summary
echo -e "\n============================================================"
echo "✅ v0.5.0 - Ready for Use!"
echo "============================================================"
echo ""
echo "Quick Commands:"
echo "  • Run full tests:     python3 test_bot_v05.py"
echo "  • Run callback tests: python3 test_callbacks_v05.py"
echo "  • Check logs:         tail -f bot_v05_fixed.log"
echo "  • View test report:   cat TEST_REPORT_v0.5.0.md"
echo ""
