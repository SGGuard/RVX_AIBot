# Rate Limiting Implementation (v0.39.0 - QUICK WIN #3)

## Overview
IP-based rate limiting for DDoS protection with automatic cleanup and thread-safe operations.

## Features

### Core Functionality
- **Per-IP Rate Limiting**: Track requests per client IP
- **Configurable Limits**: Default 30 requests per 60 seconds
- **Automatic Cleanup**: Remove inactive IP entries to prevent memory leaks
- **Thread-Safe**: Lock-based synchronization for concurrent requests
- **Statistics**: Monitor blocked IPs and active connections

### Protection Against
- DDoS attacks from single IP
- Brute force attempts
- API abuse
- Resource exhaustion

## Implementation Details

### IPRateLimiter Class
```python
class IPRateLimiter:
    """IP-based rate limiter for DDoS protection."""
    
    def __init__(self, max_requests: int = 30, window_seconds: int = 60, 
                 cleanup_interval: int = 300):
        """
        Args:
            max_requests: Maximum requests allowed (default: 30)
            window_seconds: Time window in seconds (default: 60)
            cleanup_interval: Cleanup old entries every N seconds (default: 300)
        """
```

### Public Methods

#### `check_rate_limit(ip_address: str) -> bool`
Check if request from IP should be allowed.

**Returns:** 
- `True` if request is allowed
- `False` if rate limit exceeded

**Example:**
```python
if not rate_limiter.check_rate_limit(user_ip):
    await send_error_response("Too many requests")
    return
```

#### `get_remaining_requests(ip_address: str) -> int`
Get remaining requests before hitting limit.

**Returns:** Number of requests remaining (0 if at limit)

#### `reset_ip(ip_address: str) -> None`
Reset rate limit for specific IP (admin function).

#### `get_stats() -> Dict[str, Any]`
Get rate limiter statistics.

**Returns:**
```python
{
    'total_tracked_ips': 42,
    'blocked_ips': 3,
    'max_requests_per_window': 30,
    'window_seconds': 60,
    'cleanup_interval': 300
}
```

## Integration in bot.py

### Location
- **Class Definition**: Lines 535-650 (IPRateLimiter class)
- **Global Instance**: Line 652 (`rate_limiter = IPRateLimiter(...)`)
- **Usage**: In `handle_message()` function after input validation (lines 12680-12700)

### Usage Example
```python
# In handle_message() handler
if not rate_limiter.check_rate_limit(client_ip):
    remaining = rate_limiter.get_remaining_requests(client_ip)
    await update.message.reply_text(
        "⚠️ Слишком много запросов. Пожалуйста, подождите минуту."
    )
    return
```

## Configuration

### Default Settings
```python
rate_limiter = IPRateLimiter(
    max_requests=30,       # 30 requests
    window_seconds=60,     # per 60 seconds (1 minute)
    cleanup_interval=300   # cleanup every 5 minutes
)
```

### Customization
To change limits, modify in bot.py:
```python
# For stricter limits (DDoS-prone environment):
rate_limiter = IPRateLimiter(max_requests=20, window_seconds=60)

# For looser limits (high-volume legitimate traffic):
rate_limiter = IPRateLimiter(max_requests=50, window_seconds=60)
```

## Algorithm

### Request Tracking
1. On each request:
   - Get current timestamp
   - Filter old timestamps outside window
   - Check if count >= max_requests
   - Return allow/block decision
   - Add current timestamp to list

### Time Window
- Window = current_time - window_seconds
- Only timestamps > window_start are kept
- Older timestamps are automatically discarded

### Cleanup
- Runs every cleanup_interval seconds
- Removes IPs with no recent requests
- Prevents unbounded memory growth
- Thread-safe with lock protection

## Testing

### Test Coverage
**Total Tests:** 14 tests, all passing ✅

**Test Categories:**
1. **Basic Functionality** (3 tests)
   - Initialization
   - Single request allowed
   - Multiple requests within limit

2. **Rate Limiting** (4 tests)
   - Limit exceeded
   - Different IPs independent
   - Remaining requests calculation
   - IP reset

3. **Advanced Features** (3 tests)
   - Statistics reporting
   - Window expiry
   - Thread safety (concurrent requests)

4. **Maintenance** (1 test)
   - Cleanup of inactive IPs

5. **Integration** (3 tests)
   - Typical DDoS scenario
   - Gradual legitimate requests
   - Custom limits

### Running Tests
```bash
# Run rate limiting tests only
pytest tests/test_v0_39_0_rate_limiting.py -v

# Run all v0.39.0 tests
pytest tests/test_v0_39_0*.py -v

# With coverage
pytest tests/test_v0_39_0*.py --cov=bot --cov-report=html
```

## Performance Characteristics

### Time Complexity
- `check_rate_limit()`: O(N) where N = requests in window
  - Typically N ≤ 30, so effectively O(1)
  - Filter operation: O(N) once per request
  
- `get_remaining_requests()`: O(N)
- `get_stats()`: O(M) where M = number of tracked IPs

### Space Complexity
- O(M * N) where:
  - M = number of unique IPs
  - N = max requests per window (typically 30)
  - Example: 1000 IPs * 30 requests = ~30KB memory

### Cleanup Benefits
- Removes unused entries periodically
- Prevents unbounded growth
- ~300 seconds (5 min) default interval
- Customizable for different deployments

## Error Handling

### User Message
When rate limit exceeded, user sees:
```
⚠️ Слишком много запросов. Пожалуйста, подождите минуту перед следующим запросом.

Это ограничение существует для защиты сервиса от злоупотреблений.
```

### Logging
- WARNING: "Rate limit exceeded for IP {ip}: {current}/{max}"
- DEBUG: "Rate limiter cleanup: removed {count} inactive IPs"

## Security Considerations

### Strengths
✅ Protects against simple DDoS attacks
✅ Per-IP isolation prevents one attacker affecting others
✅ Thread-safe for concurrent environments
✅ Automatic memory management

### Limitations
⚠️ No distributed rate limiting (single-instance only)
⚠️ IP-based (unreliable behind proxies/VPNs)
⚠️ No persistent storage (resets on restart)
⚠️ No user-based rate limiting (IP only)

### Recommendations
1. **Proxy environments**: Use X-Forwarded-For header
2. **Distributed systems**: Use Redis-based rate limiting
3. **Additional layers**: Combine with Telegram's built-in rate limiting
4. **Monitoring**: Check rate limiter stats periodically

## Files Modified

- `bot.py`:
  - Lines 535-650: IPRateLimiter class
  - Line 652: Global instance creation
  - Lines 12680-12700: Integration in handle_message()

## Files Created

- `tests/test_v0_39_0_rate_limiting.py` (350+ lines, 14 tests)

## Statistics

| Metric | Value |
|--------|-------|
| IPRateLimiter class | 115 lines |
| Integration code | 20 lines |
| Test suite | 350 lines |
| Test cases | 14 |
| Test coverage | 100% |
| Thread safety | ✅ Yes |
| Memory overhead | ~30KB typical |
| CPU overhead | <1% (sub-millisecond) |

## Future Enhancements

### Priority HIGH
1. **Distributed Rate Limiting**: Redis-backed for multi-instance
2. **User-Based Limiting**: Per-user limits (combined with IP)
3. **Adaptive Limits**: Adjust based on system load
4. **Persistent Storage**: Database-backed history

### Priority MEDIUM
5. **Header Extraction**: Use X-Forwarded-For properly
6. **Whitelist**: Bypass for trusted IPs
7. **Graduated Penalties**: Increasing delays instead of blocks
8. **Analytics**: Detailed abuse pattern detection

### Priority LOW
9. **Machine Learning**: Anomaly detection
10. **Visualization Dashboard**: Real-time monitoring

## Deployment Checklist

- [x] Implementation complete
- [x] Unit tests (14 tests, 100% pass)
- [x] Integration in handle_message()
- [x] Logging integrated
- [x] Documentation complete
- [ ] Production testing
- [ ] Monitoring setup
- [ ] Incident response plan

## References

- [OWASP Rate Limiting](https://owasp.org/www-community/attacks/Rate_Limit)
- [DDoS Prevention Best Practices](https://www.cloudflare.com/learning/ddos/ddos-mitigation/)
- Python threading.Lock documentation

---

**Version:** v0.39.0 - QUICK WIN #3  
**Status:** ✅ COMPLETE AND TESTED  
**Tests:** 14/14 PASSED  
**Date:** 2025-12-26  
**Impact:** HIGH - Security enhancement  
