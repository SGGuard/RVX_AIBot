# 🎓 RVX Bot - Quest System Implementation (v0.12.0)

## ✅ What Was Implemented

### 1. **Core Quest Files**

#### `daily_quests.py` (NEW)
- Defines all available daily quests in a clean, simple structure
- Each quest has: `title`, `description`, `material` (educational text), `test` (questions), `xp_reward`
- Current quests:
  - **what_is_dex**: DEX explanation with 3 test questions (50 XP)
  - **what_is_staking**: Staking explanation with 3 test questions (60 XP)
- Structure is easily extensible for adding more quests

#### `quest_handler.py` (NEW)
- Four main functions:
  - `start_quest()`: Shows material + initializes test context
  - `show_question()`: Displays current question with option buttons
  - `handle_answer()`: Processes user's answer, checks correctness, moves to next question
  - `show_results()`: Calculates score, grants XP if passed (75%+)

### 2. **Bot Integration**

#### `bot.py` Updates
1. **Import**: Added `from quest_handler import start_quest, handle_answer`
2. **New Command Handler**: `quest_command()` - parses `/quest_*` commands and launches quests
3. **Dynamic Command Registration**: Registers handlers for all `/quest_what_is_dex`, `/quest_what_is_staking`, etc.
4. **Callback Handler**: Updated `button_callback()` to handle `answer_*` callbacks
5. **Updated `tasks_command()`**: Now displays all quests from `DAILY_QUESTS` with material previews and command suggestions

## 🎮 User Flow

### How a User Takes a Quest:
1. User clicks `/tasks` or `/quest_what_is_dex`
2. Bot shows educational material (826-875 characters)
3. Bot shows first test question with 4 clickable options
4. User clicks answer → gets feedback (correct/incorrect + explanation)
5. Next question appears automatically
6. After all questions: bot shows score and grants XP

### XP Calculation:
- **75%+**: ✅ Full XP reward (e.g., 50 XP for DEX quest)
- **50-74%**: 👍 70% of XP (e.g., 35 XP)
- **<50%**: ❌ 0 XP (no penalty, just try again tomorrow)

## 📊 Data Flow

```
/quest_what_is_dex (command)
    ↓
quest_command() → parses quest_id → start_quest()
    ↓
start_quest() → shows material → show_question(0)
    ↓
User sees: Q1 of 3 with 4 buttons
    ↓
User clicks button → answer_what_is_dex_0_1 (callback)
    ↓
button_callback() → parses quest_id, q_num, answer_idx → handle_answer()
    ↓
handle_answer() → checks correctness → shows alert → show_question(1)
    ↓
... repeat for Q2, Q3 ...
    ↓
show_results() → calculates score → grants XP → shows final message
```

## 🔧 Callback Data Format

```
answer_{quest_id}_{question_num}_{answer_idx}

Examples:
- answer_what_is_dex_0_1 → DEX quest, Q0, selected option 1
- answer_what_is_staking_2_3 → Staking quest, Q2, selected option 3
```

## 📁 File Structure

```
/home/sv4096/rvx_backend/
├── bot.py                    (updated with quest handlers)
├── quest_handler.py          (NEW - quest logic)
├── daily_quests.py           (NEW - quest definitions)
└── quest_demo.py             (NEW - demonstration script)
```

## ✨ Key Features

1. **Simple & Clear**: Material → Test → XP (nothing else)
2. **Immediate Feedback**: After each answer, user sees if they're correct + explanation
3. **Progressive**: Questions appear one at a time for better focus
4. **Rewarding**: XP only granted for passing tests (75%+)
5. **Extensible**: Easy to add new quests - just add to `DAILY_QUESTS` dict
6. **Context Tracking**: Bot tracks which quest user is on, current question, correct answers

## 🚀 How to Add New Quests

Simply add to `DAILY_QUESTS` in `daily_quests.py`:

```python
DAILY_QUESTS = {
    "your_quest_id": {
        "title": "Quest Title",
        "description": "Short description",
        "material": """Educational material text...
        Can be multi-line, formatted with emojis, etc.""",
        "test": [
            {
                "question": "What is...?",
                "options": ["A", "B", "C", "D"],
                "correct_index": 1,  # Index of correct answer (0-3)
                "explanation": "Why B is correct..."
            },
            # ... more questions ...
        ],
        "xp_reward": 50
    }
}
```

Then the bot will automatically:
- Register `/quest_your_quest_id` command
- Display it in `/tasks`
- Handle all the test logic

## 🧪 Testing

Run the demo script:
```bash
python3 quest_demo.py
```

This shows:
- Quest structure validation
- Callback parsing examples
- Command parsing examples
- Full test flow explanation
- XP calculation examples

## 📈 What's Working

✅ Quest material display
✅ Test question display with buttons
✅ Answer validation (checking correct_index)
✅ Callback parsing
✅ Multiple questions flow
✅ XP calculation and granting
✅ Result display
✅ Dynamic command registration for all quests
✅ Integration with existing bot features

## 🔮 Future Enhancements

- Daily quest reset at midnight
- Quest completion tracking in DB
- User statistics (quests completed per day)
- Quest retry limits
- Leaderboard for most quests completed
- Difficulty levels for quests
- Quest categories/tags

## ✅ Testing Checklist

- [x] Import chains work (no circular imports)
- [x] Syntax validation (py_compile)
- [x] Bot starts successfully
- [x] Quest structure is valid
- [x] Callback parsing logic is correct
- [x] Command parsing logic is correct
- [x] XP calculation examples work
- [x] Demo script runs without errors
