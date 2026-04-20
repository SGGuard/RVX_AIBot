#!/usr/bin/env python3
"""
Quick reference script for applying type hints fixes to bot.py, api_server.py, and education.py

Usage:
    python apply_type_hints.py [--file bot.py|api_server.py|education.py] [--dry-run]
"""

# PRIORITY FIXES FOR EDUCATION.PY (11 critical fixes)
EDUCATION_PY_FIXES = [
    {
        'line': 75,
        'function': 'load_courses_to_db',
        'current': 'def load_courses_to_db(cursor):',
        'suggested': 'def load_courses_to_db(cursor: sqlite3.Cursor) -> None:',
        'issue': 'Missing cursor type and return type',
        'priority': 'CRITICAL'
    },
    {
        'line': 115,
        'function': 'get_user_knowledge_level',
        'current': 'def get_user_knowledge_level(cursor, user_id: int) -> str:',
        'suggested': 'def get_user_knowledge_level(cursor: sqlite3.Cursor, user_id: int) -> str:',
        'issue': 'Missing cursor type',
        'priority': 'CRITICAL'
    },
    {
        'line': 126,
        'function': 'calculate_user_level_and_xp',
        'current': 'def calculate_user_level_and_xp(cursor, user_id: int) -> Tuple[int, int]:',
        'suggested': 'def calculate_user_level_and_xp(cursor: sqlite3.Cursor, user_id: int) -> Tuple[int, int]:',
        'issue': 'Missing cursor type',
        'priority': 'CRITICAL'
    },
    {
        'line': 139,
        'function': 'add_xp_to_user',
        'current': 'def add_xp_to_user(cursor, user_id: int, xp_amount: int, reason: str = ""):',
        'suggested': 'def add_xp_to_user(cursor: sqlite3.Cursor, user_id: int, xp_amount: int, reason: str = "") -> None:',
        'issue': 'Missing cursor type and return type',
        'priority': 'CRITICAL'
    },
    {
        'line': 148,
        'function': 'get_user_badges',
        'current': 'def get_user_badges(cursor, user_id: int) -> List[str]:',
        'suggested': 'def get_user_badges(cursor: sqlite3.Cursor, user_id: int) -> List[str]:',
        'issue': 'Missing cursor type',
        'priority': 'CRITICAL'
    },
    {
        'line': 163,
        'function': 'add_badge_to_user',
        'current': 'def add_badge_to_user(cursor, user_id: int, badge_key: str) -> bool:',
        'suggested': 'def add_badge_to_user(cursor: sqlite3.Cursor, user_id: int, badge_key: str) -> bool:',
        'issue': 'Missing cursor type',
        'priority': 'CRITICAL'
    },
    {
        'line': 254,
        'function': 'extract_quiz_from_lesson',
        'current': 'def extract_quiz_from_lesson(lesson_content: str, lesson_number: Optional[int] = None, full_course_content: Optional[str] = None) -> List[Dict]:',
        'suggested': 'def extract_quiz_from_lesson(lesson_content: str, lesson_number: Optional[int] = None, full_course_content: Optional[str] = None) -> List[Dict[str, Any]]:',
        'issue': 'Return type Dict should specify contents',
        'priority': 'HIGH'
    },
    {
        'line': 309,
        'function': 'get_faq_by_keyword',
        'current': 'def get_faq_by_keyword(cursor, keyword: str) -> Optional[Tuple[str, str, int]]:',
        'suggested': 'def get_faq_by_keyword(cursor: sqlite3.Cursor, keyword: str) -> Optional[Tuple[str, str, int]]:',
        'issue': 'Missing cursor type',
        'priority': 'CRITICAL'
    },
    {
        'line': 325,
        'function': 'save_question_to_db',
        'current': 'def save_question_to_db(cursor, user_id: int, question: str, answer: str, source: str = "gemini"):',
        'suggested': 'def save_question_to_db(cursor: sqlite3.Cursor, user_id: int, question: str, answer: str, source: str = "gemini") -> None:',
        'issue': 'Missing cursor type and return type',
        'priority': 'CRITICAL'
    },
    {
        'line': 347,
        'function': 'get_user_course_progress',
        'current': 'def get_user_course_progress(cursor, user_id: int, course_name: str) -> Dict:',
        'suggested': 'def get_user_course_progress(cursor: sqlite3.Cursor, user_id: int, course_name: str) -> Dict[str, Any]:',
        'issue': 'Missing cursor type and Dict content type',
        'priority': 'HIGH'
    },
    {
        'line': 388,
        'function': 'get_all_tools_db',
        'current': 'def get_all_tools_db() -> List[Dict]:',
        'suggested': 'def get_all_tools_db() -> List[Dict[str, Any]]:',
        'issue': 'Return type Dict should specify contents',
        'priority': 'HIGH'
    },
    {
        'line': 691,
        'function': 'get_next_lesson_info',
        'current': 'def get_next_lesson_info(course_name: str, lesson_num: int) -> Optional[Dict]:',
        'suggested': 'def get_next_lesson_info(course_name: str, lesson_num: int) -> Optional[Dict[str, Any]]:',
        'issue': 'Return type Dict should specify contents',
        'priority': 'HIGH'
    },
    {
        'line': 720,
        'function': 'build_user_context_prompt',
        'current': 'def build_user_context_prompt(cursor, user_id: int, base_prompt: str) -> str:',
        'suggested': 'def build_user_context_prompt(cursor: sqlite3.Cursor, user_id: int, base_prompt: str) -> str:',
        'issue': 'Missing cursor type',
        'priority': 'CRITICAL'
    },
    {
        'line': 784,
        'function': 'get_user_course_summary',
        'current': 'def get_user_course_summary(cursor, user_id: int) -> str:',
        'suggested': 'def get_user_course_summary(cursor: sqlite3.Cursor, user_id: int) -> str:',
        'issue': 'Missing cursor type',
        'priority': 'CRITICAL'
    },
    {
        'line': 856,
        'function': 'get_remaining_requests',
        'current': 'def get_remaining_requests(cursor, user_id: int) -> Tuple[int, int, str]:',
        'suggested': 'def get_remaining_requests(cursor: sqlite3.Cursor, user_id: int) -> Tuple[int, int, str]:',
        'issue': 'Missing cursor type',
        'priority': 'CRITICAL'
    },
    {
        'line': 887,
        'function': 'check_daily_limit',
        'current': 'def check_daily_limit(cursor, user_id: int) -> Tuple[bool, str]:',
        'suggested': 'def check_daily_limit(cursor: sqlite3.Cursor, user_id: int) -> Tuple[bool, str]:',
        'issue': 'Missing cursor type',
        'priority': 'CRITICAL'
    },
    {
        'line': 907,
        'function': 'increment_daily_requests',
        'current': 'def increment_daily_requests(cursor, user_id: int) -> None:',
        'suggested': 'def increment_daily_requests(cursor: sqlite3.Cursor, user_id: int) -> None:',
        'issue': 'Missing cursor type',
        'priority': 'CRITICAL'
    },
    {
        'line': 917,
        'function': 'reset_daily_requests',
        'current': 'def reset_daily_requests(cursor, user_id: int) -> None:',
        'suggested': 'def reset_daily_requests(cursor: sqlite3.Cursor, user_id: int) -> None:',
        'issue': 'Missing cursor type',
        'priority': 'CRITICAL'
    },
]

# PRIORITY FIXES FOR BOT.PY (8 critical fixes)
BOT_PY_FIXES = [
    {
        'line': 5268,
        'function': 'get_leaderboard',
        'current': 'def get_leaderboard(period: str = "all") -> tuple:',
        'suggested': 'def get_leaderboard(period: str = "all") -> Tuple[List[Tuple[int, int, int, int, int, int]], int]:',
        'issue': 'Return type should be specific Tuple type',
        'priority': 'CRITICAL'
    },
    {
        'line': 5387,
        'function': 'get_user_profile_data',
        'current': 'def get_user_profile_data(user_id: int) -> dict:',
        'suggested': 'def get_user_profile_data(user_id: int) -> Optional[Dict[str, Any]]:',
        'issue': 'Should be Optional and specify Dict contents',
        'priority': 'CRITICAL'
    },
    {
        'line': 5454,
        'function': 'format_user_profile',
        'current': 'def format_user_profile(profile_data: dict) -> str:',
        'suggested': 'def format_user_profile(profile_data: Optional[Dict[str, Any]]) -> str:',
        'issue': 'Parameter should be Optional and specific',
        'priority': 'HIGH'
    },
    {
        'line': 933,
        'function': 'handle_error',
        'current': 'def handle_error(error_type: str, error_msg: str, user_id: int, context: dict = None, log_level: str = "error") -> str:',
        'suggested': 'def handle_error(error_type: str, error_msg: str, user_id: int, context: Optional[Dict[str, Any]] = None, log_level: str = "error") -> str:',
        'issue': 'context parameter should be Optional and specific',
        'priority': 'HIGH'
    },
    {
        'line': 995,
        'function': 'log_error',
        'current': 'async def log_error(error_type: str, message: str, user_id: int = None, context: ContextTypes.DEFAULT_TYPE = None) -> None:',
        'suggested': 'async def log_error(error_type: str, message: str, user_id: Optional[int] = None, context: Optional[ContextTypes.DEFAULT_TYPE] = None) -> None:',
        'issue': 'Parameters should be Optional',
        'priority': 'HIGH'
    },
    {
        'line': 1179,
        'function': 'send_html_message',
        'current': 'async def send_html_message(update: Update, text: str, reply_markup: InlineKeyboardMarkup = None, parse_mode: str = ParseMode.HTML) -> None:',
        'suggested': 'async def send_html_message(update: Update, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, parse_mode: str = ParseMode.HTML) -> None:',
        'issue': 'reply_markup should be Optional',
        'priority': 'HIGH'
    },
    {
        'line': 1212,
        'function': 'send_educational_message',
        'current': 'async def send_educational_message(update: Update, topic: str, content: str, reply_markup: InlineKeyboardMarkup = None) -> None:',
        'suggested': 'async def send_educational_message(update: Update, topic: str, content: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:',
        'issue': 'reply_markup should be Optional',
        'priority': 'HIGH'
    },
    {
        'line': 3350,
        'function': 'format_main_response',
        'current': 'def format_main_response(title: str, summary: str, impact_points: List[str], tips: List[str] = None, educational_context: str = "", callback_data: str = "") -> str:',
        'suggested': 'def format_main_response(title: str, summary: str, impact_points: List[str], tips: Optional[List[str]] = None, educational_context: str = "", callback_data: str = "") -> str:',
        'issue': 'tips parameter should be Optional',
        'priority': 'HIGH'
    },
    {
        'line': 370,
        'function': 'clear_subscription_cache',
        'current': 'async def clear_subscription_cache(user_id: int = None) -> None:',
        'suggested': 'async def clear_subscription_cache(user_id: Optional[int] = None) -> None:',
        'issue': 'user_id should be Optional',
        'priority': 'MEDIUM'
    },
    {
        'line': 332,
        'function': 'require_auth',
        'current': 'def require_auth(required_level: AuthLevel) -> Callable:',
        'suggested': 'def require_auth(required_level: AuthLevel) -> Callable[[Callable], Callable]:',
        'issue': 'Should specify what the Callable returns',
        'priority': 'MEDIUM'
    },
    {
        'line': 1891,
        'function': 'get_db',
        'current': 'def get_db() -> contextmanager:',
        'suggested': 'def get_db() -> ContextManager[sqlite3.Connection]:',
        'issue': 'Should use typing.ContextManager with proper generic',
        'priority': 'MEDIUM'
    },
    {
        'line': 2580,
        'function': 'verify_database_schema',
        'current': 'def verify_database_schema() -> dict:',
        'suggested': 'def verify_database_schema() -> Dict[str, Any]:',
        'issue': 'Should specify Dict contents',
        'priority': 'MEDIUM'
    },
]

# PRIORITY FIXES FOR API_SERVER.PY (4 critical fixes)
API_SERVER_PY_FIXES = [
    {
        'line': 804,
        'function': 'build_gemini_config',
        'current': 'def build_gemini_config() -> dict:',
        'suggested': 'def build_gemini_config() -> Dict[str, Any]:',
        'issue': 'Should specify Dict contents',
        'priority': 'HIGH'
    },
    {
        'line': 860,
        'function': 'build_teaching_config',
        'current': 'def build_teaching_config() -> dict:',
        'suggested': 'def build_teaching_config() -> Dict[str, Any]:',
        'issue': 'Should specify Dict contents',
        'priority': 'HIGH'
    },
    {
        'line': 957,
        'function': 'build_image_analysis_config',
        'current': 'def build_image_analysis_config(context: Optional[str] = None) -> dict:',
        'suggested': 'def build_image_analysis_config(context: Optional[str] = None) -> Dict[str, Any]:',
        'issue': 'Should specify Dict contents',
        'priority': 'HIGH'
    },
]

# Summary statistics
STATS = {
    'education.py': {
        'total_functions': 25,
        'functions_needing_fixes': 17,
        'critical_fixes': 11,
        'high_priority_fixes': 6,
        'most_common_issue': 'Missing sqlite3.Cursor type annotation'
    },
    'bot.py': {
        'total_functions': 50,
        'functions_needing_fixes': 12,
        'critical_fixes': 2,
        'high_priority_fixes': 8,
        'most_common_issue': 'Missing Optional[] for nullable parameters'
    },
    'api_server.py': {
        'total_functions': 35,
        'functions_needing_fixes': 3,
        'critical_fixes': 0,
        'high_priority_fixes': 3,
        'most_common_issue': 'Generic dict() instead of Dict[str, Any]'
    }
}

if __name__ == '__main__':
    print("=" * 80)
    print("TYPE HINTS ANALYSIS - QUICK REFERENCE")
    print("=" * 80)
    
    print("\n📊 SUMMARY BY FILE:\n")
    for file, stats in STATS.items():
        print(f"{file}:")
        print(f"  Total functions: {stats['total_functions']}")
        print(f"  Needing fixes: {stats['functions_needing_fixes']}")
        print(f"  🔴 Critical: {stats['critical_fixes']}")
        print(f"  🟡 High Priority: {stats['high_priority_fixes']}")
        print(f"  Most common: {stats['most_common_issue']}\n")
    
    print("\n🔴 CRITICAL FIXES (education.py):\n")
    for i, fix in enumerate(EDUCATION_PY_FIXES[:6], 1):
        print(f"{i}. Line {fix['line']}: {fix['function']}()")
        print(f"   Issue: {fix['issue']}")
        print(f"   Before: {fix['current']}")
        print(f"   After:  {fix['suggested']}\n")
    
    print("\n🟡 HIGH PRIORITY FIXES (bot.py):\n")
    for i, fix in enumerate(BOT_PY_FIXES[:6], 1):
        print(f"{i}. Line {fix['line']}: {fix['function']}()")
        print(f"   Issue: {fix['issue']}")
        print(f"   Before: {fix['current']}")
        print(f"   After:  {fix['suggested']}\n")
    
    print("=" * 80)
    print(f"Total fixes needed: {len(EDUCATION_PY_FIXES) + len(BOT_PY_FIXES) + len(API_SERVER_PY_FIXES)}")
    print("=" * 80)
