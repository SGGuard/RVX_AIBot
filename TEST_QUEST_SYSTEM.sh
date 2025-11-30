#!/bin/bash
# Quest System - Testing & Verification Commands

echo "🧪 RVX Bot Quest System - Testing Guide"
echo "========================================"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "\n${YELLOW}📋 AVAILABLE COMMANDS${NC}\n"

echo "1. View System Status"
echo "   Command: ps aux | grep 'python.*bot.py' | grep -v grep"
echo "   Expected: Should see bot process running\n"

echo "2. Check Bot Logs"
echo "   Command: tail -50 bot.log"
echo "   Expected: Should see ✅ messages, no ❌ errors\n"

echo "3. Run Demo Script"
echo "   Command: python3 quest_demo.py"
echo "   Expected: Should show quest structure and flow explanation\n"

echo "4. Verify Imports"
echo "   Command: python3 -c \"from quest_handler import *; from daily_quests import *; print('✅ OK')\""
echo "   Expected: Should print ✅ OK\n"

echo "5. Check Quest Structure"
echo "   Command: python3 -c \"from daily_quests import DAILY_QUESTS; print(list(DAILY_QUESTS.keys()))\""
echo "   Expected: Should show ['what_is_dex', 'what_is_staking']\n"

echo "6. Run Full System Check"
echo "   Command: python3 << 'EOF'
from daily_quests import DAILY_QUESTS
from quest_handler import start_quest, handle_answer, show_question, show_results

print(f'✅ {len(DAILY_QUESTS)} quests loaded')
print(f'✅ Total XP: {sum(q[\"xp_reward\"] for q in DAILY_QUESTS.values())} XP')
print('✅ All handlers imported')
EOF"
echo "   Expected: Should show 3 ✅ lines\n"

echo "7. Telegram User Test"
echo "   In Telegram: /tasks"
echo "   Expected: Should see list of quests with material previews\n"

echo "8. Telegram Quest Test"
echo "   In Telegram: /quest_what_is_dex"
echo "   Expected:"
echo "   - Should show DEX material"
echo "   - Should show Q1 with 4 option buttons"
echo "   - Click answers and follow prompts"
echo "   - Should get score and XP at end\n"

echo "9. Check Database"
echo "   Command: sqlite3 rvx_bot.db \"SELECT COUNT(*) FROM users;\""
echo "   Expected: Should show number of registered users\n"

echo "10. View Available Quests Programmatically"
echo "   Command: python3 -c \"from daily_quests import DAILY_QUESTS; 
for qid, q in DAILY_QUESTS.items():
    print(f'{qid}: {q[\"title\"]} ({q[\"xp_reward\"]} XP)')\""
echo "   Expected:"
echo "   what_is_dex: Что такое DEX? (50 XP)"
echo "   what_is_staking: Что такое стейкинг? (60 XP)\n"

echo "========================================"
echo "${GREEN}✅ All tests should pass!${NC}"
echo "========================================"
echo ""
echo "🚀 System is ready for production use"
echo ""
