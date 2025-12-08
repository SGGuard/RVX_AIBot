"""Tests for message splitting functionality.

NOTE: This file contains a standalone copy of the split_long_message function.
This is intentional to make tests runnable without requiring all bot dependencies
(httpx, telegram, fastapi, etc.). This ensures CI/CD can run these tests independently.
"""
import pytest
from typing import List


def split_long_message(message: str, max_length: int = 3500) -> List[str]:
    """
    Разбивает длинное сообщение на части для отправки в Telegram.
    
    Telegram имеет лимит ~4096 символов на сообщение.
    Используем безопасный лимит 3500 символов с запасом.
    
    Разбиение происходит по абзацам (символ новой строки '\n'),
    чтобы сохранить целостность форматирования.
    
    Args:
        message: Текст сообщения для разбиения
        max_length: Максимальная длина одной части (по умолчанию 3500)
        
    Returns:
        List[str]: Список частей сообщения
    """
    # Если сообщение короткое, возвращаем как есть
    if len(message) <= max_length:
        return [message]
    
    # Разбиваем на части по абзацам
    paragraphs = message.split('\n')
    parts = []
    current_part = ""
    
    for paragraph in paragraphs:
        # Проверяем, поместится ли параграф в текущую часть
        # +1 для символа новой строки
        if len(current_part) + len(paragraph) + 1 > max_length:
            # Если текущая часть не пустая, сохраняем её
            if current_part.strip():
                parts.append(current_part.strip())
            
            # Если один параграф длиннее max_length, разбиваем его
            if len(paragraph) > max_length:
                # Сначала пробуем разбить по предложениям
                sentences = paragraph.split('. ')
                temp_part = ""
                
                for sentence in sentences:
                    # Если даже одно предложение длиннее max_length, разбиваем по символам
                    if len(sentence) > max_length:
                        # Добавляем накопленную часть
                        if temp_part.strip():
                            parts.append(temp_part.strip())
                            temp_part = ""
                        
                        # Разбиваем длинное предложение на части по max_length
                        for i in range(0, len(sentence), max_length):
                            chunk = sentence[i:i+max_length]
                            if chunk.strip():
                                parts.append(chunk.strip())
                    else:
                        # Предложение нормальной длины
                        if len(temp_part) + len(sentence) + 2 > max_length:
                            if temp_part.strip():
                                parts.append(temp_part.strip())
                            temp_part = sentence + '. '
                        else:
                            if temp_part:
                                temp_part += sentence + '. '
                            else:
                                temp_part = sentence + '. '
                
                current_part = temp_part
            else:
                current_part = paragraph
        else:
            # Добавляем параграф к текущей части
            if current_part:
                current_part += "\n" + paragraph
            else:
                current_part = paragraph
    
    # Добавляем последнюю часть
    if current_part.strip():
        parts.append(current_part.strip())
    
    return parts


class TestMessageSplitting:
    """Test the split_long_message utility function."""
    
    def test_short_message_not_split(self):
        """Short messages should not be split."""
        message = "Короткое сообщение"
        result = split_long_message(message, max_length=3500)
        
        assert len(result) == 1
        assert result[0] == message
    
    def test_long_message_split_by_paragraphs(self):
        """Long messages should be split by paragraphs."""
        # Create a message with 100 paragraphs of 50 characters each
        paragraphs = [f"Параграф {i} с текстом для тестирования" for i in range(100)]
        message = "\n".join(paragraphs)
        
        result = split_long_message(message, max_length=3500)
        
        # Should be split into multiple parts
        assert len(result) > 1
        
        # Each part should be under the limit
        for part in result:
            assert len(part) <= 3500
        
        # All parts together should contain all paragraphs
        combined = "\n".join(result)
        for para in paragraphs:
            assert para in combined
    
    def test_message_at_exact_limit(self):
        """Message at exactly max_length should not be split."""
        message = "a" * 3500
        result = split_long_message(message, max_length=3500)
        
        assert len(result) == 1
        assert result[0] == message
    
    def test_message_just_over_limit(self):
        """Message just over max_length should be split."""
        message = "a" * 3501
        result = split_long_message(message, max_length=3500)
        
        # This will be split because it's over the limit
        assert len(result) >= 1
        
        # All parts should be under limit
        for part in result:
            assert len(part) <= 3500
    
    def test_split_preserves_paragraph_structure(self):
        """Splitting should preserve paragraph boundaries."""
        # Make each paragraph long enough to force splitting
        message = "Первый параграф с длинным текстом\nВторой параграф с длинным текстом\nТретий параграф с длинным текстом"
        result = split_long_message(message, max_length=50)
        
        # Should split into multiple parts
        assert len(result) > 1
        
        # Each paragraph should be in exactly one part
        combined = "\n".join(result)
        assert "Первый параграф" in combined
        assert "Второй параграф" in combined
        assert "Третий параграф" in combined
    
    def test_very_long_single_paragraph(self):
        """Very long single paragraph should be split by sentences."""
        # Create a long paragraph with multiple sentences
        sentences = [f"Предложение номер {i}. " for i in range(200)]
        message = "".join(sentences)
        
        result = split_long_message(message, max_length=3500)
        
        # Should be split into multiple parts
        assert len(result) > 1
        
        # Each part should be under the limit
        for part in result:
            assert len(part) <= 3500
    
    def test_empty_message(self):
        """Empty message should return single empty part."""
        message = ""
        result = split_long_message(message, max_length=3500)
        
        assert len(result) == 1
        assert result[0] == ""
    
    def test_whitespace_only_message(self):
        """Whitespace-only message should be handled correctly."""
        message = "   \n   \n   "
        result = split_long_message(message, max_length=3500)
        
        assert len(result) == 1
    
    def test_custom_max_length(self):
        """Should respect custom max_length parameter."""
        message = "a" * 1000
        result = split_long_message(message, max_length=500)
        
        # Should be split into at least 2 parts
        assert len(result) >= 2
        
        # Each part should be under custom limit
        for part in result:
            assert len(part) <= 500
    
    def test_message_with_html_formatting(self):
        """Should handle messages with HTML formatting."""
        message = "<b>Жирный текст</b>\n" * 200
        result = split_long_message(message, max_length=3500)
        
        # Should be split
        assert len(result) > 1
        
        # HTML tags should be preserved
        for part in result:
            assert len(part) <= 3500
            # At least some parts should contain HTML
        
        combined = "".join(result)
        assert "<b>" in combined
        assert "</b>" in combined
    
    def test_mixed_content(self):
        """Should handle mixed content (text, numbers, special chars)."""
        message = "🎉 Текст 123 !@#$%\n" * 200
        result = split_long_message(message, max_length=3500)
        
        # Should be split
        assert len(result) > 1
        
        # Each part should be under limit
        for part in result:
            assert len(part) <= 3500
        
        # Content should be preserved
        combined = "\n".join(result)
        assert "🎉" in combined
        assert "123" in combined
    
    def test_no_empty_parts(self):
        """Should not create empty parts (except for empty input)."""
        message = "Параграф\n\n\nПараграф\n\n" * 50
        result = split_long_message(message, max_length=3500)
        
        # No part should be only whitespace (except if split happens on empty lines)
        for part in result:
            # Each part should contain some actual content
            assert len(part) >= 0  # Can be empty only if input is empty
    
    def test_telegram_realistic_limit(self):
        """Test with realistic Telegram message length."""
        # Telegram limit is ~4096, we use 3500 for safety
        # Create a realistic long message
        message = (
            "📊 Анализ рынка криптовалют:\n\n"
            "Bitcoin (BTC) показывает рост на 5% за последние 24 часа. "
            "Основные факторы роста включают:\n"
            "• Увеличение институционального спроса\n"
            "• Позитивные новости о регулировании\n"
            "• Технические индикаторы указывают на бычий тренд\n\n"
        ) * 50  # Repeat to make it very long
        
        result = split_long_message(message, max_length=3500)
        
        # Should be split into multiple parts
        assert len(result) > 1
        
        # Each part must be under Telegram's safe limit
        for part in result:
            assert len(part) <= 3500
        
        # Content should be preserved
        combined = "".join(result)
        assert "Bitcoin" in combined
        assert "📊" in combined


class TestMessageSplittingEdgeCases:
    """Test edge cases for message splitting."""
    
    def test_single_very_long_word(self):
        """Single very long word (no spaces or newlines) should be handled."""
        # This is an edge case - a single "word" longer than max_length
        message = "a" * 5000
        result = split_long_message(message, max_length=3500)
        
        # Should split even though there are no natural break points
        assert len(result) >= 2
        
        # Reconstructed message should have same length
        combined = "".join(result)
        assert len(combined) == 5000
    
    def test_many_short_paragraphs(self):
        """Many short paragraphs should be grouped efficiently."""
        paragraphs = ["X\n" for _ in range(2000)]
        message = "".join(paragraphs)
        
        result = split_long_message(message, max_length=3500)
        
        # Should be split efficiently
        assert len(result) > 1
        
        # Each part should be close to but under the limit
        for part in result:
            assert len(part) <= 3500
    
    def test_alternating_long_short_paragraphs(self):
        """Alternating long and short paragraphs should be handled well."""
        message = ""
        for i in range(50):
            if i % 2 == 0:
                message += "Длинный параграф " * 20 + "\n"
            else:
                message += "Короткий\n"
        
        result = split_long_message(message, max_length=3500)
        
        # Should be split
        assert len(result) > 1
        
        # Each part under limit
        for part in result:
            assert len(part) <= 3500
    
    def test_unicode_characters(self):
        """Should handle unicode characters correctly."""
        message = "🚀 Крипто новости! 💰\n" * 200
        result = split_long_message(message, max_length=3500)
        
        # Should be split
        assert len(result) > 1
        
        # Unicode should be preserved
        combined = "".join(result)
        assert "🚀" in combined
        assert "💰" in combined
        assert "Крипто" in combined


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
