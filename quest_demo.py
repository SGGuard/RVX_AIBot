#!/usr/bin/env python3
"""
Demo script showing how the quest system works.
This is for testing/demonstration purposes only.
"""

from daily_quests import DAILY_QUESTS
from quest_handler import show_question, show_results

def demo_quest_structure():
    """Show the structure of quests."""
    print("=" * 70)
    print("🎓 DEMO: СТРУКТУРА КВЕСТОВ")
    print("=" * 70)
    
    for quest_id, quest in DAILY_QUESTS.items():
        print(f"\n📚 Квест: {quest['title']} (ID: {quest_id})")
        print(f"   XP Reward: {quest['xp_reward']}")
        print(f"   Material preview: {quest['material'][:100]}...")
        print(f"   Test: {len(quest['test'])} questions")
        
        for i, q in enumerate(quest['test'], 1):
            print(f"\n   Q{i}: {q['question']}")
            for j, opt in enumerate(q['options']):
                marker = "✅" if j == q['correct_index'] else "  "
                print(f"      {marker} {j+1}. {opt}")
            print(f"      💡 {q['explanation']}")


def demo_callback_parsing():
    """Show how callback data is parsed."""
    print("\n" + "=" * 70)
    print("🧪 DEMO: ПАРСИНГ CALLBACK'ОВ")
    print("=" * 70)
    
    # Examples of callback data
    examples = [
        "answer_what_is_dex_0_1",       # Quest: what_is_dex, Q0, answer 1
        "answer_what_is_staking_2_0",   # Quest: what_is_staking, Q2, answer 0
        "answer_defi_farming_1_3",      # Quest: defi_farming, Q1, answer 3
    ]
    
    for callback_data in examples:
        parts = callback_data.split("_")
        
        # Parse: answer_quest_id_..._question_num_answer_idx
        answer_idx = int(parts[-1])
        question_num = int(parts[-2])
        quest_id = "_".join(parts[1:-2])
        
        print(f"\nCallback: {callback_data}")
        print(f"  Quest ID: {quest_id}")
        print(f"  Question: {question_num}")
        print(f"  Answer: {answer_idx}")


def demo_command_parsing():
    """Show how quest commands are parsed."""
    print("\n" + "=" * 70)
    print("📢 DEMO: ПАРСИНГ КОМАНД")
    print("=" * 70)
    
    # In bot.py, when /quest_what_is_dex is called:
    # context.args will be available
    
    examples = {
        "/quest_what_is_dex": "what_is_dex",
        "/quest_what_is_staking": "what_is_staking",
        "/quest_defi_farming_strategies": "defi_farming_strategies",
    }
    
    for cmd, expected_id in examples.items():
        # Remove /quest_ prefix
        quest_id = cmd.replace("/quest_", "")
        
        print(f"\nCommand: {cmd}")
        print(f"  Parsed Quest ID: {quest_id}")
        print(f"  Expected: {expected_id}")
        print(f"  Match: {'✅' if quest_id == expected_id else '❌'}")


def demo_test_flow():
    """Show the test flow."""
    print("\n" + "=" * 70)
    print("🧪 DEMO: FLOW ТЕСТИРОВАНИЯ")
    print("=" * 70)
    
    print("""
1️⃣  User writes: /quest_what_is_dex

2️⃣  Bot calls quest_command() which:
    - Parses quest_id from command args
    - Calls start_quest(update, context, 'what_is_dex')

3️⃣  start_quest() does:
    - Show material text
    - Initialize context: current_quest, current_question, correct_answers, total_questions
    - Call show_question() for first question

4️⃣  show_question() does:
    - Get question from DAILY_QUESTS
    - Show question with 4 inline buttons (one per option)
    - Each button has callback_data: "answer_what_is_dex_0_X" (X = option index)

5️⃣  User clicks button → callback: "answer_what_is_dex_0_1"

6️⃣  button_callback() does:
    - Parse callback: quest_id="what_is_dex", question_num=0, answer_idx=1
    - Call handle_answer(update, context, 'what_is_dex', 0, 1)

7️⃣  handle_answer() does:
    - Check if answer is correct
    - Show alert popup (correct/incorrect + explanation)
    - If correct: increment correct_answers counter
    - Show next question OR call show_results() if test complete

8️⃣  show_results() does:
    - Calculate percentage: (correct/total) * 100
    - Determine if passed (75%+) or not
    - If passed: grant XP via add_xp_to_user()
    - Show result message with final XP earned

🏁 User finishes test and gets XP!
    """)


def show_xp_calculation():
    """Show XP calculation examples."""
    print("\n" + "=" * 70)
    print("🏅 DEMO: РАСЧЁТ XP")
    print("=" * 70)
    
    scenarios = [
        {"correct": 3, "total": 3, "xp_reward": 50},
        {"correct": 2, "total": 3, "xp_reward": 50},
        {"correct": 1, "total": 3, "xp_reward": 50},
        {"correct": 2, "total": 4, "xp_reward": 60},
    ]
    
    for scenario in scenarios:
        correct = scenario["correct"]
        total = scenario["total"]
        xp_reward = scenario["xp_reward"]
        
        percentage = int((correct / total) * 100)
        
        if percentage >= 75:
            status = "🎉 ОТЛИЧНО!"
            xp_earned = xp_reward
        elif percentage >= 50:
            status = "👍 ХОРОШО!"
            xp_earned = int(xp_reward * 0.7)
        else:
            status = "❌ ЕЩЁ РАЗ"
            xp_earned = 0
        
        print(f"\n{status}")
        print(f"  Результат: {correct}/{total} ({percentage}%)")
        print(f"  Base XP: {xp_reward} | Earned: {xp_earned} XP")


if __name__ == "__main__":
    demo_quest_structure()
    demo_callback_parsing()
    demo_command_parsing()
    demo_test_flow()
    show_xp_calculation()
    
    print("\n" + "=" * 70)
    print("✅ DEMO COMPLETED")
    print("=" * 70)
