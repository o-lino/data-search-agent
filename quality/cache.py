"""
Quality Cache

Local cache for quality metrics with proactive sync from Athena.
"""

from typing import Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import json
import asyncio

from .athena_client import get_athena_client, TableQualityMetric


@dataclass
class CachedQualityMetric:
    """Cached quality metric with sync metadata."""
    table_name: str
    quality_score: float
    source_updated_at: datetime  # When Athena data was updated
    cached_at: datetime          # When we synced it
    
    @property
    def cache_age_hours(self) -> float:
        """How old is this cache entry."""
        return (datetime.utcnow() - self.cached_at).total_seconds() / 3600


class QualityCache:
    """
    Local cache for quality metrics.
    
    Features:
    - In-memory cache with persistence option
    - Proactive sync when source data changes
    - Stale detection
    """
    
    def __init__(self, max_stale_hours: float = 25.0):
        self._cache: dict[str, CachedQualityMetric] = {}
        self._max_stale_hours = max_stale_hours
        self._last_sync: Optional[datetime] = None
    
    def get(self, table_name: str) -> Optional[CachedQualityMetric]:
        """Get cached quality metric for a table."""
        cached = self._cache.get(table_name)
        
        if cached and cached.cache_age_hours > self._max_stale_hours:
            # Stale, but still return it (caller decides)
            return cached
        
        return cached
    
    def get_score(self, table_name: str, default: float = 0.5) -> float:
        """Get quality score, normalized to 0-1."""
        cached = self.get(table_name)
        if cached:
            return cached.quality_score / 100.0
        return default
    
    def set(self, metric: TableQualityMetric) -> None:
        """Cache a quality metric."""
        self._cache[metric.table_name] = CachedQualityMetric(
            table_name=metric.table_name,
            quality_score=metric.quality_score,
            source_updated_at=metric.last_updated,
            cached_at=datetime.utcnow(),
        )
    
    def set_batch(self, metrics: list[TableQualityMetric]) -> int:
        """Cache multiple metrics, return count."""
        for m in metrics:
            self.set(m)
        return len(metrics)
    
    async def sync_from_athena(self, force: bool = False) -> dict:
        """
        Sync quality metrics from Athena.
        
        Proactive strategy:
        1. Query Athena for tables updated since last sync
        2. Only update those tables in cache
        3. Full sync if force=True or never synced
        
        Returns:
            Sync result with counts
        """
        client = get_athena_client()
        
        if force or self._last_sync is None:
            # Full sync
            metrics = await client.get_all_quality_metrics()
            count = self.set_batch(metrics)
            self._last_sync = datetime.utcnow()
            
            return {
                "type": "full",
                "synced": count,
                "timestamp": self._last_sync.isoformat(),
            }
        
        # Incremental sync - only updated tables
        updated_metrics = await client.get_updated_tables_since(self._last_sync)
        count = self.set_batch(updated_metrics)
        self._last_sync = datetime.utcnow()
        
        return {
            "type": "incremental",
            "synced": count,
            "timestamp": self._last_sync.isoformat(),
        }
    
    def get_stale_tables(self) -> list[str]:
        """Get list of tables with stale cache entries."""
        return [
            name for name, cached in self._cache.items()
            if cached.cache_age_hours > self._max_stale_hours
        ]
    
    @property
    def stats(self) -> dict:
        """Get cache statistics."""
        return {
            "total_cached": len(self._cache),
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "stale_count": len(self.get_stale_tables()),
        }


# Global instance
_quality_cache: Optional[QualityCache] = None


def get_quality_cache() -> QualityCache:
    """Get or create quality cache."""
    global _quality_cache
    if _quality_cache is None:
        _quality_cache = QualityCache()
    return _quality_cache
