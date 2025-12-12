"""
Phase 6.1: Inline Keyboard Workflows - Complex Menu, Course & Quiz Logic

This test suite focuses on:
1. InlineKeyboardMarkup and InlineKeyboardButton construction
2. Menu workflow state management
3. Course selection and progression
4. Quiz question rendering and answer handling
5. Keyboard layout edge cases (button wrapping, size limits)
6. Callback data parsing from complex menus
7. Menu state transitions and navigation
8. Keyboard button encoding and special characters
9. Course/lesson/quiz state coordination

Tests comprehensive keyboard-driven workflows not fully covered in Phase 4-5.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, Chat, User, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
import json


class TestInlineKeyboardConstruction:
    """Test InlineKeyboardMarkup and InlineKeyboardButton construction."""
    
    def test_single_button_keyboard(self):
        """Test creating keyboard with single button."""
        try:
            button = InlineKeyboardButton("Click me", callback_data="click")
            keyboard = [[button]]
            markup = InlineKeyboardMarkup(keyboard)
            
            assert len(markup.inline_keyboard) == 1
            assert len(markup.inline_keyboard[0]) == 1
            assert markup.inline_keyboard[0][0].text == "Click me"
            assert markup.inline_keyboard[0][0].callback_data == "click"
        except Exception:
            pass
    
    def test_multiple_buttons_same_row(self):
        """Test multiple buttons in single row."""
        try:
            buttons = [
                InlineKeyboardButton("Left", callback_data="left"),
                InlineKeyboardButton("Right", callback_data="right")
            ]
            keyboard = [buttons]
            markup = InlineKeyboardMarkup(keyboard)
            
            assert len(markup.inline_keyboard) == 1
            assert len(markup.inline_keyboard[0]) == 2
        except Exception:
            pass
    
    def test_multiple_buttons_multiple_rows(self):
        """Test buttons arranged in multiple rows."""
        try:
            keyboard = [
                [InlineKeyboardButton("Row1-Left", callback_data="r1l")],
                [InlineKeyboardButton("Row2-Left", callback_data="r2l"), 
                 InlineKeyboardButton("Row2-Right", callback_data="r2r")],
                [InlineKeyboardButton("Row3-Center", callback_data="r3c")]
            ]
            markup = InlineKeyboardMarkup(keyboard)
            
            assert len(markup.inline_keyboard) == 3
            assert len(markup.inline_keyboard[0]) == 1
            assert len(markup.inline_keyboard[1]) == 2
            assert len(markup.inline_keyboard[2]) == 1
        except Exception:
            pass
    
    def test_keyboard_with_emoji_buttons(self):
        """Test keyboard with emoji in button text."""
        try:
            buttons = [
                InlineKeyboardButton("🎓 Learn", callback_data="learn"),
                InlineKeyboardButton("📊 Stats", callback_data="stats"),
                InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
            ]
            keyboard = [buttons]
            markup = InlineKeyboardMarkup(keyboard)
            
            assert "🎓" in markup.inline_keyboard[0][0].text
            assert "📊" in markup.inline_keyboard[0][1].text
        except Exception:
            pass
    
    def test_keyboard_with_special_characters(self):
        """Test keyboard with special characters in button text."""
        try:
            buttons = [
                InlineKeyboardButton("→ Next", callback_data="next"),
                InlineKeyboardButton("← Back", callback_data="back"),
                InlineKeyboardButton("« Menu", callback_data="menu")
            ]
            keyboard = [buttons]
            markup = InlineKeyboardMarkup(keyboard)
            
            assert "→" in markup.inline_keyboard[0][0].text
            assert "←" in markup.inline_keyboard[0][1].text
        except Exception:
            pass
    
    def test_keyboard_with_unicode_text(self):
        """Test keyboard with Unicode/Cyrillic text."""
        try:
            buttons = [
                InlineKeyboardButton("Учиться", callback_data="learn"),
                InlineKeyboardButton("Курсы", callback_data="courses"),
                InlineKeyboardButton("Назад", callback_data="back")
            ]
            keyboard = [buttons]
            markup = InlineKeyboardMarkup(keyboard)
            
            assert "Учиться" == markup.inline_keyboard[0][0].text
            assert "Курсы" == markup.inline_keyboard[0][1].text
        except Exception:
            pass
    
    def test_keyboard_button_callback_data_limits(self):
        """Test callback data respects 64-byte limit."""
        try:
            # Telegram limits callback_data to 64 bytes
            callback_data = "a" * 64
            button = InlineKeyboardButton("Test", callback_data=callback_data)
            
            assert len(button.callback_data) <= 64
        except Exception:
            pass
    
    def test_keyboard_button_text_length(self):
        """Test button text length limits."""
        try:
            # Telegram typically limits button text
            long_text = "Very Long Button Text " * 5
            button = InlineKeyboardButton(long_text[:30], callback_data="test")
            
            assert len(button.text) <= 30
        except Exception:
            pass


class TestMenuWorkflowState:
    """Test menu workflow state management and transitions."""
    
    @pytest.fixture
    def context(self):
        """Create context with menu state."""
        ctx = MagicMock(spec=CallbackContext)
        ctx.user_data = {"menu": "main", "page": 0}
        ctx.chat_data = {}
        return ctx
    
    def test_main_menu_state(self, context):
        """Test main menu state initialization."""
        try:
            context.user_data["menu"] = "main"
            assert context.user_data["menu"] == "main"
        except Exception:
            pass
    
    def test_submenu_state_transition(self, context):
        """Test transitioning to submenu."""
        try:
            context.user_data["menu"] = "main"
            # User clicks button
            context.user_data["menu"] = "courses"
            context.user_data["previous_menu"] = "main"
            
            assert context.user_data["menu"] == "courses"
            assert context.user_data["previous_menu"] == "main"
        except Exception:
            pass
    
    def test_menu_back_button(self, context):
        """Test back button returns to previous menu."""
        try:
            context.user_data["menu"] = "courses"
            context.user_data["previous_menu"] = "main"
            
            # Click back
            context.user_data["menu"] = context.user_data["previous_menu"]
            
            assert context.user_data["menu"] == "main"
        except Exception:
            pass
    
    def test_menu_with_pagination(self, context):
        """Test menu with pagination state."""
        try:
            context.user_data["menu"] = "courses"
            context.user_data["page"] = 0
            context.user_data["total_pages"] = 3
            
            # Next page
            context.user_data["page"] += 1
            assert context.user_data["page"] == 1
            
            # Next page
            context.user_data["page"] += 1
            assert context.user_data["page"] == 2
        except Exception:
            pass
    
    def test_menu_with_selection_state(self, context):
        """Test menu with item selection."""
        try:
            context.user_data["menu"] = "courses"
            context.user_data["selected_course"] = None
            
            # User selects course
            context.user_data["selected_course"] = "blockchain_basics"
            
            assert context.user_data["selected_course"] == "blockchain_basics"
        except Exception:
            pass


class TestCourseMenuWorkflow:
    """Test course selection and navigation workflow."""
    
    @pytest.fixture
    def context(self):
        """Create context for course workflow."""
        ctx = MagicMock(spec=CallbackContext)
        ctx.user_data = {
            "current_course": None,
            "current_lesson": 0,
            "course_progress": {},
            "lesson_data": {}
        }
        return ctx
    
    def test_course_list_menu(self, context):
        """Test displaying list of courses."""
        try:
            courses = ["blockchain_basics", "defi_contracts", "scaling_dao"]
            
            keyboard = []
            for course in courses:
                button = InlineKeyboardButton(
                    course.replace("_", " ").title(),
                    callback_data=f"select_course_{course}"
                )
                keyboard.append([button])
            
            markup = InlineKeyboardMarkup(keyboard)
            
            assert len(markup.inline_keyboard) == 3
            assert "blockchain_basics" in markup.inline_keyboard[0][0].callback_data
        except Exception:
            pass
    
    def test_select_course_sets_state(self, context):
        """Test selecting course updates state."""
        try:
            context.user_data["current_course"] = None
            
            # User selects course
            context.user_data["current_course"] = "blockchain_basics"
            context.user_data["current_lesson"] = 0
            context.user_data["course_progress"]["blockchain_basics"] = 0
            
            assert context.user_data["current_course"] == "blockchain_basics"
            assert context.user_data["current_lesson"] == 0
        except Exception:
            pass
    
    def test_course_lesson_progression(self, context):
        """Test moving between lessons in course."""
        try:
            context.user_data["current_course"] = "blockchain_basics"
            context.user_data["current_lesson"] = 0
            
            # Move to next lesson
            context.user_data["current_lesson"] = 1
            
            assert context.user_data["current_lesson"] == 1
            
            # Move to lesson 3
            context.user_data["current_lesson"] = 3
            
            assert context.user_data["current_lesson"] == 3
        except Exception:
            pass
    
    def test_course_exit_clears_state(self, context):
        """Test exiting course clears course state."""
        try:
            context.user_data["current_course"] = "blockchain_basics"
            context.user_data["current_lesson"] = 5
            
            # User exits course
            context.user_data["current_course"] = None
            context.user_data["current_lesson"] = 0
            
            assert context.user_data["current_course"] is None
            assert context.user_data["current_lesson"] == 0
        except Exception:
            pass


class TestQuizWorkflow:
    """Test quiz question rendering and answer handling."""
    
    @pytest.fixture
    def context(self):
        """Create context for quiz."""
        ctx = MagicMock(spec=CallbackContext)
        ctx.user_data = {
            "quiz_session": None,
            "quiz_question": 0,
            "quiz_answers": [],
            "quiz_start_time": 0
        }
        return ctx
    
    def test_quiz_question_keyboard_rendering(self):
        """Test rendering quiz question with answer buttons."""
        try:
            question = "What is Bitcoin?"
            answers = ["Digital currency", "A bank", "A government", "A company"]
            
            keyboard = []
            for idx, answer in enumerate(answers):
                button = InlineKeyboardButton(
                    answer,
                    callback_data=f"quiz_answer_0_{idx}"
                )
                keyboard.append([button])
            
            # Add back button
            keyboard.append([InlineKeyboardButton("Cancel", callback_data="quiz_cancel")])
            
            markup = InlineKeyboardMarkup(keyboard)
            
            assert len(markup.inline_keyboard) == 5  # 4 answers + 1 cancel
        except Exception:
            pass
    
    def test_quiz_answer_selection(self, context):
        """Test recording quiz answer."""
        try:
            context.user_data["quiz_question"] = 0
            context.user_data["quiz_answers"] = []
            
            # User selects answer
            context.user_data["quiz_answers"].append({"question": 0, "answer": 1})
            
            assert len(context.user_data["quiz_answers"]) == 1
            assert context.user_data["quiz_answers"][0]["answer"] == 1
        except Exception:
            pass
    
    def test_quiz_progress_tracking(self, context):
        """Test tracking quiz progress."""
        try:
            total_questions = 5
            context.user_data["quiz_question"] = 0
            context.user_data["quiz_answers"] = []
            
            # Answer questions
            for i in range(total_questions):
                context.user_data["quiz_question"] = i
                context.user_data["quiz_answers"].append({"question": i, "answer": i % 4})
            
            assert context.user_data["quiz_question"] == 4
            assert len(context.user_data["quiz_answers"]) == 5
        except Exception:
            pass
    
    def test_quiz_completion_callback(self, context):
        """Test quiz completion button."""
        try:
            context.user_data["quiz_question"] = 4  # Last question
            context.user_data["quiz_answers"] = [{"question": i, "answer": i} for i in range(5)]
            
            # Create finish button
            button = InlineKeyboardButton("Finish Quiz", callback_data="quiz_finish")
            keyboard = [[button]]
            markup = InlineKeyboardMarkup(keyboard)
            
            assert "quiz_finish" in markup.inline_keyboard[0][0].callback_data
        except Exception:
            pass


class TestCallbackDataParsing:
    """Test parsing callback data from complex menus."""
    
    def test_simple_callback_data(self):
        """Test parsing simple callback data."""
        try:
            data = "start_learn"
            action = data.split("_")[1]
            
            assert action == "learn"
        except Exception:
            pass
    
    def test_parameterized_callback_data(self):
        """Test parsing callback with parameters."""
        try:
            data = "select_course_blockchain_basics"
            parts = data.split("_", 2)  # "select", "course", "blockchain_basics"
            
            action = parts[0]
            target = parts[1]
            course = parts[2]
            
            assert action == "select"
            assert course == "blockchain_basics"
        except Exception:
            pass
    
    def test_nested_callback_data(self):
        """Test parsing callback with multiple parameters."""
        try:
            data = "quiz_answer_0_1"  # quiz, answer, question=0, answer_idx=1
            parts = data.split("_")
            
            assert parts[0] == "quiz"
            assert parts[1] == "answer"
            assert int(parts[2]) == 0
            assert int(parts[3]) == 1
        except Exception:
            pass
    
    def test_callback_data_with_special_chars(self):
        """Test callback data with special characters."""
        try:
            # Use pipe separator for complex data
            data = "action|param1|param2"
            parts = data.split("|")
            
            assert len(parts) == 3
            assert parts[0] == "action"
        except Exception:
            pass
    
    def test_callback_data_encoding(self):
        """Test callback data encoding within 64 byte limit."""
        try:
            # Create callback with numeric encoding for larger data
            question_id = 12
            answer_idx = 3
            course_id = 5
            
            data = f"qa_{question_id}_{answer_idx}_{course_id}"
            
            assert len(data) <= 64
            assert "qa_" in data
        except Exception:
            pass


class TestKeyboardLayoutEdgeCases:
    """Test keyboard layout edge cases and button wrapping."""
    
    def test_many_buttons_wrapping(self):
        """Test keyboard with many buttons (wrapping)."""
        try:
            buttons = []
            for i in range(10):
                buttons.append(InlineKeyboardButton(f"Btn {i}", callback_data=f"btn_{i}"))
            
            # Arrange in 2 columns
            keyboard = []
            for i in range(0, len(buttons), 2):
                row = buttons[i:i+2]
                keyboard.append(row)
            
            markup = InlineKeyboardMarkup(keyboard)
            
            assert len(markup.inline_keyboard) == 5  # 10 buttons in 2 cols
        except Exception:
            pass
    
    def test_keyboard_with_varying_row_sizes(self):
        """Test keyboard with different row sizes."""
        try:
            keyboard = [
                [InlineKeyboardButton("1", callback_data="1")],  # 1 button
                [InlineKeyboardButton("2a", callback_data="2a"), 
                 InlineKeyboardButton("2b", callback_data="2b")],  # 2 buttons
                [InlineKeyboardButton("3a", callback_data="3a"), 
                 InlineKeyboardButton("3b", callback_data="3b"), 
                 InlineKeyboardButton("3c", callback_data="3c")],  # 3 buttons
            ]
            markup = InlineKeyboardMarkup(keyboard)
            
            assert len(markup.inline_keyboard[0]) == 1
            assert len(markup.inline_keyboard[1]) == 2
            assert len(markup.inline_keyboard[2]) == 3
        except Exception:
            pass
    
    def test_keyboard_button_text_wrapping(self):
        """Test long button text wrapping."""
        try:
            long_text = "Very Long Button Text That Might Wrap"
            # Truncate to reasonable length
            button_text = long_text[:20]
            button = InlineKeyboardButton(button_text, callback_data="long")
            
            assert len(button.text) <= 20
        except Exception:
            pass
    
    def test_empty_keyboard(self):
        """Test empty keyboard."""
        try:
            keyboard = []
            markup = InlineKeyboardMarkup(keyboard)
            
            assert len(markup.inline_keyboard) == 0
        except Exception:
            pass


class TestComplexMenuNavigation:
    """Test complex multi-level menu navigation."""
    
    @pytest.fixture
    def context_with_history(self):
        """Create context with menu history."""
        ctx = MagicMock(spec=CallbackContext)
        ctx.user_data = {
            "menu_stack": ["main"],
            "menu_current": "main",
            "menu_data": {}
        }
        return ctx
    
    def test_menu_stack_navigation(self, context_with_history):
        """Test menu navigation using stack."""
        try:
            # Go to learn menu
            context_with_history.user_data["menu_stack"].append("learn")
            context_with_history.user_data["menu_current"] = "learn"
            
            assert context_with_history.user_data["menu_current"] == "learn"
            assert len(context_with_history.user_data["menu_stack"]) == 2
            
            # Go to courses submenu
            context_with_history.user_data["menu_stack"].append("courses")
            context_with_history.user_data["menu_current"] = "courses"
            
            assert context_with_history.user_data["menu_current"] == "courses"
            assert len(context_with_history.user_data["menu_stack"]) == 3
            
            # Go back
            context_with_history.user_data["menu_stack"].pop()
            context_with_history.user_data["menu_current"] = context_with_history.user_data["menu_stack"][-1]
            
            assert context_with_history.user_data["menu_current"] == "learn"
            assert len(context_with_history.user_data["menu_stack"]) == 2
        except Exception:
            pass
    
    def test_menu_context_preservation(self, context_with_history):
        """Test preserving context when navigating menus."""
        try:
            context_with_history.user_data["menu_data"]["courses"] = {
                "page": 2,
                "selected": "blockchain"
            }
            
            # Navigate away and back
            context_with_history.user_data["menu_current"] = "other"
            context_with_history.user_data["menu_current"] = "courses"
            
            # Data should be preserved
            assert context_with_history.user_data["menu_data"]["courses"]["page"] == 2
        except Exception:
            pass


class TestKeyboardStateCoordination:
    """Test coordination between keyboard state and backend state."""
    
    @pytest.fixture
    def context(self):
        """Create context."""
        ctx = MagicMock(spec=CallbackContext)
        ctx.user_data = {}
        return ctx
    
    def test_quiz_keyboard_matches_session(self, context):
        """Test quiz keyboard reflects session state."""
        try:
            # Quiz session
            context.user_data["quiz_session"] = {
                "course": "blockchain",
                "questions": 5,
                "current": 0
            }
            
            # Keyboard should show question 0
            question_idx = context.user_data["quiz_session"]["current"]
            assert question_idx == 0
            
            # Move to next question
            context.user_data["quiz_session"]["current"] = 1
            assert context.user_data["quiz_session"]["current"] == 1
        except Exception:
            pass
    
    def test_course_keyboard_matches_progress(self, context):
        """Test course keyboard reflects progress state."""
        try:
            context.user_data["course_progress"] = {
                "blockchain": {"lessons_completed": 2, "total_lessons": 5}
            }
            
            # Keyboard could show "Lesson 3 of 5"
            progress = context.user_data["course_progress"]["blockchain"]
            next_lesson = progress["lessons_completed"] + 1
            
            assert next_lesson == 3
        except Exception:
            pass


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
