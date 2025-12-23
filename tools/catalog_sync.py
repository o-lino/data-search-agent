"""
Catalog Sync Tool

Syncs table catalog from gestao-cases-2.0 to the agent's vector store.
"""

import httpx
from typing import Optional

from src.core.config import settings
from src.agent.rag.retriever import get_retriever


async def sync_from_gestao_cases(api_url: Optional[str] = None) -> dict:
    """
    Fetch tables from gestao-cases-2.0 and index them.
    
    Args:
        api_url: Override API URL (uses settings if not provided)
    
    Returns:
        Sync result with counts
    """
    url = api_url or settings.gestao_cases_api_url
    retriever = get_retriever()
    
    synced = 0
    failed = 0
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch tables from gestao-cases
            response = await client.get(f"{url}/api/v1/data-tables")
            response.raise_for_status()
            
            tables = response.json()
            
            for table in tables:
                try:
                    await retriever.index_table({
                        "id": table.get("id"),
                        "name": table.get("name"),
                        "display_name": table.get("display_name"),
                        "description": table.get("description"),
                        "domain": table.get("domain"),
                        "schema_name": table.get("schema_name"),
                        "keywords": table.get("keywords", []),
                        "columns": table.get("columns", []),
                        "owner_id": table.get("owner_id"),
                        "owner_name": table.get("owner", {}).get("name") if table.get("owner") else None,
                    })
                    synced += 1
                except Exception as e:
                    print(f"Failed to index table {table.get('id')}: {e}")
                    failed += 1
        
        return {
            "success": failed == 0,
            "tables_synced": synced,
            "tables_failed": failed,
            "source": url,
        }
        
    except Exception as e:
        return {
            "success": False,
            "tables_synced": synced,
            "tables_failed": failed,
            "error": str(e),
            "source": url,
        }


async def sync_single_table(table_data: dict) -> bool:
    """
    Sync a single table to the vector store.
    
    Args:
        table_data: Table data dictionary
    
    Returns:
        True if successful
    """
    retriever = get_retriever()
    
    try:
        await retriever.index_table(table_data)
        return True
    except Exception as e:
        print(f"Failed to sync table: {e}")
        return False
