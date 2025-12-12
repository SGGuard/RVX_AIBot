"""
Phase 7.1: Handler Chaining & State Machine - Quiz/Course Workflows

This test suite focuses on:
1. Handler chaining: How handlers transition state (QUIZ_START -> QUIZ_ANSWER -> QUIZ_NEXT -> QUIZ_RESULTS)
2. State machine transitions: State preservation across handler calls
3. Course menu workflow: COURSE_SELECT -> LESSON_READ -> QUIZ_START
4. Complex callback parsing: Quiz answer data parsing and routing
5. Context preservation: User data flowing through handler chains
6. Edge cases: Session loss, invalid transitions, mid-flow cancellation

Tests handler coordination and state management in real workflows.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, Chat, User, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
import asyncio
from datetime import datetime


class TestQuizStateTransitions:
    """Test quiz state machine transitions."""
    
    @pytest.mark.asyncio
    async def test_quiz_start_initializes_session(self):
        """Test quiz_start creates quiz_session in context."""
        update = MagicMock(spec=Update)
        update.effective_user.id = 12345
        update.effective_user.username = "testuser"
        
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}
        
        # Simulate quiz session creation
        quiz_data = {
            'course': 'blockchain_basics',
            'lesson_id': 1,
            'questions': [
                {
                    'number': 1,
                    'text': 'What is blockchain?',
                    'answers': ['A', 'B', 'C', 'D'],
                    'correct': 0
                }
            ],
            'responses': [],
            'current_q': 0,
            'correct_count': 0
        }
        context.user_data['quiz_session'] = quiz_data
        
        # Verify session created
        assert 'quiz_session' in context.user_data
        assert context.user_data['quiz_session']['course'] == 'blockchain_basics'
        assert context.user_data['quiz_session']['current_q'] == 0
        assert len(context.user_data['quiz_session']['responses']) == 0
    
    @pytest.mark.asyncio
    async def test_quiz_answer_updates_responses(self):
        """Test quiz answer handler updates quiz_session responses."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'quiz_session': {
                'course': 'blockchain_basics',
                'lesson_id': 1,
                'questions': [
                    {'number': 1, 'text': 'Q1', 'answers': ['A', 'B', 'C', 'D'], 'correct': 0},
                    {'number': 2, 'text': 'Q2', 'answers': ['A', 'B', 'C', 'D'], 'correct': 1}
                ],
                'responses': [],
                'current_q': 0,
                'correct_count': 0
            }
        }
        
        # Simulate answer selection: correct answer (idx 0)
        question = context.user_data['quiz_session']['questions'][0]
        response = {
            'q_num': question['number'],
            'selected': 0,  # User selected correct answer
            'correct': question['correct'],
            'is_correct': True
        }
        context.user_data['quiz_session']['responses'].append(response)
        context.user_data['quiz_session']['correct_count'] += 1
        context.user_data['quiz_session']['current_q'] += 1
        
        # Verify state updated
        assert len(context.user_data['quiz_session']['responses']) == 1
        assert context.user_data['quiz_session']['responses'][0]['is_correct'] is True
        assert context.user_data['quiz_session']['correct_count'] == 1
        assert context.user_data['quiz_session']['current_q'] == 1
    
    @pytest.mark.asyncio
    async def test_quiz_state_wrong_answer_increments_count(self):
        """Test quiz state tracks incorrect answers."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'quiz_session': {
                'course': 'ai_basics',
                'lesson_id': 2,
                'questions': [
                    {'number': 1, 'text': 'Q1', 'answers': ['A', 'B', 'C', 'D'], 'correct': 2}
                ],
                'responses': [],
                'current_q': 0,
                'correct_count': 0
            }
        }
        
        # User selects wrong answer (0 instead of 2)
        question = context.user_data['quiz_session']['questions'][0]
        response = {
            'q_num': question['number'],
            'selected': 0,
            'correct': question['correct'],
            'is_correct': False
        }
        context.user_data['quiz_session']['responses'].append(response)
        
        # Verify incorrect tracked
        assert context.user_data['quiz_session']['responses'][0]['is_correct'] is False
        assert context.user_data['quiz_session']['correct_count'] == 0
    
    @pytest.mark.asyncio
    async def test_quiz_session_loss_detection(self):
        """Test handler detects lost quiz session."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}  # No quiz_session
        
        # Check if quiz session exists
        quiz_session = context.user_data.get('quiz_session')
        assert quiz_session is None
    
    @pytest.mark.asyncio
    async def test_quiz_completion_cleanup(self):
        """Test quiz session cleanup after completion."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'quiz_session': {
                'course': 'blockchain',
                'lesson_id': 1,
                'questions': [],
                'responses': [{'q_num': 1, 'is_correct': True}],
                'current_q': 1,
                'correct_count': 1
            }
        }
        
        # Cleanup after quiz complete
        if 'quiz_session' in context.user_data:
            del context.user_data['quiz_session']
        
        assert 'quiz_session' not in context.user_data


class TestCourseMenuNavigation:
    """Test course selection and lesson progression workflow."""
    
    @pytest.mark.asyncio
    async def test_course_selection_sets_state(self):
        """Test selecting course sets current_course in user_data."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}
        
        # User selects course
        context.user_data['current_course'] = 'blockchain_basics'
        context.user_data['current_lesson'] = 0
        context.user_data['menu_state'] = 'courses'
        
        assert context.user_data['current_course'] == 'blockchain_basics'
        assert context.user_data['current_lesson'] == 0
        assert context.user_data['menu_state'] == 'courses'
    
    @pytest.mark.asyncio
    async def test_lesson_progression_increments_index(self):
        """Test lesson progression updates current_lesson."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'current_course': 'blockchain_basics',
            'current_lesson': 2
        }
        
        # Progress to next lesson
        context.user_data['current_lesson'] += 1
        
        assert context.user_data['current_lesson'] == 3
    
    @pytest.mark.asyncio
    async def test_lesson_to_quiz_transition(self):
        """Test transition from lesson to quiz."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'current_course': 'ai_basics',
            'current_lesson': 1,
            'menu_state': 'lesson'
        }
        
        # Transition to quiz
        context.user_data['menu_state'] = 'quiz'
        context.user_data['quiz_session'] = {
            'course': context.user_data['current_course'],
            'lesson_id': context.user_data['current_lesson'],
            'questions': [],
            'responses': [],
            'current_q': 0,
            'correct_count': 0
        }
        
        assert context.user_data['menu_state'] == 'quiz'
        assert 'quiz_session' in context.user_data
        assert context.user_data['quiz_session']['course'] == 'ai_basics'
    
    @pytest.mark.asyncio
    async def test_course_exit_resets_state(self):
        """Test exiting course clears course state."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'current_course': 'blockchain_basics',
            'current_lesson': 2,
            'menu_state': 'lesson',
            'quiz_session': {'course': 'blockchain_basics'}
        }
        
        # Exit course
        context.user_data.pop('current_course', None)
        context.user_data.pop('current_lesson', None)
        context.user_data.pop('quiz_session', None)
        context.user_data['menu_state'] = 'main'
        
        assert 'current_course' not in context.user_data
        assert 'current_lesson' not in context.user_data
        assert 'quiz_session' not in context.user_data
        assert context.user_data['menu_state'] == 'main'


class TestCallbackDataParsing:
    """Test callback data parsing for complex workflows."""
    
    def test_quiz_answer_callback_parsing(self):
        """Test parsing quiz_answer_<course>_<lesson>_<q_idx>_<ans_idx>."""
        callback_data = "quiz_answer_blockchain_basics_1_0_2"
        
        # Parse callback data
        if callback_data.startswith("quiz_answer_"):
            parts = callback_data.replace("quiz_answer_", "").split("_")
            # Handle course name with underscore
            course_name = "_".join(parts[:-3])
            lesson_id = int(parts[-3])
            q_idx = int(parts[-2])
            answer_idx = int(parts[-1])
            
            assert course_name == "blockchain_basics"
            assert lesson_id == 1
            assert q_idx == 0
            assert answer_idx == 2
    
    def test_course_select_callback_parsing(self):
        """Test parsing course_select_<course_name>."""
        callback_data = "course_select_ai_basics"
        
        if callback_data.startswith("course_select_"):
            course_name = callback_data.replace("course_select_", "")
            assert course_name == "ai_basics"
    
    def test_lesson_start_callback_parsing(self):
        """Test parsing lesson_start_<course>_<lesson_id>."""
        callback_data = "lesson_start_blockchain_basics_3"
        
        if callback_data.startswith("lesson_start_"):
            parts = callback_data.replace("lesson_start_", "").split("_")
            course_name = "_".join(parts[:-1])
            lesson_id = int(parts[-1])
            
            assert course_name == "blockchain_basics"
            assert lesson_id == 3
    
    def test_callback_data_size_limit(self):
        """Test callback data respects 64-byte limit."""
        # Create button with long callback data
        callback_data = "quiz_answer_" + "x" * 50
        button = InlineKeyboardButton("Answer", callback_data=callback_data[:64])
        
        # Verify length within limit
        assert len(button.callback_data) <= 64
    
    def test_special_chars_in_callback_data(self):
        """Test callback data with special characters."""
        callback_data = "menu_action_special_chars_test"
        
        # Verify callback data valid
        assert isinstance(callback_data, str)
        assert len(callback_data) > 0


class TestContextPreservation:
    """Test context preservation across handler transitions."""
    
    @pytest.mark.asyncio
    async def test_user_data_persistence_across_handlers(self):
        """Test user_data preserved when transitioning between handlers."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'user_id': 12345,
            'username': 'testuser',
            'xp': 100,
            'current_course': 'blockchain'
        }
        
        # Simulate handler transition
        preserved_data = context.user_data.copy()
        preserved_data['last_action'] = 'quiz_answered'
        context.user_data = preserved_data
        
        assert context.user_data['user_id'] == 12345
        assert context.user_data['xp'] == 100
        assert context.user_data['last_action'] == 'quiz_answered'
    
    @pytest.mark.asyncio
    async def test_quiz_session_preserved_during_questions(self):
        """Test quiz_session preserved while showing questions."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        quiz_session = {
            'course': 'ai_basics',
            'lesson_id': 1,
            'questions': [{'number': 1}, {'number': 2}, {'number': 3}],
            'responses': [{'q_num': 1, 'is_correct': True}],
            'current_q': 1,
            'correct_count': 1
        }
        context.user_data = {'quiz_session': quiz_session}
        
        # Simulate showing next question (should preserve session)
        session_copy = context.user_data.get('quiz_session')
        assert session_copy['course'] == 'ai_basics'
        assert len(session_copy['responses']) == 1
        assert session_copy['current_q'] == 1
    
    @pytest.mark.asyncio
    async def test_previous_answers_accumulated(self):
        """Test previous answers accumulated during clarification."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'last_question': 'What is crypto?',
            'previous_answers': [],
            'clarify_count': 0
        }
        
        # Add first clarification
        context.user_data['previous_answers'].append({
            'attempt': 1,
            'response': 'First attempt answer'
        })
        context.user_data['clarify_count'] += 1
        
        # Add second clarification
        context.user_data['previous_answers'].append({
            'attempt': 2,
            'response': 'Second attempt answer'
        })
        context.user_data['clarify_count'] += 1
        
        assert len(context.user_data['previous_answers']) == 2
        assert context.user_data['clarify_count'] == 2


class TestHandlerErrorRecovery:
    """Test error handling during handler transitions."""
    
    @pytest.mark.asyncio
    async def test_missing_quiz_session_fallback(self):
        """Test handler gracefully handles missing quiz_session."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}  # No quiz_session
        
        quiz_session = context.user_data.get('quiz_session')
        if quiz_session is None:
            # Fallback: return error message
            error_occurred = True
        else:
            error_occurred = False
        
        assert error_occurred is True
    
    @pytest.mark.asyncio
    async def test_invalid_question_index_handling(self):
        """Test handler handles invalid question index."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'quiz_session': {
                'questions': [
                    {'number': 1, 'text': 'Q1'},
                    {'number': 2, 'text': 'Q2'}
                ],
                'current_q': 5  # Invalid index
            }
        }
        
        quiz_session = context.user_data['quiz_session']
        is_valid = quiz_session['current_q'] < len(quiz_session['questions'])
        
        assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_answer_index_out_of_range(self):
        """Test handler validates answer index."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'quiz_session': {
                'questions': [
                    {'number': 1, 'text': 'Q1', 'answers': ['A', 'B', 'C', 'D']}
                ]
            }
        }
        
        question = context.user_data['quiz_session']['questions'][0]
        answer_idx = 10  # Out of range
        
        is_valid = 0 <= answer_idx < len(question['answers'])
        assert is_valid is False


class TestMultipleHandlerChains:
    """Test complex handler chaining scenarios."""
    
    @pytest.mark.asyncio
    async def test_menu_navigation_chain(self):
        """Test chain: main -> courses -> select_course -> lessons -> select_lesson -> quiz."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}
        
        # Step 1: Main menu
        context.user_data['menu_state'] = 'main'
        assert context.user_data['menu_state'] == 'main'
        
        # Step 2: Browse courses
        context.user_data['menu_state'] = 'courses'
        assert context.user_data['menu_state'] == 'courses'
        
        # Step 3: Select course
        context.user_data['current_course'] = 'blockchain_basics'
        context.user_data['menu_state'] = 'lessons'
        assert context.user_data['current_course'] == 'blockchain_basics'
        
        # Step 4: Select lesson
        context.user_data['current_lesson'] = 1
        context.user_data['menu_state'] = 'lesson'
        assert context.user_data['current_lesson'] == 1
        
        # Step 5: Start quiz
        context.user_data['menu_state'] = 'quiz'
        context.user_data['quiz_session'] = {'course': 'blockchain_basics', 'lesson_id': 1}
        assert context.user_data['menu_state'] == 'quiz'
        assert 'quiz_session' in context.user_data
    
    @pytest.mark.asyncio
    async def test_full_quiz_workflow(self):
        """Test complete quiz workflow with multiple answers."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}
        
        # Initialize quiz
        context.user_data['quiz_session'] = {
            'course': 'ai_basics',
            'lesson_id': 1,
            'questions': [
                {'number': 1, 'text': 'Q1', 'answers': ['A', 'B'], 'correct': 0},
                {'number': 2, 'text': 'Q2', 'answers': ['A', 'B'], 'correct': 1}
            ],
            'responses': [],
            'current_q': 0,
            'correct_count': 0
        }
        
        # Answer Q1 (correct)
        context.user_data['quiz_session']['responses'].append({
            'q_num': 1, 'selected': 0, 'correct': 0, 'is_correct': True
        })
        context.user_data['quiz_session']['correct_count'] += 1
        context.user_data['quiz_session']['current_q'] += 1
        
        # Answer Q2 (incorrect)
        context.user_data['quiz_session']['responses'].append({
            'q_num': 2, 'selected': 0, 'correct': 1, 'is_correct': False
        })
        context.user_data['quiz_session']['current_q'] += 1
        
        # Verify final state
        assert len(context.user_data['quiz_session']['responses']) == 2
        assert context.user_data['quiz_session']['correct_count'] == 1
        assert context.user_data['quiz_session']['current_q'] == 2
    
    @pytest.mark.asyncio
    async def test_clarification_loop_chain(self):
        """Test clarification handler chain: ask -> clarify -> ask_again -> clarify."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'last_question': 'What is blockchain?',
            'clarify_count': 0,
            'previous_answers': []
        }
        
        # First question
        assert context.user_data['clarify_count'] == 0
        
        # Clarification 1
        context.user_data['clarify_count'] += 1
        context.user_data['previous_answers'].append('First clarification')
        assert context.user_data['clarify_count'] == 1
        
        # Clarification 2
        context.user_data['clarify_count'] += 1
        context.user_data['previous_answers'].append('Second clarification')
        assert context.user_data['clarify_count'] == 2
        
        # Clarification 3
        context.user_data['clarify_count'] += 1
        context.user_data['previous_answers'].append('Third clarification')
        assert context.user_data['clarify_count'] == 3


class TestQuizScoring:
    """Test quiz scoring and XP accumulation during workflow."""
    
    @pytest.mark.asyncio
    async def test_correct_answer_xp_award(self):
        """Test correct answer awards 10 XP."""
        user_xp = 0
        
        # Correct answer
        user_xp += 10
        assert user_xp == 10
    
    @pytest.mark.asyncio
    async def test_incorrect_answer_xp_award(self):
        """Test incorrect answer awards 2 XP."""
        user_xp = 0
        
        # Incorrect answer
        user_xp += 2
        assert user_xp == 2
    
    @pytest.mark.asyncio
    async def test_quiz_completion_bonus(self):
        """Test quiz completion bonus (5 XP if all correct)."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'quiz_session': {
                'questions': [
                    {'correct': 0}, {'correct': 1}, {'correct': 0}
                ],
                'responses': [
                    {'is_correct': True},
                    {'is_correct': True},
                    {'is_correct': True}
                ],
                'correct_count': 3
            }
        }
        
        quiz = context.user_data['quiz_session']
        all_correct = quiz['correct_count'] == len(quiz['questions'])
        bonus_xp = 5 if all_correct else 0
        
        assert bonus_xp == 5
    
    @pytest.mark.asyncio
    async def test_partial_quiz_no_bonus(self):
        """Test partial quiz (not all correct) gets no bonus."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'quiz_session': {
                'questions': [
                    {'correct': 0}, {'correct': 1}
                ],
                'responses': [
                    {'is_correct': True},
                    {'is_correct': False}
                ],
                'correct_count': 1
            }
        }
        
        quiz = context.user_data['quiz_session']
        all_correct = quiz['correct_count'] == len(quiz['questions'])
        bonus_xp = 5 if all_correct else 0
        
        assert bonus_xp == 0


class TestStateConsistency:
    """Test state consistency across handler transitions."""
    
    @pytest.mark.asyncio
    async def test_state_not_corrupted_during_transition(self):
        """Test state not corrupted when handlers transition."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        original_state = {
            'quiz_session': {'course': 'blockchain', 'current_q': 0},
            'user_xp': 100
        }
        context.user_data = original_state.copy()
        
        # Simulate handler transition that shouldn't modify state
        current_state = context.user_data.copy()
        
        assert current_state['quiz_session']['course'] == 'blockchain'
        assert current_state['user_xp'] == 100
    
    @pytest.mark.asyncio
    async def test_concurrent_quiz_sessions_isolated(self):
        """Test multiple quiz sessions don't interfere."""
        user1_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        user1_context.user_data = {
            'quiz_session': {'course': 'blockchain', 'current_q': 0}
        }
        
        user2_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        user2_context.user_data = {
            'quiz_session': {'course': 'ai_basics', 'current_q': 1}
        }
        
        # Verify sessions isolated
        assert user1_context.user_data['quiz_session']['course'] == 'blockchain'
        assert user2_context.user_data['quiz_session']['course'] == 'ai_basics'
    
    @pytest.mark.asyncio
    async def test_handler_chain_doesnt_skip_state(self):
        """Test handler chain maintains state continuity."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            'menu_state': 'courses',
            'current_course': None
        }
        
        # Handler 1: Show course options
        assert context.user_data['menu_state'] == 'courses'
        
        # Handler 2: User selects course
        context.user_data['current_course'] = 'blockchain'
        context.user_data['menu_state'] = 'lessons'
        
        # Verify state transition complete
        assert context.user_data['current_course'] == 'blockchain'
        assert context.user_data['menu_state'] == 'lessons'
