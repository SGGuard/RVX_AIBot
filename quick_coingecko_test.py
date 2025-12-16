#!/usr/bin/env python3
"""Quick test to verify CoinGecko integration works"""

import asyncio
import sys
from price_monitoring import PriceMonitor, get_quick_price, search_and_get_price

async def test_coingecko():
    print("🧪 Testing CoinGecko Integration...\n")
    
    # Test 1: Get Bitcoin price
    print("1️⃣ Testing get_quick_price('bitcoin')...")
    try:
        result = await get_quick_price("bitcoin")
        if result:
            print("✅ SUCCESS:")
            print(result)
            print()
        else:
            print("❌ No result\n")
    except Exception as e:
        print(f"❌ Error: {e}\n")
    
    # Test 2: Price Monitor
    print("2️⃣ Testing PriceMonitor.get_coin_price()...")
    try:
        async with PriceMonitor() as monitor:
            eth_price = await monitor.get_coin_price("ethereum")
            if eth_price:
                print("✅ Ethereum price data:")
                print(f"  💰 USD: ${eth_price.get('usd', 0):.2f}")
                print(f"  📈 24h Change: {eth_price.get('usd_24h_change', 0):.2f}%")
                print()
            else:
                print("❌ No result\n")
    except Exception as e:
        print(f"❌ Error: {e}\n")
    
    # Test 3: Search
    print("3️⃣ Testing search_and_get_price('doge')...")
    try:
        result = await search_and_get_price("doge")
        if result:
            print("✅ Search result:")
            print(result)
            print()
        else:
            print("❌ No result\n")
    except Exception as e:
        print(f"❌ Error: {e}\n")
    
    # Test 4: Multiple prices
    print("4️⃣ Testing get_multiple_prices()...")
    try:
        async with PriceMonitor() as monitor:
            prices = await monitor.get_multiple_prices(["bitcoin", "ethereum", "cardano"])
            if prices:
                print("✅ Multiple prices fetched:")
                for coin, data in prices.items():
                    print(f"  {coin}: ${data.get('usd', 0):.2f}")
                print()
            else:
                print("❌ No result\n")
    except Exception as e:
        print(f"❌ Error: {e}\n")
    
    print("🎉 CoinGecko integration test complete!")

if __name__ == "__main__":
    try:
        asyncio.run(test_coingecko())
    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted")
        sys.exit(0)
