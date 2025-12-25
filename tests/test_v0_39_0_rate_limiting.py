"""
Unit tests for v0.39.0 Rate Limiting:
- IPRateLimiter class
- Thread safety
- Cleanup mechanism

Run: pytest tests/test_v0_39_0_rate_limiting.py -v
"""

import pytest
import time
from threading import Thread
from collections import defaultdict


# IPRateLimiter class (copied for testing)
class IPRateLimiter:
    """IP-based rate limiter for DDoS protection"""
    
    def __init__(self, max_requests: int = 30, window_seconds: int = 60, 
                 cleanup_interval: int = 300):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.cleanup_interval = cleanup_interval
        
        self.request_times = defaultdict(list)
        from threading import Lock
        self.lock = Lock()
        
        self.last_cleanup = time.time()
    
    def check_rate_limit(self, ip_address: str) -> bool:
        with self.lock:
            current_time = time.time()
            
            if current_time - self.last_cleanup > self.cleanup_interval:
                self._cleanup_old_entries(current_time)
                self.last_cleanup = current_time
            
            window_start = current_time - self.window_seconds
            self.request_times[ip_address] = [
                ts for ts in self.request_times[ip_address] 
                if ts > window_start
            ]
            
            if len(self.request_times[ip_address]) >= self.max_requests:
                return False
            
            self.request_times[ip_address].append(current_time)
            return True
    
    def get_remaining_requests(self, ip_address: str) -> int:
        with self.lock:
            current_time = time.time()
            window_start = current_time - self.window_seconds
            
            recent_requests = len([
                ts for ts in self.request_times[ip_address] 
                if ts > window_start
            ])
            
            return max(0, self.max_requests - recent_requests)
    
    def reset_ip(self, ip_address: str) -> None:
        with self.lock:
            if ip_address in self.request_times:
                del self.request_times[ip_address]
    
    def get_stats(self) -> dict:
        with self.lock:
            total_ips = len(self.request_times)
            blocked_ips = sum(
                1 for requests in self.request_times.values()
                if len(requests) >= self.max_requests
            )
            
            return {
                'total_tracked_ips': total_ips,
                'blocked_ips': blocked_ips,
                'max_requests_per_window': self.max_requests,
                'window_seconds': self.window_seconds,
                'cleanup_interval': self.cleanup_interval,
            }
    
    def _cleanup_old_entries(self, current_time: float) -> None:
        window_start = current_time - self.window_seconds
        cleanup_count = 0
        
        ips_to_remove = [
            ip for ip, timestamps in self.request_times.items()
            if not any(ts > window_start for ts in timestamps)
        ]
        
        for ip in ips_to_remove:
            del self.request_times[ip]
            cleanup_count += 1


# Tests
class TestIPRateLimiter:
    """Test IP-based rate limiting"""
    
    def test_initialization(self):
        """Verify rate limiter initializes correctly"""
        limiter = IPRateLimiter(max_requests=30, window_seconds=60)
        
        assert limiter.max_requests == 30
        assert limiter.window_seconds == 60
        assert len(limiter.request_times) == 0
    
    def test_single_request_allowed(self):
        """Verify first request is allowed"""
        limiter = IPRateLimiter(max_requests=5, window_seconds=60)
        
        assert limiter.check_rate_limit("192.168.1.1") is True
        assert len(limiter.request_times["192.168.1.1"]) == 1
    
    def test_multiple_requests_within_limit(self):
        """Verify requests within limit are allowed"""
        limiter = IPRateLimiter(max_requests=5, window_seconds=60)
        ip = "192.168.1.1"
        
        # Make 5 requests (should all pass)
        for i in range(5):
            assert limiter.check_rate_limit(ip) is True
        
        assert len(limiter.request_times[ip]) == 5
    
    def test_rate_limit_exceeded(self):
        """Verify requests are blocked when limit exceeded"""
        limiter = IPRateLimiter(max_requests=3, window_seconds=60)
        ip = "192.168.1.1"
        
        # Make 3 requests (should pass)
        for i in range(3):
            assert limiter.check_rate_limit(ip) is True
        
        # 4th request should be blocked
        assert limiter.check_rate_limit(ip) is False
        
        # Verify count didn't increase
        assert len(limiter.request_times[ip]) == 3
    
    def test_different_ips_independent(self):
        """Verify different IPs have independent limits"""
        limiter = IPRateLimiter(max_requests=2, window_seconds=60)
        
        ip1 = "192.168.1.1"
        ip2 = "192.168.1.2"
        
        # Make 2 requests from IP1
        assert limiter.check_rate_limit(ip1) is True
        assert limiter.check_rate_limit(ip1) is True
        assert limiter.check_rate_limit(ip1) is False  # Blocked
        
        # IP2 should still be able to make requests
        assert limiter.check_rate_limit(ip2) is True
        assert limiter.check_rate_limit(ip2) is True
        assert limiter.check_rate_limit(ip2) is False  # Blocked
    
    def test_remaining_requests(self):
        """Verify remaining requests calculation"""
        limiter = IPRateLimiter(max_requests=5, window_seconds=60)
        ip = "192.168.1.1"
        
        assert limiter.get_remaining_requests(ip) == 5
        
        limiter.check_rate_limit(ip)
        assert limiter.get_remaining_requests(ip) == 4
        
        limiter.check_rate_limit(ip)
        assert limiter.get_remaining_requests(ip) == 3
    
    def test_reset_ip(self):
        """Verify IP reset clears request history"""
        limiter = IPRateLimiter(max_requests=3, window_seconds=60)
        ip = "192.168.1.1"
        
        # Make 3 requests (limit reached)
        for i in range(3):
            limiter.check_rate_limit(ip)
        
        assert limiter.check_rate_limit(ip) is False  # Blocked
        
        # Reset IP
        limiter.reset_ip(ip)
        
        # Should be able to make requests again
        assert limiter.check_rate_limit(ip) is True
        assert len(limiter.request_times[ip]) == 1
    
    def test_get_stats(self):
        """Verify statistics reporting"""
        limiter = IPRateLimiter(max_requests=2, window_seconds=60)
        
        # Make requests from multiple IPs
        limiter.check_rate_limit("192.168.1.1")
        limiter.check_rate_limit("192.168.1.1")
        limiter.check_rate_limit("192.168.1.2")
        
        stats = limiter.get_stats()
        
        assert stats['total_tracked_ips'] == 2
        assert stats['blocked_ips'] == 1  # IP 1.1 is at limit
        assert stats['max_requests_per_window'] == 2
        assert stats['window_seconds'] == 60
    
    def test_window_expiry(self):
        """Verify requests expire after window closes"""
        limiter = IPRateLimiter(max_requests=3, window_seconds=1)  # 1 second window
        ip = "192.168.1.1"
        
        # Make 3 requests (limit reached)
        for i in range(3):
            limiter.check_rate_limit(ip)
        
        assert limiter.check_rate_limit(ip) is False  # Blocked
        
        # Wait for window to expire
        time.sleep(1.1)
        
        # Should be able to make new requests
        assert limiter.check_rate_limit(ip) is True
        assert len(limiter.request_times[ip]) == 1
    
    def test_thread_safety(self):
        """Verify thread-safe operations"""
        limiter = IPRateLimiter(max_requests=100, window_seconds=60)
        ip = "192.168.1.1"
        results = []
        
        def make_requests(count):
            for _ in range(count):
                result = limiter.check_rate_limit(ip)
                results.append(result)
        
        # Create multiple threads making requests simultaneously
        threads = [
            Thread(target=make_requests, args=(25,))
            for _ in range(4)
        ]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Should have made 100 requests total
        assert len(results) == 100
        
        # All should be accepted (within limit)
        assert all(results)
        
        # Next request should be blocked
        assert limiter.check_rate_limit(ip) is False
    
    def test_cleanup_inactive_ips(self):
        """Verify cleanup removes inactive IPs"""
        limiter = IPRateLimiter(
            max_requests=1,
            window_seconds=1,
            cleanup_interval=0  # Cleanup on every call
        )
        
        # Make request from IP
        limiter.check_rate_limit("192.168.1.1")
        assert len(limiter.request_times) == 1
        
        # Wait for window to expire
        time.sleep(1.1)
        
        # Trigger cleanup by making another request
        limiter.check_rate_limit("192.168.1.2")
        
        # First IP should be removed (no recent requests)
        assert "192.168.1.1" not in limiter.request_times or \
               len(limiter.request_times["192.168.1.1"]) == 0
    
    def test_custom_limits(self):
        """Verify custom limit parameters work"""
        limiter = IPRateLimiter(max_requests=10, window_seconds=120)
        
        assert limiter.max_requests == 10
        assert limiter.window_seconds == 120
        
        # Fill to limit
        for i in range(10):
            assert limiter.check_rate_limit("192.168.1.1") is True
        
        # Should block at limit
        assert limiter.check_rate_limit("192.168.1.1") is False


class TestRateLimitingIntegration:
    """Integration tests for rate limiting"""
    
    def test_typical_ddos_scenario(self):
        """Simulate typical DDoS attack scenario"""
        limiter = IPRateLimiter(max_requests=30, window_seconds=60)
        
        # Attacker from single IP making 50 requests
        attacker_ip = "10.0.0.1"
        successful = 0
        blocked = 0
        
        for _ in range(50):
            if limiter.check_rate_limit(attacker_ip):
                successful += 1
            else:
                blocked += 1
        
        # Should allow 30, block 20
        assert successful == 30
        assert blocked == 20
        
        # Legitimate user still works
        assert limiter.check_rate_limit("10.0.0.2") is True
    
    def test_gradual_requests(self):
        """Test normal user behavior with gradual requests"""
        limiter = IPRateLimiter(max_requests=30, window_seconds=60)
        
        # Make requests gradually
        for _ in range(30):
            assert limiter.check_rate_limit("10.0.0.1") is True
        
        # Hit limit
        assert limiter.check_rate_limit("10.0.0.1") is False
        
        # But stats show we're at limit
        stats = limiter.get_stats()
        assert stats['blocked_ips'] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
