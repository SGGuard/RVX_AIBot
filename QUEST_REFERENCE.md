# 🎓 Quest System - Quick Reference

## 📱 User Commands

### Start a Quest
```
/quest_what_is_dex
/quest_what_is_staking
```

### View All Quests
```
/tasks
```

## 📊 Quest Information

### What is DEX? (what_is_dex)
- **XP Reward**: 50 XP
- **Duration**: ~5 minutes
- **Difficulty**: Beginner
- **Topics**: Centralized vs Decentralized, Wallet Control, Trading
- **Command**: `/quest_what_is_dex`

### What is Staking? (what_is_staking)
- **XP Reward**: 60 XP
- **Duration**: ~5 minutes
- **Difficulty**: Beginner
- **Topics**: Passive Income, APY, Rewards, Risk
- **Command**: `/quest_what_is_staking`

## 🎯 How Scoring Works

| Score    | Result        | XP Earned      |
|----------|---------------|----------------|
| 75-100%  | 🎉 ОТЛИЧНО!   | 100% of reward |
| 50-74%   | 👍 ХОРОШО!    | 70% of reward  |
| 0-49%    | ❌ ЕЩЁ РАЗ   | 0 XP           |

## 🔧 Developer Reference

### Adding a New Quest

1. Open `daily_quests.py`
2. Add to `DAILY_QUESTS` dict:

```python
"new_quest_id": {
    "title": "Quest Title",
    "description": "Short description",
    "material": """Your educational material here.
    Can be multi-line and formatted.""",
    "test": [
        {
            "question": "Question text?",
            "options": ["Wrong 1", "Correct", "Wrong 2", "Wrong 3"],
            "correct_index": 1,
            "explanation": "Explanation of why option 1 is correct"
        },
        # Add more questions...
    ],
    "xp_reward": 50
}
```

3. Bot automatically creates:
   - `/quest_new_quest_id` command
   - Displays in `/tasks`
   - Handles all test logic

### File Structure

```
quest_handler.py       ← Core quest logic (start, show_question, handle_answer, show_results)
daily_quests.py        ← Quest definitions (DAILY_QUESTS dict)
bot.py                 ← Integration (quest_command, button_callback updates, task handlers)
```

### Key Functions

**quest_handler.py**:
- `start_quest(update, context, quest_id)` - Start quest, show material
- `show_question(update, context, quest_id, question_num)` - Display question with buttons
- `handle_answer(update, context, quest_id, question_num, answer_idx)` - Process answer
- `show_results(update, context, quest_id)` - Show score, grant XP

**bot.py**:
- `quest_command(update, context)` - Handler for /quest_* commands
- `button_callback(update, context)` - Handler for answer button clicks (answer_* callbacks)
- `tasks_command(update, context)` - Display all available quests

### Callback Data Format

```
answer_{quest_id}_{question_num}_{answer_idx}

Example: answer_what_is_dex_0_2
- Quest: what_is_dex
- Question: 0 (first question, 0-indexed)
- Answer: 2 (third option, 0-indexed)
```

## 🧪 Testing

### Run Demo Script
```bash
python3 quest_demo.py
```

Shows:
- Quest structure validation
- Callback parsing examples
- Command parsing examples
- Test flow explanation
- XP calculation examples

### Manual Testing

1. Send `/tasks` to see all quests
2. Send `/quest_what_is_dex` to start DEX quest
3. Follow bot prompts
4. Answer all 3 questions
5. See final score and XP gained

### Check Bot Status

```bash
# Check if bot is running
ps aux | grep "python.*bot.py" | grep -v grep

# View logs
tail -50 bot.log

# Check for errors
grep -i "error\|❌" bot.log | tail -10
```

## 📈 Current Statistics

- **Total Quests**: 2
- **Total Available XP per Day**: 110 XP (50 + 60)
- **Questions per Quest**: 3 questions each
- **Passing Score**: 75% (2.25/3 questions correct minimum)

## 🚀 System Status

✅ Bot Running
✅ Quest Handler Working
✅ Daily Quests Defined
✅ Command Handlers Registered
✅ Callback Processing Active

## 📝 Notes

- Users can retake quests daily (no daily reset implemented yet)
- XP is only granted on quest completion (75%+ score)
- Explanations appear after wrong answers to help learning
- Material is shown before test starts
- Questions appear one at a time for focused attention
- System is extensible - easy to add new quests anytime

## 🔗 Related Files

- `/QUEST_IMPLEMENTATION.md` - Detailed implementation guide
- `quest_demo.py` - Demonstration and testing script
- `.env` - Configuration (TELEGRAM_BOT_TOKEN, etc.)
- `bot.log` - Bot activity log
