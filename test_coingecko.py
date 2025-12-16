#!/usr/bin/env python3
"""Test CoinGecko API connectivity and response"""

import aiohttp
import asyncio
import json
from datetime import datetime

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

async def test_markets():
    """Test /coins/markets endpoint"""
    print("\n📊 Testing /coins/markets endpoint...")
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{COINGECKO_BASE}/coins/markets"
            # NOTE: aiohttp requires STRING values for params, not booleans/integers
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": "5",  # STRING, not int!
                "sparkline": "false"  # STRING, not bool!
            }
            
            print(f"  URL: {url}")
            print(f"  Params: {params}")
            
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(15)) as resp:
                print(f"  Status: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  ✅ Response received: {len(data)} coins")
                    if data:
                        print(f"  First coin: {data[0]['name']} ({data[0]['symbol'].upper()}) - ${data[0]['current_price']}")
                    return data
                else:
                    text = await resp.text()
                    print(f"  ❌ Error response: {text[:200]}")
                    return None
    except asyncio.TimeoutError:
        print("  ❌ Timeout!")
        return None
    except Exception as e:
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
        return None

async def test_global():
    """Test /global endpoint"""
    print("\n🌍 Testing /global endpoint...")
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{COINGECKO_BASE}/global"
            
            print(f"  URL: {url}")
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(15)) as resp:
                print(f"  Status: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  ✅ Response received")
                    if "data" in data:
                        print(f"  Market Cap: ${data['data'].get('total_market_cap', {}).get('usd', 'N/A')}")
                    return data
                else:
                    text = await resp.text()
                    print(f"  ❌ Error response: {text[:200]}")
                    return None
    except asyncio.TimeoutError:
        print("  ❌ Timeout!")
        return None
    except Exception as e:
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
        return None

async def test_trending():
    """Test /search/trending endpoint (alternative to fear & greed)"""
    print("\n🔥 Testing /search/trending endpoint...")
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{COINGECKO_BASE}/search/trending"
            
            print(f"  URL: {url}")
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(15)) as resp:
                print(f"  Status: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  ✅ Response received")
                    if "coins" in data:
                        print(f"  Trending coins: {len(data['coins'])}")
                    return data
                else:
                    text = await resp.text()
                    print(f"  ❌ Error response: {text[:200]}")
                    return None
    except asyncio.TimeoutError:
        print("  ❌ Timeout!")
        return None
    except Exception as e:
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
        return None

async def main():
    print(f"\n🔍 CoinGecko API Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)
    
    markets = await test_markets()
    global_data = await test_global()
    trending = await test_trending()
    
    print("\n" + "=" * 60)
    print("\n📊 Test Summary:")
    print(f"  Markets API: {'✅ Working' if markets else '❌ Failed'}")
    print(f"  Global API: {'✅ Working' if global_data else '❌ Failed'}")
    print(f"  Trending API: {'✅ Working' if trending else '❌ Failed'}")
    
    if markets and global_data and trending:
        print("\n✅ All endpoints working!")
    else:
        print("\n⚠️ Some endpoints failed - check network/API availability")

if __name__ == "__main__":
    asyncio.run(main())

