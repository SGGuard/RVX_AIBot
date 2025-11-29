"""
Модуль обучения (v0.5.0) для RVX Bot.
Управление курсами, уроками, прогрессом и XP системой.
"""

import os
import json
import re
from datetime import datetime
from typing import Optional, List, Tuple, Dict

# Курсы с локальным кешем (заполняются при запуске)
COURSES_DATA = {
    'blockchain_basics': {
        'name': 'blockchain_basics',
        'title': 'Blockchain Basics',
        'level': 'beginner',
        'description': 'Базовый курс для понимания блокчейна и криптографии',
        'file': 'courses/beginner_blockchain_basics.md',
        'total_lessons': 5,
        'total_xp': 150
    },
    'defi_contracts': {
        'name': 'defi_contracts',
        'title': 'DeFi & Smart Contracts',
        'level': 'intermediate',
        'description': 'Углубленный курс о децентрализованных финансах и смарт-контрактах',
        'file': 'courses/intermediate_defi_contracts.md',
        'total_lessons': 5,
        'total_xp': 200
    },
    'scaling_dao': {
        'name': 'scaling_dao',
        'title': 'Layer 2 Scaling & DAO Governance',
        'level': 'advanced',
        'description': 'Продвинутый курс о масштабировании и децентрализованном управлении',
        'file': 'courses/advanced_scaling_dao.md',
        'total_lessons': 5,
        'total_xp': 300
    }
}

# XP таблица
XP_REWARDS = {
    'lesson_completed': 10,
    'quiz_completed': 25,
    'quiz_perfect': 50,  # 100% правильных ответов
    'ask_question': 5,
    'weekly_streak': 100,
    'course_completed': 150  # бонус за завершение курса
}

# Уровни и бейджи
LEVEL_THRESHOLDS = {
    1: (0, 500, '🌱', 'Newbie'),
    2: (500, 1500, '📚', 'Learner'),
    3: (1500, 3500, '🚀', 'Trader'),
    4: (3500, 7000, '🎓', 'Expert'),
    5: (7000, float('inf'), '💎', 'Legend')
}

BADGES = {
    'first_steps': {'name': '🏅 First Steps', 'description': 'Прошел первый урок'},
    'blockchain_graduate': {'name': '🎓 Blockchain Graduate', 'description': 'Завершил курс Blockchain Basics'},
    'defi_master': {'name': '🚀 DeFi Master', 'description': 'Завершил курс DeFi & Smart Contracts'},
    'legend': {'name': '💎 Legend', 'description': 'Завершил все курсы'},
    'weekly_streak_7': {'name': '🔥 7-Day Streak', 'description': '7 дней подряд учится'},
    'quiz_master': {'name': '✨ Quiz Master', 'description': '90%+ правильных ответов'},
}


def load_courses_to_db(cursor):
    """Загружает курсы из markdown файлов в БД (если не загружены)."""
    cursor.execute("SELECT COUNT(*) FROM courses")
    if cursor.fetchone()[0] > 0:
        return  # Курсы уже загружены
    
    for course_key, course_data in COURSES_DATA.items():
        # Вставляем курс
        cursor.execute("""
            INSERT INTO courses (name, title, level, description, total_lessons)
            VALUES (?, ?, ?, ?, ?)
        """, (course_data['name'], course_data['title'], course_data['level'],
              course_data['description'], course_data['total_lessons']))
        
        course_id = cursor.lastrowid
        
        # Парсим markdown и добавляем уроки
        file_path = course_data['file']
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Парсим уроки (Lesson N:)
            lessons = re.findall(r'## Lesson (\d+):(.*?(?=## Lesson|\Z))', content, re.DOTALL)
            
            for lesson_num, lesson_content in lessons:
                title_match = re.search(r'\*{2}(.+?)\*{2}', lesson_content)
                title = title_match.group(1) if title_match else f"Lesson {lesson_num}"
                
                # Извлекаем Quiz
                quiz_match = re.search(r'### ❓ Quiz(.*?)(?=---|\Z)', lesson_content, re.DOTALL)
                quiz_text = quiz_match.group(1) if quiz_match else ""
                
                # Сохраняем урок
                cursor.execute("""
                    INSERT INTO lessons (course_id, lesson_number, title, content, xp_reward)
                    VALUES (?, ?, ?, ?, ?)
                """, (course_id, int(lesson_num), title, lesson_content, XP_REWARDS['lesson_completed']))


def get_user_knowledge_level(cursor, user_id: int) -> str:
    """Получает уровень знаний пользователя или проводит диагностику."""
    cursor.execute("SELECT knowledge_level FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row and row[0] and row[0] != 'unknown':
        return row[0]
    
    return 'unknown'  # Нужно провести assessment


def calculate_user_level_and_xp(cursor, user_id: int) -> Tuple[int, int]:
    """Рассчитывает уровень пользователя на основе XP."""
    cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    xp = row[0] if row else 0
    
    for level, (min_xp, max_xp, emoji, name) in LEVEL_THRESHOLDS.items():
        if min_xp <= xp < max_xp:
            return level, xp
    
    return 1, xp


def add_xp_to_user(cursor, user_id: int, xp_amount: int, reason: str = ""):
    """Добавляет XP пользователю и обновляет уровень."""
    cursor.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (xp_amount, user_id))
    
    # Проверяем наличие новых бейджей
    level, new_xp = calculate_user_level_and_xp(cursor, user_id)
    cursor.execute("UPDATE users SET level = ? WHERE user_id = ?", (level, user_id))


def get_user_badges(cursor, user_id: int) -> List[str]:
    """Получает список бейджей пользователя."""
    cursor.execute("SELECT badges FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row and row[0]:
        try:
            return json.loads(row[0])
        except:
            return []
    
    return []


def add_badge_to_user(cursor, user_id: int, badge_key: str) -> bool:
    """Добавляет бейдж пользователю если его еще нет."""
    badges = get_user_badges(cursor, user_id)
    
    if badge_key not in badges and badge_key in BADGES:
        badges.append(badge_key)
        cursor.execute(
            "UPDATE users SET badges = ? WHERE user_id = ?",
            (json.dumps(badges), user_id)
        )
        return True
    
    return False


def get_lesson_content(course_name: str, lesson_num: int) -> Optional[str]:
    """Получает контент урока из markdown файла."""
    if course_name not in COURSES_DATA:
        return None
    
    file_path = COURSES_DATA[course_name]['file']
    if not os.path.exists(file_path):
        return None
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Парсим нужный урок
    pattern = rf'## Lesson {lesson_num}:(.*?)(?=## Lesson|\Z)'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    
    return None


def extract_quiz_from_lesson(lesson_content: str) -> List[Dict]:
    """Извлекает вопросы quiz из контента урока."""
    quiz_pattern = r'\*\*Q(\d+):(.*?)\*\*\s*\n((?:- [^-].*\n)*)'
    matches = re.findall(quiz_pattern, lesson_content)
    
    questions = []
    for q_num, question, answers in matches:
        answer_lines = [a.strip() for a in answers.split('\n') if a.strip()]
        
        # Находим правильный ответ (с ✅)
        correct_answer = None
        for i, ans in enumerate(answer_lines):
            if '✅' in ans:
                correct_answer = i
                break
        
        questions.append({
            'number': int(q_num),
            'text': question.strip(),
            'answers': [a.replace('✅', '').strip() for a in answer_lines],
            'correct': correct_answer
        })
    
    return questions


def get_faq_by_keyword(cursor, keyword: str) -> Optional[Tuple[str, str, int]]:
    """Получает FAQ по ключевому слову."""
    cursor.execute("""
        SELECT question, answer, id FROM faq
        WHERE LOWER(question) LIKE LOWER(?)
        ORDER BY views DESC
        LIMIT 1
    """, (f"%{keyword}%",))
    
    row = cursor.fetchone()
    if row:
        return row[0], row[1], row[2]
    
    return None


def save_question_to_db(cursor, user_id: int, question: str, answer: str, source: str = "gemini"):
    """Сохраняет вопрос и ответ в БД."""
    cursor.execute("""
        INSERT INTO user_questions (user_id, question, answer, source)
        VALUES (?, ?, ?, ?)
    """, (user_id, question, answer, source))


def add_question_to_faq(cursor, question: str, answer: str, category: str = "general"):
    """Добавляет вопрос в FAQ базу."""
    try:
        cursor.execute("""
            INSERT INTO faq (question, answer, category)
            VALUES (?, ?, ?)
        """, (question, answer, category))
        return True
    except:
        # Вопрос уже в FAQ
        return False


def get_user_course_progress(cursor, user_id: int, course_name: str) -> Dict:
    """Получает прогресс пользователя по курсу."""
    progress = {
        'completed_lessons': 0,
        'total_lessons': 0,
        'xp_earned': 0,
        'completed': False
    }
    
    if course_name not in COURSES_DATA:
        return progress
    
    course_data = COURSES_DATA[course_name]
    progress['total_lessons'] = course_data['total_lessons']
    
    # Получаем курс ID из БД
    cursor.execute("SELECT id FROM courses WHERE name = ?", (course_name,))
    row = cursor.fetchone()
    if not row:
        return progress
    
    course_id = row[0]
    
    # Получаем завершенные уроки
    cursor.execute("""
        SELECT COUNT(*) as completed, SUM(xp_earned) as xp
        FROM user_progress
        WHERE user_id = ? AND lesson_id IN (
            SELECT id FROM lessons WHERE course_id = ?
        ) AND completed_at IS NOT NULL
    """, (user_id, course_id))
    
    row = cursor.fetchone()
    if row:
        progress['completed_lessons'] = row[0] or 0
        progress['xp_earned'] = row[1] or 0
        progress['completed'] = progress['completed_lessons'] == progress['total_lessons']
    
    return progress


def get_all_tools_db() -> List[Dict]:
    """Возвращает предопределенный список инструментов."""
    return [
        {
            'name': 'Etherscan',
            'category': 'Explorer',
            'difficulty': 'beginner',
            'description': 'Блокчейн обозреватель Ethereum',
            'url': 'https://etherscan.io',
            'tutorial': '1. Откройте https://etherscan.io\n2. Вставьте адрес/tx hash в поиск\n3. Анализируйте данные'
        },
        {
            'name': 'Uniswap',
            'category': 'DEX',
            'difficulty': 'beginner',
            'description': 'Децентрализованная биржа для обмена токенов',
            'url': 'https://uniswap.org',
            'tutorial': '1. Подключите MetaMask\n2. Выберите токены для обмена\n3. Подтвердите транзакцию'
        },
        {
            'name': 'MetaMask',
            'category': 'Wallet',
            'difficulty': 'beginner',
            'description': 'Браузерный кошелек для взаимодействия с блокчейном',
            'url': 'https://metamask.io',
            'tutorial': '1. Установите расширение\n2. Создайте кошелек\n3. Сохраните seed phrase в безопасном месте'
        },
        {
            'name': 'Aave',
            'category': 'Lending',
            'difficulty': 'intermediate',
            'description': 'Протокол кредитования для получения процентов',
            'url': 'https://aave.com',
            'tutorial': '1. Подключите кошелек\n2. Депозит токены\n3. Получайте процент!'
        },
        {
            'name': 'Curve',
            'category': 'DEX',
            'difficulty': 'intermediate',
            'description': 'DEX специализированный для стейблов и обмена',
            'url': 'https://curve.fi',
            'tutorial': '1. Выберите пул\n2. Добавьте liquidity\n3. Получайте комиссии'
        },
        {
            'name': 'WalletConnect',
            'category': 'Connection',
            'difficulty': 'intermediate',
            'description': 'Протокол для подключения кошелька к приложениям',
            'url': 'https://walletconnect.com',
            'tutorial': '1. Отсканируйте QR код\n2. Подтвердите подключение\n3. Взаимодействуйте с app'
        },
        {
            'name': 'Arbitrum',
            'category': 'Layer2',
            'difficulty': 'advanced',
            'description': 'Layer 2 решение для быстрых и дешевых транзакций',
            'url': 'https://arbitrum.io',
            'tutorial': '1. Добавьте сеть в MetaMask\n2. Отправьте средства через мост\n3. Используйте приложения на L2'
        },
        {
            'name': 'Lido',
            'category': 'Staking',
            'difficulty': 'intermediate',
            'description': 'Простой стейкинг ETH без минимума',
            'url': 'https://lido.fi',
            'tutorial': '1. Подключите кошелек\n2. Стейкьте ETH\n3. Получайте stETH'
        }
    ]


def get_educational_context(news_text: str, user_id: int) -> Tuple[Optional[str], Optional[str]]:
    """
    Анализирует новость и рекомендует связанные уроки для обучения.
    Возвращает (контекст_текст, lesson_id_для_кнопки) или (None, None)
    """
    
    # Ключевые слова и соответствующие курсы/уроки
    keyword_map = {
        # Blockchain Basics
        ('блокчейн', 'криптография', 'транзакция', 'сеть', 'валидация'): {
            'course': 'blockchain_basics',
            'lesson': 1,
            'title': 'Blockchain Basics',
            'emoji': '⛓️',
            'description': 'Уроки о том, как работают блокчейны',
            'callback_data': 'learn_blockchain_basics_1'
        },
        ('bitcoin', 'btc', 'bitcoin', 'майнинг', 'pow'): {
            'course': 'blockchain_basics',
            'lesson': 5,
            'title': 'Майнинг и Proof of Work',
            'emoji': '⛏️',
            'description': 'Как создаются новые блоки и зарабатываются монеты',
            'callback_data': 'learn_blockchain_basics_5'
        },
        ('ethereum', 'eth', 'смарт-контракт', 'умный контракт'): {
            'course': 'blockchain_basics',
            'lesson': 2,
            'title': 'Bitcoin vs Ethereum',
            'emoji': '🟪',
            'description': 'Разница между Ethereum и Bitcoin',
            'callback_data': 'learn_blockchain_basics_2'
        },
        
        # DeFi & Smart Contracts
        ('defi', 'децентрализованный финанс', 'финансы', 'кредит', 'заём', 'покупай'): {
            'course': 'defi_contracts',
            'lesson': 1,
            'title': 'DeFi & Smart Contracts',
            'emoji': '🏦',
            'description': 'Основы децентрализованных финансов',
            'callback_data': 'learn_defi_contracts_1'
        },
        ('uniswap', 'dex', 'биржа', 'обмен', 'swap', 'liquidity'): {
            'course': 'defi_contracts',
            'lesson': 3,
            'title': 'Liquidity Pools',
            'emoji': '💧',
            'description': 'Как работают пулы ликвидности и DEX',
            'callback_data': 'learn_defi_contracts_3'
        },
        ('yield farming', 'фарминг', 'yield', 'apy', 'apр', 'доход', 'инвестиции'): {
            'course': 'defi_contracts',
            'lesson': 4,
            'title': 'Yield Farming',
            'emoji': '🌾',
            'description': 'Зарабатывайте проценты на крипто',
            'callback_data': 'learn_defi_contracts_4'
        },
        ('staking', 'стейкинг', 'валидатор', 'eth2', 'награда'): {
            'course': 'defi_contracts',
            'lesson': 5,
            'title': 'Staking & Validators',
            'emoji': '🔐',
            'description': 'Стейкьте криптовалюту и получайте награды',
            'callback_data': 'learn_defi_contracts_5'
        },
        
        # Layer 2 & DAO
        ('layer 2', 'l2', 'arbitrum', 'optimism', 'polygon', 'масштабирование'): {
            'course': 'scaling_dao',
            'lesson': 1,
            'title': 'Layer 2 Решения',
            'emoji': '🚀',
            'description': 'Как сделать блокчейн быстрее и дешевле',
            'callback_data': 'learn_scaling_dao_1'
        },
        ('dao', 'governance', 'управление', 'голосование', 'proposal', 'binance'): {
            'course': 'scaling_dao',
            'lesson': 3,
            'title': 'DAO & Governance',
            'emoji': '🏛️',
            'description': 'Децентрализованное управление протоколами',
            'callback_data': 'learn_scaling_dao_3'
        },
        ('токен', 'tokenomics', 'токеномика', 'эмиссия', 'supply'): {
            'course': 'scaling_dao',
            'lesson': 4,
            'title': 'Токеномика',
            'emoji': '💰',
            'description': 'Как устроена экономика криптопроектов',
            'callback_data': 'learn_scaling_dao_4'
        },
        ('мост', 'bridge', 'cross-chain', 'кроссчейн'): {
            'course': 'scaling_dao',
            'lesson': 2,
            'title': 'Cross-Chain Bridges',
            'emoji': '🌉',
            'description': 'Переводы между разными блокчейнами',
            'callback_data': 'learn_scaling_dao_2'
        },
        
        # Security & Wallets
        ('кошелек', 'приватный ключ', 'seed phrase', 'безопасность', 'security'): {
            'course': 'blockchain_basics',
            'lesson': 3,
            'title': 'Кошельки и приватные ключи',
            'emoji': '🔑',
            'description': 'Как безопасно хранить крипто',
            'callback_data': 'learn_blockchain_basics_3'
        },
        ('hack', 'хак', 'взлом', 'уязвимость', 'risk', 'риск'): {
            'course': 'blockchain_basics',
            'lesson': 3,
            'title': 'Безопасность',
            'emoji': '🛡️',
            'description': 'Защита ваших активов',
            'callback_data': 'learn_blockchain_basics_3'
        },
    }
    
    news_lower = news_text.lower()
    
    # Ищем совпадения по ключевым словам
    matched_lesson = None
    for keywords, lesson_info in keyword_map.items():
        if any(keyword in news_lower for keyword in keywords):
            matched_lesson = lesson_info
            break
    
    if not matched_lesson:
        return None, None
    
    # Формируем образовательный контекст
    context = (
        f"\n\n📚 **ХОТИТЕ ПОНЯТЬ ГЛУБЖЕ?**\n\n"
        f"{matched_lesson['emoji']} **{matched_lesson['title']}**\n"
        f"_{matched_lesson['description']}_\n\n"
        f"Уровень: {'🌱 Beginner' if matched_lesson['course'] == 'blockchain_basics' else '📚 Intermediate' if matched_lesson['course'] == 'defi_contracts' else '🚀 Advanced'}"
    )
    
    return context, matched_lesson['callback_data']
