#!/bin/bash

# 🧪 RVX AI Bot - Unit Tests Quick Start Guide

set -e

echo "🚀 RVX AI Bot - Unit Tests Quick Start"
echo "======================================"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest not found. Installing..."
    pip install pytest pytest-cov pytest-asyncio pytest-xdist
    echo "✅ pytest installed"
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Menu
while true; do
    echo -e "${BLUE}Select test suite to run:${NC}"
    echo ""
    echo "1. 🚀 All tests (38 tests)"
    echo "2. 🔐 Security tests only (SQL Injection, Rate Limiting)"
    echo "3. ⚡ Fast tests only (<100ms each)"
    echo "4. 📊 With coverage report"
    echo "5. 🔄 Watch mode (rerun on file change)"
    echo "6. 📝 Verbose output (all details)"
    echo "7. ✅ Single test (enter test name)"
    echo "8. 📋 List all tests"
    echo "9. ❌ Exit"
    echo ""
    read -p "Choose option (1-9): " choice

    case $choice in
        1)
            echo -e "${YELLOW}Running all tests...${NC}"
            pytest tests/test_critical_functions.py tests/test_bot_database.py -v
            ;;
        2)
            echo -e "${YELLOW}Running security tests...${NC}"
            pytest tests/test_bot_database.py::TestSQLInjectionProtection -v
            pytest tests/test_critical_functions.py::TestAIRateLimiting -v
            ;;
        3)
            echo -e "${YELLOW}Running fast tests...${NC}"
            pytest tests/test_critical_functions.py tests/test_bot_database.py -v -m "not slow"
            ;;
        4)
            echo -e "${YELLOW}Running tests with coverage...${NC}"
            pytest tests/test_critical_functions.py tests/test_bot_database.py \
                --cov=. \
                --cov-report=html \
                --cov-report=term-missing \
                -v
            echo ""
            echo -e "${GREEN}✅ Coverage report generated: htmlcov/index.html${NC}"
            ;;
        5)
            echo -e "${YELLOW}Starting watch mode...${NC}"
            echo "(Press Ctrl+C to exit)"
            if command -v pytest-watch &> /dev/null; then
                ptw tests/test_critical_functions.py tests/test_bot_database.py -v
            else
                echo "⚠️  pytest-watch not installed. Install with: pip install pytest-watch"
                pytest tests/test_critical_functions.py tests/test_bot_database.py -v
            fi
            ;;
        6)
            echo -e "${YELLOW}Running tests with verbose output...${NC}"
            pytest tests/test_critical_functions.py tests/test_bot_database.py -vv --tb=long
            ;;
        7)
            read -p "Enter test name pattern (e.g., 'rate_limit' or 'sql_injection'): " pattern
            echo -e "${YELLOW}Searching for tests matching: $pattern${NC}"
            pytest tests/ -v -k "$pattern"
            ;;
        8)
            echo -e "${BLUE}Available tests:${NC}"
            echo ""
            pytest tests/test_critical_functions.py tests/test_bot_database.py --collect-only -q
            echo ""
            ;;
        9)
            echo "👋 Goodbye!"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option. Please choose 1-9.${NC}"
            ;;
    esac

    echo ""
    read -p "Press Enter to continue..."
    clear
done
