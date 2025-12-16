"""
Price Monitoring Module - CoinGecko API Integration
Мониторинг цен криптовалют, price alerts, портфолио трекинг
"""

import logging
import aiohttp
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

COINGECKO_API_KEY = os.getenv('COINGECKO_API_KEY', '')
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
COINGECKO_PRO_BASE = "https://pro-api.coingecko.com/api/v3"

# Выбираем базу в зависимости от наличия ключа
BASE_URL = COINGECKO_PRO_BASE if COINGECKO_API_KEY else COINGECKO_BASE


class PriceMonitor:
    """Мониторинг цен с поддержкой API ключа CoinGecko"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_key = COINGECKO_API_KEY
        self.base_url = BASE_URL
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_coin_price(self, coin_id: str, vs_currency: str = "usd") -> Optional[Dict]:
        """
        Получить цену конкретной монеты
        
        Args:
            coin_id: ID монеты (например: 'bitcoin', 'ethereum')
            vs_currency: Валюта для сравнения (usd, eur, etc)
        
        Returns:
            Dict с ценой, изменением за 24h и другой информацией
        """
        try:
            url = f"{self.base_url}/simple/price"
            params = {
                "ids": coin_id,
                "vs_currencies": vs_currency,
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
                "include_last_updated_at": "true"
            }
            
            if self.api_key:
                params["x_cg_pro_api_key"] = self.api_key
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get(coin_id, {})
                else:
                    logger.error(f"❌ Price API error: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"❌ Error fetching price for {coin_id}: {e}")
            return None
    
    async def get_multiple_prices(self, coin_ids: List[str], vs_currency: str = "usd") -> Dict:
        """
        Получить цены нескольких монет одним запросом
        
        Args:
            coin_ids: Список ID монет
            vs_currency: Валюта
        
        Returns:
            Dict с ценами всех монет
        """
        try:
            url = f"{self.base_url}/simple/price"
            params = {
                "ids": ",".join(coin_ids),
                "vs_currencies": vs_currency,
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true"
            }
            
            if self.api_key:
                params["x_cg_pro_api_key"] = self.api_key
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"❌ Multiple prices API error: {resp.status}")
                    return {}
        except Exception as e:
            logger.error(f"❌ Error fetching multiple prices: {e}")
            return {}
    
    async def get_coin_details(self, coin_id: str) -> Optional[Dict]:
        """
        Получить детальную информацию о монете
        
        Args:
            coin_id: ID монеты
        
        Returns:
            Полная информация о монете
        """
        try:
            url = f"{self.base_url}/coins/{coin_id}"
            params = {
                "localization": "false",
                "tickers": "true",
                "market_data": "true",
                "community_data": "true"
            }
            
            if self.api_key:
                params["x_cg_pro_api_key"] = self.api_key
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"❌ Coin details API error: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"❌ Error fetching coin details: {e}")
            return None
    
    async def search_coins(self, query: str) -> List[Dict]:
        """
        Поиск монет по названию или символу
        
        Args:
            query: Строка поиска
        
        Returns:
            Список найденных монет
        """
        try:
            url = f"{self.base_url}/search"
            params = {"query": query}
            
            if self.api_key:
                params["x_cg_pro_api_key"] = self.api_key
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("coins", [])[:10]  # Top 10 results
                else:
                    logger.error(f"❌ Search API error: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"❌ Error searching coins: {e}")
            return []
    
    async def get_historical_price(self, coin_id: str, days: str = "30") -> Optional[List]:
        """
        Получить историческую цену монеты
        
        Args:
            coin_id: ID монеты
            days: Количество дней (1, 7, 30, 90, 365, max)
        
        Returns:
            Список исторических данных [timestamp, price]
        """
        try:
            url = f"{self.base_url}/coins/{coin_id}/market_chart"
            params = {
                "vs_currency": "usd",
                "days": days
            }
            
            if self.api_key:
                params["x_cg_pro_api_key"] = self.api_key
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("prices", [])
                else:
                    logger.error(f"❌ Historical price API error: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"❌ Error fetching historical price: {e}")
            return None


class PortfolioTracker:
    """Трекинг портфолио криптовалют с расчетом стоимости"""
    
    def __init__(self):
        self.monitor = None
    
    async def __aenter__(self):
        self.monitor = PriceMonitor()
        await self.monitor.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.monitor:
            await self.monitor.__aexit__(exc_type, exc_val, exc_tb)
    
    async def calculate_portfolio_value(self, holdings: Dict[str, float]) -> Tuple[float, Dict]:
        """
        Рассчитать стоимость портфолио
        
        Args:
            holdings: Dict {coin_id: amount} например {'bitcoin': 0.5, 'ethereum': 2}
        
        Returns:
            Кортеж (total_value_usd, detailed_dict)
        """
        if not holdings:
            return 0.0, {}
        
        try:
            prices = await self.monitor.get_multiple_prices(list(holdings.keys()))
            
            total_value = 0.0
            detailed = {}
            
            for coin_id, amount in holdings.items():
                coin_data = prices.get(coin_id, {})
                if coin_data:
                    price = coin_data.get('usd', 0)
                    value = amount * price
                    total_value += value
                    detailed[coin_id] = {
                        "amount": amount,
                        "price_usd": price,
                        "value_usd": value,
                        "change_24h": coin_data.get('usd_24h_change', 0)
                    }
            
            return total_value, detailed
        except Exception as e:
            logger.error(f"❌ Error calculating portfolio: {e}")
            return 0.0, {}
    
    async def get_portfolio_summary(self, holdings: Dict[str, float]) -> str:
        """
        Получить красивую сводку портфолио
        
        Args:
            holdings: Dict {coin_id: amount}
        
        Returns:
            Отформатированная строка с данными портфолио
        """
        total_value, detailed = await self.calculate_portfolio_value(holdings)
        
        if not detailed:
            return "❌ Не удалось получить данные портфолио"
        
        summary = "💼 **ВАШ ПОРТФОЛИО**\n\n"
        
        for coin_id, data in detailed.items():
            change = "📈" if data["change_24h"] >= 0 else "📉"
            summary += (
                f"{change} **{coin_id.upper()}**\n"
                f"  💰 {data['amount']:.4f} @ ${data['price_usd']:.2f}\n"
                f"  📊 ${data['value_usd']:.2f} ({data['change_24h']:.2f}%)\n\n"
            )
        
        summary += f"<b>💵 ИТОГО: ${total_value:.2f}</b>"
        
        return summary


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

async def get_quick_price(coin_id: str) -> Optional[str]:
    """Быстро получить текущую цену монеты"""
    async with PriceMonitor() as monitor:
        price_data = await monitor.get_coin_price(coin_id)
        if price_data:
            price = price_data.get('usd', 0)
            change = price_data.get('usd_24h_change', 0)
            market_cap = price_data.get('usd_market_cap', 0)
            
            emoji = "📈" if change >= 0 else "📉"
            
            return (
                f"💱 **{coin_id.upper()}**\n"
                f"💰 Цена: ${price:.2f}\n"
                f"{emoji} 24h: {change:+.2f}%\n"
                f"📊 Market Cap: ${market_cap:,.0f}"
            )
        return None


async def search_and_get_price(query: str) -> Optional[str]:
    """Найти монету и получить её цену"""
    async with PriceMonitor() as monitor:
        results = await monitor.search_coins(query)
        if not results:
            return "❌ Монета не найдена"
        
        # Берем первый результат
        coin = results[0]
        coin_id = coin.get('id')
        
        # Получаем цену
        price_data = await monitor.get_coin_price(coin_id)
        if price_data:
            price = price_data.get('usd', 0)
            change = price_data.get('usd_24h_change', 0)
            
            emoji = "📈" if change >= 0 else "📉"
            
            return (
                f"💱 **{coin['name']} ({coin['symbol'].upper()})**\n"
                f"💰 Цена: ${price:.2f}\n"
                f"{emoji} 24h: {change:+.2f}%"
            )
        return None


if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Test price monitoring
        async with PriceMonitor() as monitor:
            price = await monitor.get_coin_price("bitcoin")
            print("Bitcoin:", price)
        
        # Test portfolio tracking
        holdings = {"bitcoin": 0.5, "ethereum": 2}
        async with PortfolioTracker() as tracker:
            total, detailed = await tracker.calculate_portfolio_value(holdings)
            print(f"Portfolio value: ${total:.2f}")
            for coin, data in detailed.items():
                print(f"  {coin}: ${data['value_usd']:.2f}")
    
    asyncio.run(test())
