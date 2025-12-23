"""
Column Retriever

Semantic search over column-level metadata.
Finds tables based on specific field names and concepts.
"""

from typing import Optional, Protocol
from dataclasses import dataclass


@dataclass
class ColumnSearchResult:
    """Result from column search."""
    column_id: int
    column_name: str
    column_display_name: str
    column_description: str
    column_type: str
    
    # Parent table info
    table_id: int
    table_name: str
    table_display_name: str
    domain: str
    owner_id: int
    owner_name: str
    
    # Search metadata
    distance: float  # Vector distance (lower = better match)
    
    @property
    def similarity_score(self) -> float:
        """Convert distance to similarity (0-1)."""
        return max(0.0, 1.0 - self.distance)


class ColumnRetriever(Protocol):
    """Protocol for column retrieval."""
    
    async def search(
        self,
        query: str,
        domain_filter: Optional[str] = None,
        table_filter: Optional[int] = None,
        max_results: int = 20,
    ) -> list[ColumnSearchResult]:
        """Search for columns matching query."""
        ...
    
    async def index_column(self, column_data: dict) -> bool:
        """Index a single column."""
        ...
    
    async def index_batch(self, columns: list[dict]) -> int:
        """Index multiple columns, return count."""
        ...


class ChromaColumnRetriever:
    """
    ChromaDB-based column retriever.
    
    Uses a separate collection for column-level search.
    """
    
    def __init__(
        self,
        collection_name: str = "table_columns",
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self._collection = None
        self._embedding_fn = None
    
    def _get_collection(self):
        """Get or create ChromaDB collection."""
        if self._collection is None:
            try:
                import chromadb
                from chromadb.utils import embedding_functions
                
                client = chromadb.Client()
                
                self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=self.embedding_model
                )
                
                self._collection = client.get_or_create_collection(
                    name=self.collection_name,
                    embedding_function=self._embedding_fn,
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception as e:
                print(f"Warning: ChromaDB init failed: {e}")
                return None
        
        return self._collection
    
    async def search(
        self,
        query: str,
        domain_filter: Optional[str] = None,
        table_filter: Optional[int] = None,
        max_results: int = 20,
    ) -> list[ColumnSearchResult]:
        """
        Search for columns matching query.
        
        Searches across:
        - column_name
        - column_display_name
        - column_description
        """
        collection = self._get_collection()
        if collection is None:
            return []
        
        # Build where filter
        where_filter = None
        if domain_filter or table_filter:
            conditions = []
            if domain_filter:
                conditions.append({"domain": domain_filter})
            if table_filter:
                conditions.append({"table_id": table_filter})
            
            if len(conditions) == 1:
                where_filter = conditions[0]
            else:
                where_filter = {"$and": conditions}
        
        try:
            results = collection.query(
                query_texts=[query],
                n_results=max_results,
                where=where_filter,
            )
            
            column_results = []
            
            if results and results["ids"] and results["ids"][0]:
                for i, col_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else 0.5
                    
                    column_results.append(ColumnSearchResult(
                        column_id=int(col_id.split("_")[1]) if "_" in col_id else 0,
                        column_name=metadata.get("column_name", ""),
                        column_display_name=metadata.get("column_display_name", ""),
                        column_description=metadata.get("column_description", ""),
                        column_type=metadata.get("column_type", ""),
                        table_id=metadata.get("table_id", 0),
                        table_name=metadata.get("table_name", ""),
                        table_display_name=metadata.get("table_display_name", ""),
                        domain=metadata.get("domain", ""),
                        owner_id=metadata.get("owner_id", 0),
                        owner_name=metadata.get("owner_name", ""),
                        distance=distance,
                    ))
            
            return column_results
            
        except Exception as e:
            print(f"Warning: Column search failed: {e}")
            return []
    
    async def index_column(self, column_data: dict) -> bool:
        """
        Index a single column.
        
        Expected column_data format:
        {
            "column_id": int,
            "column_name": str,
            "column_display_name": str,
            "column_description": str,
            "column_type": str,
            "table_id": int,
            "table_name": str,
            "table_display_name": str,
            "domain": str,
            "owner_id": int,
            "owner_name": str,
        }
        """
        collection = self._get_collection()
        if collection is None:
            return False
        
        try:
            # Build document text for embedding
            doc_text = self._build_document_text(column_data)
            
            # Unique ID
            doc_id = f"col_{column_data['column_id']}_{column_data['table_id']}"
            
            collection.upsert(
                ids=[doc_id],
                documents=[doc_text],
                metadatas=[{
                    "column_name": column_data.get("column_name", ""),
                    "column_display_name": column_data.get("column_display_name", ""),
                    "column_description": column_data.get("column_description", ""),
                    "column_type": column_data.get("column_type", ""),
                    "table_id": column_data.get("table_id", 0),
                    "table_name": column_data.get("table_name", ""),
                    "table_display_name": column_data.get("table_display_name", ""),
                    "domain": column_data.get("domain", ""),
                    "owner_id": column_data.get("owner_id", 0),
                    "owner_name": column_data.get("owner_name", ""),
                }]
            )
            
            return True
            
        except Exception as e:
            print(f"Warning: Column index failed: {e}")
            return False
    
    async def index_batch(self, columns: list[dict]) -> int:
        """Index multiple columns."""
        success_count = 0
        for col in columns:
            if await self.index_column(col):
                success_count += 1
        return success_count
    
    def _build_document_text(self, column_data: dict) -> str:
        """Build searchable document text from column data."""
        parts = [
            column_data.get("column_name", ""),
            column_data.get("column_display_name", ""),
            column_data.get("column_description", ""),
            f"tabela: {column_data.get('table_name', '')}",
            f"domínio: {column_data.get('domain', '')}",
        ]
        return " | ".join(filter(None, parts))


class MockColumnRetriever:
    """Mock retriever for development/testing."""
    
    def __init__(self):
        self._mock_columns = self._generate_mock_data()
    
    def _generate_mock_data(self) -> list[ColumnSearchResult]:
        """Generate mock column data."""
        return [
            ColumnSearchResult(
                column_id=1, column_name="nr_cpf", column_display_name="CPF do Cliente",
                column_description="Número do CPF com 11 dígitos", column_type="string",
                table_id=1, table_name="tb_clientes", table_display_name="Clientes",
                domain="cadastro", owner_id=1, owner_name="João", distance=0.0
            ),
            ColumnSearchResult(
                column_id=2, column_name="nr_cnpj", column_display_name="CNPJ da Empresa",
                column_description="Número do CNPJ com 14 dígitos", column_type="string",
                table_id=2, table_name="tb_empresas", table_display_name="Empresas",
                domain="cadastro", owner_id=1, owner_name="João", distance=0.0
            ),
            ColumnSearchResult(
                column_id=3, column_name="vl_faturamento", column_display_name="Valor Faturamento",
                column_description="Valor total faturado no período", column_type="decimal",
                table_id=3, table_name="tb_vendas_sot", table_display_name="Vendas SOT",
                domain="vendas", owner_id=2, owner_name="Maria", distance=0.0
            ),
            ColumnSearchResult(
                column_id=4, column_name="dt_transacao", column_display_name="Data Transação",
                column_description="Data em que a transação ocorreu", column_type="date",
                table_id=3, table_name="tb_vendas_sot", table_display_name="Vendas SOT",
                domain="vendas", owner_id=2, owner_name="Maria", distance=0.0
            ),
            ColumnSearchResult(
                column_id=5, column_name="nr_contrato", column_display_name="Número Contrato",
                column_description="Identificador único do contrato", column_type="string",
                table_id=4, table_name="tb_contratos_consig", table_display_name="Contratos Consignado",
                domain="crédito", owner_id=3, owner_name="Pedro", distance=0.0
            ),
        ]
    
    async def search(
        self,
        query: str,
        domain_filter: Optional[str] = None,
        table_filter: Optional[int] = None,
        max_results: int = 20,
    ) -> list[ColumnSearchResult]:
        """Search mock columns."""
        query_lower = query.lower()
        results = []
        
        for col in self._mock_columns:
            # Simple keyword matching
            score = 0.0
            
            if query_lower in col.column_name.lower():
                score = 0.9
            elif query_lower in col.column_display_name.lower():
                score = 0.8
            elif query_lower in col.column_description.lower():
                score = 0.6
            
            if domain_filter and col.domain != domain_filter:
                continue
            if table_filter and col.table_id != table_filter:
                continue
            
            if score > 0:
                col.distance = 1.0 - score
                results.append(col)
        
        # Sort by distance (lower = better)
        results.sort(key=lambda x: x.distance)
        return results[:max_results]
    
    async def index_column(self, column_data: dict) -> bool:
        return True
    
    async def index_batch(self, columns: list[dict]) -> int:
        return len(columns)


# Global instance
_column_retriever: Optional[ColumnRetriever] = None


def get_column_retriever(use_mock: bool = True) -> ColumnRetriever:
    """Get or create column retriever."""
    global _column_retriever
    if _column_retriever is None:
        if use_mock:
            _column_retriever = MockColumnRetriever()
        else:
            _column_retriever = ChromaColumnRetriever()
    return _column_retriever
