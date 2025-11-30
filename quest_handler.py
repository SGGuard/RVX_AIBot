from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from daily_quests import DAILY_QUESTS
from education import add_xp_to_user


async def start_quest(update: Update, context: ContextTypes.DEFAULT_TYPE, quest_id: str):
    """Показывает материал + сразу же тест."""
    user_id = update.effective_user.id
    
    quest = DAILY_QUESTS.get(quest_id)
    if not quest:
        await update.message.reply_text("❌ Квест не найден", parse_mode=ParseMode.HTML)
        return
    
    # Показываем материал
    material_text = f"""<b>{quest['title']}</b>

{quest['material']}

═══════════════════════════════════
<b>🧪 ТЕСТ ({len(quest['test'])} вопросов):</b>
"""
    
    await update.message.reply_text(material_text, parse_mode=ParseMode.HTML)
    
    # Показываем первый вопрос теста
    context.user_data['current_quest'] = quest_id
    context.user_data['current_question'] = 0
    context.user_data['correct_answers'] = 0
    context.user_data['total_questions'] = len(quest['test'])
    
    await show_question(update, context, quest_id, 0)


async def show_question(update: Update, context: ContextTypes.DEFAULT_TYPE, quest_id: str, question_num: int):
    """Показывает вопрос теста с вариантами ответа."""
    quest = DAILY_QUESTS.get(quest_id)
    test = quest['test']
    
    if question_num >= len(test):
        # Тест завершен
        await show_results(update, context, quest_id)
        return
    
    q = test[question_num]
    
    text = f"""<b>Вопрос {question_num + 1}/{len(test)}:</b>

{q['question']}
"""
    
    # Кнопки с вариантами ответа
    keyboard = []
    for i, option in enumerate(q['options']):
        keyboard.append([InlineKeyboardButton(f"{i+1}. {option}", callback_data=f"answer_{quest_id}_{question_num}_{i}")])
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, quest_id: str, question_num: int, answer_idx: int):
    """Обрабатывает ответ пользователя."""
    query = update.callback_query
    quest = DAILY_QUESTS.get(quest_id)
    test = quest['test']
    
    if question_num >= len(test):
        await query.answer("❌ Тест уже завершен", show_alert=True)
        return
    
    q = test[question_num]
    is_correct = answer_idx == q['correct_index']
    
    if is_correct:
        context.user_data['correct_answers'] = context.user_data.get('correct_answers', 0) + 1
        await query.answer("✅ Правильно!", show_alert=False)
    else:
        correct_answer = q['options'][q['correct_index']]
        await query.answer(f"❌ Неправильно!\n✅ Правильный ответ: {correct_answer}\n\n💡 {q['explanation']}", show_alert=True)
    
    # Переходим к следующему вопросу
    next_question = question_num + 1
    await query.edit_message_text("⏳ Загрузка следующего вопроса...")
    
    if next_question >= len(test):
        await show_results(update, context, quest_id)
    else:
        context.user_data['current_question'] = next_question
        # Показываем новый вопрос
        quest_data = DAILY_QUESTS.get(quest_id)
        test_data = quest_data['test']
        q_next = test_data[next_question]
        
        text = f"""<b>Вопрос {next_question + 1}/{len(test_data)}:</b>

{q_next['question']}
"""
        
        keyboard = []
        for i, option in enumerate(q_next['options']):
            keyboard.append([InlineKeyboardButton(f"{i+1}. {option}", callback_data=f"answer_{quest_id}_{next_question}_{i}")])
        
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE, quest_id: str):
    """Показывает результаты теста и выдает XP."""
    query = update.callback_query if update.callback_query else None
    user_id = update.effective_user.id
    
    correct = context.user_data.get('correct_answers', 0)
    total = context.user_data.get('total_questions', 0)
    quest = DAILY_QUESTS.get(quest_id)
    xp_reward = quest['xp_reward']
    
    percentage = int((correct / total) * 100) if total > 0 else 0
    
    # Результаты
    if percentage >= 75:
        status = "🎉 ОТЛИЧНО!"
        xp_earned = xp_reward
    elif percentage >= 50:
        status = "👍 ХОРОШО!"
        xp_earned = int(xp_reward * 0.7)
    else:
        status = "❌ ПРИ СЛЕДУЮЩЕМ РАЗЕ БУДЕТ ЛУЧШЕ"
        xp_earned = 0
    
    result_text = f"""{status}

✅ Правильно: {correct}/{total} ({percentage}%)
🏅 XP: +{xp_earned}
"""
    
    # Выдаем XP пользователю
    if xp_earned > 0:
        add_xp_to_user(user_id, xp_earned)
        result_text += f"\n💰 <i>XP добавлено в профиль!</i>"
    
    if query:
        await query.edit_message_text(result_text, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)
