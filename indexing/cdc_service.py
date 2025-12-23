"""
CDC Sync Service

Change Data Capture service for automatic catalog synchronization.
Receives dataframes and applies INSERT, UPDATE, DELETE automatically.
"""

from typing import Optional
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json


class ChangeType(str, Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    UNCHANGED = "UNCHANGED"


@dataclass
class ChangeRecord:
    """A single change detected in the catalog."""
    table_id: int
    table_name: str
    change_type: ChangeType
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None
    changed_fields: list[str] = field(default_factory=list)


@dataclass
class CDCResult:
    """Result of a CDC sync operation."""
    success: bool
    inserts: int = 0
    updates: int = 0
    deletes: int = 0
    unchanged: int = 0
    errors: int = 0
    changes: list[ChangeRecord] = field(default_factory=list)
    duration_ms: int = 0
    
    @property
    def total_changes(self) -> int:
        return self.inserts + self.updates + self.deletes


class CDCSyncService:
    """
    Change Data Capture service for catalog synchronization.

    Features:
    - Receives dataframe (as list of dicts)
    - Compares with existing data
    - Detects INSERT, UPDATE, DELETE
    - Applies changes automatically
    - Returns detailed change report
    """
    
    # Fields used for hashing (change detection)
    HASH_FIELDS = [
        "name", "display_name", "description", "domain",
        "keywords", "owner_name", "data_layer", "is_golden_source"
    ]
    
    def __init__(self, retriever=None):
        self._retriever = retriever
        self._hash_cache: dict[int, str] = {}
    
    def _get_retriever(self):
        if self._retriever is None:
            # Use optimized retriever for accuracy
            try:
                from src.agent.rag.optimized_retriever import get_optimized_retriever
                self._retriever = get_optimized_retriever(mode="high_accuracy")
            except Exception:
                from src.agent.rag.retriever import get_retriever
                self._retriever = get_retriever()
        return self._retriever
    
    def _compute_hash(self, record: dict) -> str:
        """Compute hash for change detection."""
        hash_data = {}
        for field in self.HASH_FIELDS:
            value = record.get(field)
            if isinstance(value, list):
                value = sorted(value)
            hash_data[field] = value
        
        serialized = json.dumps(hash_data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]
    
    async def _load_existing_hashes(self) -> dict[int, str]:
        """Load hashes of all existing records."""
        retriever = self._get_retriever()
        
        # Get all current tables
        existing = await retriever.list_tables(limit=10000)
        
        hashes = {}
        for table in existing:
            table_id = table.get("id")
            if table_id:
                # Get full record for hashing
                full_record = await retriever.get_table(table_id)
                if full_record:
                    hashes[table_id] = self._compute_hash(full_record)
        
        return hashes
    
    def _detect_changes(
        self,
        incoming: list[dict],
        existing_hashes: dict[int, str],
    ) -> list[ChangeRecord]:
        """Detect all changes between incoming and existing data."""
        changes = []
        incoming_ids = set()
        
        for record in incoming:
            table_id = record.get("id")
            if not table_id:
                continue
            
            incoming_ids.add(table_id)
            new_hash = self._compute_hash(record)
            old_hash = existing_hashes.get(table_id)
            
            if old_hash is None:
                # New record
                changes.append(ChangeRecord(
                    table_id=table_id,
                    table_name=record.get("name", ""),
                    change_type=ChangeType.INSERT,
                    new_hash=new_hash,
                ))
            elif old_hash != new_hash:
                # Updated record
                changes.append(ChangeRecord(
                    table_id=table_id,
                    table_name=record.get("name", ""),
                    change_type=ChangeType.UPDATE,
                    old_hash=old_hash,
                    new_hash=new_hash,
                ))
            else:
                # Unchanged
                changes.append(ChangeRecord(
                    table_id=table_id,
                    table_name=record.get("name", ""),
                    change_type=ChangeType.UNCHANGED,
                ))
        
        # Detect deletes (in existing but not in incoming)
        for table_id in existing_hashes:
            if table_id not in incoming_ids:
                changes.append(ChangeRecord(
                    table_id=table_id,
                    table_name="",
                    change_type=ChangeType.DELETE,
                    old_hash=existing_hashes[table_id],
                ))
        
        return changes
    
    async def sync(
        self,
        dataframe: list[dict],
        apply_deletes: bool = True,
        dry_run: bool = False,
    ) -> CDCResult:
        """
        Sync dataframe with catalog.
        
        Args:
            dataframe: List of table records (from DataFrame.to_dict('records'))
            apply_deletes: If True, delete tables not in dataframe
            dry_run: If True, only detect changes without applying
            
        Returns:
            CDCResult with detailed change information
        """
        start_time = datetime.utcnow()
        retriever = self._get_retriever()
        
        # Load existing data
        existing_hashes = await self._load_existing_hashes()
        
        # Detect changes
        changes = self._detect_changes(dataframe, existing_hashes)
        
        result = CDCResult(success=True, changes=[])
        
        # Create lookup for incoming records
        incoming_by_id = {r["id"]: r for r in dataframe if r.get("id")}
        
        # Apply changes
        for change in changes:
            try:
                if change.change_type == ChangeType.INSERT:
                    if not dry_run:
                        record = incoming_by_id.get(change.table_id)
                        if record:
                            await retriever.index_table(record)
                    result.inserts += 1
                    result.changes.append(change)
                
                elif change.change_type == ChangeType.UPDATE:
                    if not dry_run:
                        record = incoming_by_id.get(change.table_id)
                        if record:
                            await retriever.index_table(record)
                    result.updates += 1
                    result.changes.append(change)
                
                elif change.change_type == ChangeType.DELETE:
                    if apply_deletes:
                        if not dry_run:
                            await retriever.delete_table(change.table_id)
                        result.deletes += 1
                        result.changes.append(change)
                
                elif change.change_type == ChangeType.UNCHANGED:
                    result.unchanged += 1
                    
            except Exception as e:
                print(f"Error applying {change.change_type} for {change.table_id}: {e}")
                result.errors += 1
                result.success = False
        
        # Calculate duration
        end_time = datetime.utcnow()
        result.duration_ms = int((end_time - start_time).total_seconds() * 1000)
        
        return result
    
    async def preview(self, dataframe: list[dict]) -> CDCResult:
        """
        Preview changes without applying them.
        
        Same as sync(dry_run=True).
        """
        return await self.sync(dataframe, dry_run=True)


# ============== DataFrame Schema ==============

DATAFRAME_SCHEMA = {
    "required": ["id", "name"],
    "optional": [
        "display_name",
        "description", 
        "domain",
        "schema_name",
        "keywords",
        "columns",
        "owner_id",
        "owner_name",
        "data_layer",
        "is_golden_source",
        "update_frequency",
    ],
    "example": {
        "id": 123,
        "name": "tb_vendas_sot",
        "display_name": "Vendas SOT",
        "description": "Tabela de vendas consolidadas",
        "domain": "Vendas",
        "keywords": ["vendas", "mensal"],
        "owner_name": "Time Vendas",
        "data_layer": "SoT",
        "is_golden_source": True,
    }
}


# Global instance
_cdc_service: Optional[CDCSyncService] = None


def get_cdc_service() -> CDCSyncService:
    """Get or create CDC service."""
    global _cdc_service
    if _cdc_service is None:
        _cdc_service = CDCSyncService()
    return _cdc_service
