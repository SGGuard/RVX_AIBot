"""
Digest Formatter - Красивое форматирование крипто дайджеста
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DigestFormatter:
    """Форматирует данные дайджеста в красивый Telegram пост"""
    
    @staticmethod
    def format_price(price: Optional[float]) -> str:
        """Форматировать цену с символом валюты"""
        if price is None:
            return "N/A"
        if price >= 1000:
            return f"${price:,.0f}"
        elif price >= 1:
            return f"${price:,.2f}"
        else:
            return f"${price:.6f}"
    
    @staticmethod
    def format_percent(percent: Optional[float]) -> str:
        """Форматировать процент с цветом"""
        if percent is None:
            return "N/A"
        
        if percent >= 0:
            return f"<b>+{percent:.2f}%</b> 📈"
        else:
            return f"<b>{percent:.2f}%</b> 📉"
    
    @staticmethod
    def create_coingecko_link(coin_id: str, coin_name: str) -> str:
        """Создать ссылку на CoinGecko"""
        return f'<a href="https://www.coingecko.com/en/coins/{coin_id}">{coin_name}</a>'
    
    @staticmethod
    def create_coinmarketcap_link(coin_name: str) -> str:
        """Создать ссылку на CoinMarketCap"""
        coin_slug = coin_name.lower().replace(" ", "-")
        return f'<a href="https://coinmarketcap.com/currencies/{coin_slug}">{coin_name}</a>'
    
    def format_market_overview(self, data: Dict) -> str:
        """Форматировать обзор рынка"""
        if not data.get("market_data"):
            return "❌ Данные недоступны"
        
        market = data["market_data"]
        global_data = data.get("global_data", {}).get("data", {})
        
        # Основные монеты
        btc = next((m for m in market if m["symbol"].upper() == "BTC"), None)
        eth = next((m for m in market if m["symbol"].upper() == "ETH"), None)
        
        text = "📉 <b>Обзор рынка</b>\n\n"
        
        if btc:
            btc_link = self.create_coingecko_link("bitcoin", "Bitcoin")
            text += f"₿ {btc_link}: {self.format_price(btc['current_price'])} {self.format_percent(btc['price_change_percentage_24h'])}\n"
        
        if eth:
            eth_link = self.create_coingecko_link("ethereum", "Ethereum")
            text += f"Ξ {eth_link}: {self.format_price(eth['current_price'])} {self.format_percent(eth['price_change_percentage_24h'])}\n"
        
        # Market Cap
        if global_data.get("total_market_cap", {}).get("usd"):
            market_cap = global_data["total_market_cap"]["usd"]
            text += f"\n💰 Market Cap: ${market_cap/1e12:.2f}T\n"
        
        # BTC Dominance
        if global_data.get("btc_market_cap_percentage"):
            btc_dom = global_data["btc_market_cap_percentage"]
            text += f"🔗 BTC Dominance: {btc_dom:.1f}%\n"
        
        # Volume
        if global_data.get("total_volume", {}).get("usd"):
            volume = global_data["total_volume"]["usd"]
            text += f"📊 24h Volume: ${volume/1e9:.2f}B\n"
        
        return text
    
    def format_fear_greed(self, fear_greed: Optional[Dict]) -> str:
        """Форматировать Fear & Greed Index"""
        if not fear_greed:
            return ""
        
        value = int(fear_greed.get("value", 0))
        text = fear_greed.get("value_classification", "")
        
        # Эмодзи в зависимости от значения
        if value < 20:
            emoji = "😨"
        elif value < 40:
            emoji = "😟"
        elif value < 50:
            emoji = "😐"
        elif value < 70:
            emoji = "🙂"
        else:
            emoji = "🤑"
        
        return f"\n{emoji} <b>Fear & Greed Index:</b> {value}/100 ({text})\n"
    
    def format_gainers_losers(self, gainers_losers: Dict) -> str:
        """Форматировать gainers и losers"""
        text = ""
        
        gainers = gainers_losers.get("gainers", [])[:3]
        losers = gainers_losers.get("losers", [])[:3]
        
        if gainers:
            text += "\n📈 <b>Топ Gainers (24h)</b>\n"
            for coin in gainers:
                coin_link = self.create_coingecko_link(coin["id"], coin["name"])
                percent = coin.get("price_change_percentage_24h", 0)
                text += f"• {coin_link}: <b>+{percent:.2f}%</b>\n"
        
        if losers:
            text += "\n📉 <b>Топ Losers (24h)</b>\n"
            for coin in losers:
                coin_link = self.create_coingecko_link(coin["id"], coin["name"])
                percent = coin.get("price_change_percentage_24h", 0)
                text += f"• {coin_link}: <b>{percent:.2f}%</b>\n"
        
        return text
    
    def format_top_coins(self, market_data: List[Dict]) -> str:
        """Форматировать топ монеты"""
        if not market_data:
            return ""
        
        text = "\n📊 <b>Топ монеты по рыночной капитализации</b>\n"
        
        for i, coin in enumerate(market_data[:10], 1):
            coin_link = self.create_coingecko_link(coin["id"], coin["name"])
            price = self.format_price(coin["current_price"])
            percent = coin.get("price_change_percentage_24h", 0)
            
            emoji = "📈" if percent > 0 else "📉"
            text += f"{i}. {coin_link}: {price} {emoji} <b>{percent:.2f}%</b>\n"
        
        return text
    
    def format_news(self, news: List[Dict]) -> str:
        """Форматировать новости"""
        if not news:
            return ""
        
        text = "\n📰 <b>Последние новости крипто</b>\n"
        
        for item in news[:5]:
            title = item.get("title", "")[:60]  # Обрезаем до 60 символов
            link = item.get("link", "")
            source = item.get("source", "News")
            
            if link:
                text += f"• <a href='{link}'>{title}...</a> ({source})\n"
            else:
                text += f"• {title} ({source})\n"
        
        return text
    
    def format_events(self, events: List[Dict]) -> str:
        """Форматировать важные события"""
        if not events:
            return ""
        
        text = "\n⏰ <b>Важные события на сегодня</b>\n"
        
        for event in events[:5]:
            time = event.get("time", "")
            title = event.get("title", "")
            importance = event.get("importance", "")
            
            emoji = "🔴" if importance == "High" else "🟡" if importance == "Medium" else "🟢"
            text += f"{emoji} <b>{time}</b> - {title}\n"
        
        return text
    
    def format_full_digest(self, data: Dict) -> str:
        """Создать полный дайджест"""
        
        digest = "🚀 <b>КРИПТО ДАЙДЖЕСТ НА ДЕНЬ</b>\n"
        digest += "=" * 50 + "\n"
        
        # Обзор рынка
        digest += self.format_market_overview(data)
        
        # Fear & Greed
        digest += self.format_fear_greed(data.get("fear_greed"))
        
        # Gainers/Losers
        digest += self.format_gainers_losers(data.get("gainers_losers", {}))
        
        # Топ монеты
        digest += self.format_top_coins(data.get("market_data", []))
        
        # Новости
        digest += self.format_news(data.get("news", []))
        
        # События
        digest += self.format_events(data.get("events", []))
        
        # Подпись
        digest += "\n" + "=" * 50 + "\n"
        digest += "⏱️ Обновлено: <code>" + datetime.now().strftime("%d.%m.%Y %H:%M:%S") + "</code>\n"
        digest += "💬 RVX AI - Your Crypto Intelligence\n"
        
        return digest


def format_digest(data: Dict) -> str:
    """Быстрое форматирование дайджеста"""
    formatter = DigestFormatter()
    return formatter.format_full_digest(data)


if __name__ == "__main__":
    # Тестовые данные
    test_data = {
        "market_data": [
            {
                "id": "bitcoin",
                "name": "Bitcoin",
                "symbol": "btc",
                "current_price": 43000,
                "price_change_percentage_24h": 2.5,
                "market_cap": 850000000000
            }
        ],
        "fear_greed": {
            "value": "45",
            "value_classification": "Neutral"
        },
        "gainers_losers": {
            "gainers": [],
            "losers": []
        },
        "global_data": {
            "data": {
                "total_market_cap": {"usd": 3200000000000},
                "total_volume": {"usd": 150000000000},
                "btc_market_cap_percentage": 54.5
            }
        },
        "news": [
            {
                "title": "Bitcoin hits new record",
                "link": "https://example.com",
                "source": "CoinTelegraph"
            }
        ],
        "events": [
            {
                "time": "14:30 UTC",
                "title": "FOMC Meeting",
                "importance": "High"
            }
        ]
    }
    
    formatter = DigestFormatter()
    print(formatter.format_full_digest(test_data))
