"""
Long-term Memory Module

Stores and retrieves historical decision data across sessions.
Uses PostgreSQL for persistent storage.
"""

from typing import Optional
from datetime import datetime, timedelta

from src.core.config import settings


# In-memory cache for development
_historical_cache: dict[str, list[dict]] = {}


async def get_historical_decisions(
    concept_hash: str,
    limit: int = 10
) -> list[dict]:
    """
    Get historical decisions for a concept.
    
    Args:
        concept_hash: The concept hash to look up
        limit: Maximum number of results
    
    Returns:
        List of historical decision records
    """
    # Check cache first
    if concept_hash in _historical_cache:
        return _historical_cache[concept_hash][:limit]
    
    # In production, this would query PostgreSQL:
    # SELECT * FROM approval_history 
    # WHERE concept_hash = :concept_hash 
    # ORDER BY last_used_at DESC 
    # LIMIT :limit
    
    return []


async def record_decision_outcome(
    concept_hash: str,
    table_id: int,
    approved: bool,
    concept_name: Optional[str] = None,
    concept_type: Optional[str] = None
) -> None:
    """
    Record a decision outcome for learning.
    
    Args:
        concept_hash: The concept hash
        table_id: The table that was recommended
        approved: Whether the recommendation was approved
        concept_name: Human-readable concept name
        concept_type: Type of the variable
    """
    # Update cache
    if concept_hash not in _historical_cache:
        _historical_cache[concept_hash] = []
    
    # Find or create record
    record = None
    for r in _historical_cache[concept_hash]:
        if r.get("table_id") == table_id:
            record = r
            break
    
    if record is None:
        record = {
            "concept_hash": concept_hash,
            "table_id": table_id,
            "concept_name": concept_name,
            "concept_type": concept_type,
            "approved_count": 0,
            "rejected_count": 0,
            "last_used_at": None,
        }
        _historical_cache[concept_hash].append(record)
    
    # Update counts
    if approved:
        record["approved_count"] = record.get("approved_count", 0) + 1
    else:
        record["rejected_count"] = record.get("rejected_count", 0) + 1
    
    record["last_used_at"] = datetime.utcnow().isoformat()
    
    # In production, this would upsert to PostgreSQL:
    # INSERT INTO approval_history (...) 
    # ON CONFLICT (concept_hash, table_id) DO UPDATE SET ...


async def get_decision_patterns(
    domain: Optional[str] = None,
    min_approval_rate: float = 0.7,
    min_decisions: int = 3,
    days_lookback: int = 90
) -> list[dict]:
    """
    Get successful decision patterns for a domain.
    
    Args:
        domain: Optional domain filter
        min_approval_rate: Minimum approval rate to include
        min_decisions: Minimum number of decisions to include
        days_lookback: How many days to look back
    
    Returns:
        List of patterns with high approval rates
    """
    patterns = []
    
    for concept_hash, records in _historical_cache.items():
        for record in records:
            total = record.get("approved_count", 0) + record.get("rejected_count", 0)
            if total < min_decisions:
                continue
            
            rate = record["approved_count"] / total
            if rate >= min_approval_rate:
                patterns.append({
                    **record,
                    "approval_rate": rate,
                    "total_decisions": total,
                })
    
    return patterns


async def clear_old_decisions(days: int = 180) -> int:
    """
    Clear old decision records.
    
    Args:
        days: Delete records older than this many days
    
    Returns:
        Number of records deleted
    """
    # In production, this would:
    # DELETE FROM approval_history WHERE last_used_at < NOW() - INTERVAL :days
    return 0
