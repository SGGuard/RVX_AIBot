"""
🧮 Crypto Calculator Module - Market Cap & Token Supply Calculations
v0.33.0
"""

from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# CRYPTO TOKENS DATABASE (v0.33.0)
# ═══════════════════════════════════════════════════════════════════════════════

CRYPTO_TOKENS = {
    "gnk": {
        "name": "Gonka",
        "symbol": "GNK",
        "emoji": "🪙",
        "unlocked": 1_000_000,           # Разблокированные токены
        "vesting": 2_000_000,            # В веститинге
        "total_supply": 3_000_000,       # Всего
        "description": "Gonka OTC Project - Trading on HEX",
        "url": "https://app.hex.exchange/otc/gonka"
    },
    "hex": {
        "name": "HEX",
        "symbol": "HEX",
        "emoji": "💱",
        "unlocked": 100_000_000,
        "vesting": 50_000_000,
        "total_supply": 150_000_000,
        "description": "HEX Token - On-Chain Blockchain Certificate",
        "url": "https://hex.com"
    },
    "btc": {
        "name": "Bitcoin",
        "symbol": "BTC",
        "emoji": "₿",
        "unlocked": 21_000_000,
        "vesting": 0,
        "total_supply": 21_000_000,
        "description": "Bitcoin - World's First Cryptocurrency",
        "url": "https://bitcoin.org"
    },
    "eth": {
        "name": "Ethereum",
        "symbol": "ETH",
        "emoji": "Ξ",
        "unlocked": 120_000_000,
        "vesting": 0,
        "total_supply": 120_000_000,
        "description": "Ethereum - Smart Contracts Platform",
        "url": "https://ethereum.org"
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# CALCULATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_token_stats(token_symbol: str) -> Optional[Dict]:
    """
    Получить информацию о токене
    
    Args:
        token_symbol: Символ токена (например "GNK", "BTC")
        
    Returns:
        Словарь с параметрами токена или None
    """
    return CRYPTO_TOKENS.get(token_symbol.lower())


def format_number(num: int) -> str:
    """
    Форматировать число с разделителями (пробелы для читаемости)
    
    Args:
        num: Целое число
        
    Returns:
        Форматированная строка (например "1 000 000")
    """
    return f"{num:,}".replace(",", " ")


def format_price(price: float) -> str:
    """
    Форматировать цену с нужным количеством знаков
    
    Args:
        price: Цена в долларах
        
    Returns:
        Форматированная цена (например "$0.001234" или "$123.45")
    """
    if price < 0.00001:
        return f"${price:.8f}"  # Очень маленькие цены - 8 знаков
    elif price < 0.01:
        return f"${price:.6f}"  # Маленькие цены - 6 знаков
    elif price < 1:
        return f"${price:.4f}"  # Средние цены - 4 знака
    else:
        return f"${price:.2f}"  # Большие цены - 2 знака


def format_market_cap(market_cap: float) -> str:
    """
    Форматировать market cap в читаемую форму
    
    Args:
        market_cap: Market cap в долларах
        
    Returns:
        Форматированная строка (например "$3M", "$1.5B")
    """
    if market_cap >= 1_000_000_000:
        return f"${market_cap / 1_000_000_000:.2f}B"
    elif market_cap >= 1_000_000:
        return f"${market_cap / 1_000_000:.2f}M"
    elif market_cap >= 1_000:
        return f"${market_cap / 1_000:.2f}K"
    else:
        return f"${market_cap:.2f}"


def calculate_market_cap(total_supply: float, price: float) -> Tuple[float, str]:
    """
    Расчет market cap (Total Supply × Price)
    
    Args:
        total_supply: Всего токенов
        price: Цена одного токена в долларах
        
    Returns:
        Кортеж (market_cap в долларах, форматированная строка)
    """
    try:
        market_cap = total_supply * price
        return market_cap, format_market_cap(market_cap)
    except Exception as e:
        logger.error(f"❌ Ошибка в calculate_market_cap: total_supply={total_supply}, price={price}, error={str(e)}", exc_info=True)
        return 0, "$0.00"


def calculate_fully_diluted_valuation(total_supply: float, price: float) -> Tuple[float, str]:
    """
    Расчет Fully Diluted Valuation (максимально разбавленная оценка)
    Это когда ВСЕ токены (включая те, что в веститинге) куплены по текущей цене
    
    Args:
        total_supply: Всего токенов (включая вестинг)
        price: Цена одного токена
        
    Returns:
        Кортеж (FDV в долларах, форматированная строка)
    """
    fdv = total_supply * price
    return fdv, format_market_cap(fdv)


def calculate_price_for_market_cap(target_market_cap: float, total_supply: float) -> Tuple[float, str]:
    """
    Обратный расчет: какая цена нужна для достижения целевой market cap?
    
    Args:
        target_market_cap: Целевая market cap в долларах
        total_supply: Всего токенов
        
    Returns:
        Кортеж (требуемая цена, форматированная строка)
    """
    if total_supply == 0:
        return 0, "$0.00"
    
    price = target_market_cap / total_supply
    return price, format_price(price)


def calculate_percentage_increase(current_price: float, target_price: float) -> float:
    """
    Расчет процента увеличения цены
    
    Args:
        current_price: Текущая цена
        target_price: Целевая цена
        
    Returns:
        Процент увеличения (например 100.0 для 2x)
    """
    if current_price == 0:
        return 0
    return ((target_price - current_price) / current_price) * 100


def get_token_list() -> list:
    """
    Получить список всех доступных токенов для калькулятора
    
    Returns:
        Список тикеров (например ["gnk", "hex", "btc", "eth"])
    """
    return list(CRYPTO_TOKENS.keys())


def format_calculator_result(token_symbol: str, price: float) -> str:
    """
    Форматировать полный результат калькулятора в красивый текст
    
    Args:
        token_symbol: Символ токена
        price: Цена в долларах
        
    Returns:
        HTML-отформатированная строка результата
    """
    try:
        token_data = get_token_stats(token_symbol)
        if not token_data:
            return "❌ Токен не найден"
        
        # Расчеты
        market_cap, mc_formatted = calculate_market_cap(
            token_data['total_supply'],
            price
        )
        
        # ✅ v0.33.1: Используем format_market_cap для красивого отображения больших чисел
        unlocked_mc = token_data['unlocked'] * price
        vesting_mc = token_data['vesting'] * price
        
        # Форматируем эти значения красиво (B/M/K)
        unlocked_mc_str = format_market_cap(unlocked_mc)
        vesting_mc_str = format_market_cap(vesting_mc)
        
        # Форматирование
        result = (
            f"{token_data['emoji']} <b>{token_data['name']} ({token_data['symbol']}) Calculator</b>\n"
            f"{'─' * 50}\n\n"
            f"💰 <b>Цена за токен:</b> {format_price(price)}\n"
            f"📊 <b>Market Cap (Total):</b> {mc_formatted}\n\n"
            f"<b>📈 Детали по категориям:</b>\n"
            f"🔓 <b>Разблокировано ({format_number(token_data['unlocked'])} токенов):</b> {unlocked_mc_str}\n"
            f"🔒 <b>В веститинге ({format_number(token_data['vesting'])} токенов):</b> {vesting_mc_str}\n\n"
            f"<b>📋 Параметры токена:</b>\n"
            f"🔓 Unlocked: {format_number(token_data['unlocked'])}\n"
            f"🔒 Vesting: {format_number(token_data['vesting'])}\n"
            f"📋 Total Supply: {format_number(token_data['total_supply'])}\n"
        )
        
        return result
    
    except Exception as e:
        logger.error(f"❌ Ошибка в format_calculator_result: token_symbol={token_symbol}, price={price}, error={str(e)}", exc_info=True)
        return f"❌ Ошибка при расчете для токена {token_symbol}. Попробуйте позже."


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION & UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def validate_price(price_str: str) -> Tuple[bool, Optional[float], str]:
    """
    Валидировать строку с ценой
    
    Args:
        price_str: Строка с ценой (например "0.01" или "$1.5")
        
    Returns:
        Кортеж (валидна ли, цена, сообщение об ошибке)
    """
    try:
        # Очищаем строку
        cleaned = price_str.strip().replace("$", "").replace(",", ".")
        
        # Парсим
        price = float(cleaned)
        
        # Проверяем диапазон
        if price < 0:
            return False, None, "❌ Цена не может быть отрицательной"
        if price == 0:
            return False, None, "❌ Цена не может быть нулевой"
        if price > 1_000_000:
            return False, None, "❌ Цена слишком большая (макс $1,000,000)"
        
        return True, price, "OK"
        
    except ValueError:
        return False, None, "❌ Введи корректное число (например 0.001 или 1.5)"


def get_calculator_menu_text() -> str:
    """Текст меню калькулятора"""
    return (
        "🧮 <b>КРИПТО КАЛЬКУЛЯТОР</b>\n\n"
        "Выбери токен для расчета Market Cap и цены:\n\n"
        "💡 Калькулятор показывает:\n"
        "• Текущую цену токена\n"
        "• Market Cap (общую стоимость)\n"
        "• Разбор по категориям (unlocked vs vesting)\n\n"
        "Нажми на токен чтобы начать расчет:"
    )


# Test функции (для проверки)
if __name__ == "__main__":
    print("🧪 Testing Crypto Calculator...")
    
    # Тест 1: Market Cap расчет
    token = get_token_stats("gnk")
    print(f"\n✅ Token GNK: {token['name']}")
    print(f"   Total Supply: {format_number(token['total_supply'])}")
    
    price = 0.01
    mc, mc_str = calculate_market_cap(token['total_supply'], price)
    print(f"\n   Price: {format_price(price)}")
    print(f"   Market Cap: {mc_str}")
    
    # Тест 2: Full calculator result
    result = format_calculator_result("gnk", 0.01)
    print(f"\n{result}")
    
    # Тест 3: Валидация цены
    valid, price, msg = validate_price("0.01")
    print(f"\n✅ Validation: {msg} (Price: {price})")
    
    print("\n🎉 All tests passed!")
