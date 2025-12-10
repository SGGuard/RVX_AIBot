#!/usr/bin/env python3
"""
🧪 RVX AI Bot - Unit Tests Quick Start (Python Interactive)

Interactive menu for running different test suites.
Works on all platforms (Windows, macOS, Linux)

Usage:
    python run_tests.py
"""

import subprocess
import sys
import os
from pathlib import Path


class Colors:
    """ANSI color codes"""
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    RED = '\033[0;31m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header():
    """Print menu header"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}🧪 RVX AI Bot - Unit Tests Quick Start{Colors.END}")
    print("=" * 50)
    print()


def run_command(cmd, description=""):
    """Run a shell command"""
    if description:
        print(f"{Colors.YELLOW}{description}{Colors.END}\n")
    
    try:
        result = subprocess.run(cmd, shell=True)
        return result.returncode == 0
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.END}")
        return False


def menu():
    """Main menu loop"""
    os.chdir(Path(__file__).parent)  # Change to script directory
    
    options = {
        '1': {
            'name': '🚀 All tests (38 tests)',
            'cmd': 'pytest tests/test_critical_functions.py tests/test_bot_database.py -v',
        },
        '2': {
            'name': '🔐 Security tests only (SQL Injection, Rate Limiting)',
            'cmd': 'pytest tests/test_bot_database.py::TestSQLInjectionProtection tests/test_critical_functions.py::TestAIRateLimiting -v',
        },
        '3': {
            'name': '⚡ Fast tests (quick check)',
            'cmd': 'pytest tests/test_critical_functions.py tests/test_bot_database.py -q',
        },
        '4': {
            'name': '📊 With coverage report',
            'cmd': 'pytest tests/test_critical_functions.py tests/test_bot_database.py --cov=. --cov-report=html --cov-report=term-missing -v',
        },
        '5': {
            'name': '📝 Verbose output (all details)',
            'cmd': 'pytest tests/test_critical_functions.py tests/test_bot_database.py -vv --tb=long',
        },
        '6': {
            'name': '✅ Performance tests only',
            'cmd': 'pytest tests/test_critical_functions.py::TestPerformance -v',
        },
        '7': {
            'name': '🔄 Database tests only',
            'cmd': 'pytest tests/test_bot_database.py -v',
        },
        '8': {
            'name': '⏱️  Rate limiting tests only',
            'cmd': 'pytest tests/test_critical_functions.py::TestAIRateLimiting -v',
        },
        '9': {
            'name': '📋 List all available tests',
            'cmd': 'pytest tests/test_critical_functions.py tests/test_bot_database.py --collect-only -q',
        },
        '0': {
            'name': '❌ Exit',
            'cmd': None,
        },
    }
    
    while True:
        print_header()
        
        print(f"{Colors.BLUE}Select test suite to run:{Colors.END}\n")
        for key, option in options.items():
            print(f"{key}. {option['name']}")
        
        print()
        choice = input(f"{Colors.BOLD}Choose option (0-9): {Colors.END}").strip()
        
        if choice not in options:
            print(f"{Colors.RED}❌ Invalid option. Please choose 0-9.{Colors.END}")
            input("Press Enter to continue...")
            continue
        
        if choice == '0':
            print(f"\n{Colors.GREEN}👋 Goodbye!{Colors.END}\n")
            break
        
        option = options[choice]
        print()
        
        # Run the command
        success = run_command(option['cmd'], option['name'])
        
        print()
        if success:
            print(f"{Colors.GREEN}✅ Tests completed successfully{Colors.END}")
        else:
            print(f"{Colors.RED}❌ Tests failed{Colors.END}")
        
        input(f"\n{Colors.BOLD}Press Enter to continue...{Colors.END}")


def main():
    """Main entry point"""
    # Check if pytest is installed
    try:
        subprocess.run(['pytest', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"{Colors.RED}❌ pytest not found. Installing...{Colors.END}")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pytest', 'pytest-cov', 'pytest-asyncio'])
        print(f"{Colors.GREEN}✅ pytest installed{Colors.END}\n")
    
    try:
        menu()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.RED}Interrupted by user{Colors.END}\n")
        sys.exit(0)


if __name__ == '__main__':
    main()
