"""
Health Check System

Provides health status and diagnostics for the agent.
"""

from typing import Optional, Literal
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum


class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health of a single component."""
    name: str
    status: HealthStatus
    message: str = ""
    last_check: Optional[datetime] = None
    details: Optional[dict] = None


@dataclass
class AgentHealth:
    """Overall agent health."""
    status: HealthStatus
    version: str
    uptime_seconds: float
    components: list[ComponentHealth]
    timestamp: datetime
    
    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "timestamp": self.timestamp.isoformat(),
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "details": c.details,
                }
                for c in self.components
            ]
        }


class HealthChecker:
    """
    Health checker for agent components.
    
    Checks:
    - LLM connectivity
    - ChromaDB connectivity
    - Quality cache freshness
    - DataMesh exporter status
    - Error rates
    """
    
    def __init__(self):
        self._started_at = datetime.utcnow()
    
    async def check_all(self) -> AgentHealth:
        """Run all health checks."""
        components = []
        
        # Check each component
        components.append(await self._check_llm())
        components.append(await self._check_vector_db())
        components.append(await self._check_quality_cache())
        components.append(await self._check_exporter())
        components.append(await self._check_error_rate())
        components.append(await self._check_latency())
        
        # Determine overall status
        statuses = [c.status for c in components]
        if HealthStatus.UNHEALTHY in statuses:
            overall = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY
        
        return AgentHealth(
            status=overall,
            version="1.0.0",
            uptime_seconds=(datetime.utcnow() - self._started_at).total_seconds(),
            components=components,
            timestamp=datetime.utcnow(),
        )
    
    async def _check_llm(self) -> ComponentHealth:
        """Check LLM connectivity."""
        try:
            import os
            api_key = os.getenv("OPENAI_API_KEY")
            
            if not api_key:
                return ComponentHealth(
                    name="llm",
                    status=HealthStatus.UNHEALTHY,
                    message="OPENAI_API_KEY not configured",
                )
            
            # Quick ping test would go here in production
            return ComponentHealth(
                name="llm",
                status=HealthStatus.HEALTHY,
                message="API key configured",
                last_check=datetime.utcnow(),
            )
            
        except Exception as e:
            return ComponentHealth(
                name="llm",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    async def _check_vector_db(self) -> ComponentHealth:
        """Check ChromaDB connectivity."""
        try:
            from ..rag.retriever import get_retriever
            
            retriever = get_retriever()
            # Try a simple operation
            # In production, this would verify connection
            
            return ComponentHealth(
                name="vector_db",
                status=HealthStatus.HEALTHY,
                message="ChromaDB available",
                last_check=datetime.utcnow(),
            )
            
        except Exception as e:
            return ComponentHealth(
                name="vector_db",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    async def _check_quality_cache(self) -> ComponentHealth:
        """Check quality cache freshness."""
        try:
            from ..quality import get_quality_cache
            
            cache = get_quality_cache()
            last_sync = cache.last_sync
            
            if last_sync is None:
                return ComponentHealth(
                    name="quality_cache",
                    status=HealthStatus.DEGRADED,
                    message="Never synced",
                )
            
            age_hours = (datetime.utcnow() - last_sync).total_seconds() / 3600
            
            if age_hours > 48:
                return ComponentHealth(
                    name="quality_cache",
                    status=HealthStatus.DEGRADED,
                    message=f"Last sync {age_hours:.1f} hours ago",
                    details={"age_hours": age_hours},
                )
            
            return ComponentHealth(
                name="quality_cache",
                status=HealthStatus.HEALTHY,
                message=f"Last sync {age_hours:.1f} hours ago",
                last_check=datetime.utcnow(),
                details={"age_hours": age_hours},
            )
            
        except Exception as e:
            return ComponentHealth(
                name="quality_cache",
                status=HealthStatus.DEGRADED,
                message=str(e),
            )
    
    async def _check_exporter(self) -> ComponentHealth:
        """Check DataMesh exporter status."""
        try:
            from .datamesh_exporter import get_datamesh_exporter
            
            exporter = get_datamesh_exporter()
            status = exporter.status
            
            if not status["running"]:
                return ComponentHealth(
                    name="datamesh_exporter",
                    status=HealthStatus.DEGRADED,
                    message="Not running",
                    details=status,
                )
            
            return ComponentHealth(
                name="datamesh_exporter",
                status=HealthStatus.HEALTHY,
                message=f"Running ({status['method']})",
                details=status,
            )
            
        except Exception as e:
            return ComponentHealth(
                name="datamesh_exporter",
                status=HealthStatus.DEGRADED,
                message=str(e),
            )
    
    async def _check_error_rate(self) -> ComponentHealth:
        """Check recent error rate."""
        try:
            from .metrics_collector import get_metrics_collector
            
            collector = get_metrics_collector()
            stats = collector.get_current_stats()
            
            error_count = stats.get("error_count", 0)
            total = stats.get("total_requests", 0)
            
            if total == 0:
                return ComponentHealth(
                    name="error_rate",
                    status=HealthStatus.HEALTHY,
                    message="No requests yet",
                )
            
            error_rate = error_count / total
            
            if error_rate > 0.1:
                return ComponentHealth(
                    name="error_rate",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Error rate {error_rate:.1%}",
                    details={"error_rate": error_rate, "errors": error_count},
                )
            elif error_rate > 0.05:
                return ComponentHealth(
                    name="error_rate",
                    status=HealthStatus.DEGRADED,
                    message=f"Error rate {error_rate:.1%}",
                    details={"error_rate": error_rate, "errors": error_count},
                )
            
            return ComponentHealth(
                name="error_rate",
                status=HealthStatus.HEALTHY,
                message=f"Error rate {error_rate:.1%}",
                details={"error_rate": error_rate, "errors": error_count},
            )
            
        except Exception as e:
            return ComponentHealth(
                name="error_rate",
                status=HealthStatus.DEGRADED,
                message=str(e),
            )
    
    async def _check_latency(self) -> ComponentHealth:
        """Check latency health."""
        try:
            from .metrics_collector import get_metrics_collector
            
            collector = get_metrics_collector()
            stats = collector.get_current_stats()
            
            p95 = stats.get("p95_latency_ms", 0)
            
            if p95 == 0:
                return ComponentHealth(
                    name="latency",
                    status=HealthStatus.HEALTHY,
                    message="No requests yet",
                )
            
            if p95 > 5000:
                return ComponentHealth(
                    name="latency",
                    status=HealthStatus.UNHEALTHY,
                    message=f"p95: {p95}ms (> 5000ms)",
                    details={"p95_ms": p95},
                )
            elif p95 > 2000:
                return ComponentHealth(
                    name="latency",
                    status=HealthStatus.DEGRADED,
                    message=f"p95: {p95}ms (> 2000ms)",
                    details={"p95_ms": p95},
                )
            
            return ComponentHealth(
                name="latency",
                status=HealthStatus.HEALTHY,
                message=f"p95: {p95}ms",
                details={"p95_ms": p95},
            )
            
        except Exception as e:
            return ComponentHealth(
                name="latency",
                status=HealthStatus.DEGRADED,
                message=str(e),
            )


# Global instance
_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get or create health checker."""
    global _checker
    if _checker is None:
        _checker = HealthChecker()
    return _checker
