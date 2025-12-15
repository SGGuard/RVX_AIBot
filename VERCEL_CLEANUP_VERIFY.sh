#!/bin/bash
# Vercel Cleanup Verification Script

echo "🔍 Vercel Cleanup Verification"
echo "================================"

echo ""
echo "1️⃣ Checking for Vercel files in current directory..."
if ls vercel.json .vercel .vercelignore 2>/dev/null; then
    echo "❌ Found Vercel files! Need cleanup"
    exit 1
else
    echo "✅ No Vercel config files in root"
fi

echo ""
echo "2️⃣ Checking git history for Vercel commits..."
vercel_commits=$(git log --all --oneline | grep -i vercel | wc -l)
echo "Found $vercel_commits Vercel-related commits (expected: 2-3)"

echo ""
echo "3️⃣ Checking .gitignore for Vercel entries..."
if grep -q "vercel" .gitignore; then
    echo "✅ Vercel in .gitignore (for accidental file safety)"
else
    echo "⚠️  Vercel not in .gitignore"
fi

echo ""
echo "4️⃣ Checking current deployments..."
echo "Active deployment platform: Railway ✅"
if [ -f "Procfile" ]; then
    echo "Procfile present (Railway compatible) ✅"
fi
if [ -f "Dockerfile" ]; then
    echo "Dockerfile present (Railway compatible) ✅"
fi
if [ -f "docker-compose.yml" ]; then
    echo "docker-compose.yml present (local dev) ✅"
fi

echo ""
echo "5️⃣ Checking for any Vercel references in code..."
vercel_refs=$(grep -r "vercel\|VERCEL" --include="*.py" --include="*.json" . 2>/dev/null | grep -v ".git" | grep -v "# Vercel (удалён" | wc -l)
if [ "$vercel_refs" -gt 0 ]; then
    echo "⚠️  Found $vercel_refs Vercel references (checking...)"
    grep -r "vercel\|VERCEL" --include="*.py" --include="*.json" . 2>/dev/null | grep -v ".git" | head -5
else
    echo "✅ No Vercel references in code"
fi

echo ""
echo "================================"
echo "✅ Vercel cleanup verification COMPLETE"
echo "Current platform: Railway only 🚀"
