#!/usr/bin/env python3
"""
Автоматический локализатор для bot.py
Это скрипт парсит bot.py, находит все русские строки в обработчиках,
создает translation keys и заменяет их на вызовы get_text()
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Tuple

# Регулярное выражение для поиска русского текста в кавычках
RUSSIAN_TEXT_PATTERN = r'(["\'])([а-яА-ЯёЁ\d\s\-\.\,\!\?\:\;\(\)\/\@\#\$\%\&\*\+\=\~\`\\]+)\1'

class BotLocalizer:
    def __init__(self, bot_file: str, ru_locale: str, uk_locale: str):
        self.bot_file = Path(bot_file)
        self.ru_locale = Path(ru_locale)
        self.uk_locale = Path(uk_locale)
        
        # Загружаем существующие локали
        with open(self.ru_locale) as f:
            self.ru_dict = json.load(f)
        with open(self.uk_locale) as f:
            self.uk_dict = json.load(f)
        
        # Читаем bot.py
        with open(self.bot_file) as f:
            self.bot_content = f.read()
        
        self.new_keys = {}
        self.replacements = {}
    
    def extract_russian_text(self) -> List[Tuple[str, str]]:
        """Находит все русские строки в bot.py"""
        matches = []
        for match in re.finditer(RUSSIAN_TEXT_PATTERN, self.bot_content):
            quote_type = match.group(1)
            text = match.group(2)
            
            # Пропускаем слишком короткие строки
            if len(text) < 3:
                continue
            
            # Пропускаем уже переведенные (начинающиеся с emoji)
            if text[0] in ['🎓', '✅', '❌', '📚', '🏆', '💬', '📊', '⚙️', '⬅️', '📦', '🎯', '📋', '⚠️', '🌐']:
                continue
            
            matches.append((text, quote_type))
        
        return matches
    
    def generate_key(self, text: str, context: str = "") -> str:
        """Генерирует уникальный ключ для текста"""
        # Удаляем спецсимволы и emoji
        clean = re.sub(r'[^\w\s\-]', '', text.lower())
        clean = ' '.join(clean.split())[:50]  # Макс 50 символов
        clean = clean.replace(' ', '_')
        return f"general.{clean}"
    
    def process_handler_profile(self):
        """Обновляет обработчик profile"""
        print("Processing profile handler...")
        
        # Это требует ручной работы, так что пока пропускаем
        pass
    
    def generate_report(self):
        """Генерирует отчет о найденных русских строках"""
        print(f"\n✅ Найдено {len(self.new_keys)} новых ключей для добавления")
        print(f"   Примеры: {list(self.new_keys.keys())[:5]}")

if __name__ == "__main__":
    print("🚀 Запуск локализатора bot.py...")
    
    localizer = BotLocalizer(
        "bot.py",
        "locales/ru.json",
        "locales/uk.json"
    )
    
    russian_texts = localizer.extract_russian_text()
    print(f"🔍 Найдено {len(russian_texts)} русских текстов")
    
    # Выводим первые 10
    for i, (text, quote) in enumerate(russian_texts[:10]):
        key = localizer.generate_key(text)
        print(f"  {i+1}. [{key}] = {text[:60]}")
    
    print(f"\n⚠️ СЛИШКОМ МНОГО ДЛЯ АВТОМАТИЗАЦИИ!")
    print("Нужна ручная работа или более сложный алгоритм")
