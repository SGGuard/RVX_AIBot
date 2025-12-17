"""
Crypto Daily Digest Module
Получает данные о криптовалютах, финансовых новостях и событиях
"""

import logging
import aiohttp
import feedparser
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ============================================================================
# COINGECKO API - С поддержкой API ключа для увеличенных лимитов
# ============================================================================

COINGECKO_API_KEY = os.getenv('COINGECKO_API_KEY', '')
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
COINGECKO_PRO_BASE = "https://pro-api.coingecko.com/api/v3"  # Pro API с ключом

class CryptoDigestCollector:
    """Собирает данные для крипто дайджеста с поддержкой API ключа"""
    
    # Выбираем базу в зависимости от наличия ключа
    BASE_URL = COINGECKO_PRO_BASE if COINGECKO_API_KEY else COINGECKO_BASE
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_key = COINGECKO_API_KEY
        self.base_url = self.BASE_URL
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_market_data(self) -> List[Dict]:
        """Получить данные о рынке: BTC, ETH и топ альты"""
        try:
            url = f"{self.base_url}/coins/markets"
            # aiohttp requires string values for params, not booleans
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": "15",
                "sparkline": "false",
                "locale": "ru"
            }
            
            # Добавляем API ключ если он есть (для Pro API)
            if self.api_key:
                params["x_cg_pro_api_key"] = self.api_key
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"✅ Market data fetched: {len(data)} coins")
                    return data
                else:
                    logger.error(f"❌ CoinGecko API error: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"❌ Error fetching market data: {e}")
            return []
    
    async def get_fear_greed_index(self) -> Optional[Dict]:
        """Получить Fear & Greed Index (только с Pro API ключом)"""
        if not self.api_key:
            logger.debug("⚠️ Fear & Greed Index требует Pro API ключ")
            return None
        
        try:
            url = f"{self.base_url}/fear_and_greed"
            params = {"x_cg_pro_api_key": self.api_key}
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", {})
                else:
                    logger.warning(f"⚠️ Fear & Greed API error: {resp.status} (требуется Pro API)")
                    return None
        except Exception as e:
            logger.error(f"Error fetching fear & greed: {e}")
            return None
    
    async def get_gainers_losers(self) -> Dict:
        """Получить топ gainers и losers за 24h"""
        try:
            url = f"{self.base_url}/coins/markets"
            base_params = {"x_cg_pro_api_key": self.api_key} if self.api_key else {}
            
            # Gainers
            gainers_params = {
                "vs_currency": "usd",
                "order": "percent_change_24h_desc",
                "per_page": "5",
                "sparkline": "false",
                **base_params
            }
            
            async with self.session.get(url, params=gainers_params, timeout=aiohttp.ClientTimeout(10)) as resp:
                gainers = await resp.json() if resp.status == 200 else []
            
            # Losers
            losers_params = {
                "vs_currency": "usd",
                "order": "percent_change_24h_asc",
                "per_page": "5",
                "sparkline": "false",
                **base_params
            }
            
            async with self.session.get(url, params=losers_params, timeout=aiohttp.ClientTimeout(10)) as resp:
                losers = await resp.json() if resp.status == 200 else []
            
            return {"gainers": gainers, "losers": losers}
        except Exception as e:
            logger.error(f"Error fetching gainers/losers: {e}")
            return {"gainers": [], "losers": []}
    
    async def get_global_market_data(self) -> Dict:
        """Получить глобальные данные рынка (total market cap, volume, BTC dominance)"""
        try:
            url = f"{self.base_url}/global"
            params = {"x_cg_pro_api_key": self.api_key} if self.api_key else {}
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Global market API error: {resp.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error fetching global market data: {e}")
            return {}


class NewsCollector:
    """Собирает новости из RSS"""
    
    FEEDS = {
        "CoinTelegraph": "https://feeds.bloomberg.com/markets/news/cryptocurrency.rss",
        "CryptoNews": "https://cryptonews.com/news-feed/",
        "Cointelegraph": "https://cointelegraph.com/feed",
    }
    
    async def get_top_news(self, limit: int = 5) -> List[Dict]:
        """Получить топ новостей из RSS"""
        try:
            all_news = []
            
            # Пытаемся получить из Cointelegraph RSS
            feed = feedparser.parse(self.FEEDS["Cointelegraph"])
            
            if feed.entries:
                for entry in feed.entries[:limit]:
                    news_item = {
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "source": "Cointelegraph"
                    }
                    all_news.append(news_item)
            
            return all_news[:limit]
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            return []


class FinanceNewsCollector:
    """Собирает финансовые новости и события (геополитика, рынки, ЦБ и т.д.)"""
    
    async def get_important_events(self) -> List[Dict]:
        """
        Получить важные финансовые события на день
        В реальности можно интегрировать с Calendar API или парсить финансовые сайты
        """
        # Placeholder - в реальности интегрировать с:
        # - Trading Economics (экономический календарь)
        # - Federal Reserve анонсы
        # - ECB новости
        # - Геополитические события
        
        events = [
            {
                "time": "14:30 UTC",
                "title": "FOMC Meeting Minutes",
                "importance": "High",
                "impact": "USD, Crypto"
            }
        ]
        return events


async def collect_digest_data() -> Dict:
    """
    Собрать все данные для дайджеста
    """
    try:
        async with CryptoDigestCollector() as collector:
            market_data = await collector.get_market_data()
            fear_greed = await collector.get_fear_greed_index()
            gainers_losers = await collector.get_gainers_losers()
            global_data = await collector.get_global_market_data()
        
        news_collector = NewsCollector()
        news = await news_collector.get_top_news(5)
        
        finance_collector = FinanceNewsCollector()
        events = await finance_collector.get_important_events()
        
        return {
            "market_data": market_data,
            "fear_greed": fear_greed,
            "gainers_losers": gainers_losers,
            "global_data": global_data,
            "news": news,
            "events": events,
            "timestamp": datetime.now(timezone.utc)
        }
    except Exception as e:
        logger.error(f"Error collecting digest data: {e}")
        return {
            "market_data": [],
            "fear_greed": None,
            "gainers_losers": {"gainers": [], "losers": []},
            "global_data": {},
            "news": [],
            "events": [],
            "timestamp": datetime.now(timezone.utc)
        }


if __name__ == "__main__":
    # Тест
    import asyncio
    
    async def test():
        data = await collect_digest_data()
        print("BTC Price:", data["market_data"][0]["current_price"] if data["market_data"] else "N/A")
        print("Fear & Greed:", data["fear_greed"])
    
    asyncio.run(test())
