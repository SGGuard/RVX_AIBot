"""
Crypto Daily Digest Module v0.5.1
Получает данные о криптовалютах, финансовых новостях и событиях

Улучшения v0.5.1:
- Расширенный список финансовых событий по дням недели
- Лучшая обработка новостей
- События с указанием влияния на рынки
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
    
    # ⚠️ ВАЖНО: Demo/Trial ключи работают ТОЛЬКО с обычным API (api.coingecko.com)
    # Не переходим на про-api даже если есть ключ!
    BASE_URL = COINGECKO_BASE  # Всегда используем бесплатный API
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_key = COINGECKO_API_KEY
        self.base_url = self.BASE_URL
        
        # Логируем какой режим используется
        if self.api_key:
            logger.info(f"📌 CoinGecko API mode: Free API с ключом (Demo/Trial ключи требуют api.coingecko.com)")
        else:
            logger.info(f"📌 CoinGecko API mode: Free API без ключа")
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_market_data(self) -> List[Dict]:
        """Получить данные о рынке: BTC, ETH и топ альты (включая все whitelist монеты)"""
        try:
            url = f"{self.base_url}/coins/markets"
            # aiohttp requires string values for params, not booleans
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": "25",  # Увеличили с 15 на 25 чтобы гарантировать все whitelist монеты
                "sparkline": "false",
            }
            
            # ⚠️ Для Demo API ключей НЕ используем x_cg_pro_api_key
            # Используем просто x_cg_api_key если ключ есть
            if self.api_key:
                params["x_cg_api_key"] = self.api_key
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"✅ Market data fetched: {len(data)} coins")
                    return data
                else:
                    try:
                        error_text = await resp.text()
                        logger.error(f"❌ CoinGecko API error: {resp.status} - {error_text[:200]}")
                    except:
                        logger.error(f"❌ CoinGecko API error: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"❌ Error fetching market data: {e}", exc_info=True)
            return []
    
    async def get_fear_greed_index(self) -> Optional[Dict]:
        """Получить Fear & Greed Index (требует API ключ)"""
        if not self.api_key:
            logger.debug("⚠️ Fear & Greed Index требует API ключ")
            return None
        
        try:
            url = f"{self.base_url}/fear_and_greed"
            params = {"x_cg_api_key": self.api_key}
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", {})
                else:
                    error_text = await resp.text()
                    logger.warning(f"⚠️ Fear & Greed API error: {resp.status} - {error_text[:200]}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching fear & greed: {e}")
            return None
    
    async def get_gainers_losers(self) -> Dict:
        """Получить топ gainers и losers за 24h (с исключением BTC/ETH)"""
        try:
            url = f"{self.base_url}/coins/markets"
            base_params = {"x_cg_api_key": self.api_key} if self.api_key else {}
            
            # Gainers - берем больше для фильтрации (исключим BTC/ETH)
            gainers_params = {
                "vs_currency": "usd",
                "order": "percent_change_24h_desc",
                "per_page": "20",  # Увеличили с 5 на 20
                "sparkline": "false",
                **base_params
            }
            
            try:
                async with self.session.get(url, params=gainers_params, timeout=aiohttp.ClientTimeout(10)) as resp:
                    if resp.status == 200:
                        gainers_raw = await resp.json()
                        # Исключаем BTC и ETH
                        gainers = [
                            g for g in gainers_raw 
                            if g.get("symbol", "").upper() not in {'BTC', 'ETH'}
                        ][:15]  # Берем до 15 после фильтрации
                        logger.info(f"✅ Gainers fetched: {len(gainers)} coins (after filtering)")
                    else:
                        error_text = await resp.text()
                        logger.error(f"❌ Gainers API error: {resp.status} - {error_text[:200]}")
                        gainers = []
            except Exception as e:
                logger.error(f"Error fetching gainers: {e}", exc_info=True)
                gainers = []
            
            # Losers - берем больше для фильтрации
            losers_params = {
                "vs_currency": "usd",
                "order": "percent_change_24h_asc",
                "per_page": "20",  # Увеличили с 5 на 20
                "sparkline": "false",
                **base_params
            }
            
            try:
                async with self.session.get(url, params=losers_params, timeout=aiohttp.ClientTimeout(10)) as resp:
                    if resp.status == 200:
                        losers_raw = await resp.json()
                        # Исключаем BTC и ETH
                        losers = [
                            l for l in losers_raw 
                            if l.get("symbol", "").upper() not in {'BTC', 'ETH'}
                        ][:15]  # Берем до 15 после фильтрации
                        logger.info(f"✅ Losers fetched: {len(losers)} coins (after filtering)")
                    else:
                        error_text = await resp.text()
                        logger.error(f"❌ Losers API error: {resp.status} - {error_text[:200]}")
                        losers = []
            except Exception as e:
                logger.error(f"Error fetching losers: {e}", exc_info=True)
                losers = []
            
            return {"gainers": gainers, "losers": losers}
        except Exception as e:
            logger.error(f"Error in get_gainers_losers: {e}", exc_info=True)
            return {"gainers": [], "losers": []}
    
    async def get_global_market_data(self) -> Dict:
        """Получить глобальные данные рынка (total market cap, volume, BTC dominance)"""
        try:
            url = f"{self.base_url}/global"
            params = {"x_cg_api_key": self.api_key} if self.api_key else {}
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"✅ Global market data fetched")
                    return data
                else:
                    try:
                        error_text = await resp.text()
                        logger.error(f"❌ Global market API error: {resp.status} - {error_text[:200]}")
                    except:
                        logger.error(f"❌ Global market API error: {resp.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error fetching global market data: {e}", exc_info=True)
            return {}


class NewsCollector:
    """Собирает новости из RSS"""
    
    FEEDS = {
        "Cointelegraph": "https://cointelegraph.com/feed",
    }
    
    async def get_top_news(self, limit: int = 5) -> List[Dict]:
        """Получить топ новостей из RSS"""
        try:
            all_news = []
            
            # Пытаемся получить из Cointelegraph RSS
            feed = feedparser.parse(self.FEEDS["Cointelegraph"])
            
            if feed.entries:
                for entry in feed.entries[:limit * 2]:  # Получаем больше для фильтрации
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
    
    # События которые часто влияют на крипто рынок
    WEEKDAY_EVENTS = {
        "Monday": [
            {
                "time": "13:00 UTC",
                "title": "Weekly FT Report",
                "importance": "Medium",
                "impact": "Global Markets"
            },
            {
                "time": "10:00 UTC",
                "title": "ECB Economic Bulletin",
                "importance": "Medium",
                "impact": "EUR, Global"
            }
        ],
        "Tuesday": [
            {
                "time": "16:00 UTC",
                "title": "US Inflation Data (CPI)",
                "importance": "High",
                "impact": "USD, Treasury, Crypto"
            },
            {
                "time": "14:00 UTC",
                "title": "API Calls Rate Limit Check",
                "importance": "Low",
                "impact": "Data Processing"
            }
        ],
        "Wednesday": [
            {
                "time": "14:30 UTC",
                "title": "FOMC Meeting Minutes",
                "importance": "High",
                "impact": "USD, Stocks, Bonds, Crypto"
            },
            {
                "time": "16:00 UTC",
                "title": "EIA Natural Gas Report",
                "importance": "Medium",
                "impact": "Energy, USD"
            }
        ],
        "Thursday": [
            {
                "time": "12:30 UTC",
                "title": "US Initial Jobless Claims",
                "importance": "Medium",
                "impact": "USD, Equities"
            },
            {
                "time": "16:00 UTC",
                "title": "Ethereum Network Update",
                "importance": "Medium",
                "impact": "Altcoins"
            }
        ],
        "Friday": [
            {
                "time": "12:30 UTC",
                "title": "US Non-Farm Payrolls",
                "importance": "High",
                "impact": "USD, All Markets"
            },
            {
                "time": "15:00 UTC",
                "title": "Weekly Market Close",
                "importance": "Medium",
                "impact": "All Markets"
            }
        ],
        "Saturday": [
            {
                "time": "00:00 UTC",
                "title": "Weekend Market Open",
                "importance": "Low",
                "impact": "Crypto Markets"
            }
        ],
        "Sunday": [
            {
                "time": "20:00 UTC",
                "title": "Weekly Market Preparation",
                "importance": "Low",
                "impact": "Market Sentiment"
            }
        ]
    }
    
    async def get_important_events(self) -> List[Dict]:
        """
        Получить важные финансовые события на день
        """
        try:
            today_name = datetime.now().strftime("%A")
            events = self.WEEKDAY_EVENTS.get(today_name, [])
            
            # Если на сегодня нет событий, добавляем хотя бы один
            if not events:
                events = [{
                    "time": "09:00",
                    "title": "Daily Market Analysis",
                    "importance": "Low",
                    "impact": "General Information"
                }]
            
            logger.info(f"📅 Events for {today_name}: {len(events)} events found")
            return events
        except Exception as e:
            logger.error(f"Error getting events: {e}")
            return []


async def collect_digest_data() -> Dict:
    """
    Собрать данные для дайджеста (без новостей и Fear & Greed Index)
    """
    try:
        async with CryptoDigestCollector() as collector:
            market_data = await collector.get_market_data()
            gainers_losers = await collector.get_gainers_losers()
            global_data = await collector.get_global_market_data()
        
        finance_collector = FinanceNewsCollector()
        events = await finance_collector.get_important_events()
        
        return {
            "market_data": market_data,
            "gainers_losers": gainers_losers,
            "global_data": global_data,
            "events": events,
            "timestamp": datetime.now(timezone.utc)
        }
    except Exception as e:
        logger.error(f"Error collecting digest data: {e}")
        return {
            "market_data": [],
            "gainers_losers": {"gainers": [], "losers": []},
            "global_data": {},
            "events": [],
            "timestamp": datetime.now(timezone.utc)
        }


if __name__ == "__main__":
    # Тест
    import asyncio
    
    async def test():
        data = await collect_digest_data()
        print("BTC Price:", data["market_data"][0]["current_price"] if data["market_data"] else "N/A")
        print("Gainers:", len(data["gainers_losers"].get("gainers", [])))
        print("Events:", len(data["events"]))
    
    asyncio.run(test())
