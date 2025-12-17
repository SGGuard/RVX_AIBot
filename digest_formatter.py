"""
Digest Formatter - Красивое форматирование крипто дайджеста
Улучшенная версия v0.5.0:
- Исключение стейблкоинов из топ монет
- Фильтрация мертвых ссылок в новостях
- Информативные события с указанием влияния
- Лучшая обработка ошибок Fear & Greed
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DigestFormatter:
    """Форматирует данные дайджеста в красивый Telegram пост"""
    
    # Список стейблкоинов которые нужно исключить
    STABLECOINS = {'USDT', 'USDC', 'BUSD', 'DAI', 'USDP', 'TUSD', 'GUSD', 'USDD', 'FRAX', 'LUSD', 'EURS', 'SUSD'}
    
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
    
    def is_stablecoin(self, coin_name: str, coin_symbol: str) -> bool:
        """Проверить является ли монета стейблкоином"""
        return coin_symbol.upper() in self.STABLECOINS or any(
            stable in coin_name.upper() for stable in self.STABLECOINS
        )
    
    @staticmethod
    def is_valid_news_url(url: str) -> bool:
        """Проверить валидность URL новости"""
        if not url:
            return False
        # Проверяем что это не битая ссылка и не заглушка
        invalid_patterns = ['404', 'example.com', 'localhost', '#', 'javascript:', 'tel:']
        return not any(pattern in url.lower() for pattern in invalid_patterns)
    
    def format_market_overview(self, data: Dict) -> str:
        """Форматировать обзор рынка"""
        if not data.get("market_data"):
            return "❌ <b>Обзор рынка:</b> Данные недоступны\n"
        
        market = data["market_data"]
        global_data = data.get("global_data", {}).get("data", {})
        
        # Основные монеты
        btc = next((m for m in market if m["symbol"].upper() == "BTC"), None)
        eth = next((m for m in market if m["symbol"].upper() == "ETH"), None)
        
        text = "📊 <b>Обзор рынка</b>\n\n"
        
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
            return "\n⚠️ <b>Fear & Greed Index:</b> <i>Недоступен на Demo API ключе</i>\n"
        
        try:
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
        except (TypeError, ValueError):
            return "\n⚠️ <b>Fear & Greed Index:</b> <i>Ошибка загрузки</i>\n"
    
    def format_gainers_losers(self, gainers_losers: Dict) -> str:
        """Форматировать gainers и losers (без стейблкоинов)"""
        text = ""
        
        gainers = gainers_losers.get("gainers", [])[:5]
        losers = gainers_losers.get("losers", [])[:5]
        
        # Фильтруем стейблкоины
        gainers = [g for g in gainers if not self.is_stablecoin(g.get("name", ""), g.get("symbol", ""))][:3]
        losers = [l for l in losers if not self.is_stablecoin(l.get("name", ""), l.get("symbol", ""))][:3]
        
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
        """Форматировать топ 10 монет (без стейблкоинов)"""
        if not market_data:
            return ""
        
        text = "\n📊 <b>Топ 10 монет по рыночной капитализации</b>\n"
        
        # Фильтруем стейблкоины и берем первые 10
        non_stable = [
            coin for coin in market_data 
            if not self.is_stablecoin(coin.get("name", ""), coin.get("symbol", ""))
        ][:10]
        
        for i, coin in enumerate(non_stable, 1):
            coin_link = self.create_coingecko_link(coin["id"], coin["name"])
            price = self.format_price(coin["current_price"])
            percent = coin.get("price_change_percentage_24h", 0)
            
            emoji = "📈" if percent > 0 else "📉"
            text += f"{i}. {coin_link}: {price} {emoji} <b>{percent:.2f}%</b>\n"
        
        return text
    
    def format_news(self, news: List[Dict]) -> str:
        """Форматировать новости (только с валидными ссылками)"""
        if not news:
            return ""
        
        # Фильтруем новости с валидными ссылками
        valid_news = [
            item for item in news 
            if self.is_valid_news_url(item.get("link", ""))
        ]
        
        if not valid_news:
            return "\n📰 <b>Последние новости крипто</b>\nℹ️ <i>Новости временно недоступны</i>\n"
        
        text = "\n📰 <b>Последние новости крипто</b>\n"
        
        for item in valid_news[:5]:
            title = item.get("title", "")[:75]  # Обрезаем до 75 символов
            link = item.get("link", "")
            source = item.get("source", "Cointelegraph")
            
            # Убираем HTML теги из заголовка если есть
            title = (title.replace("<b>", "")
                         .replace("</b>", "")
                         .replace("&amp;", "&")
                         .replace("&quot;", '"')
                         .replace("&#x27;", "'")
                         .strip())
            
            text += f"• <a href='{link}'>{title}</a>\n  <i>({source})</i>\n"
        
        return text
    
    def format_events(self, events: List[Dict]) -> str:
        """Форматировать важные события с деталями"""
        if not events:
            text = "\n⏰ <b>Важные события</b>\n"
            text += "🔔 <i>Нет запланированных событий на сегодня</i>\n"
            return text
        
        text = "\n⏰ <b>Важные события</b>\n"
        
        for event in events[:8]:  # Показываем до 8 событий
            time = event.get("time", "").replace(" UTC", "").strip()
            title = event.get("title", "")
            importance = event.get("importance", "Medium")
            impact = event.get("impact", "")
            
            emoji = "🔴" if importance == "High" else "🟡" if importance == "Medium" else "🟢"
            
            if impact:
                text += f"{emoji} <b>{time} UTC</b> - {title}\n   <i>Влияние: {impact}</i>\n"
            else:
                text += f"{emoji} <b>{time} UTC</b> - {title}\n"
        
        return text
    
    def format_full_digest(self, data: Dict) -> str:
        """Создать полный дайджест"""
        
        digest = "🚀 <b>КРИПТО ДАЙДЖЕСТ НА ДЕНЬ</b>\n"
        digest += "=" * 40 + "\n\n"
        
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
        digest += "\n" + "=" * 40 + "\n"
        digest += f"⏱️ <b>Обновлено:</b> <code>{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</code>\n"
        digest += "💬 <i>RVX AI - Your Crypto Intelligence</i>\n"
        
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
                "current_price": 87454,
                "price_change_percentage_24h": 1.59,
                "market_cap": 1720000000000
            },
            {
                "id": "ethereum",
                "name": "Ethereum",
                "symbol": "eth",
                "current_price": 2946,
                "price_change_percentage_24h": -0.39,
                "market_cap": 354000000000
            },
            {
                "id": "tether",
                "name": "Tether",
                "symbol": "usdt",
                "current_price": 0.999971,
                "price_change_percentage_24h": -0.01,
                "market_cap": 120000000000
            }
        ],
        "fear_greed": None,
        "gainers_losers": {
            "gainers": [],
            "losers": []
        },
        "global_data": {
            "data": {
                "total_market_cap": {"usd": 3060000000000},
                "total_volume": {"usd": 116370000000},
                "btc_market_cap_percentage": 54.2
            }
        },
        "news": [
            {
                "title": "Bitcoin hits new record high",
                "link": "https://cointelegraph.com/news/bitcoin-record",
                "source": "Cointelegraph"
            }
        ],
        "events": [
            {
                "time": "14:30 UTC",
                "title": "FOMC Meeting Minutes",
                "importance": "High",
                "impact": "USD, Crypto"
            }
        ]
    }
    
    formatter = DigestFormatter()
    print(formatter.format_full_digest(test_data))
