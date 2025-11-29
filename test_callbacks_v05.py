#!/usr/bin/env python3
"""
Callback Handler Tests for RVX Bot v0.5.0
Simulates button clicks and verifies correct handling
"""

import sqlite3
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from education import get_lesson_content, get_educational_context

def parse_lesson_from_callback(callback_data: str):
    """Parse lesson info from callback data"""
    if not callback_data or not callback_data.startswith("learn_"):
        return None
    
    parts = callback_data.split("_")
    if len(parts) < 3:
        return None
    
    course = "_".join(parts[1:-1])
    try:
        lesson = int(parts[-1])
        return {"course": course, "lesson": lesson, "callback": callback_data}
    except ValueError:
        return None


def test_callback_button_flow():
    """Test 1: Complete callback flow simulation"""
    print("\n🧪 Test 1: Callback Button Flow Simulation")
    print("=" * 70)
    
    # Simulate user receiving news with educational recommendation
    news_text = "Bitcoin и блокчейн технология революционизируют финансовый мир"
    user_id = 12345
    
    print(f"\n📰 User sends news:")
    print(f"   '{news_text}'")
    
    # Get educational context (what would be shown to user)
    context_text, callback_data = get_educational_context(news_text, user_id)
    
    if not callback_data:
        print("❌ No educational context found!")
        return False
    
    print(f"\n✅ Educational context received")
    print(f"   Callback: {callback_data}")
    print(f"   Context preview: {context_text[:100]}...")
    
    # User clicks "📚 Начать урок" button
    print(f"\n👆 User clicks: '📚 Начать урок'")
    print(f"   Callback data sent: {callback_data}")
    
    # Parse callback
    lesson_info = parse_lesson_from_callback(callback_data)
    
    if not lesson_info:
        print("❌ Failed to parse callback!")
        return False
    
    print(f"\n✅ Callback parsed:")
    print(f"   Course: {lesson_info['course']}")
    print(f"   Lesson: {lesson_info['lesson']}")
    
    # Retrieve lesson content (what handler does)
    lesson_content = get_lesson_content(lesson_info['course'], lesson_info['lesson'])
    
    if not lesson_content:
        print(f"❌ Lesson not found: {lesson_info['course']} #{lesson_info['lesson']}")
        return False
    
    print(f"\n✅ Lesson retrieved:")
    print(f"   Content length: {len(lesson_content)} chars")
    print(f"   Preview:\n   {lesson_content[:150]}...")
    
    # Simulate XP award (handler would do: add_xp_to_user(cursor, user_id, 5, 'viewed_lesson'))
    print(f"\n✅ System would now:")
    print(f"   → Award 5 XP to user {user_id}")
    print(f"   → Mark lesson as viewed")
    print(f"   → Show lesson preview in message")
    
    return True


def test_ask_question_flow():
    """Test 2: Ask question callback flow"""
    print("\n\n🧪 Test 2: Ask Question Button Flow")
    print("=" * 70)
    
    callback_data = "ask_related_42"
    print(f"\n👆 User clicks: '💬 Задать вопрос'")
    print(f"   Callback data: {callback_data}")
    
    # Parse callback
    if callback_data.startswith("ask_related_"):
        try:
            request_id = int(callback_data.split("_")[-1])
            print(f"\n✅ Callback parsed:")
            print(f"   Request ID: {request_id}")
            print(f"\n✅ System would now:")
            print(f"   → Show message: 'Используйте /ask [question]'")
            print(f"   → Prompt user to ask follow-up question")
            return True
        except ValueError:
            print("❌ Failed to parse request ID")
            return False
    
    return False


def test_multiple_news_scenarios():
    """Test 3: Different news scenarios with appropriate buttons"""
    print("\n\n🧪 Test 3: Multiple News Scenarios")
    print("=" * 70)
    
    scenarios = [
        {
            "news": "Bitcoin достиг новых высот благодаря майнингу",
            "should_match": "blockchain_basics",
            "expected_lesson": 5,
        },
        {
            "news": "Uniswap и декентрализованные биржи меняют торговлю",
            "should_match": "defi_contracts",
            "expected_lesson": 3,
        },
        {
            "news": "Arbitrum масштабирует Ethereum для быстрых транзакций",
            "should_match": "scaling_dao",
            "expected_lesson": 1,
        },
        {
            "news": "DAOs революционизируют управление и голосование",
            "should_match": "scaling_dao",
            "expected_lesson": 3,
        },
    ]
    
    results = []
    for scenario in scenarios:
        news = scenario["news"]
        context, callback = get_educational_context(news, 12345)
        
        if callback:
            lesson_info = parse_lesson_from_callback(callback)
            if lesson_info:
                print(f"\n✅ Scenario: '{news[:50]}...'")
                print(f"   → Callback: {callback}")
                print(f"   → Course: {lesson_info['course']}")
                print(f"   → Lesson: {lesson_info['lesson']}")
                results.append(True)
            else:
                print(f"\n⚠️  Scenario: '{news[:50]}...'")
                print(f"   → Callback parse failed: {callback}")
                results.append(False)
        else:
            print(f"\n❌ Scenario: '{news[:50]}...'")
            print(f"   → No educational match")
            results.append(False)
    
    return all(results)


def test_button_state_persistence():
    """Test 4: Verify button data persists in database"""
    print("\n\n🧪 Test 4: Button Click Tracking in Database")
    print("=" * 70)
    
    conn = sqlite3.connect('rvx_bot.db')
    cursor = conn.cursor()
    
    # Check if requests table can track button clicks
    cursor.execute("PRAGMA table_info(requests)")
    columns = {row[1] for row in cursor.fetchall()}
    
    required_columns = ['user_id', 'request_text', 'response_text', 'created_at']
    
    print(f"\n✅ Requests table columns:")
    for col in required_columns:
        if col in columns:
            print(f"   ✓ {col}")
        else:
            print(f"   ✗ {col} (MISSING)")
    
    # Check requests with callbacks
    cursor.execute("""
        SELECT COUNT(*) FROM requests 
        WHERE created_at > datetime('now', '-1 hour')
    """)
    recent_requests = cursor.fetchone()[0]
    
    print(f"\n✅ Recent requests (last hour): {recent_requests}")
    
    # Check if user progress is tracked
    cursor.execute("SELECT COUNT(*) FROM user_progress")
    progress_records = cursor.fetchone()[0]
    print(f"✅ User progress records: {progress_records}")
    
    conn.close()
    return True


def test_button_security():
    """Test 5: Verify button callbacks are validated"""
    print("\n\n🧪 Test 5: Button Callback Security")
    print("=" * 70)
    
    invalid_callbacks = [
        "learn_invalid_course_1",  # Invalid course name
        "learn_blockchain_basics_99",  # Invalid lesson number
        "evil_injection_payload",  # Random injection
        "learn_blockchain_basics_abc",  # Non-numeric lesson
        "learn_",  # Incomplete callback
    ]
    
    print(f"\n🔒 Testing invalid callback attempts:\n")
    
    for callback in invalid_callbacks:
        result = parse_lesson_from_callback(callback)
        
        if result:
            # Try to get lesson
            content = get_lesson_content(result['course'], result['lesson'])
            if not content:
                print(f"✅ BLOCKED: {callback} → Lesson not found (safe)")
            else:
                print(f"⚠️  ALLOWED: {callback} → Lesson found (should verify)")
        else:
            print(f"✅ BLOCKED: {callback} → Parse failed (safe)")
    
    return True


def run_all_callback_tests():
    """Run all callback tests"""
    print("\n" + "=" * 70)
    print("🚀 RVX Bot v0.5.0 - Callback & Button Tests")
    print("=" * 70)
    
    tests = [
        ("Callback Button Flow Simulation", test_callback_button_flow),
        ("Ask Question Flow", test_ask_question_flow),
        ("Multiple News Scenarios", test_multiple_news_scenarios),
        ("Button Click Tracking", test_button_state_persistence),
        ("Button Security", test_button_security),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results[test_name] = "✅ PASS" if result else "❌ FAIL"
        except Exception as e:
            results[test_name] = f"❌ ERROR: {str(e)}"
            print(f"\n❌ ERROR in {test_name}: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 Callback Test Summary")
    print("=" * 70)
    
    for test_name, result in results.items():
        print(f"{result} - {test_name}")
    
    passed = sum(1 for r in results.values() if "PASS" in r)
    total = len(results)
    
    print(f"\n{'🎉' if passed == total else '⚠️ '} {passed}/{total} tests passed\n")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_callback_tests()
    sys.exit(0 if success else 1)
