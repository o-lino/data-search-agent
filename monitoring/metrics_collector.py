"""
Enhanced Metrics Collector

Comprehensive metrics collection for agent monitoring.
Tracks quality, performance, and business metrics.
"""

from typing import Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import time
import asyncio
from enum import Enum


class MetricType(str, Enum):
    """Types of metrics tracked."""
    # Quality
    SEARCH_REQUEST = "search_request"
    SEARCH_HIT = "search_hit"
    SEARCH_MISS = "search_miss"
    FEEDBACK_APPROVED = "feedback_approved"
    FEEDBACK_REJECTED = "feedback_rejected"
    FEEDBACK_MODIFIED = "feedback_modified"
    AMBIGUITY_DETECTED = "ambiguity_detected"
    CLARIFICATION_REQUESTED = "clarification_requested"
    
    # Performance
    LATENCY = "latency"
    LLM_CALL = "llm_call"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    RERANK_ACTIVATED = "rerank_activated"
    RERANK_SKIPPED = "rerank_skipped"
    
    # Errors
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class RequestMetrics:
    """Metrics for a single request."""
    request_id: str
    timestamp: datetime
    
    # Timing
    total_latency_ms: int = 0
    intent_latency_ms: int = 0
    search_latency_ms: int = 0
    rerank_latency_ms: int = 0
    
    # Results
    tables_found: int = 0
    columns_found: int = 0
    top_score: float = 0.0
    
    # Outcome
    outcome: Optional[str] = None  # HIT, MISS, AMBIGUOUS
    ambiguity_type: Optional[str] = None
    llm_reranked: bool = False
    
    # Scores breakdown
    semantic_score: float = 0.0
    historical_score: float = 0.0
    certification_score: float = 0.0
    freshness_score: float = 0.0
    quality_score: float = 0.0
    
    # Context
    use_case: str = "default"
    domain: Optional[str] = None
    has_product_context: bool = False
    
    # Cache
    intent_cache_hit: bool = False
    quality_cache_hit: bool = False


@dataclass
class AggregatedMetrics:
    """Aggregated metrics for a time period."""
    period_start: datetime
    period_end: datetime
    period_type: str  # "hour", "day", "week"
    
    # Counts
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Quality
    hit_rate_top1: float = 0.0
    hit_rate_top5: float = 0.0
    ambiguity_rate: float = 0.0
    false_positive_rate: float = 0.0
    
    # Latency
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    
    # LLM
    llm_calls: int = 0
    rerank_activation_rate: float = 0.0
    
    # Cache
    intent_cache_hit_rate: float = 0.0
    quality_cache_hit_rate: float = 0.0
    
    # Feedback
    feedback_count: int = 0
    approval_rate: float = 0.0
    
    # Errors
    error_count: int = 0
    timeout_count: int = 0


class EnhancedMetricsCollector:
    """
    Enhanced metrics collector with aggregation.
    
    Features:
    - Per-request detailed metrics
    - Hourly/daily aggregation
    - Percentile calculations
    - Export to DataMesh
    """
    
    def __init__(self, max_history_hours: int = 24):
        self.max_history_hours = max_history_hours
        
        # Raw request metrics (circular buffer)
        self._requests: list[RequestMetrics] = []
        self._max_requests = 10000
        
        # Counters (since startup)
        self._counters: dict[str, int] = defaultdict(int)
        
        # Latency samples for percentiles
        self._latencies: list[int] = []
        self._max_latencies = 1000
        
        # Hourly aggregates
        self._hourly_aggregates: dict[str, AggregatedMetrics] = {}
        
        # Daily aggregates
        self._daily_aggregates: dict[str, AggregatedMetrics] = {}
        
        # Startup time
        self._started_at = datetime.utcnow()
    
    def record_request(self, metrics: RequestMetrics) -> None:
        """Record metrics for a single request."""
        # Add to buffer
        self._requests.append(metrics)
        if len(self._requests) > self._max_requests:
            self._requests.pop(0)
        
        # Update counters
        self._counters[MetricType.SEARCH_REQUEST.value] += 1
        
        if metrics.outcome == "HIT":
            self._counters[MetricType.SEARCH_HIT.value] += 1
        elif metrics.outcome == "MISS":
            self._counters[MetricType.SEARCH_MISS.value] += 1
        
        if metrics.ambiguity_type and metrics.ambiguity_type != "NONE":
            self._counters[MetricType.AMBIGUITY_DETECTED.value] += 1
        
        if metrics.llm_reranked:
            self._counters[MetricType.RERANK_ACTIVATED.value] += 1
        
        if metrics.intent_cache_hit:
            self._counters[MetricType.CACHE_HIT.value] += 1
        else:
            self._counters[MetricType.CACHE_MISS.value] += 1
        
        # Track latency
        self._latencies.append(metrics.total_latency_ms)
        if len(self._latencies) > self._max_latencies:
            self._latencies.pop(0)
    
    def record_feedback(
        self, 
        outcome: Literal["APPROVED", "REJECTED", "MODIFIED"],
        table_id: int,
        score_at_decision: float,
    ) -> None:
        """Record feedback event."""
        if outcome == "APPROVED":
            self._counters[MetricType.FEEDBACK_APPROVED.value] += 1
        elif outcome == "REJECTED":
            self._counters[MetricType.FEEDBACK_REJECTED.value] += 1
            # Track false positives (high score but rejected)
            if score_at_decision > 0.7:
                self._counters["false_positive"] += 1
        else:
            self._counters[MetricType.FEEDBACK_MODIFIED.value] += 1
    
    def record_error(self, error_type: str = "general") -> None:
        """Record an error."""
        self._counters[MetricType.ERROR.value] += 1
        self._counters[f"error_{error_type}"] += 1
    
    def record_llm_call(self, call_type: str, latency_ms: int) -> None:
        """Record an LLM call."""
        self._counters[MetricType.LLM_CALL.value] += 1
        self._counters[f"llm_{call_type}"] += 1
    
    def get_current_stats(self) -> dict:
        """Get current statistics."""
        total_requests = self._counters.get(MetricType.SEARCH_REQUEST.value, 0)
        hits = self._counters.get(MetricType.SEARCH_HIT.value, 0)
        approved = self._counters.get(MetricType.FEEDBACK_APPROVED.value, 0)
        rejected = self._counters.get(MetricType.FEEDBACK_REJECTED.value, 0)
        
        # Calculate percentiles
        p50, p95, p99 = self._calculate_percentiles()
        
        return {
            "uptime_seconds": (datetime.utcnow() - self._started_at).total_seconds(),
            "total_requests": total_requests,
            
            # Quality
            "hit_rate": hits / total_requests if total_requests > 0 else 0,
            "ambiguity_rate": (
                self._counters.get(MetricType.AMBIGUITY_DETECTED.value, 0) / 
                total_requests if total_requests > 0 else 0
            ),
            "false_positive_rate": (
                self._counters.get("false_positive", 0) /
                rejected if rejected > 0 else 0
            ),
            
            # Feedback
            "feedback_count": approved + rejected,
            "approval_rate": (
                approved / (approved + rejected) if (approved + rejected) > 0 else 0
            ),
            
            # Performance
            "avg_latency_ms": (
                sum(self._latencies) / len(self._latencies) 
                if self._latencies else 0
            ),
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "p99_latency_ms": p99,
            
            # LLM
            "llm_calls_total": self._counters.get(MetricType.LLM_CALL.value, 0),
            "rerank_activation_rate": (
                self._counters.get(MetricType.RERANK_ACTIVATED.value, 0) /
                total_requests if total_requests > 0 else 0
            ),
            
            # Cache
            "cache_hit_rate": (
                self._counters.get(MetricType.CACHE_HIT.value, 0) /
                (self._counters.get(MetricType.CACHE_HIT.value, 0) + 
                 self._counters.get(MetricType.CACHE_MISS.value, 0))
                if (self._counters.get(MetricType.CACHE_HIT.value, 0) + 
                    self._counters.get(MetricType.CACHE_MISS.value, 0)) > 0 else 0
            ),
            
            # Errors
            "error_count": self._counters.get(MetricType.ERROR.value, 0),
        }
    
    def _calculate_percentiles(self) -> tuple[float, float, float]:
        """Calculate latency percentiles."""
        if not self._latencies:
            return 0, 0, 0
        
        sorted_latencies = sorted(self._latencies)
        n = len(sorted_latencies)
        
        p50 = sorted_latencies[int(n * 0.50)]
        p95 = sorted_latencies[int(n * 0.95)]
        p99 = sorted_latencies[min(int(n * 0.99), n - 1)]
        
        return p50, p95, p99
    
    def aggregate_hourly(self) -> AggregatedMetrics:
        """Aggregate metrics for the last hour."""
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        
        recent = [r for r in self._requests if r.timestamp >= hour_ago]
        
        return self._aggregate_requests(recent, hour_ago, now, "hour")
    
    def aggregate_daily(self) -> AggregatedMetrics:
        """Aggregate metrics for the last 24 hours."""
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        
        recent = [r for r in self._requests if r.timestamp >= day_ago]
        
        return self._aggregate_requests(recent, day_ago, now, "day")
    
    def _aggregate_requests(
        self,
        requests: list[RequestMetrics],
        start: datetime,
        end: datetime,
        period_type: str,
    ) -> AggregatedMetrics:
        """Aggregate a list of request metrics."""
        if not requests:
            return AggregatedMetrics(
                period_start=start,
                period_end=end,
                period_type=period_type,
            )
        
        total = len(requests)
        hits = sum(1 for r in requests if r.outcome == "HIT")
        ambiguous = sum(1 for r in requests if r.ambiguity_type and r.ambiguity_type != "NONE")
        reranked = sum(1 for r in requests if r.llm_reranked)
        cache_hits = sum(1 for r in requests if r.intent_cache_hit)
        
        latencies = sorted([r.total_latency_ms for r in requests])
        n = len(latencies)
        
        return AggregatedMetrics(
            period_start=start,
            period_end=end,
            period_type=period_type,
            total_requests=total,
            successful_requests=hits,
            hit_rate_top1=hits / total,
            ambiguity_rate=ambiguous / total,
            avg_latency_ms=sum(latencies) / n,
            p50_latency_ms=latencies[int(n * 0.50)],
            p95_latency_ms=latencies[int(n * 0.95)],
            p99_latency_ms=latencies[min(int(n * 0.99), n - 1)],
            rerank_activation_rate=reranked / total,
            intent_cache_hit_rate=cache_hits / total,
        )
    
    def get_export_data(self) -> dict:
        """Get data formatted for DataMesh export."""
        stats = self.get_current_stats()
        hourly = self.aggregate_hourly()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "agent_version": "1.0.0",
            "current": stats,
            "hourly": {
                "total_requests": hourly.total_requests,
                "hit_rate": hourly.hit_rate_top1,
                "ambiguity_rate": hourly.ambiguity_rate,
                "p50_latency_ms": hourly.p50_latency_ms,
                "p95_latency_ms": hourly.p95_latency_ms,
                "rerank_rate": hourly.rerank_activation_rate,
                "cache_hit_rate": hourly.intent_cache_hit_rate,
            }
        }


# Global instance
_collector: Optional[EnhancedMetricsCollector] = None


def get_metrics_collector() -> EnhancedMetricsCollector:
    """Get or create metrics collector."""
    global _collector
    if _collector is None:
        _collector = EnhancedMetricsCollector()
    return _collector
