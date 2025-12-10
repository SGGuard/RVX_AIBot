"""
Обработчик квестов - управление тестами и XP
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from daily_quests_v2 import DAILY_QUESTS, get_user_level, get_level_name
import logging

logger = logging.getLogger(__name__)

async def start_quest(update: Update, context: ContextTypes.DEFAULT_TYPE, quest_id: str):
    """Начать квест - показать материал"""
    if quest_id not in DAILY_QUESTS:
        if update.callback_query:
            await update.callback_query.answer("❌ Квест не найден")
        return
    
    quest = DAILY_QUESTS[quest_id]
    
    # Инициализируем состояние квеста
    context.user_data['current_quest_id'] = quest_id
    context.user_data['current_quest_q'] = 0
    context.user_data['quest_answers'] = []
    
    # Показываем материал
    text = f"""📚 <b>{quest['title']}</b>

{quest['material']}

────────────────
Когда будешь готов, нажми кнопку ниже!"""
    
    keyboard = [[InlineKeyboardButton("✅ Начать тест", callback_data=f"start_test_{quest_id}")]]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE, quest_id: str):
    """Начать тест - показать первый вопрос"""
    if quest_id not in DAILY_QUESTS:
        if update.callback_query:
            await update.callback_query.answer("❌ Квест не найден")
        return
    
    quest = DAILY_QUESTS[quest_id]
    context.user_data['current_quest_id'] = quest_id
    context.user_data['current_quest_q'] = 0
    context.user_data['quest_answers'] = []
    
    await show_question(update, context, quest_id, 0)

async def show_question(update: Update, context: ContextTypes.DEFAULT_TYPE, quest_id: str, question_num: int):
    """Показать вопрос с вариантами ответов"""
    if quest_id not in DAILY_QUESTS:
        return
    
    quest = DAILY_QUESTS[quest_id]
    test = quest.get('test', [])
    
    if question_num >= len(test):
        await show_results(update, context, quest_id)
        return
    
    q = test[question_num]
    total = len(test)
    
    text = f"""❓ <b>Вопрос {question_num + 1}/{total}</b>

{q['question']}"""
    
    keyboard = []
    for idx, option in enumerate(q['options']):
        button_text = f"{chr(65 + idx)}. {option}"
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"answer_{quest_id}_{question_num}_{idx}"
        )])
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                       quest_id: str, question_num: int, answer_idx: int):
    """Обработать ответ и показать результат"""
    if quest_id not in DAILY_QUESTS:
        if update.callback_query:
            await update.callback_query.answer("❌ Квест не найден")
        return
    
    quest = DAILY_QUESTS[quest_id]
    test = quest.get('test', [])
    
    if question_num >= len(test):
        return
    
    q = test[question_num]
    is_correct = answer_idx == q['correct_index']
    
    # Сохраняем ответ
    context.user_data['quest_answers'].append(is_correct)
    
    # Показываем объяснение
    status = "✅ Правильно!" if is_correct else "❌ Неправильно"
    text = f"""{status}

<b>Твой ответ:</b> {q['options'][answer_idx]}
<b>Правильный ответ:</b> {q['options'][q['correct_index']]}

📝 <i>{q['explanation']}</i>"""
    
    # Кнопка "Далее"
    keyboard = [[InlineKeyboardButton(
        "⏭️ Дальше",
        callback_data=f"next_q_{quest_id}_{question_num + 1}"
    )]]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE, quest_id: str):
    """Показать результаты теста и выдать XP"""
    if quest_id not in DAILY_QUESTS:
        return
    
    # Импортируем здесь чтобы избежать циклической зависимости
    from bot import get_db
    
    quest = DAILY_QUESTS[quest_id]
    answers = context.user_data.get('quest_answers', [])
    user_id = update.effective_user.id
    
    total = len(quest.get('test', []))
    correct = sum(answers)
    percentage = (correct / total * 100) if total > 0 else 0
    
    # Определяем XP
    xp_reward = 0
    if percentage >= 75:
        xp_reward = quest.get('xp', 0)
        status = "🎉 Отлично!"
    elif percentage >= 50:
        xp_reward = int(quest.get('xp', 0) * 0.7)
        status = "😐 Хорошо"
    else:
        status = "😢 Попробуй еще раз"
    
    # Добавляем XP пользователю в БД
    if xp_reward > 0:
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                # Получаем текущий XP
                cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                current_xp = row[0] if row else 0
                
                # Обновляем XP
                new_xp = current_xp + xp_reward
                cursor.execute(
                    "INSERT OR REPLACE INTO users (user_id, xp) VALUES (?, ?)",
                    (user_id, new_xp)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении XP: {e}")
    
    text = f"""{status}

📊 <b>Результаты:</b>
{correct}/{total} правильно ({percentage:.0f}%)

{'🏆 <b>+ ' + str(xp_reward) + ' XP</b>' if xp_reward > 0 else '❌ XP не получено'}"""
    
    keyboard = [[InlineKeyboardButton(
        "📋 К заданиям",
        callback_data="show_quests"
    )]]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    
    # Очищаем состояние квеста
    context.user_data.pop('current_quest_id', None)
    context.user_data.pop('current_quest_q', None)
    context.user_data.pop('quest_answers', None)

