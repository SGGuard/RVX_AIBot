#!/usr/bin/env python3
"""
🌍 ВАЛИДАЦИЯ СИСТЕМЫ ЛОКАЛИЗАЦИИ RVX BOT

Этот скрипт проверяет что вся система локализации работает корректно.
Запусти: python3 validate_localization.py
"""

import json
import asyncio
import sys
from pathlib import Path


class LocalizationValidator:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        
        # Пути к файлам
        self.ru_file = Path("locales/ru.json")
        self.uk_file = Path("locales/uk.json")
        
    def print_header(self, title):
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
    
    def check(self, name: str, condition: bool, message: str = ""):
        if condition:
            print(f"  ✅ {name}")
            self.passed += 1
        else:
            print(f"  ❌ {name}")
            if message:
                print(f"     └─ {message}")
            self.failed += 1
    
    def warn(self, message: str):
        print(f"  ⚠️  {message}")
        self.warnings += 1
    
    async def validate_all(self):
        try:
            await self.validate_files()
            await self.validate_json_structure()
            await self.validate_keys_match()
            await self.validate_i18n_module()
            await self.validate_content()
            
            self.print_summary()
            return self.failed == 0
        except Exception as e:
            print(f"\n❌ ОШИБКА: {e}")
            return False
    
    async def validate_files(self):
        print_header("1️⃣  ПРОВЕРКА ФАЙЛОВ")
        
        self.check(
            "locales/ru.json существует",
            self.ru_file.exists(),
            f"Файл не найден: {self.ru_file}"
        )
        
        self.check(
            "locales/uk.json существует",
            self.uk_file.exists(),
            f"Файл не найден: {self.uk_file}"
        )
        
        if self.ru_file.exists():
            size = self.ru_file.stat().st_size
            self.check(
                f"ru.json имеет размер > 0 ({size} байт)",
                size > 1000,
                f"Файл слишком маленький: {size} байт"
            )
        
        if self.uk_file.exists():
            size = self.uk_file.stat().st_size
            self.check(
                f"uk.json имеет размер > 0 ({size} байт)",
                size > 1000,
                f"Файл слишком маленький: {size} байт"
            )
    
    async def validate_json_structure(self):
        print_header("2️⃣  ПРОВЕРКА JSON СТРУКТУРЫ")
        
        try:
            with open(self.ru_file) as f:
                self.ru_data = json.load(f)
            self.check("ru.json валидный JSON", True)
            self.check(f"ru.json содержит ключи (найдено: {len(self.ru_data)})", 
                      len(self.ru_data) > 0)
        except Exception as e:
            self.check("ru.json валидный JSON", False, str(e))
            self.ru_data = {}
        
        try:
            with open(self.uk_file) as f:
                self.uk_data = json.load(f)
            self.check("uk.json валидный JSON", True)
            self.check(f"uk.json содержит ключи (найдено: {len(self.uk_data)})", 
                      len(self.uk_data) > 0)
        except Exception as e:
            self.check("uk.json валидный JSON", False, str(e))
            self.uk_data = {}
    
    async def validate_keys_match(self):
        print_header("3️⃣  ПРОВЕРКА СОВПАДЕНИЯ КЛЮЧЕЙ")
        
        if not self.ru_data or not self.uk_data:
            print("  ⚠️  Не могу проверить - данные не загружены")
            return
        
        ru_keys = set(self.ru_data.keys())
        uk_keys = set(self.uk_data.keys())
        
        # Ключи в русском но не в украинском
        missing_uk = ru_keys - uk_keys
        if missing_uk:
            self.warn(f"Ключи в ru.json но не в uk.json ({len(missing_uk)}): {list(missing_uk)[:3]}")
        
        # Ключи в украинском но не в русском
        missing_ru = uk_keys - ru_keys
        if missing_ru:
            self.warn(f"Ключи в uk.json но не в ru.json ({len(missing_ru)}): {list(missing_ru)[:3]}")
        
        # Проверка полного совпадения
        self.check(
            "Все ключи совпадают",
            ru_keys == uk_keys,
            f"ru.json: {len(ru_keys)}, uk.json: {len(uk_keys)}"
        )
    
    async def validate_i18n_module(self):
        print_header("4️⃣  ПРОВЕРКА МОДУЛЯ i18n.py")
        
        try:
            from i18n import get_text, set_user_language, get_user_language
            self.check("Модуль i18n импортируется", True)
        except ImportError as e:
            self.check("Модуль i18n импортируется", False, str(e))
            return
        
        # Тест get_text на русском
        try:
            text = await get_text("menu.ask_button", language="ru")
            self.check(
                f"get_text('menu.ask_button', language='ru') работает",
                text and not text.startswith("[MISSING"),
                f"Результат: {text}"
            )
        except Exception as e:
            self.check("get_text работает", False, str(e))
        
        # Тест get_text на украинском
        try:
            text = await get_text("menu.ask_button", language="uk")
            self.check(
                f"get_text('menu.ask_button', language='uk') работает",
                text and not text.startswith("[MISSING"),
                f"Результат: {text}"
            )
        except Exception as e:
            self.check("get_text на украинском работает", False, str(e))
    
    async def validate_content(self):
        print_header("5️⃣  ПРОВЕРКА СОДЕРЖИМОГО")
        
        if not self.ru_data or not self.uk_data:
            print("  ⚠️  Не могу проверить - данные не загружены")
            return
        
        # Проверка что тексты не пусты
        empty_ru = [k for k, v in self.ru_data.items() if not str(v).strip()]
        empty_uk = [k for k, v in self.uk_data.items() if not str(v).strip()]
        
        self.check(
            f"Нет пустых значений в ru.json",
            len(empty_ru) == 0,
            f"Пустых ключей: {empty_ru[:3] if empty_ru else 'нет'}"
        )
        
        self.check(
            f"Нет пустых значений в uk.json",
            len(empty_uk) == 0,
            f"Пустых ключей: {empty_uk[:3] if empty_uk else 'нет'}"
        )
        
        # Проверка что много текстов начинаются с эмодзи (хороший знак)
        emoji_ru = sum(1 for v in self.ru_data.values() if any(ord(c) > 0x1F300 for c in str(v)))
        emoji_uk = sum(1 for v in self.uk_data.values() if any(ord(c) > 0x1F300 for c in str(v)))
        
        self.check(
            f"ru.json содержит эмодзи ({emoji_ru}/{ len(self.ru_data)})",
            emoji_ru > 100,
            f"Эмодзи в {emoji_ru} ключах"
        )
        
        self.check(
            f"uk.json содержит эмодзи ({emoji_uk}/{len(self.uk_data)})",
            emoji_uk > 100,
            f"Эмодзи в {emoji_uk} ключах"
        )
        
        # Проверка важных ключей
        important_keys = [
            "menu.ask_button",
            "menu.teach_button",
            "error.generic_error",
            "button.back",
            "settings.language_select"
        ]
        
        for key in important_keys:
            exists = key in self.ru_data and key in self.uk_data
            self.check(
                f"Ключ '{key}' присутствует",
                exists,
                f"Ключ не найден"
            )
    
    def print_summary(self):
        total = self.passed + self.failed
        print_header("📊 ИТОГИ")
        
        print(f"""
  Всего проверок:      {total}
  ✅ Прошло:            {self.passed}
  ❌ Не прошло:         {self.failed}
  ⚠️  Предупреждений:    {self.warnings}
""")
        
        if self.failed == 0:
            print("  🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
            print("  Система локализации готова к использованию! ✨")
        else:
            print("  ⚠️  Найдены проблемы - исправь их перед использованием")
        
        print("\n" + "="*60 + "\n")


def main():
    validator = LocalizationValidator()
    
    print("""
╔════════════════════════════════════════════════════════╗
║  🌍 ВАЛИДАЦИЯ СИСТЕМЫ ЛОКАЛИЗАЦИИ RVX BOT             ║
║     Версия 1.0 - Production Ready Check               ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # Запусти валидацию
    result = asyncio.run(validator.validate_all())
    
    # Выход с кодом
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
