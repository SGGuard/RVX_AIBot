"""
Integration Guide for Security Modules
Интеграция Security модулей в api_server.py
"""

# ============================================================================
# STEP 1: Add imports after line 33 (after other imports)
# ============================================================================

"""
# Security modules (v1.0)
from security_manager import security_manager, log_security_action, SECURITY_HEADERS
from api_auth_manager import api_key_manager, init_auth_database
from audit_logger import audit_logger
from secrets_manager import secrets_manager, get_safe_logger
from security_middleware import (
    security_headers_middleware,
    request_validation_middleware,
    rate_limit_middleware,
    request_logging_middleware,
)
"""

# ============================================================================
# STEP 2: In lifespan context manager (around line 1065)
# ============================================================================

"""
# Add after existing initialization code, before yield:

# Initialize security databases
try:
    init_auth_database()
    logger.info("✅ Auth database initialized")
except Exception as e:
    logger.warning(f"⚠️ Auth database error: {e}")

# Register environment secrets
logger.info("🔐 Secrets manager initialized - masking sensitive data")
"""

# ============================================================================
# STEP 3: Add middlewares after CORSMiddleware (around line 1170)
# ============================================================================

"""
# Add after existing CORSMiddleware (line ~1170):

# Security middleware stack
app.add_middleware(request_logging_middleware)
app.add_middleware(rate_limit_middleware)
app.add_middleware(request_validation_middleware)
app.add_middleware(security_headers_middleware)

# This creates a middleware chain:
# 1. security_headers_middleware (adds security headers)
# 2. request_validation_middleware (validates content)
# 3. rate_limit_middleware (rate limiting)
# 4. request_logging_middleware (logs requests)
"""

# ============================================================================
# STEP 4: Add API authentication endpoint
# ============================================================================

"""
@app.post("/auth/create_api_key", tags=["Security"], include_in_schema=False)
async def create_api_key(
    request: Request,
    key_name: str,
    owner_name: str,
    rate_limit: int = 60
):
    \"\"\"
    Create a new API key (ADMIN ONLY).
    
    Usage:
        POST /auth/create_api_key
        Authorization: Bearer ADMIN_TOKEN
        {
            "key_name": "Production Bot",
            "owner_name": "Team A",
            "rate_limit": 100
        }
    \"\"\"
    # TODO: Add ADMIN_TOKEN verification
    
    try:
        api_key = api_key_manager.generate_api_key(
            key_name=key_name,
            owner_name=owner_name,
            rate_limit=rate_limit
        )
        
        audit_logger.log_action(
            user_id=None,
            action=f"Created API key: {key_name}",
            result="success",
            severity="HIGH",
            source_ip=request.client.host if request.client else None
        )
        
        return {
            "api_key": api_key,  # Only shown once!
            "warning": "Store this key securely. It won't be shown again!",
            "message": "API key created successfully"
        }
    except Exception as e:
        audit_logger.log_error(
            error_msg=f"Failed to create API key: {str(e)}",
            severity="HIGH",
            source_ip=request.client.host if request.client else None
        )
        raise HTTPException(status_code=500, detail="Failed to create API key")
"""

# ============================================================================
# STEP 5: Update explain_news endpoint to verify API key
# ============================================================================

"""
# Add before existing explain_news function (around line 1250):

def verify_api_key(request: Request) -> Optional[str]:
    \"\"\"Extract and verify API key from Authorization header\"\"\"
    
    auth_header = request.headers.get("Authorization", "")
    
    if not auth_header.startswith("Bearer "):
        return None
    
    api_key = auth_header.replace("Bearer ", "").strip()
    
    is_valid, error = api_key_manager.verify_api_key(api_key)
    
    if not is_valid:
        audit_logger.log_auth_event(
            user_id=None,
            action="Invalid API key attempt",
            result="failure",
            source_ip=request.client.host if request.client else None,
            details={"error": error}
        )
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    
    return api_key

# Then update explain_news:

@app.post("/explain_news", response_model=SimplifiedResponse)
async def explain_news(request: Request, payload: NewsPayload):
    \"\"\"
    Analyze news using AI.
    
    Requires API key in Authorization header:
    Authorization: Bearer rvx_key_xxxxx
    \"\"\"
    
    # Verify API key
    api_key = verify_api_key(request)
    
    # Log the API usage
    start_time = datetime.utcnow()
    
    try:
        # ... existing code ...
        
        # Log success
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        api_key_manager.log_api_usage(
            api_key=api_key,
            endpoint="/explain_news",
            status_code=200,
            response_time_ms=int(duration_ms),
            success=True
        )
        
        audit_logger.log_api_event(
            user_id=None,
            endpoint="/explain_news",
            result="success",
            status_code=200,
            source_ip=request.client.host if request.client else None,
            details={"duration_ms": round(duration_ms)}
        )
        
        return result
        
    except Exception as e:
        # Log error
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        api_key_manager.log_api_usage(
            api_key=api_key,
            endpoint="/explain_news",
            status_code=500,
            response_time_ms=int(duration_ms),
            success=False
        )
        
        audit_logger.log_api_event(
            user_id=None,
            endpoint="/explain_news",
            result="failure",
            status_code=500,
            source_ip=request.client.host if request.client else None,
            details={"error": str(e)}
        )
        
        raise
"""

# ============================================================================
# STEP 6: Add security endpoint for status
# ============================================================================

"""
@app.get("/security/status", tags=["Security"], include_in_schema=False)
async def security_status(request: Request):
    \"\"\"Get security and audit statistics (ADMIN ONLY)\"\"\"
    
    # TODO: Verify admin token
    
    return {
        "security_events": len(security_manager.security_events),
        "critical_count": sum(1 for e in security_manager.security_events if e.severity == "CRITICAL"),
        "recent_events": security_manager.get_security_events(hours=24),
        "audit_stats": audit_logger.get_statistics(hours=24),
    }
"""

# ============================================================================
# IMPLEMENTATION CHECKLIST
# ============================================================================

INTEGRATION_CHECKLIST = """
✅ IMPLEMENTATION CHECKLIST for Security Modules

Phase 1: Preparation (5 minutes)
  [ ] Read this guide
  [ ] Backup api_server.py
  [ ] Check Python version >= 3.10

Phase 2: Add Imports (2 minutes)
  [ ] Add import statements (Step 1)
  [ ] Verify no import errors

Phase 3: Initialize Databases (3 minutes)
  [ ] Add auth database init in lifespan (Step 2)
  [ ] Add audit logger init in lifespan
  [ ] Test database creation

Phase 4: Add Middleware (5 minutes)
  [ ] Add security middleware stack (Step 3)
  [ ] Verify middleware order correct
  [ ] Add security headers

Phase 5: Add Endpoints (10 minutes)
  [ ] Add create_api_key endpoint (Step 4)
  [ ] Add API key verification to explain_news (Step 5)
  [ ] Add security/status endpoint (Step 6)

Phase 6: Testing (10 minutes)
  [ ] Test API without key -> 401 error
  [ ] Test API with key -> 200 success
  [ ] Check audit logs created
  [ ] Verify security headers in response

Phase 7: Deployment (5 minutes)
  [ ] Create first API key for bot
  [ ] Update bot.py to use API key
  [ ] Update .env with API_KEY
  [ ] Restart services

Total Time: ~40 minutes

TESTING COMMANDS:
  
  # Create API key
  curl -X POST http://localhost:8000/auth/create_api_key \\
    -H 'Content-Type: application/json' \\
    -d '{
      "key_name": "Bot Test",
      "owner_name": "RVX Bot",
      "rate_limit": 100
    }'
  
  # Test without key (should fail)
  curl -X POST http://localhost:8000/explain_news \\
    -H 'Content-Type: application/json' \\
    -d '{"text_content": "Bitcoin news"}'
  
  # Test with key (should work)
  curl -X POST http://localhost:8000/explain_news \\
    -H 'Authorization: Bearer rvx_key_YOUR_KEY_HERE' \\
    -H 'Content-Type: application/json' \\
    -d '{"text_content": "Bitcoin news"}'
  
  # Get security status
  curl http://localhost:8000/security/status
"""

