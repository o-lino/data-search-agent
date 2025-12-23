"""
Pre-indexing Pipeline

Processes and indexes metadata ONCE at ingestion time.
LLM summarizes tables, extracts entities, and creates hierarchical indices.

This runs as a background job, NOT on every query.
"""

from typing import Optional
import json
import hashlib

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from ..state import DomainInfo, OwnerInfo, TableInfo
from ..rag.retriever import get_retriever
from src.core.config import settings


# Summarization prompt
SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Você é um especialista em catalogar dados corporativos.
Sua tarefa é criar um RESUMO CONCISO de uma tabela de dados para facilitar buscas.

O resumo deve ter NO MÁXIMO 50 palavras e conter:
1. O que a tabela armazena (vendas, clientes, etc)
2. Principal entidade (cliente, produto, transação)
3. Granularidade (diária, mensal, por transação)
4. Principais métricas disponíveis

Também extraia:
- keywords: 5-10 palavras-chave para busca
- main_entities: entidades principais (cliente, produto, loja)
- granularity: periodicidade dos dados

Retorne JSON com: summary, keywords, main_entities, granularity
"""),
    ("human", """Nome da tabela: {table_name}
Display name: {display_name}
Descrição original: {description}

Colunas (resumo):
{columns_summary}

Retorne o JSON:""")
])


class PreIndexingPipeline:
    """Pipeline for pre-processing metadata before indexing."""
    
    def __init__(self):
        self._llm = None
        self._retriever = None
        
        # In-memory caches (would be Redis in production)
        self._domains: dict[str, DomainInfo] = {}
        self._owners: dict[int, OwnerInfo] = {}
        self._tables: dict[int, TableInfo] = {}
    
    def _get_llm(self):
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=settings.openai_model,
                temperature=0,
                api_key=settings.openai_api_key,
            )
        return self._llm
    
    async def process_table(
        self,
        table_id: int,
        name: str,
        display_name: str,
        description: str,
        columns: list[dict],
        domain_id: str,
        domain_name: str,
        owner_id: int,
        owner_name: str,
    ) -> TableInfo:
        """
        Process a raw table and create indexed TableInfo.
        
        Uses LLM to:
        1. Summarize the table (50 words max)
        2. Extract keywords
        3. Identify main entities
        4. Determine granularity
        """
        # Create columns summary (limit to first 30)
        columns_summary = self._create_columns_summary(columns[:30])
        
        try:
            chain = SUMMARIZE_PROMPT | self._get_llm() | JsonOutputParser()
            
            result = await chain.ainvoke({
                "table_name": name,
                "display_name": display_name,
                "description": description[:1000] if description else "Não informada",
                "columns_summary": columns_summary,
            })
            
            table_info = TableInfo(
                id=table_id,
                name=name,
                display_name=display_name,
                summary=result.get("summary", display_name)[:200],
                domain_id=domain_id,
                domain_name=domain_name,
                owner_id=owner_id,
                owner_name=owner_name,
                keywords=result.get("keywords", [])[:10],
                granularity=result.get("granularity"),
                main_entities=result.get("main_entities", []),
            )
            
        except Exception as e:
            print(f"Warning: LLM summarization failed for {name}: {e}")
            # Fallback: use original description truncated
            table_info = TableInfo(
                id=table_id,
                name=name,
                display_name=display_name,
                summary=f"{display_name}: {description[:150] if description else 'Sem descrição'}",
                domain_id=domain_id,
                domain_name=domain_name,
                owner_id=owner_id,
                owner_name=owner_name,
                keywords=[],
                granularity=None,
                main_entities=[],
            )
        
        # Cache it
        self._tables[table_id] = table_info
        
        # Index in vector store
        await self._index_table(table_info)
        
        return table_info
    
    def _create_columns_summary(self, columns: list[dict]) -> str:
        """Create a condensed summary of columns."""
        if not columns:
            return "Colunas não informadas"
        
        lines = []
        for col in columns:
            name = col.get("name", "?")
            col_type = col.get("type", "?")
            desc = col.get("description", "")[:50]
            lines.append(f"- {name} ({col_type}): {desc}")
        
        return "\n".join(lines[:15])  # Limit to 15 columns in summary
    
    async def _index_table(self, table: TableInfo):
        """Index table summary in vector store."""
        retriever = get_retriever()
        
        # Create searchable text
        search_text = f"{table.display_name} | {table.summary} | {' '.join(table.keywords)}"
        
        await retriever.index_table({
            "id": table.id,
            "name": table.name,
            "display_name": table.display_name,
            "description": search_text,  # Use summary, not raw description!
            "domain": table.domain_name,
            "keywords": table.keywords,
            "owner_id": table.owner_id,
            "owner_name": table.owner_name,
        })
    
    def register_domain(
        self,
        domain_id: str,
        name: str,
        description: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        chief_id: Optional[int] = None,
        chief_name: Optional[str] = None,
    ) -> DomainInfo:
        """Register a domain for hierarchical search."""
        domain = DomainInfo(
            id=domain_id,
            name=name,
            description=description,
            keywords=keywords or [],
            chief_id=chief_id,
            chief_name=chief_name,
        )
        self._domains[domain_id] = domain
        return domain
    
    def register_owner(
        self,
        owner_id: int,
        name: str,
        email: Optional[str],
        domain_id: str,
        domain_name: str,
        tables_count: int = 0,
    ) -> OwnerInfo:
        """Register an owner."""
        owner = OwnerInfo(
            id=owner_id,
            name=name,
            email=email,
            domain_id=domain_id,
            domain_name=domain_name,
            tables_count=tables_count,
        )
        self._owners[owner_id] = owner
        return owner
    
    def get_domain(self, domain_id: str) -> Optional[DomainInfo]:
        return self._domains.get(domain_id)
    
    def get_owner(self, owner_id: int) -> Optional[OwnerInfo]:
        return self._owners.get(owner_id)
    
    def get_table(self, table_id: int) -> Optional[TableInfo]:
        return self._tables.get(table_id)
    
    def get_domains_by_keywords(self, keywords: list[str]) -> list[DomainInfo]:
        """Find domains matching keywords."""
        results = []
        keywords_lower = {k.lower() for k in keywords}
        
        for domain in self._domains.values():
            domain_kw = {k.lower() for k in domain.keywords}
            if keywords_lower & domain_kw:
                results.append(domain)
        
        return results
    
    def get_owners_by_domain(self, domain_id: str) -> list[OwnerInfo]:
        """Get all owners in a domain."""
        return [o for o in self._owners.values() if o.domain_id == domain_id]


# Singleton
_pipeline: Optional[PreIndexingPipeline] = None


def get_pre_indexing_pipeline() -> PreIndexingPipeline:
    """Get or create the pre-indexing pipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = PreIndexingPipeline()
    return _pipeline
