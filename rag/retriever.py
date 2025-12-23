"""
RAG Retriever Module

Provides table retrieval using vector embeddings.
Supports CRUD operations for catalog management.
"""

from typing import Optional, Protocol


class TableRetriever(Protocol):
    """Protocol for table retrieval."""
    
    async def search(
        self,
        query: str,
        domain_filter: Optional[str] = None,
        max_results: int = 10
    ) -> list[dict]:
        """Search for tables matching the query."""
        ...
    
    async def index_table(self, table: dict) -> None:
        """Index/update a table in the vector store."""
        ...
    
    async def delete_table(self, table_id: int) -> bool:
        """Delete a table from the vector store."""
        ...
    
    async def get_table(self, table_id: int) -> Optional[dict]:
        """Get a specific table by ID."""
        ...
    
    async def list_tables(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """List all indexed tables."""
        ...
    
    async def count(self) -> int:
        """Count total indexed tables."""
        ...
    
    async def clear(self) -> int:
        """Clear all tables. Returns count deleted."""
        ...


class MockRetriever:
    """Mock retriever for testing without vector database."""
    
    def __init__(self):
        self._tables: dict[int, dict] = {}
    
    async def search(
        self,
        query: str,
        domain_filter: Optional[str] = None,
        max_results: int = 10,
        **kwargs
    ) -> list[dict]:
        """Return mock results based on simple matching."""
        query_lower = query.lower()
        results = []
        
        for table in self._tables.values():
            text = ' '.join(filter(None, [
                table.get("name", ""),
                table.get("display_name", ""),
                table.get("description", ""),
            ])).lower()
            
            if any(word in text for word in query_lower.split()):
                if domain_filter is None or table.get("domain") == domain_filter:
                    results.append(table)
        
        return results[:max_results]
    
    async def index_table(self, table: dict) -> None:
        """Add/update table in mock store."""
        self._tables[table["id"]] = table
    
    async def delete_table(self, table_id: int) -> bool:
        """Delete table from mock store."""
        if table_id in self._tables:
            del self._tables[table_id]
            return True
        return False
    
    async def get_table(self, table_id: int) -> Optional[dict]:
        """Get a specific table."""
        return self._tables.get(table_id)
    
    async def list_tables(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """List all tables."""
        tables = list(self._tables.values())
        return tables[offset:offset + limit]
    
    async def count(self) -> int:
        """Count tables."""
        return len(self._tables)
    
    async def clear(self) -> int:
        """Clear all tables."""
        count = len(self._tables)
        self._tables.clear()
        return count


# Global retriever instance
_retriever: Optional[TableRetriever] = None


def get_retriever(use_optimized: bool = True) -> TableRetriever:
    """
    Get or create the table retriever instance.
    
    Args:
        use_optimized: If True, use OptimizedRetriever with multi-vector search
    """
    global _retriever
    
    if _retriever is None:
        if use_optimized:
            try:
                from rag.optimized_retriever import OptimizedRetriever
                _retriever = OptimizedRetriever(mode="high_accuracy")
                print("[Retriever] Using OptimizedRetriever (high accuracy)")
            except Exception as e:
                print(f"[Retriever] OptimizedRetriever failed: {e}, using MockRetriever")
                _retriever = MockRetriever()
        else:
            _retriever = MockRetriever()
    
    return _retriever

