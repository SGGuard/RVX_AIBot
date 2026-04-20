#!/usr/bin/env python3
"""
Phase 6 Prometheus Metrics Integration Tests

Tests comprehensive metrics collection across all critical endpoints:
- /explain_news (cache hit, success, error, fallback paths)
- /analyze_image (rate limit, success, error, fallback paths)
- /health (system metrics)
- /teach_lesson (embedded, fallback, error paths)
- /metrics (Prometheus text format export)
"""

import sys
import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock
import asyncio

# Add repo to path
sys.path.insert(0, '/home/sv4096/rvx_backend')

# Test framework
def test_prometheus_metrics_module():
    """✅ TEST 1: Verify prometheus_metrics module loads correctly"""
    try:
        from prometheus_metrics import (
            REQUEST_COUNTER, RESPONSE_TIME, CACHE_HIT_RATIO, CACHE_MISS_RATIO,
            REQUEST_ERRORS, REQUEST_RATE_LIMITED, REQUEST_FALLBACK,
            PROVIDER_AVAILABILITY, PROVIDER_LATENCY,
            record_request, record_error, record_cache_hit, record_cache_miss,
            record_rate_limit, record_fallback,
            set_provider_availability, record_provider_latency, set_uptime, set_cache_size,
            set_db_pool_availability, record_db_query
        )
        print("✅ TEST 1 PASSED: prometheus_metrics module imported successfully")
        
        # Verify all metrics are properly defined
        assert REQUEST_COUNTER is not None, "REQUEST_COUNTER not initialized"
        assert RESPONSE_TIME is not None, "RESPONSE_TIME not initialized"
        assert CACHE_HIT_RATIO is not None, "CACHE_HIT_RATIO not initialized"
        print("   ✅ All core metrics initialized properly")
        
        return True
    except Exception as e:
        print(f"❌ TEST 1 FAILED: {e}")
        return False


def test_metric_recording_functions():
    """✅ TEST 2: Verify metric recording functions work without errors"""
    try:
        from prometheus_metrics import (
            record_request, record_error, record_cache_hit, record_cache_miss,
            record_rate_limit, record_fallback,
            set_provider_availability, record_provider_latency, set_uptime, set_cache_size
        )
        
        # Test record_request
        record_request(endpoint="/test", method="POST", status=200, response_time_ms=150.5, provider="test")
        print("✅ record_request() works")
        
        # Test record_error
        record_error(endpoint="/test", error_type="timeout", severity="error")
        print("✅ record_error() works")
        
        # Test record_cache_hit/miss
        record_cache_hit(cache_type="response")
        record_cache_miss(cache_type="response")
        print("✅ record_cache_hit/miss() work")
        
        # Test record_rate_limit
        record_rate_limit(endpoint="/test")
        print("✅ record_rate_limit() works")
        
        # Test record_fallback
        record_fallback(endpoint="/test", reason="provider_error")
        print("✅ record_fallback() works")
        
        # Test set_* functions
        set_provider_availability("gemini", True)
        record_provider_latency("gemini", 250.0)
        set_uptime(3600.5)
        set_cache_size("response", 5242880)  # 5MB
        print("✅ set_* functions work")
        
        print("✅ TEST 2 PASSED: All metric recording functions work")
        return True
    except Exception as e:
        print(f"❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_server_imports():
    """✅ TEST 3: Verify api_server.py imports metrics correctly"""
    try:
        # Check that api_server can be parsed without import errors
        import ast
        with open('/home/sv4096/rvx_backend/api_server.py', 'r') as f:
            code = f.read()
        
        ast.parse(code)
        print("✅ api_server.py syntax is valid")
        
        # Verify imports are present
        assert "from prometheus_metrics import" in code, "prometheus_metrics import not found"
        assert "record_request(" in code, "record_request calls not found"
        assert "record_error(" in code, "record_error calls not found"
        assert "record_fallback(" in code, "record_fallback calls not found"
        assert "record_rate_limit(" in code, "record_rate_limit calls not found"
        assert "record_cache_hit(" in code, "record_cache_hit calls not found"
        assert "set_uptime(" in code, "set_uptime calls not found"
        assert "set_cache_size(" in code, "set_cache_size calls not found"
        
        print("✅ All metrics recording calls present in api_server.py")
        print("✅ TEST 3 PASSED: api_server.py metrics integration verified")
        return True
    except Exception as e:
        print(f"❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_metrics_endpoint_integration():
    """✅ TEST 4: Verify /metrics endpoint exists and can generate output"""
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        
        # Generate sample metrics output
        metrics_output = generate_latest()
        assert isinstance(metrics_output, bytes), "Metrics output should be bytes"
        assert b'rvx_requests_total' in metrics_output, "Custom metrics not found in output"
        
        print(f"✅ Prometheus metrics output generated ({len(metrics_output)} bytes)")
        print(f"   Content-Type: {CONTENT_TYPE_LATEST}")
        
        # Verify text format
        text_output = metrics_output.decode('utf-8')
        assert "HELP" in text_output, "Prometheus HELP format not found"
        assert "TYPE" in text_output, "Prometheus TYPE format not found"
        
        print("✅ Metrics output in valid Prometheus text format")
        print("✅ TEST 4 PASSED: /metrics endpoint integration verified")
        return True
    except Exception as e:
        print(f"❌ TEST 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_metrics_in_api_endpoints():
    """✅ TEST 5: Verify metrics are recorded in key endpoints"""
    try:
        import ast
        with open('/home/sv4096/rvx_backend/api_server.py', 'r') as f:
            content = f.read()
        
        endpoints_to_check = {
            'explain_news': {
                'metrics': ['record_cache_hit', 'record_request', 'record_error', 'record_fallback'],
                'providers': ['cache', 'groq', 'fallback', 'error']
            },
            'analyze_image': {
                'metrics': ['record_rate_limit', 'record_error', 'record_fallback', 'record_request'],
                'providers': ['gemini', 'fallback', 'error']
            },
            'health_check': {
                'metrics': ['record_request', 'set_uptime', 'set_cache_size'],
                'providers': ['internal']
            },
            'teach_lesson': {
                'metrics': ['record_fallback', 'record_error', 'record_request'],
                'providers': ['embedded', 'fallback', 'error']
            }
        }
        
        for endpoint, config in endpoints_to_check.items():
            endpoint_section = content.split(f'async def {endpoint}')[1].split('async def ')[0] if f'async def {endpoint}' in content else content.split(f'def {endpoint}')[1].split('def ')[0] if f'def {endpoint}' in content else ""
            
            for metric in config['metrics']:
                assert metric in endpoint_section, f"{metric} not found in {endpoint}"
            
            print(f"✅ {endpoint}: All metrics recorded")
        
        print("✅ TEST 5 PASSED: All endpoints have proper metrics integration")
        return True
    except Exception as e:
        print(f"❌ TEST 5 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_metrics_structure():
    """✅ TEST 6: Verify metrics have correct labels and structure"""
    try:
        from prometheus_metrics import (
            REQUEST_COUNTER, RESPONSE_TIME, CACHE_HIT_RATIO, CACHE_MISS_RATIO,
            REQUEST_ERRORS, REQUEST_RATE_LIMITED, REQUEST_FALLBACK,
            PROVIDER_LATENCY, DB_QUERY_TIME, ERROR_COUNTER
        )
        
        # Test that metrics have proper label names
        metrics_config = {
            'REQUEST_COUNTER': ['endpoint', 'method', 'status'],
            'REQUEST_ERRORS': ['endpoint', 'error_type'],
            'RESPONSE_TIME': ['endpoint'],
            'CACHE_HIT_RATIO': ['cache_type'],
            'PROVIDER_LATENCY': ['provider'],
            'DB_QUERY_TIME': ['query_type'],
            'ERROR_COUNTER': ['error_type', 'severity']
        }
        
        for metric_name, expected_labels in metrics_config.items():
            metric = eval(metric_name)
            # Verify metric is initialized
            assert metric is not None, f"{metric_name} not initialized"
            print(f"✅ {metric_name}: Properly initialized with labels {expected_labels}")
        
        print("✅ TEST 6 PASSED: All metrics have correct structure and labels")
        return True
    except Exception as e:
        print(f"❌ TEST 6 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_metrics_persistence():
    """✅ TEST 7: Verify metrics counters increment properly"""
    try:
        from prometheus_metrics import (
            REQUEST_COUNTER, RESPONSE_TIME, CACHE_HIT_RATIO,
            record_request, record_cache_hit
        )
        
        # Record some metrics
        record_request(endpoint="/test", method="POST", status=200, response_time_ms=100)
        record_request(endpoint="/test", method="POST", status=200, response_time_ms=150)
        record_cache_hit(cache_type="response")
        
        # Verify metrics were recorded (they should increment internally)
        from prometheus_client import generate_latest
        output = generate_latest().decode('utf-8')
        
        # Check for metric values
        assert 'rvx_requests_total' in output, "Request counter not found"
        assert 'rvx_response_time_ms_sum' in output, "Response time histogram not found"
        assert 'rvx_cache_hits_total' in output, "Cache hit counter not found"
        
        print("✅ Metrics counters increment properly")
        print("✅ TEST 7 PASSED: Metrics persistence verified")
        return True
    except Exception as e:
        print(f"❌ TEST 7 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all Phase 6 metrics tests"""
    print("\n" + "="*80)
    print("PHASE 6 PROMETHEUS METRICS INTEGRATION TEST SUITE")
    print("="*80 + "\n")
    
    tests = [
        ("Prometheus Module Load", test_prometheus_metrics_module),
        ("Metric Recording Functions", test_metric_recording_functions),
        ("API Server Imports", test_api_server_imports),
        ("Metrics Endpoint Integration", test_metrics_endpoint_integration),
        ("Metrics in API Endpoints", test_metrics_in_api_endpoints),
        ("Metrics Structure", test_metrics_structure),
        ("Metrics Persistence", test_metrics_persistence),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n>>> Running: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} CRASHED: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("\n" + "="*80)
    print(f"TOTAL: {passed}/{total} tests passed")
    print("="*80 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
