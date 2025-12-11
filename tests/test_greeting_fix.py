"""Test for greeting handling fix - ensures greetings are not sent to AI dialogue."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import analyze_message_context


def test_greeting_detection():
    """Test that greetings are correctly detected."""
    greetings = [
        "привет",
        "hello",
        "hi",
        "пока",
        "bye",
        "привееет",
        "yo",
        "хай"
    ]
    
    for greeting in greetings:
        context = analyze_message_context(greeting)
        assert context["type"] == "greeting", f"Failed to detect '{greeting}' as greeting"
        assert context["needs_crypto_analysis"] == False, f"Greeting '{greeting}' should not need analysis"
        print(f"✓ '{greeting}' correctly detected as greeting")


def test_info_request_detection():
    """Test that info requests are correctly detected."""
    info_requests = [
        "что ты умеешь",
        "кто ты",
        "возможности",
        "помощь",
        "команды"
    ]
    
    for req in info_requests:
        context = analyze_message_context(req)
        assert context["type"] == "info_request", f"Failed to detect '{req}' as info_request"
        assert context["needs_crypto_analysis"] == False, f"Info request '{req}' should not need analysis"
        print(f"✓ '{req}' correctly detected as info_request")


def test_casual_messages():
    """Test that casual messages don't trigger crypto analysis inappropriately."""
    casual_messages = [
        "как дела",
        "что нового",
        "спасибо"
    ]
    
    for msg in casual_messages:
        context = analyze_message_context(msg)
        # Should be classified as general or casual_chat, not greeting
        assert context["type"] != "greeting", f"'{msg}' should not be classified as greeting"
        print(f"✓ '{msg}' correctly classified as {context['type']}")


if __name__ == "__main__":
    print("Testing greeting detection...")
    test_greeting_detection()
    print("\nTesting info request detection...")
    test_info_request_detection()
    print("\nTesting casual messages...")
    test_casual_messages()
    print("\n✅ All tests passed!")
