"""
DataMesh Exporter

Exports agent metrics to DataMesh for centralized monitoring.
Supports S3, Kinesis, and HTTP endpoints.
"""

from typing import Optional, Literal
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
import asyncio
import os


@dataclass 
class ExportConfig:
    """Configuration for DataMesh export."""
    # Export method
    method: Literal["s3", "kinesis", "http"] = "s3"
    
    # S3 config
    s3_bucket: str = "datamesh-metrics"
    s3_prefix: str = "agents/table-search/"
    
    # Kinesis config
    kinesis_stream: str = "agent-metrics"
    
    # HTTP config
    http_endpoint: str = ""
    http_api_key: str = ""
    
    # Schedule
    export_interval_minutes: int = 5
    
    # Batch
    batch_size: int = 100


class DataMeshExporter:
    """
    Exports metrics to DataMesh infrastructure.
    
    Supports:
    - S3: Parquet files for analytics
    - Kinesis: Real-time streaming
    - HTTP: REST API ingestion
    """
    
    def __init__(self, config: Optional[ExportConfig] = None):
        self.config = config or ExportConfig()
        self._export_buffer: list[dict] = []
        self._last_export: Optional[datetime] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the background export task."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._export_loop())
        print(f"[DataMeshExporter] Started ({self.config.method})")
    
    async def stop(self) -> None:
        """Stop the background export task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        # Flush remaining
        await self._flush_buffer()
        print("[DataMeshExporter] Stopped")
    
    async def _export_loop(self) -> None:
        """Background loop for periodic exports."""
        interval = self.config.export_interval_minutes * 60
        
        while self._running:
            try:
                await asyncio.sleep(interval)
                await self._collect_and_export()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[DataMeshExporter] Error: {e}")
    
    async def _collect_and_export(self) -> None:
        """Collect current metrics and export."""
        from .metrics_collector import get_metrics_collector
        
        collector = get_metrics_collector()
        data = collector.get_export_data()
        
        # Add metadata
        record = {
            "event_type": "agent_metrics",
            "agent_name": "table-search-agent",
            "agent_version": "1.0.0",
            "environment": os.getenv("ENVIRONMENT", "development"),
            "exported_at": datetime.utcnow().isoformat(),
            **data
        }
        
        self._export_buffer.append(record)
        
        if len(self._export_buffer) >= self.config.batch_size:
            await self._flush_buffer()
    
    async def _flush_buffer(self) -> None:
        """Flush buffer to DataMesh."""
        if not self._export_buffer:
            return
        
        try:
            if self.config.method == "s3":
                await self._export_to_s3()
            elif self.config.method == "kinesis":
                await self._export_to_kinesis()
            elif self.config.method == "http":
                await self._export_to_http()
            
            self._export_buffer.clear()
            self._last_export = datetime.utcnow()
            
        except Exception as e:
            print(f"[DataMeshExporter] Flush failed: {e}")
    
    async def _export_to_s3(self) -> None:
        """Export to S3 as JSON lines."""
        try:
            import boto3
            from io import BytesIO
            
            # Create S3 client
            s3 = boto3.client('s3')
            
            # Generate key with timestamp
            now = datetime.utcnow()
            key = (
                f"{self.config.s3_prefix}"
                f"year={now.year}/month={now.month:02d}/day={now.day:02d}/"
                f"metrics_{now.strftime('%H%M%S')}.jsonl"
            )
            
            # Create JSON Lines content
            content = "\n".join(json.dumps(r) for r in self._export_buffer)
            
            # Upload
            s3.put_object(
                Bucket=self.config.s3_bucket,
                Key=key,
                Body=content.encode('utf-8'),
                ContentType='application/json',
            )
            
            print(f"[DataMeshExporter] Exported {len(self._export_buffer)} records to s3://{self.config.s3_bucket}/{key}")
            
        except ImportError:
            print("[DataMeshExporter] boto3 not installed, using mock export")
            await self._mock_export()
        except Exception as e:
            print(f"[DataMeshExporter] S3 export failed: {e}")
            await self._mock_export()
    
    async def _export_to_kinesis(self) -> None:
        """Export to Kinesis stream."""
        try:
            import boto3
            
            kinesis = boto3.client('kinesis')
            
            records = [
                {
                    'Data': json.dumps(r).encode('utf-8'),
                    'PartitionKey': r.get('agent_name', 'default'),
                }
                for r in self._export_buffer
            ]
            
            response = kinesis.put_records(
                StreamName=self.config.kinesis_stream,
                Records=records,
            )
            
            failed = response.get('FailedRecordCount', 0)
            print(f"[DataMeshExporter] Kinesis: {len(records) - failed}/{len(records)} records sent")
            
        except ImportError:
            print("[DataMeshExporter] boto3 not installed, using mock export")
            await self._mock_export()
        except Exception as e:
            print(f"[DataMeshExporter] Kinesis export failed: {e}")
    
    async def _export_to_http(self) -> None:
        """Export via HTTP POST."""
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.config.http_endpoint,
                    json={"records": self._export_buffer},
                    headers={
                        "Authorization": f"Bearer {self.config.http_api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    print(f"[DataMeshExporter] HTTP: {len(self._export_buffer)} records sent")
                else:
                    print(f"[DataMeshExporter] HTTP failed: {response.status_code}")
                    
        except Exception as e:
            print(f"[DataMeshExporter] HTTP export failed: {e}")
    
    async def _mock_export(self) -> None:
        """Mock export for development."""
        print(f"[DataMeshExporter] Mock: {len(self._export_buffer)} records")
        for r in self._export_buffer[:3]:
            print(f"  - {r.get('exported_at')}: requests={r.get('current', {}).get('total_requests', 0)}")
    
    async def export_now(self) -> dict:
        """Force immediate export and return status."""
        await self._collect_and_export()
        await self._flush_buffer()
        
        return {
            "status": "exported",
            "method": self.config.method,
            "last_export": self._last_export.isoformat() if self._last_export else None,
            "buffer_size": len(self._export_buffer),
        }
    
    @property
    def status(self) -> dict:
        """Get exporter status."""
        return {
            "running": self._running,
            "method": self.config.method,
            "last_export": self._last_export.isoformat() if self._last_export else None,
            "buffer_size": len(self._export_buffer),
            "interval_minutes": self.config.export_interval_minutes,
        }


# Global instance
_exporter: Optional[DataMeshExporter] = None


def get_datamesh_exporter() -> DataMeshExporter:
    """Get or create DataMesh exporter."""
    global _exporter
    if _exporter is None:
        config = ExportConfig(
            method=os.getenv("DATAMESH_EXPORT_METHOD", "s3"),
            s3_bucket=os.getenv("DATAMESH_S3_BUCKET", "datamesh-metrics"),
            s3_prefix=os.getenv("DATAMESH_S3_PREFIX", "agents/table-search/"),
            kinesis_stream=os.getenv("DATAMESH_KINESIS_STREAM", "agent-metrics"),
            http_endpoint=os.getenv("DATAMESH_HTTP_ENDPOINT", ""),
            http_api_key=os.getenv("DATAMESH_HTTP_API_KEY", ""),
            export_interval_minutes=int(os.getenv("DATAMESH_EXPORT_INTERVAL", "5")),
        )
        _exporter = DataMeshExporter(config)
    return _exporter


async def start_datamesh_export() -> None:
    """Start DataMesh export."""
    exporter = get_datamesh_exporter()
    await exporter.start()


async def stop_datamesh_export() -> None:
    """Stop DataMesh export."""
    exporter = get_datamesh_exporter()
    await exporter.stop()
