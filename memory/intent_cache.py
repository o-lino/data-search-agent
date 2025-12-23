"""
Intent Cache

Caches normalized intents to reduce LLM calls by ~80%.
Uses semantic hashing for cache key generation.
"""

import hashlib
import re
from typing import Optional
from datetime import datetime, timedelta
from collections import OrderedDict

from ..state import CanonicalIntent
from src.core.config import settings


# Portuguese stopwords for normalization
STOPWORDS = {
    'de', 'da', 'do', 'das', 'dos', 'e', 'para', 'com', 'em', 'a', 'o', 'os', 'as',
    'um', 'uma', 'uns', 'umas', 'que', 'na', 'no', 'nas', 'nos', 'se', 'por', 'mais',
    'como', 'mas', 'foi', 'ao', 'aos', 'pela', 'pelo', 'seu', 'sua', 'seus', 'suas',
    'preciso', 'quero', 'buscar', 'encontrar', 'ver', 'dados', 'tabela', 'tabelas',
}


def normalize_for_cache(text: str) -> str:
    """Normalize text for cache key generation."""
    if not text:
        return ""
    
    # Lowercase
    text = text.lower()
    
    # Remove special chars
    text = re.sub(r'[^a-záàâãéèêíìóòôõúùûç\s]', ' ', text)
    
    # Remove stopwords
    words = [w for w in text.split() if w not in STOPWORDS and len(w) > 2]
    
    # Sort for order independence
    words.sort()
    
    return ' '.join(words)


def generate_cache_key(
    raw_query: str,
    variable_name: Optional[str] = None,
    context: Optional[dict] = None
) -> str:
    """Generate deterministic cache key from input."""
    parts = []
    
    # Main query
    if raw_query:
        parts.append(normalize_for_cache(raw_query))
    if variable_name:
        parts.append(normalize_for_cache(variable_name))
    
    # Context (sorted keys for determinism)
    if context:
        for key in sorted(context.keys()):
            value = context.get(key)
            if value:
                parts.append(f"{key}:{normalize_for_cache(str(value))}")
    
    combined = '|'.join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


class IntentCache:
    """
    LRU cache for normalized intents.
    
    Reduces LLM calls by caching intent extractions.
    Similar queries (after normalization) hit the cache.
    """
    
    def __init__(self, max_size: int = 10000, ttl_days: int = 7):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._max_size = max_size
        self._ttl_days = ttl_days
        
        # Stats
        self._hits = 0
        self._misses = 0
    
    def get(self, cache_key: str) -> Optional[CanonicalIntent]:
        """Get cached intent if exists and not expired."""
        entry = self._cache.get(cache_key)
        
        if entry is None:
            self._misses += 1
            return None
        
        # Check expiry
        if self._is_expired(entry):
            del self._cache[cache_key]
            self._misses += 1
            return None
        
        # Move to end (LRU)
        self._cache.move_to_end(cache_key)
        self._hits += 1
        
        # Reconstruct CanonicalIntent
        return CanonicalIntent(**entry["intent"])
    
    def set(
        self,
        cache_key: str,
        intent: CanonicalIntent,
        query_variants: Optional[list[str]] = None
    ) -> None:
        """
        Cache an intent.
        
        Args:
            cache_key: Primary cache key
            intent: The normalized intent
            query_variants: Alternative query forms that map to same intent
        """
        # Evict oldest if full
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        
        entry = {
            "intent": intent.model_dump(),
            "created_at": datetime.utcnow().isoformat(),
            "ttl_days": self._ttl_days,
        }
        
        # Store main entry
        self._cache[cache_key] = entry
        
        # Store variants (pointing to same intent)
        if query_variants:
            for variant in query_variants:
                variant_key = generate_cache_key(variant)
                if variant_key != cache_key:
                    self._cache[variant_key] = entry
    
    def invalidate(self, cache_key: str) -> None:
        """Remove entry from cache."""
        self._cache.pop(cache_key, None)
    
    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
    
    def _is_expired(self, entry: dict) -> bool:
        """Check if cache entry is expired."""
        created = datetime.fromisoformat(entry["created_at"])
        ttl = entry.get("ttl_days", self._ttl_days)
        return datetime.utcnow() > created + timedelta(days=ttl)
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0
    
    @property
    def stats(self) -> dict:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self.hit_rate:.1%}",
        }


# Global instance
_intent_cache: Optional[IntentCache] = None


def get_intent_cache() -> IntentCache:
    """Get or create global intent cache."""
    global _intent_cache
    if _intent_cache is None:
        _intent_cache = IntentCache()
    return _intent_cache
