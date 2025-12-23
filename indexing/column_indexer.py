"""
Column Indexer

Batch indexing of column metadata for column-level search.
"""

from typing import Optional
from dataclasses import dataclass
import asyncio

from ..rag.column_retriever import get_column_retriever


@dataclass
class ColumnMetadata:
    """Column metadata for indexing."""
    column_id: int
    column_name: str
    column_display_name: str
    column_description: str
    column_type: str
    table_id: int
    table_name: str
    table_display_name: str
    domain: str
    owner_id: int
    owner_name: str


class ColumnIndexer:
    """
    Batch indexer for column metadata.
    
    Features:
    - Batch processing with rate limiting
    - Progress tracking
    - Resume from checkpoint
    """
    
    def __init__(
        self,
        batch_size: int = 100,
        delay_between_batches: float = 0.5,
    ):
        self.batch_size = batch_size
        self.delay = delay_between_batches
        self._indexed_count = 0
        self._error_count = 0
    
    async def index_table_columns(
        self,
        table_id: int,
        table_name: str,
        table_display_name: str,
        domain: str,
        owner_id: int,
        owner_name: str,
        columns: list[dict],
    ) -> int:
        """
        Index all columns for a table.
        
        Args:
            table_id: Table ID
            table_name: Table name
            table_display_name: Display name
            domain: Domain name
            owner_id: Owner ID
            owner_name: Owner name
            columns: List of column dicts with:
                - column_id
                - column_name
                - column_display_name (optional)
                - column_description (optional)
                - column_type
        
        Returns:
            Number of columns indexed
        """
        retriever = get_column_retriever(use_mock=False)
        indexed = 0
        
        for col in columns:
            column_data = {
                "column_id": col.get("column_id", 0),
                "column_name": col.get("column_name", ""),
                "column_display_name": col.get("column_display_name", col.get("column_name", "")),
                "column_description": col.get("column_description", ""),
                "column_type": col.get("column_type", "string"),
                "table_id": table_id,
                "table_name": table_name,
                "table_display_name": table_display_name,
                "domain": domain,
                "owner_id": owner_id,
                "owner_name": owner_name,
            }
            
            try:
                success = await retriever.index_column(column_data)
                if success:
                    indexed += 1
                    self._indexed_count += 1
            except Exception as e:
                self._error_count += 1
                print(f"Warning: Failed to index column {col.get('column_name')}: {e}")
        
        return indexed
    
    async def bulk_index(
        self,
        tables_with_columns: list[dict],
        progress_callback: Optional[callable] = None,
    ) -> dict:
        """
        Bulk index columns from multiple tables.
        
        Args:
            tables_with_columns: List of dicts with:
                - table_id
                - table_name
                - table_display_name
                - domain
                - owner_id
                - owner_name
                - columns: list of column dicts
            progress_callback: Optional callback(current, total)
        
        Returns:
            Summary dict
        """
        total_tables = len(tables_with_columns)
        total_columns = sum(len(t.get("columns", [])) for t in tables_with_columns)
        
        self._indexed_count = 0
        self._error_count = 0
        
        for i, table in enumerate(tables_with_columns):
            await self.index_table_columns(
                table_id=table.get("table_id", 0),
                table_name=table.get("table_name", ""),
                table_display_name=table.get("table_display_name", ""),
                domain=table.get("domain", ""),
                owner_id=table.get("owner_id", 0),
                owner_name=table.get("owner_name", ""),
                columns=table.get("columns", []),
            )
            
            if progress_callback:
                progress_callback(i + 1, total_tables)
            
            # Rate limiting
            if (i + 1) % self.batch_size == 0:
                await asyncio.sleep(self.delay)
        
        return {
            "tables_processed": total_tables,
            "columns_total": total_columns,
            "columns_indexed": self._indexed_count,
            "errors": self._error_count,
        }
    
    @property
    def stats(self) -> dict:
        """Get indexing statistics."""
        return {
            "indexed": self._indexed_count,
            "errors": self._error_count,
        }


# Global instance
_column_indexer: Optional[ColumnIndexer] = None


def get_column_indexer() -> ColumnIndexer:
    """Get or create column indexer."""
    global _column_indexer
    if _column_indexer is None:
        _column_indexer = ColumnIndexer()
    return _column_indexer
