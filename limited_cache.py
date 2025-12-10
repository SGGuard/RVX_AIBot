"""
Limited Cache v1.0
Кэш с LRU eviction и TTL для api_server.py
"""

import time
import threading
import logging
from collections import OrderedDict
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

class LimitedCache:
    """Кэш с LRU eviction и TTL"""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache = OrderedDict()
        self.timestamps = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Dict]:
        """Получить значение"""
        with self._lock:
            if key not in self.cache:
                return None
            
            # Проверяем TTL
            age = time.time() - self.timestamps[key]
            if age > self.ttl_seconds:
                del self.cache[key]
                del self.timestamps[key]
                logger.debug(f"🔄 Cache expired: {key} (age={age:.0f}s)")
                return None
            
            # LRU: перемещаем в конец
            self.cache.move_to_end(key)
            logger.debug(f"✅ Cache hit: {key}")
            return self.cache[key]
    
    def set(self, key: str, value: Dict) -> None:
        """Установить значение"""
        with self._lock:
            # Удаляем если существует (обновляем)
            if key in self.cache:
                del self.cache[key]
                del self.timestamps[key]
            
            # Если переполнено, удаляем самый старый
            while len(self.cache) >= self.max_size:
                oldest_key, _ = self.cache.popitem(last=False)
                del self.timestamps[oldest_key]
                logger.debug(f"🔄 Cache evicted (LRU): {oldest_key}")
            
            # Добавляем новый
            self.cache[key] = value
            self.timestamps[key] = time.time()
            logger.debug(f"✅ Cache set: {key} (size={len(self.cache)}/{self.max_size})")
    
    def clear(self) -> None:
        """Очищает весь кэш"""
        with self._lock:
            self.cache.clear()
            self.timestamps.clear()
            logger.info(f"✅ Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику"""
        with self._lock:
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'utilization_percent': (len(self.cache) / self.max_size * 100) if self.max_size > 0 else 0,
                'ttl_seconds': self.ttl_seconds
            }
