"""
Quality Sync Scheduler

Proactive daily sync of quality metrics from Athena.
Checks if source was updated before syncing.
"""

import asyncio
from datetime import datetime, time
from typing import Optional
import logging

from .cache import get_quality_cache
from .athena_client import get_athena_client

logger = logging.getLogger(__name__)


class QualitySyncScheduler:
    """
    Scheduler for proactive quality sync.
    
    Strategy:
    1. Run daily at configured time (default: 06:00)
    2. Check if Athena has new data
    3. Only sync if data was updated
    """
    
    def __init__(
        self,
        sync_hour: int = 6,
        sync_minute: int = 0,
        check_interval_hours: float = 1.0,
    ):
        self.sync_time = time(hour=sync_hour, minute=sync_minute)
        self.check_interval_hours = check_interval_hours
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_daily_sync: Optional[datetime] = None
    
    async def start(self) -> None:
        """Start the sync scheduler."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Quality sync scheduler started. Daily sync at {self.sync_time}")
    
    async def stop(self) -> None:
        """Stop the sync scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Quality sync scheduler stopped")
    
    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_and_sync()
            except Exception as e:
                logger.error(f"Sync error: {e}")
            
            # Wait before next check
            await asyncio.sleep(self.check_interval_hours * 3600)
    
    async def _check_and_sync(self) -> None:
        """Check if sync is needed and execute."""
        now = datetime.utcnow()
        
        # Check if it's time for daily sync
        if self._should_run_daily_sync(now):
            logger.info("Running daily quality sync...")
            result = await self._execute_sync()
            self._last_daily_sync = now
            logger.info(f"Daily sync complete: {result}")
    
    def _should_run_daily_sync(self, now: datetime) -> bool:
        """Check if we should run the daily sync."""
        # Never synced
        if self._last_daily_sync is None:
            return True
        
        # Already synced today
        if self._last_daily_sync.date() == now.date():
            return False
        
        # Past sync time today
        if now.time() >= self.sync_time:
            return True
        
        return False
    
    async def _execute_sync(self) -> dict:
        """Execute the sync operation."""
        cache = get_quality_cache()
        
        # Check if Athena has updates
        client = get_athena_client()
        
        if cache._last_sync:
            # Check for updates since last sync
            updated = await client.get_updated_tables_since(cache._last_sync)
            
            if not updated:
                return {"type": "skipped", "reason": "no_updates"}
            
            # Incremental sync
            return await cache.sync_from_athena(force=False)
        else:
            # First sync - full
            return await cache.sync_from_athena(force=True)
    
    async def force_sync(self) -> dict:
        """Force immediate full sync."""
        cache = get_quality_cache()
        return await cache.sync_from_athena(force=True)


# Global instance
_scheduler: Optional[QualitySyncScheduler] = None


def get_sync_scheduler() -> QualitySyncScheduler:
    """Get or create sync scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = QualitySyncScheduler()
    return _scheduler


async def start_quality_sync() -> None:
    """Start the quality sync scheduler."""
    scheduler = get_sync_scheduler()
    await scheduler.start()


async def stop_quality_sync() -> None:
    """Stop the quality sync scheduler."""
    scheduler = get_sync_scheduler()
    await scheduler.stop()
