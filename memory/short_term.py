"""
Short-term Memory Module

Session-level memory using in-memory caching.
Used for conversation context and intermediate results.
"""

from typing import Optional, Any
from datetime import datetime, timedelta
from collections import OrderedDict

from src.core.config import settings


class SessionMemory:
    """Session-based memory with TTL."""
    
    def __init__(self, max_sessions: int = 1000):
        self._sessions: OrderedDict[str, dict] = OrderedDict()
        self._max_sessions = max_sessions
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session data."""
        session = self._sessions.get(session_id)
        if session and self._is_expired(session):
            del self._sessions[session_id]
            return None
        return session
    
    def set_session(self, session_id: str, data: dict) -> None:
        """Set session data."""
        # Evict oldest if at capacity
        while len(self._sessions) >= self._max_sessions:
            self._sessions.popitem(last=False)
        
        self._sessions[session_id] = {
            "data": data,
            "created_at": datetime.utcnow(),
            "ttl_hours": settings.semantic_cache_ttl_hours,
        }
    
    def update_session(self, session_id: str, **kwargs) -> None:
        """Update specific session fields."""
        session = self.get_session(session_id)
        if session:
            session["data"].update(kwargs)
    
    def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        self._sessions.pop(session_id, None)
    
    def _is_expired(self, session: dict) -> bool:
        """Check if session is expired."""
        created = session.get("created_at", datetime.utcnow())
        ttl = session.get("ttl_hours", 24)
        return datetime.utcnow() > created + timedelta(hours=ttl)


# Global session memory
_session_memory = SessionMemory()


def get_session_memory() -> SessionMemory:
    """Get the global session memory instance."""
    return _session_memory


class SemanticCache:
    """Semantic caching for similar queries."""
    
    def __init__(self, max_entries: int = 500):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._max_entries = max_entries
    
    def get(self, cache_key: str) -> Optional[dict]:
        """Get cached result by key."""
        entry = self._cache.get(cache_key)
        if entry and self._is_expired(entry):
            del self._cache[cache_key]
            return None
        return entry.get("value") if entry else None
    
    def set(self, cache_key: str, value: Any, ttl_hours: Optional[int] = None) -> None:
        """Set cache entry."""
        # Evict oldest if at capacity
        while len(self._cache) >= self._max_entries:
            self._cache.popitem(last=False)
        
        self._cache[cache_key] = {
            "value": value,
            "created_at": datetime.utcnow(),
            "ttl_hours": ttl_hours or settings.semantic_cache_ttl_hours,
        }
    
    def invalidate(self, cache_key: str) -> None:
        """Invalidate a cache entry."""
        self._cache.pop(cache_key, None)
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
    
    def _is_expired(self, entry: dict) -> bool:
        """Check if entry is expired."""
        created = entry.get("created_at", datetime.utcnow())
        ttl = entry.get("ttl_hours", 24)
        return datetime.utcnow() > created + timedelta(hours=ttl)


# Global semantic cache
_semantic_cache = SemanticCache()


def get_semantic_cache() -> SemanticCache:
    """Get the global semantic cache instance."""
    return _semantic_cache
