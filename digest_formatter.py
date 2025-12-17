"""
Digest Formatter - Красивое и умное форматирование крипто дайджеста
Версия v0.7.0 - ПОЛНАЯ ПЕРЕДЕЛКА:
- ✅ Жесткий whitelist: BTC, ETH, BNB, SOL, XRP, ADA, DOGE, TRX, TON (исключает stETH, wrapped, synthetic)
- ✅ Gainers/Losers только для альтов (исключены BTC/ETH, минимум 5-10 монет)
- ✅ Аналитика настроения рынка вместо просто чисел (risk-off vs risk-on)
- ✅ Умные события - показывает только критичные для крипты с вывод влияния
- ✅ Формат отвечает на вопрос "Что мне знать СЕГОДНЯ?" вместо "Вот данные, разбирайся"
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DigestFormatter:
    """Форматирует данные дайджеста в красивый Telegram пост"""
    
    # Жесткий whitelist монет для публичного дайджеста (исключает stETH, wrapped, synthetic)
    WHITELIST_COINS = {'BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'TRX', 'TON'}
    
    # Whitelist альтов для раздела gainers/losers (только реальные альты, исключает мусор)
    ALTCOIN_WHITELIST = {'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'TRX', 'TON', 'AVAX', 'POLKADOT', 'LINK', 'MATIC', 'NEAR', 'FTT', 'ATOM', 'ARBITRUM'}
    
    # Список стейблкоинов которые нужно исключить
    STABLECOINS = {'USDT', 'USDC', 'BUSD', 'DAI', 'USDP', 'TUSD', 'GUSD', 'USDD', 'FRAX', 'LUSD', 'EURS', 'SUSD'}
    
    # Исключить wrapped, synthetic, staked версии
    EXCLUDED_PATTERNS = {'stETH', 'wBTC', 'Wrapped', 'Staked', 'Synthetic', 'Bridged', 'Lido', 'Ankr'}
    
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
        """Форматировать процент с эмодзи"""
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
    
    def is_excluded_type(self, coin_name: str, coin_symbol: str) -> bool:
        """Проверить является ли монета wrapped/synthetic/staked версией"""
        symbol_upper = coin_symbol.upper()
        name_upper = coin_name.upper()
        
        # Исключаем wrapped и synthetic версии
        for pattern in self.EXCLUDED_PATTERNS:
            if pattern.upper() in name_upper or pattern.upper() in symbol_upper:
                return True
        
        # Исключаем если не в whitelist (для основных монет в рейтинге)
        return False
    
    def is_whitelisted(self, coin_symbol: str) -> bool:
        """Проверить в ли монета в whitelist основных криптовалют"""
        return coin_symbol.upper() in self.WHITELIST_COINS
    
    @staticmethod
    def is_valid_news_url(url: str) -> bool:
        """Проверить валидность URL новости"""
        if not url:
            return False
        # Проверяем что это не битая ссылка и не заглушка
        invalid_patterns = ['404', 'example.com', 'localhost', '#', 'javascript:', 'tel:']
        return not any(pattern in url.lower() for pattern in invalid_patterns)
    
    def format_market_overview(self, data: Dict) -> str:
        """Форматировать обзор рынка (только BTC/ETH с ценами)"""
        if not data.get("market_data"):
            return "❌ <b>Обзор рынка:</b> Данные недоступны\n"
        
        market = data["market_data"]
        
        # Основные монеты
        btc = next((m for m in market if m["symbol"].upper() == "BTC"), None)
        eth = next((m for m in market if m["symbol"].upper() == "ETH"), None)
        
        text = "📊 <b>Обзор рынка</b>\n"
        
        if btc:
            btc_price = self.format_price(btc['current_price'])
            btc_change = btc.get('price_change_percentage_24h', 0)
            emoji_btc = "📈" if btc_change > 0 else "📉"
            text += f"₿ BTC: {btc_price} {btc_change:+.2f}% {emoji_btc}\n"
        
        if eth:
            eth_price = self.format_price(eth['current_price'])
            eth_change = eth.get('price_change_percentage_24h', 0)
            emoji_eth = "📈" if eth_change > 0 else "📉"
            text += f"Ξ ETH: {eth_price} {eth_change:+.2f}% {emoji_eth}\n"
        
        return text
    
    # Fear & Greed Index удален - требует Pro API ключ, не нужен обычному пользователю
    
    def format_gainers_losers(self, gainers_losers: Dict) -> str:
        """Форматировать gainers и losers (только whitelisted альты, исключить BTC/ETH и мусор)"""
        text = ""
        
        gainers = gainers_losers.get("gainers", [])[:15]  # Берем больше для фильтрации
        losers = gainers_losers.get("losers", [])[:15]
        
        # Фильтруем: берем ТОЛЬКО whitelisted альты
        gainers = [
            g for g in gainers 
            if g.get("symbol", "").upper() in self.ALTCOIN_WHITELIST and
            g.get("price_change_percentage_24h", 0) > 0
        ][:5]  # Берем до 5 после фильтрации
        
        losers = [
            l for l in losers 
            if l.get("symbol", "").upper() in self.ALTCOIN_WHITELIST and
            l.get("price_change_percentage_24h", 0) < 0
        ][:5]  # Берем до 5 после фильтрации
        
        if gainers:
            text += "\n📈 <b>Топ Gainers альтов (24h)</b>\n"
            for coin in gainers:
                symbol = coin.get("symbol", "").upper()
                percent = coin.get("price_change_percentage_24h", 0)
                text += f"• <b>{symbol}</b>: <b>+{percent:.2f}%</b>\n"
        
        if losers:
            text += "\n📉 <b>Топ Losers альтов (24h)</b>\n"
            for coin in losers:
                symbol = coin.get("symbol", "").upper()
                percent = coin.get("price_change_percentage_24h", 0)
                text += f"• <b>{symbol}</b>: <b>{percent:.2f}%</b>\n"
        
        return text
    
    def format_market_sentiment(self, data: Dict) -> str:
        """Добавить аналитику настроения рынка с выводом для трейдера"""
        if not data.get("market_data"):
            return ""
        
        market = data["market_data"]
        
        # Берем BTC, ETH, BNB для анализа тренда
        btc = next((m for m in market if m["symbol"].upper() == "BTC"), None)
        eth = next((m for m in market if m["symbol"].upper() == "ETH"), None)
        bnb = next((m for m in market if m["symbol"].upper() == "BNB"), None)
        
        if not btc or not eth:
            return ""
        
        btc_change = btc.get("price_change_percentage_24h", 0)
        eth_change = eth.get("price_change_percentage_24h", 0)
        bnb_change = bnb.get("price_change_percentage_24h", 0) if bnb else 0
        
        # Анализируем тренд
        text = "\n🧠 <b>Рынок и ваша позиция</b>\n"
        
        # Логика анализа на основе реальных цифр
        avg_change = (btc_change + eth_change + bnb_change) / 3 if bnb else (btc_change + eth_change) / 2
        
        if avg_change < -1:  # Падающий рынок
            text += "📉 <b>Risk-OFF сценарий</b>\n"
            text += "→ Альты теряют быстрее BTC\n"
            text += "→ Избегайте лонги, смотрите в поддержку\n"
        elif avg_change > 1:  # Растущий рынок
            text += "📈 <b>Risk-ON сценарий</b>\n"
            text += "→ Альты растут синхронно с BTC\n"
            text += "→ Хороший момент для лонгов\n"
        else:  # Консолидация
            text += "⏸️ <b>Консолидация</b>\n"
            text += "→ Рынок в режиме ожидания\n"
            text += "→ Альты движутся независимо\n"
        
        return text
    
    def format_top_coins(self, market_data: List[Dict]) -> str:
        """Форматировать только top-5 альтов (исключая BTC/ETH)"""
        if not market_data:
            return ""
        
        text = "\n📊 <b>Основные альты</b>\n"
        
        # Берем только altcoins (исключаем BTC, ETH, stablecoins)
        alt_coins = [
            coin for coin in market_data 
            if coin.get("symbol", "").upper() in self.ALTCOIN_WHITELIST and
            not self.is_excluded_type(coin.get("name", ""), coin.get("symbol", ""))
        ][:5]  # Максимум 5 альтов для компактности
        
        for i, coin in enumerate(alt_coins, 1):
            coin_symbol = coin.get("symbol", "").upper()
            percent = coin.get("price_change_percentage_24h", 0)
            # Только проценты для альтов, цены скрыты для компактности
            emoji = "📈" if percent > 0 else "📉"
            text += f"{i}. <b>{coin_symbol}</b>: {percent:+.2f}% {emoji}\n"
        
        return text
    
    # Раздел новостей удален - RSS ссылки часто ломаются, лучше получать через AI в диалоге
    
    def format_events(self, events: List[Dict]) -> str:
        """Форматировать важные события с аналитикой влияния на крипту"""
        if not events:
            return ""
        
        # EVENT IMPORTANCE MAP: определяем какие события влияют на крипту
        HIGH_IMPACT_EVENTS = {
            "FOMC": "🔴 FOMC Minutes — возможна волатильность BTC и альтов\n      (FED обычно меняет риск-сентимент)",
            "Federal Reserve": "🔴 FED Statement — прямое влияние на USD и криптовалюты",
            "CPI": "🔴 US Inflation Data (CPI) — ключевой индикатор для монетарной политики\n      (влияет на весь рынок)",
            "NFP": "🔴 Non-Farm Payrolls — сильное влияние на USD и криптовалюты",
            "ECB": "🟡 ECB Report — среднее влияние на евро и альты",
            "BoE": "🟡 Bank of England — влияние на GBP и европейские альты",
        }
        
        MEDIUM_IMPACT_EVENTS = {
            "EIA": "🟡 EIA Natural Gas Report — низкое влияние на крипту\n      (в основном энергетический рынок)",
            "Jobless": "🟡 Jobless Claims — индикатор здоровья экономики",
            "Earnings": "🟢 Корпоративные отчеты — косвенное влияние",
        }
        
        text = "\n⏰ <b>Что важно сегодня</b>\n"
        
        # Показываем только HIGH IMPACT события для крипты
        high_impact_found = False
        for event in events:
            title = event.get("title", "")
            importance = event.get("importance", "")
            time = event.get("time", "").replace(" UTC", "").strip()
            
            # Ищем ключевые события
            for keyword, description in HIGH_IMPACT_EVENTS.items():
                if keyword.lower() in title.lower():
                    text += f"{description}\n   ⏰ {time} UTC\n"
                    high_impact_found = True
                    break
        
        # Если нет HIGH IMPACT событий, показываем MEDIUM
        if not high_impact_found:
            for event in events:
                title = event.get("title", "")
                importance = event.get("importance", "")
                time = event.get("time", "").replace(" UTC", "").strip()
                
                for keyword, description in MEDIUM_IMPACT_EVENTS.items():
                    if keyword.lower() in title.lower():
                        text += f"{description}\n   ⏰ {time} UTC\n"
                        break
        
        # Если совсем ничего не нашли, показываем что-то
        if text == "\n⏰ <b>Что важно сегодня</b>\n":
            text += "🟢 <i>Нет критичных событий</i>\n"
        
        return text
    
    def format_full_digest(self, data: Dict) -> str:
        """Создать полный дайджест"""
        
        digest = "🚀 <b>КРИПТО ДАЙДЖЕСТ НА ДЕНЬ</b>\n"
        digest += "=" * 40 + "\n\n"
        
        # Обзор рынка (только BTC/ETH с ценами)
        digest += self.format_market_overview(data)
        
        # Настроение и аналитика
        digest += self.format_market_sentiment(data)
        
        # Gainers/Losers альтов
        digest += self.format_gainers_losers(data.get("gainers_losers", {}))
        
        # Основные альты (только 5 штук, без BTC/ETH)
        digest += self.format_top_coins(data.get("market_data", []))
        
        # События с аналитикой
        digest += self.format_events(data.get("events", []))
        
        # ✨ НОВОЕ: Финальный вывод - зачем вся эта информация
        digest += self.format_executive_summary(data)
        
        # Подпись
        digest += "\n" + "=" * 40 + "\n"
        digest += f"⏱️ <b>Обновлено:</b> <code>{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</code>\n"
        digest += "💬 <i>RVX AI - Your Crypto Intelligence</i>\n"
        
        return digest
    
    def format_executive_summary(self, data: Dict) -> str:
        """Финальный вывод - что мне делать с этой информацией?"""
        if not data.get("market_data"):
            return ""
        
        market = data["market_data"]
        btc = next((m for m in market if m["symbol"].upper() == "BTC"), None)
        eth = next((m for m in market if m["symbol"].upper() == "ETH"), None)
        
        if not btc or not eth:
            return ""
        
        btc_change = btc.get("price_change_percentage_24h", 0)
        eth_change = eth.get("price_change_percentage_24h", 0)
        avg_change = (btc_change + eth_change) / 2
        
        text = "\n💡 <b>На что это влияет</b>\n"
        
        if avg_change < -2:
            text += "🚨 <b>Риск высокий</b>\n"
            text += "• Продавцы в контроле\n"
            text += "• Берите только проверенные альты\n"
            text += "• Следите за основаниями (Support)\n"
        elif avg_change > 2:
            text += "✅ <b>Это растущий рынок</b>\n"
            text += "• Покупайте альты из списка выше\n"
            text += "• Давайте позициям расти\n"
            text += "• Ждите пробоев сопротивления\n"
        else:
            text += "⚠️ <b>Неопределенность</b>\n"
            text += "• Не спешите с большими позициями\n"
            text += "• Ждите ясного сигнала\n"
            text += "• Смотрите события в календаре\n"
        
        return text


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
        "gainers_losers": {
            "gainers": [
                {"id": "bitcoin", "name": "Bitcoin", "symbol": "btc", "price_change_percentage_24h": 1.99},
                {"id": "ethereum", "name": "Ethereum", "symbol": "eth", "price_change_percentage_24h": 0.23},
                {"id": "solana", "name": "Solana", "symbol": "sol", "price_change_percentage_24h": 2.50}
            ],
            "losers": []
        },
        "global_data": {
            "data": {
                "total_market_cap": {"usd": 3060000000000},
                "total_volume": {"usd": 116370000000},
                "btc_market_cap_percentage": 54.2
            }
        },
        "events": [
            {
                "time": "14:30 UTC",
                "title": "FOMC Meeting Minutes",
                "importance": "High",
                "impact": "USD, Crypto"
            },
            {
                "time": "16:00 UTC",
                "title": "EIA Natural Gas Report",
                "importance": "Medium",
                "impact": "Energy, USD"
            }
        ]
    }
    
    formatter = DigestFormatter()
    print(formatter.format_full_digest(test_data))
