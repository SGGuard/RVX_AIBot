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

logger = logging.getLogger(__name__)

# ============================================================================
# COINGECKO API - Бесплатный API без ключа
# ============================================================================

class CryptoDigestCollector:
    """Собирает данные для крипто дайджеста"""
    
    COINGECKO_BASE = "https://api.coingecko.com/api/v3"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_market_data(self) -> Dict:
        """Получить данные о рынке: BTC, ETH и топ альты"""
        try:
            url = f"{self.COINGECKO_BASE}/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 15,
                "sparkline": False,
                "locale": "ru"
            }
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"CoinGecko API error: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return []
    
    async def get_fear_greed_index(self) -> Optional[Dict]:
        """Получить Fear & Greed Index"""
        try:
            url = f"{self.COINGECKO_BASE}/fear_and_greed"
            
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", {})
                else:
                    logger.error(f"Fear & Greed API error: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching fear & greed: {e}")
            return None
    
    async def get_gainers_losers(self) -> Dict:
        """Получить топ gainers и losers за 24h"""
        try:
            url = f"{self.COINGECKO_BASE}/coins/markets"
            
            # Gainers
            gainers_params = {
                "vs_currency": "usd",
                "order": "percent_change_24h_desc",
                "per_page": 5,
                "sparkline": False
            }
            
            async with self.session.get(url, params=gainers_params, timeout=aiohttp.ClientTimeout(10)) as resp:
                gainers = await resp.json() if resp.status == 200 else []
            
            # Losers
            losers_params = {
                "vs_currency": "usd",
                "order": "percent_change_24h_asc",
                "per_page": 5,
                "sparkline": False
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
            url = f"{self.COINGECKO_BASE}/global"
            
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(10)) as resp:
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
