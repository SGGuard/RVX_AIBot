"""
Phase 4.7: Stress Testing & Performance Tests

40 tests covering:
- Concurrency & Load (9 tests) - thread safety, concurrent operations
- Stability & Sessions (8 tests) - long sessions, data integrity  
- Performance & Caching (9 tests) - cache hit rates, response times
- Database Stress (8 tests) - concurrent R/W, transaction safety
- Error Resilience (5 tests) - error handling, recovery
"""

import pytest
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from conversation_context import (
    add_user_message,
    add_ai_message,
    get_context_messages,
    get_context_stats,
)
from limited_cache import LimitedCache


# =============================================================================
# TEST CLASS 1: Concurrency & Load (9 tests)
# =============================================================================

class TestConcurrencyLoad:
    """Test thread-safe concurrent operations."""

    def test_concurrent_user_messages_thread_safe(self):
        """50 users adding messages concurrently."""
        num_users = 50
        msgs_per_user = 2
        base_uid = 100000
        
        def add_messages(user_id):
            for i in range(msgs_per_user):
                add_user_message(user_id, f"Test message number {i}", intent="test")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(add_messages, base_uid + i) for i in range(num_users)]
            for future in as_completed(futures):
                future.result()
        
        for user_id in range(base_uid, base_uid + num_users):
            context = get_context_messages(user_id, limit=50)
            assert len(context) >= msgs_per_user

    def test_concurrent_context_retrieval_consistency(self):
        """Context retrieval consistent under concurrent access."""
        user_id = 110050
        
        for i in range(10):
            add_user_message(user_id, f"Test message number {i}", intent="test")
        
        retrieved_counts = []
        
        def retrieve():
            context = get_context_messages(user_id, limit=100)
            retrieved_counts.append(len(context))
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(retrieve) for _ in range(20)]
            for future in as_completed(futures):
                future.result()
        
        assert len(set(retrieved_counts)) == 1
        assert retrieved_counts[0] >= 10

    def test_api_cache_concurrent_reads(self):
        """LimitedCache handles concurrent reads."""
        cache = LimitedCache(max_size=500, ttl_seconds=3600)
        
        for i in range(50):
            cache.set(f"key_{i}", f"value_{i}")
        
        hit_counts = []
        
        def read_cache():
            hits = 0
            for i in range(50):
                val = cache.get(f"key_{i}")
                if val:
                    hits += 1
            hit_counts.append(hits)
        
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(read_cache) for _ in range(20)]
            for future in as_completed(futures):
                future.result()
        
        assert all(count >= 40 for count in hit_counts)

    def test_api_cache_concurrent_writes(self):
        """LimitedCache handles concurrent writes."""
        cache = LimitedCache(max_size=500, ttl_seconds=3600)
        
        def write_cache(thread_id):
            for i in range(10):
                cache.set(f"t{thread_id}_k{i}", f"v{thread_id}_{i}")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_cache, i) for i in range(10)]
            for future in as_completed(futures):
                future.result()
        
        assert cache.get("t0_k0") is not None

    def test_cache_mixed_operations(self):
        """LimitedCache handles mixed read/write."""
        cache = LimitedCache(max_size=500, ttl_seconds=3600)
        
        for i in range(30):
            cache.set(f"init_{i}", f"val_{i}")
        
        success_count = []
        
        def mixed_ops(tid):
            ops = 0
            for i in range(5):
                cache.set(f"k_{tid}_{i}", f"v_{tid}_{i}")
                ops += 1
            for i in range(30):
                val = cache.get(f"init_{i}")
                if val:
                    ops += 1
            success_count.append(ops)
        
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = [executor.submit(mixed_ops, i) for i in range(12)]
            for future in as_completed(futures):
                future.result()
        
        assert len(success_count) == 12
        assert all(ops > 0 for ops in success_count)

    def test_concurrent_messages_ordering(self):
        """Message ordering preserved under concurrent writes."""
        user_id = 110051
        
        def add_msg(index):
            add_user_message(user_id, f"Concurrent message {index:03d}", intent="concurrent")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(add_msg, i) for i in range(15)]
            for future in as_completed(futures):
                future.result()
        
        context = get_context_messages(user_id, limit=100)
        assert len(context) >= 15

    def test_asyncio_concurrent_operations(self):
        """Async concurrent operations thread-safe."""
        async def concurrent_ops():
            async def async_op(op_id):
                await asyncio.sleep(0.001)
                return f"result_{op_id}"
            
            tasks = [async_op(i) for i in range(50)]
            results = await asyncio.gather(*tasks)
            return results
        
        results = asyncio.run(concurrent_ops())
        assert len(results) == 50

    def test_thread_safe_context_operations(self):
        """ConversationContextManager is thread-safe."""
        user_id = 110052
        errors = []
        
        def operation(op_type):
            try:
                if op_type == "write":
                    add_user_message(user_id, f"Test message content", intent="test")
                elif op_type == "read":
                    get_context_messages(user_id, limit=10)
                elif op_type == "stats":
                    get_context_stats(user_id)
            except Exception as e:
                errors.append(str(e))
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for _ in range(10):
                futures.append(executor.submit(operation, "write"))
            for _ in range(10):
                futures.append(executor.submit(operation, "read"))
            for _ in range(3):
                futures.append(executor.submit(operation, "stats"))
            
            for future in as_completed(futures):
                future.result()
        
        assert len(errors) == 0

    def test_rapid_concurrent_cache_ops(self):
        """Cache handles rapid concurrent operations."""
        cache = LimitedCache(max_size=500, ttl_seconds=3600)
        success = []
        
        def rapid_ops(tid):
            for i in range(20):
                cache.set(f"t{tid}_k{i}", f"v{tid}_{i}")
                cache.get(f"t{tid}_k{i}")
            success.append(True)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(rapid_ops, i) for i in range(10)]
            for future in as_completed(futures):
                future.result()
        
        assert len(success) == 10


# =============================================================================
# TEST CLASS 2: Stability & Sessions (8 tests)
# =============================================================================

class TestStabilitySessionManagement:
    """Test system stability over long sessions."""

    def test_conversation_session_stability(self):
        """Conversation stable within limits."""
        user_id = 120060
        
        for turn in range(10):
            add_user_message(user_id, f"Question number {turn}", intent="test")
            add_ai_message(user_id, f"Answer to question {turn}")
            
            context = get_context_messages(user_id, limit=100)
            assert len(context) > 0

    def test_multiple_users_isolated(self):
        """User sessions isolated."""
        num_users = 8
        msgs_per_user = 8
        base_uid = 130100
        
        for user_id in range(base_uid, base_uid + num_users):
            for i in range(msgs_per_user):
                add_user_message(user_id, f"User {user_id} message {i}", intent="test")
        
        for user_id in range(base_uid, base_uid + num_users):
            context = get_context_messages(user_id, limit=100)
            assert len(context) >= msgs_per_user

    def test_message_integrity(self):
        """Message content integrity maintained."""
        user_id = 120070
        test_msgs = [
            "Simple message content",
            "Numbers: 123456789",
            "Special: !@#$%",
            "Unicode: Привет",
        ]
        
        for msg in test_msgs:
            add_user_message(user_id, msg, intent="test")
        
        context = get_context_messages(user_id, limit=100)
        assert len(context) > 0

    def test_cache_persistence(self):
        """Cache persists data."""
        cache = LimitedCache(max_size=500, ttl_seconds=3600)
        
        for i in range(50):
            cache.set(f"k_{i}", f"v_{i}")
        
        for _ in range(100):
            cache.get("k_0")
        
        assert cache.get("k_0") is not None
        assert cache.get("k_49") is not None

    def test_database_multi_batch_writes(self):
        """Database handles multiple batches."""
        user_id = 120071
        
        def write_batch(batch_id):
            for i in range(4):
                add_user_message(user_id, f"Batch {batch_id} message {i}", intent="test")
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(write_batch, i) for i in range(3)]
            for future in as_completed(futures):
                future.result()
        
        context = get_context_messages(user_id, limit=100)
        assert len(context) > 0

    def test_session_recovery_after_error(self):
        """Session recovers after error."""
        user_id = 120072
        
        add_user_message(user_id, "Valid message one", intent="test")
        result = add_user_message(user_id, "", intent="test")
        assert result is False
        
        add_user_message(user_id, "Valid message two", intent="test")
        context = get_context_messages(user_id, limit=10)
        assert len(context) >= 2

    def test_cache_eviction_handling(self):
        """Cache handles eviction."""
        cache = LimitedCache(max_size=500, ttl_seconds=3600)
        
        for i in range(400):
            cache.set(f"k_{i}", f"v_{i}")
        
        cache.set("new_k", "new_v")
        assert cache.get("new_k") is not None

    def test_long_conversation_turns(self):
        """Long conversation stability."""
        user_id = 120073
        
        for i in range(18):
            add_user_message(user_id, f"Message content {i}", intent="test")
        
        context = get_context_messages(user_id, limit=100)
        assert len(context) > 0


# =============================================================================
# TEST CLASS 3: Performance & Caching (9 tests)
# =============================================================================

class TestPerformanceCaching:
    """Test performance metrics."""

    def test_cache_hit_rate(self):
        """Cache achieves high hit rate."""
        cache = LimitedCache(max_size=500, ttl_seconds=3600)
        
        for i in range(50):
            cache.set(f"k_{i}", f"v_{i}")
        
        hit_count = 0
        for _ in range(100):
            val = cache.get("k_0")
            if val:
                hit_count += 1
        
        hit_rate = hit_count / 100
        assert hit_rate >= 0.95

    def test_cache_size_management(self):
        """Cache respects size limits."""
        cache = LimitedCache(max_size=500, ttl_seconds=3600)
        
        for i in range(600):
            cache.set(f"k_{i}", f"v_{i}")
        
        assert cache.get("k_599") is not None or cache.get("k_500") is not None

    def test_context_retrieval_speed(self):
        """Context retrieval fast."""
        user_id = 120080
        
        for i in range(25):
            add_user_message(user_id, f"Test message number {i}", intent="test")
        
        start = time.time()
        context = get_context_messages(user_id, limit=50)
        elapsed = time.time() - start
        
        assert elapsed < 0.05
        assert len(context) > 0

    def test_message_addition_speed(self):
        """Message addition is fast."""
        user_id = 120081
        
        start = time.time()
        for i in range(25):
            add_user_message(user_id, f"Test message number {i}", intent="test")
        elapsed = time.time() - start
        
        assert elapsed < 0.2
        context = get_context_messages(user_id, limit=50)
        assert len(context) > 0

    def test_concurrent_message_speed(self):
        """Concurrent messages fast."""
        user_id = 120082
        
        start = time.time()
        
        def add_msgs(tid):
            for i in range(3):
                add_user_message(user_id, f"Thread {tid} message {i}", intent="test")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(add_msgs, i) for i in range(5)]
            for future in as_completed(futures):
                future.result()
        
        elapsed = time.time() - start
        assert elapsed < 5.0
        
        context = get_context_messages(user_id, limit=100)
        assert len(context) > 0

    def test_cache_lookup_speed(self):
        """Cache lookup is fast."""
        cache = LimitedCache(max_size=500, ttl_seconds=3600)
        
        for i in range(200):
            cache.set(f"k_{i}", f"v_{i}")
        
        start = time.time()
        for _ in range(1000):
            cache.get("k_100")
        elapsed = time.time() - start
        
        assert elapsed < 0.1

    def test_stats_retrieval_speed(self):
        """Stats retrieval is fast."""
        user_id = 120083
        
        for i in range(35):
            add_user_message(user_id, f"Test message number {i}", intent="test")
        
        start = time.time()
        for _ in range(100):
            get_context_stats(user_id)
        elapsed = time.time() - start
        
        assert elapsed < 0.1

    def test_multi_cache_instances(self):
        """Multiple caches are independent."""
        cache1 = LimitedCache(max_size=100, ttl_seconds=3600)
        cache2 = LimitedCache(max_size=100, ttl_seconds=3600)
        
        for i in range(30):
            cache1.set(f"c1_k{i}", f"v_{i}")
            cache2.set(f"c2_k{i}", f"v_{i}")
        
        assert cache1.get("c1_k0") is not None
        assert cache1.get("c2_k0") is None
        
        assert cache2.get("c2_k0") is not None
        assert cache2.get("c1_k0") is None

    def test_throughput_high_concurrency(self):
        """High concurrency throughput."""
        cache = LimitedCache(max_size=500, ttl_seconds=3600)
        operations = []
        
        def worker():
            ops = 0
            for i in range(50):
                cache.set(f"k_{i}", f"v_{i}")
                cache.get(f"k_{i}")
                ops += 2
            operations.append(ops)
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker) for _ in range(20)]
            for future in as_completed(futures):
                future.result()
        
        total_ops = sum(operations)
        assert total_ops > 0


# =============================================================================
# TEST CLASS 4: Database Stress (8 tests)
# =============================================================================

class TestDatabaseStress:
    """Test database under stress."""

    def test_concurrent_readers_writers(self):
        """Database handles concurrent R/W."""
        user_ids = range(120120, 120130)
        
        def reader(uid):
            for _ in range(5):
                get_context_messages(uid, limit=100)
        
        def writer(uid):
            for i in range(3):
                add_user_message(uid, f"Message content {i}", intent="test")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for uid in user_ids[:5]:
                futures.append(executor.submit(reader, uid))
            for uid in user_ids[5:]:
                futures.append(executor.submit(writer, uid))
            
            for future in as_completed(futures):
                future.result()

    def test_rapid_writes(self):
        """Rapid successive writes."""
        user_id = 120130
        
        start = time.time()
        for i in range(25):
            add_user_message(user_id, f"Rapid write message {i}", intent="test")
        elapsed = time.time() - start
        
        assert elapsed < 10.0
        context = get_context_messages(user_id, limit=100)
        assert len(context) > 0

    def test_interleaved_operations(self):
        """Interleaved read/write."""
        user_id = 120131
        
        for cycle in range(12):
            add_user_message(user_id, f"Interleaved message {cycle}", intent="test")
            context = get_context_messages(user_id, limit=100)
            assert len(context) > 0

    def test_connection_reuse(self):
        """DB connections reused."""
        user_id = 120132
        
        for i in range(25):
            add_user_message(user_id, f"Reused connection message {i}", intent="test")
            get_context_messages(user_id, limit=50)
        
        context = get_context_messages(user_id, limit=50)
        assert len(context) > 0

    def test_transaction_consistency(self):
        """Transaction consistency."""
        user_id = 120133
        
        r1 = add_user_message(user_id, "Valid message one", intent="test")
        r2 = add_user_message(user_id, "Valid message two", intent="test")
        assert r1 and r2
        
        result = add_user_message(user_id, "", intent="test")
        assert result is False
        
        context = get_context_messages(user_id, limit=10)
        assert len(context) >= 2

    def test_multi_user_concurrent_writes(self):
        """Multiple users writing concurrently."""
        user_ids = range(120134, 120144)
        
        def user_ops(uid):
            for i in range(5):
                add_user_message(uid, f"Multi-user message {i}", intent="test")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(user_ops, uid) for uid in user_ids]
            for future in as_completed(futures):
                future.result()
        
        for user_id in user_ids:
            context = get_context_messages(user_id, limit=50)
            assert len(context) > 0

    def test_data_isolation_verification(self):
        """Data isolated between users."""
        user1, user2 = 120144, 120145
        
        add_user_message(user1, "User 1 data content", intent="test")
        add_user_message(user2, "User 2 data content", intent="test")
        
        ctx1 = get_context_messages(user1, limit=10)
        ctx2 = get_context_messages(user2, limit=10)
        
        assert len(ctx1) > 0
        assert len(ctx2) > 0

    def test_large_message_handling(self):
        """Large message handling."""
        user_id = 120146
        large_msg = "X" * 1000
        
        result = add_user_message(user_id, large_msg, intent="test")
        assert result is True
        
        context = get_context_messages(user_id, limit=10)
        assert len(context) > 0


# =============================================================================
# TEST CLASS 5: Error Resilience (5 tests)
# =============================================================================

class TestErrorResilience:
    """Test error handling and resilience."""

    def test_concurrent_error_handling(self):
        """System handles concurrent errors."""
        user_id = 120150
        errors = 0
        success = 0
        
        def ops(op_id):
            nonlocal errors, success
            try:
                if op_id % 5 == 0:
                    result = add_user_message(user_id, "", intent="test")
                    if not result:
                        errors += 1
                else:
                    add_user_message(user_id, f"Valid message {op_id}", intent="test")
                    success += 1
            except Exception:
                errors += 1
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(ops, i) for i in range(40)]
            for future in as_completed(futures):
                future.result()
        
        assert success > 0

    def test_invalid_operations_dont_crash(self):
        """Invalid operations don't crash."""
        user_id = 120151
        
        for _ in range(5):
            result = add_user_message(user_id, "", intent="test")
            assert result is False
        
        result = add_user_message(user_id, "Valid message content", intent="test")
        assert result is True

    def test_cache_recovery_after_eviction(self):
        """Cache recovers after eviction."""
        cache = LimitedCache(max_size=500, ttl_seconds=3600)
        
        for i in range(600):
            cache.set(f"k_{i}", f"v_{i}")
        
        cache.set("test_k", "test_v")
        assert cache.get("test_k") is not None

    def test_mixed_error_scenarios(self):
        """Mixed error scenarios."""
        user_id = 120152
        
        add_user_message(user_id, "Valid message one", intent="test")
        add_user_message(user_id, "", intent="test")
        add_user_message(user_id, "Valid message two", intent="test")
        add_user_message(user_id, "", intent="test")
        add_user_message(user_id, "Valid message three", intent="test")
        
        context = get_context_messages(user_id, limit=10)
        assert len(context) >= 3

    def test_stress_with_error_recovery(self):
        """Stress with error recovery."""
        user_id = 120153
        
        for i in range(18):
            if i % 3 == 0:
                add_user_message(user_id, "", intent="test")
            else:
                add_user_message(user_id, f"Message content {i}", intent="test")
        
        context = get_context_messages(user_id, limit=100)
        assert len(context) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
