"""
Admin API - Secure Administrative Endpoints

This module provides protected administrative endpoints for database management.
All operations require multi-factor authentication and confirmation.

Security Layers:
1. Admin API Key (env: ADMIN_API_KEY)
2. Two-Step Confirmation (request token → confirm with token)
3. Rate Limiting (1 cleanup per 5 minutes)
4. Audit Logging (all operations logged)
5. Explicit confirmation string required
"""

import os
import time
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

# Configure audit logging
logging.basicConfig(level=logging.INFO)
audit_logger = logging.getLogger("admin_audit")
audit_handler = logging.FileHandler("admin_audit.log")
audit_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
audit_logger.addHandler(audit_handler)

app = FastAPI(
    title="Admin API",
    description="Secure administrative endpoints for database management",
    version="1.0.0",
    docs_url="/admin/docs",  # Hidden docs path
    redoc_url=None,  # Disable redoc
)

# ============================================
# SECURITY CONFIGURATION
# ============================================

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
CLEANUP_COOLDOWN_SECONDS = 300  # 5 minutes between cleanups
TOKEN_EXPIRY_SECONDS = 120  # 2 minutes to confirm

# In-memory storage for security tokens and rate limiting
_pending_tokens: dict[str, dict] = {}  # token -> {expires_at, client_ip, action}
_last_cleanup_time: Optional[datetime] = None

# Security headers
api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


# ============================================
# SECURITY HELPERS
# ============================================

def verify_admin_key(api_key: str = Depends(api_key_header)) -> bool:
    """Verify the admin API key."""
    if not ADMIN_API_KEY:
        audit_logger.error("ADMIN_API_KEY not configured! Blocking all admin requests.")
        raise HTTPException(
            status_code=503,
            detail="Admin API not configured. Set ADMIN_API_KEY environment variable."
        )
    
    if not api_key or not secrets.compare_digest(api_key, ADMIN_API_KEY):
        audit_logger.warning(f"Invalid admin API key attempt")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return True


def check_rate_limit() -> None:
    """Enforce cleanup rate limit."""
    global _last_cleanup_time
    
    if _last_cleanup_time:
        elapsed = (datetime.now() - _last_cleanup_time).total_seconds()
        if elapsed < CLEANUP_COOLDOWN_SECONDS:
            remaining = int(CLEANUP_COOLDOWN_SECONDS - elapsed)
            audit_logger.warning(f"Rate limit hit. {remaining}s remaining.")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit: wait {remaining} seconds before next cleanup"
            )


def generate_confirmation_token(action: str, client_ip: str) -> str:
    """Generate a secure confirmation token."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(seconds=TOKEN_EXPIRY_SECONDS)
    
    _pending_tokens[token] = {
        "expires_at": expires_at,
        "client_ip": client_ip,
        "action": action,
        "created_at": datetime.now().isoformat(),
    }
    
    # Clean expired tokens
    current_time = datetime.now()
    expired = [t for t, data in _pending_tokens.items() if data["expires_at"] < current_time]
    for t in expired:
        del _pending_tokens[t]
    
    return token


def verify_confirmation_token(token: str, expected_action: str) -> bool:
    """Verify and consume a confirmation token."""
    if token not in _pending_tokens:
        return False
    
    data = _pending_tokens[token]
    
    # Check expiry
    if datetime.now() > data["expires_at"]:
        del _pending_tokens[token]
        return False
    
    # Check action match
    if data["action"] != expected_action:
        return False
    
    # Consume token (one-time use)
    del _pending_tokens[token]
    return True


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class CleanupRequestResponse(BaseModel):
    """Response for cleanup request (step 1)."""
    message: str
    confirmation_token: str
    expires_in_seconds: int
    confirm_endpoint: str
    required_confirmation: str


class CleanupConfirmRequest(BaseModel):
    """Request body for cleanup confirmation (step 2)."""
    confirmation_token: str
    confirm_text: str  # Must be "DELETE ALL DATA"


class CleanupConfirmResponse(BaseModel):
    """Response for completed cleanup."""
    success: bool
    message: str
    tables_deleted: int
    timestamp: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    table_count: int
    timestamp: str


# ============================================
# ENDPOINTS
# ============================================

@app.get("/admin/health", response_model=HealthResponse)
async def admin_health(authenticated: bool = Depends(verify_admin_key)):
    """
    Check database health and current table count.
    Requires: X-Admin-API-Key header
    """
    from rag.optimized_retriever import get_optimized_retriever
    
    retriever = get_optimized_retriever()
    count = await retriever.count()
    
    return HealthResponse(
        status="healthy",
        table_count=count,
        timestamp=datetime.now().isoformat()
    )


@app.post("/admin/cleanup/request", response_model=CleanupRequestResponse)
async def request_cleanup(
    authenticated: bool = Depends(verify_admin_key),
    x_forwarded_for: Optional[str] = Header(None)
):
    """
    Step 1: Request a cleanup confirmation token.
    
    This endpoint generates a time-limited token that must be used
    to confirm the cleanup operation within 2 minutes.
    
    Requires: X-Admin-API-Key header
    """
    client_ip = x_forwarded_for or "unknown"
    
    # Check rate limit
    check_rate_limit()
    
    # Generate confirmation token
    token = generate_confirmation_token("cleanup_database", client_ip)
    
    audit_logger.info(f"Cleanup requested by {client_ip}. Token issued.")
    
    return CleanupRequestResponse(
        message="Cleanup token generated. Confirm within 2 minutes.",
        confirmation_token=token,
        expires_in_seconds=TOKEN_EXPIRY_SECONDS,
        confirm_endpoint="POST /admin/cleanup/confirm",
        required_confirmation='You must send confirm_text: "DELETE ALL DATA"'
    )


@app.post("/admin/cleanup/confirm", response_model=CleanupConfirmResponse)
async def confirm_cleanup(
    body: CleanupConfirmRequest,
    authenticated: bool = Depends(verify_admin_key),
    x_forwarded_for: Optional[str] = Header(None)
):
    """
    Step 2: Confirm and execute the cleanup operation.
    
    Requires:
    - X-Admin-API-Key header
    - Valid confirmation_token from step 1
    - confirm_text must be exactly "DELETE ALL DATA"
    """
    client_ip = x_forwarded_for or "unknown"
    
    # Verify confirmation text (prevents accidental triggers)
    REQUIRED_CONFIRMATION = "DELETE ALL DATA"
    if body.confirm_text != REQUIRED_CONFIRMATION:
        audit_logger.warning(f"Invalid confirmation text from {client_ip}: {body.confirm_text}")
        raise HTTPException(
            status_code=400,
            detail=f'Invalid confirmation. Must be exactly: "{REQUIRED_CONFIRMATION}"'
        )
    
    # Verify token
    if not verify_confirmation_token(body.confirmation_token, "cleanup_database"):
        audit_logger.warning(f"Invalid/expired token from {client_ip}")
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired confirmation token. Request a new one."
        )
    
    # Execute cleanup
    global _last_cleanup_time
    
    try:
        from rag.optimized_retriever import get_optimized_retriever
        
        retriever = get_optimized_retriever()
        count_before = await retriever.count()
        
        await retriever.clear()
        
        count_after = await retriever.count()
        
        # Update rate limit tracker
        _last_cleanup_time = datetime.now()
        
        audit_logger.info(
            f"CLEANUP EXECUTED by {client_ip}. "
            f"Tables before: {count_before}, after: {count_after}"
        )
        
        return CleanupConfirmResponse(
            success=True,
            message="Database cleanup completed successfully.",
            tables_deleted=count_before,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        audit_logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


# ============================================
# STANDALONE RUNNER
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    if not ADMIN_API_KEY:
        print("⚠️  WARNING: ADMIN_API_KEY not set!")
        print("   Set it via: export ADMIN_API_KEY=your-secure-key")
    
    uvicorn.run(app, host="0.0.0.0", port=8001)
