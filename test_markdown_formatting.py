#!/usr/bin/env python3
"""
Test markdown_to_html formatting function for Telegram bot.

Validates that Markdown formatting is properly converted to HTML
for better Telegram message readability.
"""

import sys
import re

sys.path.insert(0, '/home/sv4096/rvx_backend')

def test_markdown_to_html():
    """Test the markdown_to_html function"""
    
    # Import the function
    from bot import markdown_to_html
    
    test_cases = [
        # (input, expected_output, description)
        (
            "**Bitcoin** проживает коррекцию",
            "<b>Bitcoin</b> проживает коррекцию",
            "Bold text conversion"
        ),
        (
            "**ETF** одобрен, это __важно__",
            "<b>ETF</b> одобрен, это <u>важно</u>",
            "Bold and underline"
        ),
        (
            "~~Старая информация~~ Новая дата",
            "<s>Старая информация</s> Новая дата",
            "Strikethrough text"
        ),
        (
            "Посмотрите код: `while(true) { buy() }`",
            "Посмотрите код: <code>while(true) { buy() }</code>",
            "Code snippet"
        ),
        (
            "**Bitcoin** взлетел на **10%** за сутки",
            "<b>Bitcoin</b> взлетел на <b>10%</b> за сутки",
            "Multiple bold phrases"
        ),
        (
            "**Ключевые факты:**\n• __Цена__ выросла\n• ~~Прогноз~~ **Реальность**",
            "<b>Ключевые факты:</b>\n• <u>Цена</u> выросла\n• <s>Прогноз</s> <b>Реальность</b>",
            "Mixed formatting with newlines"
        ),
        (
            None,
            None,
            "None input"
        ),
        (
            "",
            "",
            "Empty string"
        ),
        (
            "Обычный текст без форматирования",
            "Обычный текст без форматирования",
            "Plain text without formatting"
        ),
        (
            "*курсив* текст",
            "<i>курсив</i> текст",
            "Italic text"
        ),
    ]
    
    passed = 0
    failed = 0
    
    print("=" * 80)
    print("TESTING markdown_to_html() FUNCTION")
    print("=" * 80 + "\n")
    
    for input_text, expected, description in test_cases:
        result = markdown_to_html(input_text)
        
        if result == expected:
            print(f"✅ PASS: {description}")
            print(f"   Input:    {repr(input_text)}")
            print(f"   Output:   {repr(result)}")
            passed += 1
        else:
            print(f"❌ FAIL: {description}")
            print(f"   Input:    {repr(input_text)}")
            print(f"   Expected: {repr(expected)}")
            print(f"   Got:      {repr(result)}")
            failed += 1
        print()
    
    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 80 + "\n")
    
    return failed == 0


def test_html_tag_safety():
    """Test that HTML conversion doesn't create malformed tags"""
    from bot import markdown_to_html
    
    test_cases = [
        "**Текст** с **множественным** форматированием",
        "**A** __B__ ~~C~~ `D` *E*",
        "**Bold at start** и в конце **Bold**",
        "Текст с `code` и **bold** вместе",
    ]
    
    print("=" * 80)
    print("TESTING HTML TAG SAFETY")
    print("=" * 80 + "\n")
    
    all_valid = True
    
    for text in test_cases:
        result = markdown_to_html(text)
        
        # Count opening and closing tags
        open_b = result.count("<b>")
        close_b = result.count("</b>")
        open_u = result.count("<u>")
        close_u = result.count("</u>")
        open_s = result.count("<s>")
        close_s = result.count("</s>")
        open_code = result.count("<code>")
        close_code = result.count("</code>")
        open_i = result.count("<i>")
        close_i = result.count("</i>")
        
        valid = (
            open_b == close_b and
            open_u == close_u and
            open_s == close_s and
            open_code == close_code and
            open_i == close_i
        )
        
        status = "✅" if valid else "❌"
        print(f"{status} {text}")
        print(f"   → {result}")
        
        if not valid:
            print(f"   Tag mismatch detected!")
            all_valid = False
        print()
    
    print("=" * 80)
    print(f"SAFETY CHECK: {'PASSED ✅' if all_valid else 'FAILED ❌'}")
    print("=" * 80 + "\n")
    
    return all_valid


def test_real_world_examples():
    """Test with real-world bot response examples"""
    from bot import markdown_to_html
    
    examples = [
        {
            "name": "News analysis response",
            "input": "**Bitcoin** достиг **$45,000** на фоне одобрения **ETF**. Это __очень позитивный__ сигнал для крипторынка.",
            "description": "Analysis with multiple bold terms and key facts"
        },
        {
            "name": "Educational content",
            "input": "**Что такое blockchain?** Это __распределённая__ система записи данных. Технология использует `hash` для защиты.",
            "description": "Educational message with terms and code"
        },
        {
            "name": "Price alert",
            "input": "🚨 **Внимание!** Цена **Ethereum** упала на **15%** - это возможность купить по `дешевой цене`.",
            "description": "Alert message with urgency markers"
        },
    ]
    
    print("=" * 80)
    print("TESTING REAL-WORLD EXAMPLES")
    print("=" * 80 + "\n")
    
    for example in examples:
        result = markdown_to_html(example["input"])
        
        print(f"📝 {example['name']}")
        print(f"   Description: {example['description']}")
        print(f"   Input:  {example['input']}")
        print(f"   Output: {result}")
        
        # Check that tags are balanced
        if result.count("<") == result.count(">"):
            print("   ✅ HTML tags balanced")
        else:
            print("   ❌ HTML tags NOT balanced")
        print()
    
    print("=" * 80 + "\n")
    return True


if __name__ == "__main__":
    print("\n")
    
    test1 = test_markdown_to_html()
    test2 = test_html_tag_safety()
    test3 = test_real_world_examples()
    
    if test1 and test2 and test3:
        print("✅ ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        sys.exit(1)
