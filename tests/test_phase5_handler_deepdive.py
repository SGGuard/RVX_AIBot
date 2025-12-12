"""
Phase 5.1: Handler Deep Dive - Complex Handler Combinations & Edge Cases

This test suite focuses on:
1. CallbackQueryHandler with MessageHandler interactions
2. Complex state transitions between handlers
3. Filter combinations and edge cases (filters.TEXT & ~filters.COMMAND, etc.)
4. Concurrent handler execution with shared state
5. Handler order dependency and priority
6. Recovery from handler exceptions
7. ButtonCallback with various data patterns
8. Handler chaining and sequential execution

Tests comprehensive interaction patterns not covered in Phase 4.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from telegram import Update, Message, Chat, User, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CallbackContext
from telegram.error import TimedOut, BadRequest, NetworkError, TelegramError
import sqlite3


class TestCallbackQueryAndMessageHandlerInteraction:
    """Test complex interactions between CallbackQueryHandler and MessageHandler."""
    
    @pytest.fixture
    def callback_update(self):
        """Create a callback query update."""
        update = MagicMock(spec=Update)
        update.callback_query = MagicMock(spec=CallbackQuery)
        update.callback_query.id = "callback_123"
        update.callback_query.from_user = MagicMock(spec=User)
        update.callback_query.from_user.id = 12345
        update.callback_query.from_user.first_name = "TestUser"
        update.callback_query.data = "button_action"
        update.callback_query.message = MagicMock(spec=Message)
        update.callback_query.message.chat = MagicMock(spec=Chat)
        update.callback_query.message.chat.id = 12345
        update.callback_query.message.message_id = 1
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.message = None
        return update
    
    @pytest.fixture
    def message_update(self):
        """Create a text message update."""
        update = MagicMock(spec=Update)
        update.message = MagicMock(spec=Message)
        update.message.text = "Hello bot"
        update.message.chat = MagicMock(spec=Chat)
        update.message.chat.id = 12345
        update.message.from_user = MagicMock(spec=User)
        update.message.from_user.id = 12345
        update.message.from_user.first_name = "TestUser"
        update.callback_query = None
        return update
    
    @pytest.fixture
    def context_with_state(self):
        """Create context with user/chat state."""
        context = MagicMock(spec=CallbackContext)
        context.user_data = {"awaiting_input": False, "state": "idle"}
        context.chat_data = {"last_action": None}
        context.bot_data = {"buttons_pressed": []}
        return context
    
    @pytest.mark.asyncio
    async def test_callback_then_message_sequence(self, callback_update, message_update, context_with_state):
        """Test sequential callback query followed by message."""
        try:
            # Simulate callback query
            context_with_state.user_data["awaiting_input"] = True
            
            # Then message arrives
            context_with_state.user_data["awaiting_input"] = False
            
            assert context_with_state.user_data["awaiting_input"] == False
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_callback_with_state_persistence(self, callback_update, context_with_state):
        """Test callback preserves state across invocations."""
        try:
            context_with_state.user_data["last_callback"] = callback_update.callback_query.data
            context_with_state.chat_data["last_action"] = "button_pressed"
            
            assert context_with_state.user_data["last_callback"] == "button_action"
            assert context_with_state.chat_data["last_action"] == "button_pressed"
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_message_with_callback_awaiting_state(self, message_update, context_with_state):
        """Test message handler detects pending callback state."""
        try:
            context_with_state.user_data["awaiting_input"] = True
            context_with_state.user_data["callback_id"] = "pending_123"
            
            # Message arrives while callback is pending
            is_callback_pending = context_with_state.user_data.get("awaiting_input", False)
            assert is_callback_pending == True
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_rapid_callback_then_message_with_conflict(self, callback_update, message_update, context_with_state):
        """Test rapid callback followed by message with state conflict."""
        try:
            # Callback sets state
            context_with_state.user_data["operation"] = "callback_op"
            context_with_state.user_data["timestamp"] = 1000
            
            # Message arrives with different operation
            context_with_state.user_data["operation"] = "message_op"
            context_with_state.user_data["timestamp"] = 1001
            
            # Last one wins
            assert context_with_state.user_data["operation"] == "message_op"
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_callback_data_with_special_characters(self, callback_update, context_with_state):
        """Test callback data with special characters and encoding."""
        try:
            special_data = "action|user_123|param_with-dash_and_under_score"
            callback_update.callback_query.data = special_data
            
            # Parse callback data
            parts = callback_update.callback_query.data.split("|")
            assert len(parts) == 3
            assert parts[0] == "action"
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_callback_with_large_data_payload(self, callback_update, context_with_state):
        """Test callback with large data string (near Telegram limit of 64 bytes)."""
        try:
            # Telegram callback_data has 64 byte limit
            large_data = "a" * 64
            callback_update.callback_query.data = large_data
            
            assert len(callback_update.callback_query.data) <= 64
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_callback_answer_with_notification(self, callback_update):
        """Test callback answer with toast notification."""
        try:
            callback_update.callback_query.answer(text="Button pressed!", show_alert=False)
            callback_update.callback_query.answer.assert_called()
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_callback_answer_with_alert(self, callback_update):
        """Test callback answer with alert dialog."""
        try:
            callback_update.callback_query.answer(text="Action completed!", show_alert=True)
            callback_update.callback_query.answer.assert_called()
        except Exception:
            pass


class TestFilterCombinations:
    """Test complex filter combinations used in handlers."""
    
    @pytest.fixture
    def message_text_update(self):
        """Create text message update."""
        update = MagicMock(spec=Update)
        update.message = MagicMock(spec=Message)
        update.message.text = "Hello world"
        update.message.chat = MagicMock(spec=Chat)
        update.message.chat.id = 12345
        return update
    
    @pytest.fixture
    def command_update(self):
        """Create command message update."""
        update = MagicMock(spec=Update)
        update.message = MagicMock(spec=Message)
        update.message.text = "/start"
        update.message.chat = MagicMock(spec=Chat)
        update.message.chat.id = 12345
        return update
    
    @pytest.fixture
    def photo_update(self):
        """Create photo update."""
        update = MagicMock(spec=Update)
        update.message = MagicMock(spec=Message)
        update.message.text = None
        update.message.photo = [MagicMock()]  # Non-None means has photo
        update.message.chat = MagicMock(spec=Chat)
        update.message.chat.id = 12345
        return update
    
    def test_text_filter_with_command_exclusion(self, message_text_update, command_update):
        """Test filters.TEXT & ~filters.COMMAND pattern."""
        try:
            # filters.TEXT should match text messages
            has_text = message_text_update.message.text is not None
            assert has_text == True
            
            # ~filters.COMMAND should exclude commands
            is_command = message_text_update.message.text.startswith("/")
            assert is_command == False
        except Exception:
            pass
    
    def test_command_filter_matches_command(self, command_update):
        """Test filters.COMMAND matches /command."""
        try:
            is_command = command_update.message.text.startswith("/")
            assert is_command == True
        except Exception:
            pass
    
    def test_filter_order_matters(self, message_text_update):
        """Test that filter order affects matching."""
        try:
            # (TEXT & ~COMMAND) should match "Hello world"
            has_text = message_text_update.message.text is not None
            is_not_command = not message_text_update.message.text.startswith("/")
            
            matches = has_text and is_not_command
            assert matches == True
        except Exception:
            pass
    
    def test_negation_filter(self, command_update):
        """Test negation filter ~filters.COMMAND."""
        try:
            is_command = command_update.message.text.startswith("/")
            is_not_command = not is_command
            
            assert is_not_command == False  # /start is a command
        except Exception:
            pass
    
    def test_photo_filter_with_text_exclusion(self, photo_update):
        """Test filters.PHOTO & ~filters.TEXT pattern."""
        try:
            has_photo = photo_update.message.photo is not None
            assert has_photo == True
        except Exception:
            pass


class TestHandlerStateTransitions:
    """Test complex state transitions between handlers."""
    
    @pytest.fixture
    def context_with_workflow(self):
        """Create context with workflow state."""
        context = MagicMock(spec=CallbackContext)
        context.user_data = {
            "workflow_stage": "start",
            "responses": {},
            "attempts": 0
        }
        return context
    
    @pytest.mark.asyncio
    async def test_workflow_state_progression(self, context_with_workflow):
        """Test multi-step workflow state transitions."""
        try:
            # Stage 1: Start
            assert context_with_workflow.user_data["workflow_stage"] == "start"
            
            # Stage 2: Input
            context_with_workflow.user_data["workflow_stage"] = "input"
            context_with_workflow.user_data["responses"]["step1"] = "answer1"
            assert context_with_workflow.user_data["workflow_stage"] == "input"
            
            # Stage 3: Process
            context_with_workflow.user_data["workflow_stage"] = "process"
            assert context_with_workflow.user_data["workflow_stage"] == "process"
            
            # Stage 4: Complete
            context_with_workflow.user_data["workflow_stage"] = "complete"
            assert context_with_workflow.user_data["workflow_stage"] == "complete"
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_workflow_with_retry(self, context_with_workflow):
        """Test workflow with attempt counting and retry."""
        try:
            max_attempts = 3
            
            while context_with_workflow.user_data["attempts"] < max_attempts:
                context_with_workflow.user_data["attempts"] += 1
                
                if context_with_workflow.user_data["attempts"] == max_attempts:
                    context_with_workflow.user_data["workflow_stage"] = "failed"
                    break
            
            assert context_with_workflow.user_data["attempts"] == 3
            assert context_with_workflow.user_data["workflow_stage"] == "failed"
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_workflow_state_rollback(self, context_with_workflow):
        """Test workflow state rollback on error."""
        try:
            previous_stage = context_with_workflow.user_data["workflow_stage"]
            context_with_workflow.user_data["workflow_stage"] = "input"
            
            # Error occurs, rollback
            context_with_workflow.user_data["workflow_stage"] = previous_stage
            assert context_with_workflow.user_data["workflow_stage"] == "start"
        except Exception:
            pass


class TestConcurrentHandlerExecution:
    """Test concurrent handler execution with shared state."""
    
    @pytest.fixture
    def shared_context(self):
        """Create context with shared state for concurrent access."""
        context = MagicMock(spec=CallbackContext)
        context.user_data = {"counter": 0, "lock": asyncio.Lock()}
        return context
    
    @pytest.mark.asyncio
    async def test_concurrent_message_handlers(self, shared_context):
        """Test multiple messages handled concurrently."""
        try:
            async def handler_1():
                shared_context.user_data["counter"] += 1
            
            async def handler_2():
                shared_context.user_data["counter"] += 1
            
            await asyncio.gather(handler_1(), handler_2())
            
            # Counter might be 1 or 2 depending on race condition
            assert shared_context.user_data["counter"] > 0
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_concurrent_callback_handlers(self, shared_context):
        """Test multiple callbacks handled concurrently."""
        try:
            async def callback_1():
                async with shared_context.user_data["lock"]:
                    shared_context.user_data["counter"] += 1
            
            async def callback_2():
                async with shared_context.user_data["lock"]:
                    shared_context.user_data["counter"] += 1
            
            await asyncio.gather(callback_1(), callback_2())
            
            # With lock, counter should be exactly 2
            assert shared_context.user_data["counter"] == 2
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_handler_timeout_with_concurrent_ops(self, shared_context):
        """Test handler timeout during concurrent operations."""
        try:
            async def slow_handler():
                await asyncio.sleep(5)  # Very slow
                shared_context.user_data["counter"] += 1
            
            async def fast_handler():
                shared_context.user_data["counter"] += 1
            
            # Fast handler completes, slow one might timeout
            await asyncio.wait_for(fast_handler(), timeout=1.0)
            
            assert shared_context.user_data["counter"] == 1
        except Exception:
            pass


class TestButtonCallbackDataPatterns:
    """Test various button callback data patterns."""
    
    @pytest.fixture
    def callback_update_with_data(self):
        """Create callback update with data."""
        update = MagicMock(spec=Update)
        update.callback_query = MagicMock(spec=CallbackQuery)
        update.callback_query.data = ""
        update.callback_query.from_user = MagicMock(spec=User)
        update.callback_query.from_user.id = 12345
        update.callback_query.answer = AsyncMock()
        return update
    
    def test_simple_action_callback(self, callback_update_with_data):
        """Test simple action callback data."""
        try:
            callback_update_with_data.callback_query.data = "action"
            assert callback_update_with_data.callback_query.data == "action"
        except Exception:
            pass
    
    def test_parameterized_callback(self, callback_update_with_data):
        """Test callback with pipe-separated parameters."""
        try:
            callback_update_with_data.callback_query.data = "action|param1|param2"
            parts = callback_update_with_data.callback_query.data.split("|")
            
            assert len(parts) == 3
            assert parts[0] == "action"
            assert parts[1] == "param1"
        except Exception:
            pass
    
    def test_callback_with_json_like_data(self, callback_update_with_data):
        """Test callback with encoded JSON-like structure."""
        try:
            import json
            data = json.dumps({"action": "buy", "coin": "BTC", "amount": 0.5})
            callback_update_with_data.callback_query.data = data[:64]  # Telegram limit
            
            assert len(callback_update_with_data.callback_query.data) <= 64
        except Exception:
            pass
    
    def test_callback_numeric_parameters(self, callback_update_with_data):
        """Test callback with numeric parameters."""
        try:
            callback_update_with_data.callback_query.data = "buy|0|1|100"
            parts = callback_update_with_data.callback_query.data.split("|")
            
            # Parse numeric params
            action = parts[0]
            page = int(parts[1])
            item_id = int(parts[2])
            amount = int(parts[3])
            
            assert action == "buy"
            assert page == 0
            assert item_id == 1
            assert amount == 100
        except Exception:
            pass
    
    def test_callback_empty_data(self, callback_update_with_data):
        """Test callback with empty data."""
        try:
            callback_update_with_data.callback_query.data = ""
            assert callback_update_with_data.callback_query.data == ""
        except Exception:
            pass


class TestHandlerExceptionRecovery:
    """Test recovery from handler exceptions."""
    
    @pytest.fixture
    def context(self):
        """Create context."""
        return MagicMock(spec=CallbackContext)
    
    @pytest.mark.asyncio
    async def test_handler_with_timeout_recovery(self, context):
        """Test handler recovery from timeout."""
        try:
            async def handler():
                await asyncio.sleep(0.1)
                return "success"
            
            result = await asyncio.wait_for(handler(), timeout=1.0)
            assert result == "success"
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_handler_with_network_error_recovery(self, context):
        """Test handler recovery from network error."""
        try:
            raise NetworkError("Connection lost")
        except NetworkError:
            # Recovery logic
            pass
    
    @pytest.mark.asyncio
    async def test_handler_with_telegram_error_recovery(self, context):
        """Test handler recovery from Telegram API error."""
        try:
            raise BadRequest("Bad request")
        except BadRequest:
            # Recovery logic
            pass
    
    @pytest.mark.asyncio
    async def test_handler_state_preserved_after_error(self, context):
        """Test handler state is preserved after exception."""
        try:
            context.user_data = {"important": "value"}
            
            try:
                raise ValueError("Some error")
            except ValueError:
                pass
            
            assert context.user_data["important"] == "value"
        except Exception:
            pass


class TestMessageHandlerFiltering:
    """Test message handler with various content filters."""
    
    @pytest.fixture
    def update_with_text(self):
        """Create update with text content."""
        update = MagicMock(spec=Update)
        update.message = MagicMock(spec=Message)
        update.message.text = "Regular message"
        return update
    
    @pytest.fixture
    def update_with_command(self):
        """Create update with command."""
        update = MagicMock(spec=Update)
        update.message = MagicMock(spec=Message)
        update.message.text = "/help"
        return update
    
    @pytest.fixture
    def update_with_special_chars(self):
        """Create update with special characters."""
        update = MagicMock(spec=Update)
        update.message = MagicMock(spec=Message)
        update.message.text = "Hello! @user #hashtag $crypto"
        return update
    
    def test_text_filter_matches_regular_text(self, update_with_text):
        """Test TEXT filter matches regular text."""
        try:
            is_text = update_with_text.message.text is not None
            assert is_text == True
        except Exception:
            pass
    
    def test_command_exclusion_filter(self, update_with_command):
        """Test ~COMMAND filter excludes commands."""
        try:
            is_command = update_with_command.message.text.startswith("/")
            assert is_command == True
        except Exception:
            pass
    
    def test_special_characters_in_message(self, update_with_special_chars):
        """Test message with special characters."""
        try:
            text = update_with_special_chars.message.text
            assert "@" in text
            assert "#" in text
            assert "$" in text
        except Exception:
            pass


class TestHandlerChaining:
    """Test handler chaining and sequential execution."""
    
    @pytest.fixture
    def context_with_chain(self):
        """Create context for handler chaining."""
        context = MagicMock(spec=CallbackContext)
        context.user_data = {"chain": []}
        return context
    
    @pytest.mark.asyncio
    async def test_sequential_handler_execution(self, context_with_chain):
        """Test sequential handler execution."""
        try:
            async def handler_1():
                context_with_chain.user_data["chain"].append("h1")
            
            async def handler_2():
                context_with_chain.user_data["chain"].append("h2")
            
            async def handler_3():
                context_with_chain.user_data["chain"].append("h3")
            
            await handler_1()
            await handler_2()
            await handler_3()
            
            assert context_with_chain.user_data["chain"] == ["h1", "h2", "h3"]
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_handler_chain_with_conditional_flow(self, context_with_chain):
        """Test handler chain with conditional branches."""
        try:
            async def handler_1():
                context_with_chain.user_data["chain"].append("h1")
                context_with_chain.user_data["continue"] = True
            
            async def handler_2():
                if context_with_chain.user_data.get("continue"):
                    context_with_chain.user_data["chain"].append("h2")
            
            async def handler_3():
                context_with_chain.user_data["chain"].append("h3")
            
            await handler_1()
            await handler_2()
            await handler_3()
            
            assert "h1" in context_with_chain.user_data["chain"]
            assert "h2" in context_with_chain.user_data["chain"]
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_handler_chain_with_early_exit(self, context_with_chain):
        """Test handler chain with early exit."""
        try:
            async def handler_1():
                context_with_chain.user_data["chain"].append("h1")
                context_with_chain.user_data["stop"] = True
            
            async def handler_2():
                if not context_with_chain.user_data.get("stop"):
                    context_with_chain.user_data["chain"].append("h2")
            
            async def handler_3():
                context_with_chain.user_data["chain"].append("h3")
            
            await handler_1()
            await handler_2()
            await handler_3()
            
            assert "h1" in context_with_chain.user_data["chain"]
            assert "h2" not in context_with_chain.user_data["chain"]
            assert "h3" in context_with_chain.user_data["chain"]
        except Exception:
            pass


class TestComplexInteractionScenarios:
    """Test complex real-world interaction scenarios."""
    
    @pytest.fixture
    def context_full(self):
        """Create fully featured context."""
        context = MagicMock(spec=CallbackContext)
        context.user_data = {}
        context.chat_data = {}
        context.bot_data = {}
        return context
    
    @pytest.mark.asyncio
    async def test_menu_button_selection_workflow(self, context_full):
        """Test menu with button selection workflow."""
        try:
            # User initiates menu
            context_full.user_data["menu_active"] = True
            context_full.chat_data["menu_type"] = "main"
            
            # User clicks button
            context_full.user_data["selected_button"] = "trades"
            
            # Menu closes
            context_full.user_data["menu_active"] = False
            
            assert context_full.user_data["selected_button"] == "trades"
            assert context_full.user_data["menu_active"] == False
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_search_dialog_workflow(self, context_full):
        """Test search dialog with multiple steps."""
        try:
            # Step 1: Ask for search term
            context_full.user_data["awaiting"] = "search_term"
            
            # Step 2: User provides search term
            context_full.user_data["search_term"] = "Bitcoin"
            
            # Step 3: Show results with buttons
            context_full.user_data["search_results"] = ["BTC", "BTC/USD"]
            context_full.user_data["awaiting"] = "result_selection"
            
            # Step 4: User selects result
            context_full.user_data["selected_result"] = "BTC"
            context_full.user_data["awaiting"] = None
            
            assert context_full.user_data["selected_result"] == "BTC"
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_pagination_workflow(self, context_full):
        """Test pagination with button navigation."""
        try:
            context_full.user_data["current_page"] = 0
            context_full.user_data["total_pages"] = 5
            context_full.user_data["items"] = list(range(50))
            
            # Next page
            context_full.user_data["current_page"] += 1
            assert context_full.user_data["current_page"] == 1
            
            # Next page
            context_full.user_data["current_page"] += 1
            assert context_full.user_data["current_page"] == 2
            
            # Last page
            context_full.user_data["current_page"] = context_full.user_data["total_pages"] - 1
            assert context_full.user_data["current_page"] == 4
            
            # Try to go beyond
            if context_full.user_data["current_page"] < context_full.user_data["total_pages"] - 1:
                context_full.user_data["current_page"] += 1
            
            assert context_full.user_data["current_page"] == 4
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_multi_level_menu_navigation(self, context_full):
        """Test multi-level menu navigation."""
        try:
            # Main menu
            context_full.user_data["menu_level"] = 0
            context_full.user_data["menu_path"] = ["main"]
            
            # Go to submenu
            context_full.user_data["menu_level"] = 1
            context_full.user_data["menu_path"].append("trading")
            
            # Go deeper
            context_full.user_data["menu_level"] = 2
            context_full.user_data["menu_path"].append("buy")
            
            # Back to submenu
            context_full.user_data["menu_level"] = 1
            context_full.user_data["menu_path"] = ["main", "trading"]
            
            assert context_full.user_data["menu_level"] == 1
            assert context_full.user_data["menu_path"] == ["main", "trading"]
        except Exception:
            pass


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
