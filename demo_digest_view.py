#!/usr/bin/env python3
"""
Demo of Daily Digest - показывает как выглядит пост
Не требует реальных API ключей!
"""

from datetime import datetime

# Демо-данные (как будто пришли от CoinGecko)
demo_data = {
    "market_data": [
        {
            "id": "bitcoin",
            "name": "Bitcoin",
            "symbol": "BTC",
            "current_price": 43250.50,
            "price_change_percentage_24h": 2.45,
            "market_cap": 850000000000
        },
        {
            "id": "ethereum",
            "name": "Ethereum",
            "symbol": "ETH",
            "current_price": 2305.20,
            "price_change_percentage_24h": 1.82,
            "market_cap": 277000000000
        },
        {
            "id": "solana",
            "name": "Solana",
            "symbol": "SOL",
            "current_price": 198.45,
            "price_change_percentage_24h": 12.56,
            "market_cap": 72000000000
        },
        {
            "id": "polkadot",
            "name": "Polkadot",
            "symbol": "DOT",
            "current_price": 8.92,
            "price_change_percentage_24h": 10.23,
            "market_cap": 10000000000
        },
        {
            "id": "ripple",
            "name": "XRP",
            "symbol": "XRP",
            "current_price": 2.15,
            "price_change_percentage_24h": -8.34,
            "market_cap": 120000000000
        },
        {
            "id": "cardano",
            "name": "Cardano",
            "symbol": "ADA",
            "current_price": 1.08,
            "price_change_percentage_24h": -6.12,
            "market_cap": 39000000000
        }
    ],
    "fear_greed": {
        "value": "45",
        "value_classification": "Neutral"
    },
    "gainers_losers": {
        "gainers": [
            {"name": "Solana", "symbol": "SOL", "price_change_percentage_24h": 12.56},
            {"name": "Polkadot", "symbol": "DOT", "price_change_percentage_24h": 10.23},
        ],
        "losers": [
            {"name": "XRP", "symbol": "XRP", "price_change_percentage_24h": -8.34},
            {"name": "Cardano", "symbol": "ADA", "price_change_percentage_24h": -6.12},
        ]
    },
    "global_data": {
        "total_market_cap": {"usd": 1820000000000},
        "total_volume": {"usd": 85400000000},
        "btc_market_cap_percentage": 52.3
    },
    "news": [
        {
            "title": "Bitcoin ETF Approvals Drive Institutional Adoption",
            "link": "https://cointelegraph.com/news/bitcoin",
            "source": "Cointelegraph"
        },
        {
            "title": "Ethereum Shanghai Upgrade Improves Staking Rewards",
            "link": "https://cointelegraph.com/news/eth",
            "source": "Cointelegraph"
        },
        {
            "title": "FED Decision Impacts Crypto Markets",
            "link": "https://cointelegraph.com/news/fed",
            "source": "Cointelegraph"
        }
    ],
    "events": [
        {
            "time": "14:30 UTC",
            "title": "FOMC Meeting Minutes",
            "importance": "High",
            "impact": "USD, Crypto"
        },
        {
            "time": "10:00 UTC",
            "title": "ECB President Speech",
            "importance": "Medium",
            "impact": "EUR, Crypto"
        }
    ],
    "timestamp": datetime.now()
}


def format_price(price):
    if price is None:
        return "N/A"
    return f"${price:,.2f}"


def format_percent(percent):
    if percent is None:
        return "N/A"
    if percent > 0:
        return f"📈 +{percent:.2f}%"
    else:
        return f"📉 {percent:.2f}%"


def demo_digest():
    """Показать как выглядит полный дайджест"""
    
    print("\n" + "="*80)
    print("🚀 КРИПТО ДАЙДЖЕСТ НА ДЕНЬ")
    print("="*80)
    
    # ОБЗОР РЫНКА
    print("\n💰 <b>ОБЗОР РЫНКА</b>")
    
    btc = demo_data["market_data"][0]
    eth = demo_data["market_data"][1]
    
    btc_link = f"<a href='https://www.coingecko.com/en/coins/bitcoin'>Bitcoin</a>"
    eth_link = f"<a href='https://www.coingecko.com/en/coins/ethereum'>Ethereum</a>"
    
    print(f"₿ {btc_link}: {format_price(btc['current_price'])} {format_percent(btc['price_change_percentage_24h'])}")
    print(f"Ξ {eth_link}: {format_price(eth['current_price'])} {format_percent(eth['price_change_percentage_24h'])}")
    
    global_data = demo_data["global_data"]
    if global_data.get("total_market_cap", {}).get("usd"):
        market_cap = global_data["total_market_cap"]["usd"]
        print(f"\n💰 Market Cap: ${market_cap/1e12:.2f}T")
    
    if global_data.get("btc_market_cap_percentage"):
        btc_dom = global_data["btc_market_cap_percentage"]
        print(f"🔗 BTC Dominance: {btc_dom:.1f}%")
    
    if global_data.get("total_volume", {}).get("usd"):
        volume = global_data["total_volume"]["usd"]
        print(f"📊 24h Volume: ${volume/1e9:.2f}B")
    
    # FEAR & GREED
    print("\n😱 <b>FEAR & GREED INDEX</b>")
    fear_greed = demo_data.get("fear_greed", {})
    if fear_greed:
        value = fear_greed.get("value", "N/A")
        classification = fear_greed.get("value_classification", "")
        print(f"Значение: {value} ({classification})")
        
        # Интерпретация
        if int(value) < 25:
            mood = "Экстремальный страх 😱"
        elif int(value) < 45:
            mood = "Страх 😟"
        elif int(value) < 55:
            mood = "Нейтрально 😐"
        elif int(value) < 75:
            mood = "Жадность 🤑"
        else:
            mood = "Экстремальная жадность 🔥"
        
        print(f"Настроение: {mood}")
    
    # GAINERS & LOSERS
    print("\n📈 <b>TOP GAINERS (24h)</b>")
    gainers = demo_data.get("gainers_losers", {}).get("gainers", [])
    for i, coin in enumerate(gainers[:3], 1):
        change = coin.get("price_change_percentage_24h", 0)
        print(f"{i}. 🟢 <b>{coin['name']} ({coin['symbol']})</b>: +{change:.2f}%")
    
    print("\n📉 <b>TOP LOSERS (24h)</b>")
    losers = demo_data.get("gainers_losers", {}).get("losers", [])
    for i, coin in enumerate(losers[:3], 1):
        change = coin.get("price_change_percentage_24h", 0)
        print(f"{i}. 🔴 <b>{coin['name']} ({coin['symbol']})</b>: {change:.2f}%")
    
    # НОВОСТИ
    print("\n📰 <b>ПОСЛЕДНИЕ НОВОСТИ КРИПТО</b>")
    news = demo_data.get("news", [])
    for item in news[:5]:
        title = item.get("title", "")[:60]
        link = item.get("link", "")
        source = item.get("source", "News")
        
        if link:
            print(f"• <a href='{link}'>{title}...</a> ({source})")
        else:
            print(f"• {title} ({source})")
    
    # СОБЫТИЯ
    print("\n⏰ <b>ВАЖНЫЕ СОБЫТИЯ НА ДЕНЬ</b>")
    events = demo_data.get("events", [])
    for event in events[:5]:
        time = event.get("time", "")
        title = event.get("title", "")
        importance = event.get("importance", "")
        
        emoji = "🔴" if importance == "High" else "🟡" if importance == "Medium" else "🟢"
        print(f"{emoji} <b>{time}</b> - {title}")
    
    # ПОДПИСЬ
    print("\n" + "="*80)
    print(f"⏱️ Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M:%S UTC')}")
    print("💬 RVX AI - Your Crypto Intelligence")
    print("="*80 + "\n")


if __name__ == "__main__":
    demo_digest()
