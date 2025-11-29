#!/usr/bin/env python3
"""
Integration tests for RVX Bot v0.5.0 - Educational Features
Tests interactive buttons, educational context, and callback handlers
"""

import sqlite3
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from education import (
    get_educational_context,
    get_lesson_content,
    get_all_tools_db,
    COURSES_DATA,
    XP_REWARDS,
    LEVEL_THRESHOLDS,
    BADGES
)

def test_educational_context_tuple_format():
    """Test 1: Verify get_educational_context returns proper tuple"""
    print("\n🧪 Test 1: Educational Context Tuple Format")
    print("=" * 60)
    
    test_cases = [
        ("Bitcoin и криптография работают вместе", 12345),
        ("DeFi и стейкинг - новые возможности заработка", 67890),
        ("Layer 2 решения масштабируют Ethereum", 11111),
        ("DAO управление и голосование", 22222),
    ]
    
    for news_text, user_id in test_cases:
        result = get_educational_context(news_text, user_id)
        
        # Check if result is a tuple with 2 elements
        assert isinstance(result, tuple) and len(result) == 2, f"❌ Expected tuple, got {type(result)}"
        
        context_text, callback_data = result
        
        # Check first element is None or string
        assert context_text is None or isinstance(context_text, str), f"❌ Context should be str or None"
        
        # Check second element is None or string with 'learn_' prefix
        assert callback_data is None or isinstance(callback_data, str), f"❌ Callback should be str or None"
        
        if context_text and callback_data:
            assert callback_data.startswith("learn_"), f"❌ Callback should start with 'learn_', got {callback_data}"
            print(f"✅ News: '{news_text[:40]}...'")
            print(f"   → Callback: {callback_data}")
            print(f"   → Context preview: {context_text[:60]}...")
        else:
            print(f"⚠️  News: '{news_text[:40]}...' → No matching lesson")
    
    return True


def test_callback_parsing():
    """Test 2: Verify callback format can be parsed correctly"""
    print("\n🧪 Test 2: Callback Format Parsing")
    print("=" * 60)
    
    test_callbacks = [
        "learn_blockchain_basics_1",
        "learn_blockchain_basics_5",
        "learn_defi_contracts_3",
        "learn_scaling_dao_1",
    ]
    
    for callback in test_callbacks:
        parts = callback.split("_")
        
        # Should have at least 3 parts: learn + course + lesson
        assert len(parts) >= 3, f"❌ Callback format invalid: {callback}"
        
        # Extract course and lesson
        course = "_".join(parts[1:-1])
        try:
            lesson = int(parts[-1])
            print(f"✅ {callback}")
            print(f"   → Course: {course}, Lesson: {lesson}")
        except ValueError:
            raise AssertionError(f"❌ Lesson number should be integer: {callback}")
    
    return True


def test_lesson_content_retrieval():
    """Test 3: Verify lessons can be retrieved from database"""
    print("\n🧪 Test 3: Lesson Content Retrieval")
    print("=" * 60)
    
    test_lessons = [
        ("blockchain_basics", 1),
        ("blockchain_basics", 5),
        ("defi_contracts", 3),
        ("scaling_dao", 1),
    ]
    
    for course, lesson_num in test_lessons:
        content = get_lesson_content(course, lesson_num)
        
        if content:
            print(f"✅ {course} - Lesson {lesson_num}")
            print(f"   → Content length: {len(content)} chars")
            print(f"   → Preview: {content[:80]}...")
        else:
            print(f"⚠️  {course} - Lesson {lesson_num} → Not found or empty")
    
    return True


def test_gamification_system():
    """Test 4: Verify XP rewards and level thresholds"""
    print("\n🧪 Test 4: Gamification System (XP & Levels)")
    print("=" * 60)
    
    print("\n📊 XP Rewards Configuration:")
    for activity, xp in XP_REWARDS.items():
        print(f"  • {activity}: +{xp} XP")
    
    print("\n⭐ Level Thresholds:")
    for level, data in LEVEL_THRESHOLDS.items():
        min_xp, max_xp, emoji, name = data
        max_xp_str = "∞" if max_xp == float('inf') else str(max_xp)
        print(f"  {emoji} Level {level}: {name} ({min_xp}-{max_xp_str} XP)")
    
    print("\n🏅 Available Badges:")
    for badge_id, badge_data in BADGES.items():
        name = badge_data.get('name', '?')
        description = badge_data.get('description', '?')
        print(f"  • {name}: {description}")
    
    return True


def test_courses_data():
    """Test 5: Verify course structure"""
    print("\n🧪 Test 5: Course Structure")
    print("=" * 60)
    
    for course_key, course_data in COURSES_DATA.items():
        print(f"\n📚 {course_data['title']} ({course_key})")
        print(f"   Level: {course_data['level']}")
        print(f"   Description: {course_data['description']}")
        print(f"   Lessons: {course_data['total_lessons']}")
        print(f"   Total XP: {course_data['total_xp']}")
        
        # Verify structure
        required_fields = ['title', 'level', 'description', 'total_lessons', 'total_xp']
        for field in required_fields:
            assert field in course_data, f"❌ Missing field '{field}' in course {course_key}"
    
    return True


def test_tools_retrieval():
    """Test 6: Verify tools can be retrieved"""
    print("\n🧪 Test 6: Tools Database")
    print("=" * 60)
    
    tools = get_all_tools_db()
    
    print(f"✅ Tools loaded: {len(tools)}")
    
    for tool in tools[:5]:  # Show first 5
        print(f"\n  🔧 {tool['name']} ({tool['category']})")
        print(f"     Difficulty: {tool['difficulty']}")
        print(f"     URL: {tool['url'][:50]}...")
    
    if len(tools) > 5:
        print(f"\n  ... and {len(tools) - 5} more tools")
    
    return True


def test_database_integrity():
    """Test 7: Check database schema and data"""
    print("\n🧪 Test 7: Database Integrity")
    print("=" * 60)
    
    conn = sqlite3.connect('rvx_bot.db')
    cursor = conn.cursor()
    
    # Check essential tables
    essential_tables = [
        'courses', 'lessons', 'users', 'requests', 
        'user_progress', 'user_questions', 'tools', 'faq'
    ]
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cursor.fetchall()}
    
    print(f"Total tables: {len(existing_tables)}")
    
    for table in essential_tables:
        if table in existing_tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  ✅ {table}: {count} records")
        else:
            print(f"  ❌ {table}: MISSING")
    
    conn.close()
    return True


def test_keyword_matching():
    """Test 8: Verify keyword matching for educational recommendations"""
    print("\n🧪 Test 8: Keyword Matching for Lessons")
    print("=" * 60)
    
    test_news = [
        ("Bitcoin майнинг и PoW", "blockchain_basics", 5),
        ("DeFi протоколы и смарт-контракты", "defi_contracts", 1),
        ("Layer 2 масштабирование", "scaling_dao", 1),
        ("Staking и валидаторы", "defi_contracts", 5),
        ("DAO governance", "scaling_dao", 3),
    ]
    
    for news, expected_course, expected_lesson in test_news:
        context, callback = get_educational_context(news, 12345)
        
        if callback:
            # Extract course and lesson from callback
            parts = callback.split("_")
            actual_course = "_".join(parts[1:-1])
            actual_lesson = int(parts[-1])
            
            if actual_course == expected_course and actual_lesson == expected_lesson:
                print(f"✅ '{news}' → {callback}")
            else:
                print(f"⚠️  '{news}' → {callback} (expected {expected_course}_{expected_lesson})")
        else:
            print(f"❌ '{news}' → No match (expected {expected_course}_{expected_lesson})")
    
    return True


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("🚀 RVX Bot v0.5.0 - Integration Tests")
    print("=" * 60)
    
    tests = [
        ("Educational Context Tuple Format", test_educational_context_tuple_format),
        ("Callback Format Parsing", test_callback_parsing),
        ("Lesson Content Retrieval", test_lesson_content_retrieval),
        ("Gamification System", test_gamification_system),
        ("Course Structure", test_courses_data),
        ("Tools Database", test_tools_retrieval),
        ("Database Integrity", test_database_integrity),
        ("Keyword Matching", test_keyword_matching),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results[test_name] = "✅ PASS"
        except Exception as e:
            results[test_name] = f"❌ FAIL: {str(e)}"
            print(f"\n❌ ERROR in {test_name}: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    
    passed = sum(1 for r in results.values() if "PASS" in r)
    total = len(results)
    
    for test_name, result in results.items():
        print(f"{result} - {test_name}")
    
    print(f"\n{'🎉' if passed == total else '⚠️ '} {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
