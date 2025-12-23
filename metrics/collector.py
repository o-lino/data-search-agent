"""
Metrics Collector

Collects quality metrics for agent performance tracking.
Enables data-driven improvements.
"""

from typing import Optional
from datetime import datetime
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import json


@dataclass
class SearchEvent:
    """A single search event with outcome."""
    request_id: str
    timestamp: str
    
    # Query info
    raw_query: str
    normalized_intent: Optional[dict] = None
    
    # Results
    domain_suggested: Optional[str] = None
    owner_suggested: Optional[str] = None
    table_suggested: Optional[str] = None
    
    confidence_score: float = 0.0
    data_existence: str = "UNCERTAIN"
    processing_time_ms: int = 0
    
    # Outcome (filled later via feedback)
    outcome: Optional[str] = None  # APPROVED, REJECTED, MODIFIED
    actual_table_id: Optional[int] = None
    feedback_at: Optional[str] = None


@dataclass 
class MetricsSummary:
    """Aggregated metrics summary."""
    period_start: str
    period_end: str
    
    # Volume
    total_requests: int = 0
    total_with_feedback: int = 0
    
    # Accuracy
    hit_rate_top1: float = 0.0  # Suggested correct
    hit_rate_owner: float = 0.0  # Owner correct even if table wrong
    
    # Confidence calibration
    avg_confidence_when_approved: float = 0.0
    avg_confidence_when_rejected: float = 0.0
    false_positive_rate: float = 0.0  # High confidence but rejected
    
    # Performance
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    
    # Cache
    intent_cache_hit_rate: float = 0.0


class MetricsCollector:
    """
    Collects and aggregates search quality metrics.
    
    Metrics tracked:
    - hit_rate_top1: Was the top suggestion correct?
    - hit_rate_owner: Was the owner correct?
    - confidence_calibration: Are high scores actually correct?
    - latency: How fast are searches?
    """
    
    def __init__(self, max_events: int = 100000):
        self._events: dict[str, SearchEvent] = {}
        self._max_events = max_events
        
        # Aggregated counts
        self._approved_count = 0
        self._rejected_count = 0
        self._modified_count = 0
        
        # For calibration
        self._confidence_when_approved: list[float] = []
        self._confidence_when_rejected: list[float] = []
        
        # Latencies
        self._latencies: list[int] = []
    
    def record_search(
        self,
        request_id: str,
        raw_query: str,
        domain_suggested: Optional[str],
        owner_suggested: Optional[str],
        table_suggested: Optional[str],
        confidence_score: float,
        data_existence: str,
        processing_time_ms: int,
        normalized_intent: Optional[dict] = None,
    ) -> None:
        """Record a search event."""
        # Evict oldest if at capacity
        if len(self._events) >= self._max_events:
            oldest_key = next(iter(self._events))
            del self._events[oldest_key]
        
        event = SearchEvent(
            request_id=request_id,
            timestamp=datetime.utcnow().isoformat(),
            raw_query=raw_query,
            normalized_intent=normalized_intent,
            domain_suggested=domain_suggested,
            owner_suggested=owner_suggested,
            table_suggested=table_suggested,
            confidence_score=confidence_score,
            data_existence=data_existence,
            processing_time_ms=processing_time_ms,
        )
        
        self._events[request_id] = event
        self._latencies.append(processing_time_ms)
    
    def record_feedback(
        self,
        request_id: str,
        outcome: str,
        actual_table_id: Optional[int] = None,
    ) -> bool:
        """
        Record feedback for a previous search.
        
        Returns True if event was found and updated.
        """
        event = self._events.get(request_id)
        if not event:
            return False
        
        event.outcome = outcome
        event.actual_table_id = actual_table_id
        event.feedback_at = datetime.utcnow().isoformat()
        
        # Update aggregates
        if outcome == "APPROVED":
            self._approved_count += 1
            self._confidence_when_approved.append(event.confidence_score)
        elif outcome == "REJECTED":
            self._rejected_count += 1
            self._confidence_when_rejected.append(event.confidence_score)
        elif outcome == "MODIFIED":
            self._modified_count += 1
        
        return True
    
    def get_summary(self, last_n_days: Optional[int] = None) -> MetricsSummary:
        """Get aggregated metrics summary."""
        events_with_feedback = [
            e for e in self._events.values() 
            if e.outcome is not None
        ]
        
        total = len(self._events)
        with_feedback = len(events_with_feedback)
        
        # Hit rates
        hit_rate_top1 = 0.0
        if with_feedback > 0:
            approved = sum(1 for e in events_with_feedback if e.outcome == "APPROVED")
            hit_rate_top1 = approved / with_feedback
        
        # Confidence calibration
        avg_conf_approved = 0.0
        avg_conf_rejected = 0.0
        false_positive_rate = 0.0
        
        if self._confidence_when_approved:
            avg_conf_approved = sum(self._confidence_when_approved) / len(self._confidence_when_approved)
        
        if self._confidence_when_rejected:
            avg_conf_rejected = sum(self._confidence_when_rejected) / len(self._confidence_when_rejected)
            # False positives: rejected but confidence > 0.7
            high_conf_rejected = sum(1 for c in self._confidence_when_rejected if c > 0.7)
            false_positive_rate = high_conf_rejected / len(self._confidence_when_rejected)
        
        # Latency
        avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0
        p95_latency = sorted(self._latencies)[int(len(self._latencies) * 0.95)] if len(self._latencies) > 20 else avg_latency
        
        # Cache hit rate
        from ..memory.intent_cache import get_intent_cache
        cache = get_intent_cache()
        
        return MetricsSummary(
            period_start=min((e.timestamp for e in self._events.values()), default=""),
            period_end=max((e.timestamp for e in self._events.values()), default=""),
            total_requests=total,
            total_with_feedback=with_feedback,
            hit_rate_top1=hit_rate_top1,
            hit_rate_owner=0.0,  # TODO: track owner accuracy
            avg_confidence_when_approved=avg_conf_approved,
            avg_confidence_when_rejected=avg_conf_rejected,
            false_positive_rate=false_positive_rate,
            avg_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            intent_cache_hit_rate=cache.hit_rate,
        )
    
    def export_events(self, path: str) -> int:
        """Export all events to JSON file for analysis."""
        events = [asdict(e) for e in self._events.values()]
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        
        return len(events)


# Global instance
_metrics: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
