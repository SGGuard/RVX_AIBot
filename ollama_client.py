"""
Ollama Local LLM Integration Module
===================================
Интеграция с локальной Ollama для использования LLM без облачных сервисов.
Модель: qwen2.5 (7.6B параметров) - отлично работает для кодинга и анализа.

Функциональность:
- Асинхронное подключение к Ollama API (http://localhost:11434)
- Автоматические повторы при ошибках
- Кеширование результатов
- Fallback на облачные провайдеры если Ollama недоступна
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("Ollama")

class OllamaClient:
    """Клиент для работы с локальной Ollama моделью."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5",
        timeout: int = 60,
        enable_cache: bool = True
    ):
        """
        Инициализация Ollama клиента.
        
        Args:
            base_url: URL где запущена Ollama (по умолчанию localhost:11434)
            model: Имя модели для использования (по умолчанию qwen2.5)
            timeout: Таймаут для запросов в секундах
            enable_cache: Включить ли кеширование результатов
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.enable_cache = enable_cache
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.api_endpoint = f"{self.base_url}/api/generate"
        self.health_endpoint = f"{self.base_url}/api/tags"
        self.is_available = False
        
        logger.info(f"📦 Ollama Client инициализирован: {self.base_url}")
        logger.info(f"   Модель: {self.model}")
        logger.info(f"   Таймаут: {self.timeout}s")
        logger.info(f"   Кеш: {'✅ включён' if self.enable_cache else '❌ отключён'}")
    
    async def check_health(self) -> bool:
        """
        Проверяет доступность Ollama сервера и наличие модели.
        
        Returns:
            True если сервер доступен и модель загружена, False иначе
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.health_endpoint)
                
                if response.status_code != 200:
                    logger.error(f"❌ Ollama сервер недоступен (статус {response.status_code})")
                    self.is_available = False
                    return False
                
                data = response.json()
                models = [m.get('name', '') for m in data.get('models', [])]
                
                # Проверяем, есть ли нужная модель
                if self.model in models or any(self.model in m for m in models):
                    logger.info(f"✅ Ollama доступна! Модель '{self.model}' загружена")
                    self.is_available = True
                    return True
                else:
                    logger.error(f"❌ Модель '{self.model}' не найдена в Ollama")
                    logger.info(f"   Доступные модели: {models}")
                    self.is_available = False
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке Ollama: {type(e).__name__}: {e}")
            self.is_available = False
            return False
    
    def _get_cache_key(self, prompt: str) -> str:
        """Генерирует ключ для кеша на основе промпта."""
        import hashlib
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]
    
    def _get_from_cache(self, prompt: str) -> Optional[str]:
        """Получает результат из кеша если есть."""
        if not self.enable_cache:
            return None
        
        cache_key = self._get_cache_key(prompt)
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            age_seconds = (datetime.now() - cached['timestamp']).total_seconds()
            
            # Кеш действителен 24 часов
            if age_seconds < 86400:
                logger.debug(f"📦 Результат найден в кесе (ключ: {cache_key})")
                return cached['response']
            else:
                # Кеш устарел, удаляем
                del self.cache[cache_key]
        
        return None
    
    def _save_to_cache(self, prompt: str, response: str) -> None:
        """Сохраняет результат в кеш."""
        if not self.enable_cache:
            return
        
        cache_key = self._get_cache_key(prompt)
        self.cache[cache_key] = {
            'response': response,
            'timestamp': datetime.now(),
            'model': self.model
        }
        
        # Ограничиваем размер кеша (максимум 100 записей)
        if len(self.cache) > 100:
            oldest_key = min(
                self.cache.keys(),
                key=lambda k: self.cache[k]['timestamp']
            )
            del self.cache[oldest_key]
            logger.debug(f"🧹 Кеш переполнен, удалена старая запись")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        stream: bool = False
    ) -> str:
        """
        Генерирует текст используя Ollama.
        
        Args:
            prompt: Основной запрос
            system_prompt: Системный промпт (инструкции моделе)
            temperature: Творческость ответа (0=детерминированный, 1=случайный)
            max_tokens: Максимальное количество токенов в ответе
            stream: Использовать ли потоковый ответ
            
        Returns:
            Сгенерированный текст
        """
        if not self.is_available:
            logger.warning("⚠️ Ollama не доступна, попробуй проверить здоровье сервера")
            raise ConnectionError("Ollama сервер недоступен")
        
        # Проверяем кеш
        cached = self._get_from_cache(prompt)
        if cached:
            return cached
        
        # Формируем полный промпт с системным сообщением
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout * 2) as client:
                payload = {
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": stream,
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "options": {
                        "temperature": temperature,
                        "top_k": 40,
                        "top_p": 0.95,
                    }
                }
                
                logger.debug(f"🔄 Отправляем запрос к Ollama...")
                logger.debug(f"   Модель: {self.model}")
                logger.debug(f"   Размер промпта: {len(full_prompt)} символов")
                
                if stream:
                    # Потоковый ответ
                    response_text = ""
                    async with client.stream('POST', self.api_endpoint, json=payload) as response:
                        if response.status_code != 200:
                            error = await response.text()
                            logger.error(f"❌ Ollama вернула ошибку {response.status_code}: {error}")
                            raise RuntimeError(f"Ollama error: {error}")
                        
                        async for line in response.aiter_lines():
                            if line:
                                try:
                                    chunk = json.loads(line)
                                    response_text += chunk.get('response', '')
                                except json.JSONDecodeError:
                                    continue
                else:
                    # Обычный ответ
                    response = await client.post(self.api_endpoint, json=payload)
                    
                    if response.status_code != 200:
                        logger.error(f"❌ Ollama вернула ошибку {response.status_code}")
                        raise RuntimeError(f"Ollama HTTP {response.status_code}")
                    
                    data = response.json()
                    response_text = data.get('response', '')
                
                logger.info(f"✅ Ollama ответила успешно")
                logger.debug(f"   Размер ответа: {len(response_text)} символов")
                
                # Сохраняем в кеш
                self._save_to_cache(prompt, response_text)
                
                return response_text.strip()
                
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Timeout при запросе к Ollama ({self.timeout}s)")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка Ollama: {type(e).__name__}: {e}")
            raise
    
    async def analyze_code(
        self,
        code: str,
        analysis_type: str = "general"
    ) -> str:
        """
        Специализированная функция для анализа кода.
        
        Args:
            code: Код для анализа
            analysis_type: Тип анализа: "general", "security", "performance", "style"
            
        Returns:
            Результат анализа
        """
        analysis_prompts = {
            "general": """Проанализируй этот код. Найди:
1. Потенциальные баги и проблемы
2. Места для улучшения читаемости
3. Возможности оптимизации
4. Нарушения best practices

Код:
""",
            "security": """Проанализируй этот код с точки зрения безопасности:
1. Уязвимости
2. Проблемы с вводом пользователя
3. Проблемы аутентификации/авторизации
4. Утечки данных

Код:
""",
            "performance": """Проанализируй этот код на производительность:
1. Узкие места
2. Неэффективные алгоритмы
3. Утечки памяти
4. Возможности кеширования

Код:
""",
            "style": """Проверь стиль кода:
1. Соответствие PEP8 (для Python)
2. Имена переменных и функций
3. Документация и комментарии
4. Структура и организация

Код:
"""
        }
        
        system_prompt = "Ты опытный разработчик. Анализируй код внимательно и предлагай конкретные улучшения."
        prompt = analysis_prompts.get(analysis_type, analysis_prompts["general"])
        full_prompt = f"{prompt}{code}"
        
        return await self.generate(
            full_prompt,
            system_prompt=system_prompt,
            temperature=0.2
        )
    
    async def generate_docstring(self, code: str, language: str = "python") -> str:
        """Генерирует документацию/docstring для кода."""
        system_prompt = f"Ты эксперт в документировании кода на {language}."
        prompt = f"""Напиши подробный docstring для этого кода используя стиль Google-style документации:
        
{code}

Включи:
- Описание что делает функция/класс
- Args и их описания
- Returns и его описание
- Примеры использования
- Возможные исключения"""
        
        return await self.generate(
            prompt,
            system_prompt=system_prompt,
            temperature=0.1
        )
    
    async def write_tests(self, code: str, language: str = "python") -> str:
        """Генерирует юнит-тесты для кода."""
        system_prompt = f"""Ты эксперт в написании тестов на {language}.
Пиши тесты используя {language} unittest або pytest."""
        
        prompt = f"""Напиши полный набор юнит-тестов для этого кода:

{code}

Включи:
- Тесты позитивных случаев
- Тесты граничных случаев
- Тесты ошибок
- Тесты производительности если применимо"""
        
        return await self.generate(
            prompt,
            system_prompt=system_prompt,
            temperature=0.2
        )
    
    def clear_cache(self) -> None:
        """Очищает весь кеш."""
        self.cache.clear()
        logger.info("🧹 Кеш очищен")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кеша."""
        return {
            "cache_size": len(self.cache),
            "enabled": self.enable_cache,
            "is_available": self.is_available,
            "model": self.model,
            "base_url": self.base_url
        }


# Глобальный экземпляр клиента
_ollama_client: Optional[OllamaClient] = None


async def initialize_ollama(
    base_url: str = "http://localhost:11434",
    model: str = "qwen2.5",
    timeout: int = 60
) -> OllamaClient:
    """
    Инициализирует глобальный Ollama клиент.
    
    Returns:
        Инициализированный OllamaClient
    """
    global _ollama_client
    
    _ollama_client = OllamaClient(
        base_url=base_url,
        model=model,
        timeout=timeout
    )
    
    # Проверяем здоровье сервера
    health = await _ollama_client.check_health()
    if not health:
        logger.warning("⚠️ Ollama недоступна! Падбэки будут использовать облачные провайдеры")
    
    return _ollama_client


def get_ollama_client() -> Optional[OllamaClient]:
    """Возвращает инициализированный Ollama клиент или None."""
    return _ollama_client


async def generate_with_ollama(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1500
) -> Optional[str]:
    """
    Быстрый способ генерировать текст через Ollama.
    
    Returns:
        Сгенерированный текст или None если Ollama недоступна
    """
    client = get_ollama_client()
    if not client or not client.is_available:
        logger.warning("⚠️ Ollama клиент не инициализирован или недоступен")
        return None
    
    try:
        return await client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при генерации через Ollama: {e}")
        return None
