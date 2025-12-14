#!/bin/bash
# 🧹 CLEANUP SCRIPT - RVX_BACKEND DOCUMENTATION
# Удаляет старые/дублирующиеся документы (100+ файлов)
# Сохраняет только необходимые

echo "🧹 Starting cleanup of old documentation..."
echo ""

# KEEP - Важные файлы (не трогаем)
KEEP_FILES=(
    "README.md"
    "DEPLOYMENT.md"
    "FINAL_COMPREHENSIVE_AUDIT_2025.md"
    "Dockerfile"
    "docker-compose.yml"
    "Procfile"
    "requirements.txt"
    ".env.example"
    ".gitignore"
    "pytest.ini"
)

# DELETE - Старые документы
DELETE_PATTERNS=(
    "AUDIT_*.md"
    "CODE_AUDIT_*.md"
    "CODE_AUDIT_*.json"
    "COMPREHENSIVE_*.md"
    "PHASE_*_COMPLETION*.md"
    "PHASE_[0-9]_*.md"
    "*_SUMMARY.md"
    "*_SUMMARY.txt"
    "*_AUDIT_*.md"
    "ANALYSIS_*.md"
    "IMPLEMENTATION_*.md"
    "IMPROVEMENTS_*.md"
    "*_REPORT.md"
    "*_REPORT.txt"
    "*_REPORT.json"
    "CLEANUP_*.md"
    "CLEANUP_*.txt"
    "*_ANALYSIS.md"
    "ACTION_PLAN*.md"
    "FIXES_*.md"
    "*_FIX*.md"
    "RELEASE_*.txt"
    "DIALOGUE_SYSTEM.md"
    "CHANNEL_*.md"
    "DROPS_*.md"
    "DROPS_*.txt"
    "DEPLOYMENT_*.md"
    "DUPLICATE_*.md"
    "RAILWAY_*.md"
    "TEACHING_*.md"
    "TEACHING_*.txt"
    "QUICK_*.md"
    "TECH_*.md"
    "MIGRATION_*.md"
    "SECURITY_*.md"
    "BOT_*.md"
    "MISTRAL_*.md"
    "TIER1_*.md"
    "LOCK_*.md"
    "LEADERBOARD_*.md"
    "QUEST_*.md"
    "SMART_*.md"
    "DAILY_*.md"
    "CRITICAL_*.md"
    "ROOT_*.md"
    "TESTS_*.md"
    "INDEX.md"
    "*_v0*.md"
    "*_v0*.txt"
    "*_GUIDE.md"
    "*_CHECKLIST.md"
    "*.save"
    "main.py.save"
)

# Count files to delete
DELETED=0
KEEP_COUNT=0

# Функция для проверки нужно ли удалять файл
should_delete() {
    local file=$1
    for keep in "${KEEP_FILES[@]}"; do
        if [[ "$file" == "$keep" ]]; then
            return 1  # Don't delete (keep it)
        fi
    done
    return 0  # Delete it
}

# Scan and delete
for file in *.md *.txt *.json *.save; do
    [ -e "$file" ] || continue
    
    if should_delete "$file"; then
        echo "❌ Deleting: $file"
        rm -f "$file"
        ((DELETED++))
    else
        echo "✅ Keeping:  $file"
        ((KEEP_COUNT++))
    fi
done

echo ""
echo "📊 CLEANUP RESULTS:"
echo "   ✅ Files kept:    $KEEP_COUNT"
echo "   ❌ Files deleted: $DELETED"
echo ""
echo "🎯 Repository cleaned! Remaining docs are in ./docs/ and README.md"
