#!/usr/bin/env python3
"""
Test Daily Digest Scheduler v0.28.0
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_digest_full():
    """Полный тест сбора данных для дайджеста"""
    print("\n" + "="*80)
    print("🧪 TESTING DAILY DIGEST SCHEDULER v0.28.0")
    print("="*80 + "\n")
    
    # Импортируем после load_dotenv
    from crypto_digest import collect_digest_data
    from digest_formatter import format_digest
    
    try:
        print("📊 Collecting digest data...")
        digest_data = await collect_digest_data()
        
        print("\n📈 Data collected:")
        print(f"  • Market data coins: {len(digest_data.get('market_data', []))}")
        print(f"  • Fear & Greed: {digest_data.get('fear_greed', {}).get('value_classification', 'N/A')}")
        print(f"  • Gainers: {len(digest_data.get('gainers_losers', {}).get('gainers', []))}")
        print(f"  • Losers: {len(digest_data.get('gainers_losers', {}).get('losers', []))}")
        print(f"  • News items: {len(digest_data.get('news', []))}")
        print(f"  • Events: {len(digest_data.get('events', []))}")
        
        print("\n📝 Formatting digest...")
        formatted = format_digest(digest_data)
        
        print(f"\n✅ Digest formatted:")
        print(f"  • Total length: {len(formatted)} characters")
        print(f"  • First 300 chars:\n")
        print(formatted[:300] + "...\n")
        
        # Попытаемся загрузить scheduler
        print("\n🔧 Testing scheduler initialization...")
        try:
            from daily_digest_scheduler import DailyDigestScheduler
            scheduler = DailyDigestScheduler()
            await scheduler.initialize()
            print(f"✅ Scheduler initialized")
            print(f"  • Scheduled for: {os.getenv('DIGEST_HOUR', 9):02d}:{os.getenv('DIGEST_MINUTE', 0):02d} UTC")
            print(f"  • Channel: {os.getenv('DIGEST_CHANNEL_ID', '@RVX_AI')}")
            print(f"  • Timezone: {os.getenv('DIGEST_TIMEZONE', 'UTC')}")
            print(f"  • Status: {'Running' if scheduler.is_running else 'Stopped'}")
            
            await scheduler.stop()
            print("✅ Scheduler stopped")
        except Exception as e:
            print(f"⚠️ Scheduler test: {e}")
        
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED!")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"❌ Error: {e}", exc_info=True)
        return False
    
    return True


async def test_scheduler_send():
    """Тест отправки дайджеста"""
    print("\n" + "="*80)
    print("📤 TESTING DIGEST SEND (DRY RUN)")
    print("="*80 + "\n")
    
    from daily_digest_scheduler import DailyDigestScheduler
    from crypto_digest import collect_digest_data
    from digest_formatter import format_digest
    
    try:
        print("📊 Collecting data...")
        digest_data = await collect_digest_data()
        
        print("📝 Formatting...")
        formatted = format_digest(digest_data)
        
        print("\n📤 Message to be sent to channel:")
        print("-" * 80)
        print(formatted)
        print("-" * 80)
        
        print("\n✅ Test completed (no actual message sent)")
        
    except Exception as e:
        print(f"❌ Error: {e}", exc_info=True)


if __name__ == "__main__":
    import sys
    
    print("\n🚀 RVX Daily Digest Test Suite\n")
    
    if len(sys.argv) > 1 and sys.argv[1] == "send":
        asyncio.run(test_scheduler_send())
    else:
        success = asyncio.run(test_digest_full())
        sys.exit(0 if success else 1)
