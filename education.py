"""
Модуль обучения (v0.5.0) для RVX Bot.
Управление курсами, уроками, прогрессом и XP системой.
"""

import os
import json
import re
import logging
from datetime import datetime
from typing import Optional, List, Tuple, Dict

logger = logging.getLogger(__name__)

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


def clean_lesson_content(content: str) -> str:
    """Очищает контент урока для отображения в Telegram (HTML).
    Удаляет проблемные символы и переносит markdown в простой текст."""
    # Удаляем *** символы
    content = content.replace('***', '')
    # Удаляем одиночные * которые используются для выделения
    content = re.sub(r'\*([^*]+)\*', r'\1', content)
    # Удаляем ** для жирного текста в markdown и заменяем на просто текст
    content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)
    return content


def split_lesson_content(content: str) -> Tuple[str, str]:
    """Разделяет контент урока на основной текст и quiz.
    Возвращает (lesson_text, quiz_text)."""
    # Ищем раздел с quiz
    quiz_match = re.search(r'### ❓ Quiz(.*?)(?:---|\Z)', content, re.DOTALL)
    
    if quiz_match:
        # Контент ДО quiz (без самого заголовка quiz)
        lesson_text = content[:quiz_match.start()].strip()
        # Контент quiz (весь раздел quiz)
        quiz_text = quiz_match.group(0)
        return lesson_text, quiz_text
    
    # Если нет quiz, вернуть весь контент как lesson
    return content, ""


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


def get_practical_tips(news_text: str) -> List[str]:
    """
    Анализирует новость и генерирует практические советы для пользователя.
    """
    tips = []
    news_lower = news_text.lower()
    
    # Советы по безопасности и взломам
    if any(word in news_lower for word in ['взлом', 'hack', 'уязвимость', 'атака', 'взломана', 'скам', 'scam']):
        tips.append("⚠️ **БЕЗОПАСНОСТЬ**: Никогда не используйте один пароль для разных кошельков. Включите 2FA везде!")
        tips.append("🔐 **ЗАЩИТА**: При взломах сразу переводите активы на холодный кошелек (Ledger, Trezor)")
        return tips
    
    # Советы по падению цены
    if any(word in news_lower for word in ['цена упала', 'падение', 'dump', 'обвал', 'медведь', 'bear', 'crash']):
        tips.append("📉 **РЫНОК**: Не паникуйте при падении. Проверьте фундаментальные причины перед продажей")
        tips.append("💡 **СОВЕТ**: Падение часто создает лучшие точки входа для долгосрочных инвесторов")
        return tips
    
    # Советы по новым максимумам
    if any(word in news_lower for word in ['новый ath', 'рекорд', 'максимум', 'all time high', 'peak', 'бычий', 'bull']):
        tips.append("📈 **ВНИМАНИЕ**: На максимумах цены чаще возникают откаты. Рассчитайте свой take profit")
        tips.append("🎯 **СТРАТЕГИЯ**: Закрепляйте прибыль частями, не дожидаясь максимума")
        return tips
    
    # Советы по ETF и институциональному входу
    if any(word in news_lower for word in ['etf', 'фонд', 'инсти', 'инвести', 'компания', 'blackrock', 'vanguard']):
        tips.append("🏦 **ИНСТИТУЦИОНАЛЬНЫЙ**: Когда инсты входят - это обычно долгосрочный положительный сигнал")
        tips.append("💰 **СОВЕТ**: Институциональное финансирование помогает легализации крипто в странах")
        return tips
    
    # Советы по регулированию
    if any(word in news_lower for word in ['reg', 'закон', 'запрет', 'разрешен', 'лицензия', 'sec', 'cftc']):
        tips.append("⚖️ **РЕГУЛИРОВАНИЕ**: Ясное законодательство обычно позитивно влияет на долгосроч цену")
        tips.append("📋 **ПОМНИТЕ**: Разные страны имеют разные подходы к крипто-регулированию")
        return tips
    
    # Советы по апгрейдам и техническому развитию
    if any(word in news_lower for word in ['fork', 'апгрейд', 'update', 'обновление', 'версия', 'улучшен', 'upgrade']):
        tips.append("🔄 **ТЕХНОЛОГИЯ**: Апгрейды часто приносят новые возможности и улучшают производительность")
        tips.append("⚡ **СОВЕТ**: Изучите детали апгрейда перед торговлей вокруг события")
        return tips
    
    # Советы по финансированию и инвестициям
    if any(word in news_lower for word in ['деньги', 'взнос', 'funding', 'инвестиция', 'раунд', 'seed', 'series', 'привлек']):
        tips.append("💵 **ФИНАНСИРОВАНИЕ**: Свежее финансирование часто помогает проекту развиваться быстрее")
        tips.append("📊 **АНАЛИЗ**: Посмотрите, кто инвестирует - репутация инвестора важна")
        return tips
    
    # Советы по партнерствам
    if any(word in news_lower for word in ['партнер', 'интеграция', 'коллаб', 'partnership', 'together', 'договор']):
        tips.append("🤝 **ПАРТНЕРСТВА**: Стратегические партнерства часто открывают новые рынки и использование")
        tips.append("🌐 **ЭКОСИСТЕМА**: Интеграция с крупными игроками - положительный знак принятия")
        return tips
    
    # Советы по DeFi
    if any(word in news_lower for word in ['uniswap', 'dex', 'биржа', 'обмен', 'swap', 'defi', 'лп']):
        tips.append("💧 **ЛИПИДНОСТЬ**: Проверяйте слипаж перед большими свопами на DEX")
        tips.append("⚡ **LP**: Перед входом в пулы ликвидности проверьте соотношение токенов и impermanent loss")
        return tips
    
    # Советы по стейкингу и yield
    if any(word in news_lower for word in ['staking', 'стейк', 'yield', 'фарм', 'apy', 'apр', 'награда', 'доход']):
        tips.append("🌾 **ДОХОД**: High APY обычно означает высокий риск. Изучите механизм генерации доходности")
        tips.append("🔐 **СТЕЙК**: Перед стейкингом проверьте период локапа и условия вывода")
        return tips
    
    # Советы по Layer 2 решениям
    if any(word in news_lower for word in ['layer 2', 'l2', 'arbitrum', 'optimism', 'polygon', 'масштаб']):
        tips.append("🚀 **L2**: Layer 2 сильно уменьшает комиссии, но будьте осторожны с новыми мостами")
        tips.append("⛓️ **МОСТ**: Мосты несут смарт-контрактный риск. Используйте проверенные решения (Stargate, Connext)")
        return tips
    
    # Советы по DAO и голосованию
    if any(word in news_lower for word in ['dao', 'governance', 'управление', 'голос', 'proposal']):
        tips.append("🏛️ **DAO**: Если вы держите токен - участвуйте в голосованиях, это влияет на будущее проекта")
        tips.append("🗳️ **ГОЛОС**: Внимательно изучайте предложения перед голосованием, даже если голосуете делегатом")
        return tips
    
    # Общие советы для новичков
    tips.append("💡 **СОВЕТ**: Всегда исследуйте новость из нескольких источников перед торговлей")
    tips.append("🎓 **ОБУЧЕНИЕ**: Изучите фундаментальный анализ перед техническим анализом")
    
    return tips[:2]  # Возвращаем максимум 2 совета


def get_educational_context(news_text: str, user_id: int) -> Tuple[Optional[str], Optional[str], List[str]]:
    """
    Анализирует новость и рекомендует связанные уроки для обучения + практические советы.
    Возвращает (контекст_текст, lesson_id_для_кнопки, советы) или (None, None, [])
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
    
    # Получаем практические советы
    tips = get_practical_tips(news_text)
    
    if not matched_lesson:
        return None, None, tips
    
    # Формируем образовательный контекст
    context = (
        f"\n\n📚 **ХОТИТЕ ПОНЯТЬ ГЛУБЖЕ?**\n\n"
        f"{matched_lesson['emoji']} **{matched_lesson['title']}**\n"
        f"_{matched_lesson['description']}_\n\n"
        f"Уровень: {'🌱 Beginner' if matched_lesson['course'] == 'blockchain_basics' else '📚 Intermediate' if matched_lesson['course'] == 'defi_contracts' else '🚀 Advanced'}"
    )
    
    return context, matched_lesson['callback_data'], tips


def get_next_lesson_info(course_name: str, lesson_num: int) -> Optional[Dict]:
    """Получает информацию о следующем уроке.
    
    Args:
        course_name: Имя курса
        lesson_num: Текущий номер урока
    
    Returns:
        Dict с info о следующем уроке или None если это последний урок
    """
    course_data = COURSES_DATA.get(course_name)
    if not course_data:
        return None
    
    total_lessons = course_data['total_lessons']
    next_lesson_num = lesson_num + 1
    
    if next_lesson_num > total_lessons:
        return None  # Это последний урок
    
    return {
        'course': course_name,
        'lesson_num': next_lesson_num,
        'title': course_data['title'],
        'total_lessons': total_lessons,
        'callback_data': f"next_lesson_{course_name}_{next_lesson_num}"
    }


def build_user_context_prompt(cursor, user_id: int, base_prompt: str) -> str:
    """Строит промпт с контекстом знаний пользователя.
    
    Args:
        cursor: Курсор БД
        user_id: ID пользователя
        base_prompt: Базовый промпт для анализа
    
    Returns:
        Промпт с добавленным контекстом уровня знаний
    """
    try:
        # Получаем уровень знаний пользователя
        cursor.execute("SELECT knowledge_level FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        knowledge_level = row[0] if row else "beginner"
        
        # Получаем прогресс пользователя по курсам (через JOIN)
        cursor.execute("""
            SELECT c.name, COUNT(DISTINCT l.id) as completed_lessons
            FROM user_progress up
            JOIN lessons l ON up.lesson_id = l.id
            JOIN courses c ON l.course_id = c.id
            WHERE up.user_id = ? AND (up.completed_at IS NOT NULL OR up.quiz_score > 0)
            GROUP BY c.name
        """, (user_id,))
        
        course_progress = cursor.fetchall()
        progress_text = ""
        if course_progress:
            progress_text = "Пользователь завершил уроки в следующих курсах: "
            progress_text += ", ".join([f"{course} ({count} уроков)" for course, count in course_progress])
        
        # Добавляем контекст к промпту
        enhanced_prompt = (
            f"КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:\n"
            f"- Уровень знаний: {knowledge_level}\n"
            f"- {progress_text}\n\n"
            f"ИНСТРУКЦИЯ:\n"
            f"Объясни следующую информацию подходящим образом для пользователя с уровнем '{knowledge_level}'.\n"
            f"Если это {knowledge_level}, используй:\n"
        )
        
        if knowledge_level == "beginner":
            enhanced_prompt += "- Простой язык, избегай терминов\n"
            enhanced_prompt += "- Аналогии и примеры из жизни\n"
            enhanced_prompt += "- Фокус на базовых концепциях\n\n"
        elif knowledge_level == "intermediate":
            enhanced_prompt += "- Технические детали с объяснениями\n"
            enhanced_prompt += "- Ссылки на более сложные концепции\n"
            enhanced_prompt += "- Примеры использования\n\n"
        else:  # expert
            enhanced_prompt += "- Технический язык и детали реализации\n"
            enhanced_prompt += "- Взаимосвязи с другими концепциями\n"
            enhanced_prompt += "- Источники и ссылки для углубления\n\n"
        
        enhanced_prompt += base_prompt
        return enhanced_prompt
    
    except Exception as e:
        logger.error(f"Ошибка при построении контекста пользователя: {e}")
        return base_prompt


def get_user_course_summary(cursor, user_id: int) -> str:
    """Получает краткое резюме прогресса пользователя по курсам.
    
    Returns:
        Форматированная строка с информацией о прогрессе
    """
    try:
        summary_parts = []
        
        for course_name, course_data in COURSES_DATA.items():
            # Подсчитываем завершенные уроки в этом курсе
            # (у которых есть quiz_score или completed_at)
            cursor.execute("""
                SELECT COUNT(DISTINCT l.id) as completed
                FROM user_progress up
                JOIN lessons l ON up.lesson_id = l.id
                JOIN courses c ON l.course_id = c.id
                WHERE up.user_id = ? AND c.name = ? 
                  AND (up.completed_at IS NOT NULL OR up.quiz_score > 0)
            """, (user_id, course_name))
            
            row = cursor.fetchone()
            completed = row[0] if row else 0
            total = course_data['total_lessons']
            
            if completed > 0:
                progress_pct = (completed / total) * 100
                summary_parts.append(
                    f"📚 {course_data['title']}: {completed}/{total} ({progress_pct:.0f}%)"
                )
        
        if not summary_parts:
            return "Начните изучение курсов для отслеживания прогресса!"
        
        return "\n".join(summary_parts)
    
    except Exception as e:
        logger.error(f"Ошибка при получении резюме курса: {e}")
        return ""
