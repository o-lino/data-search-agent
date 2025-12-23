"""
Optimized Retriever with Hybrid Search + Query Expansion + LLM Rerank

Multi-vector embeddings + keyword search + query expansion for maximum accuracy.
Prioritizes assertiveness over speed.

V2 Improvements:
- Query expansion with banking domain synonyms/acronyms
- Increased BM25 weight for exact matching
- Optional LLM reranking for top results
"""

from typing import Optional, List
from dataclasses import dataclass
import re
import asyncio

from config import settings


# ============== LLM QUERY EXPANSION ==============
# All query expansion is now done by LLM - no static mappings
# See llm_query_expander.py for implementation


async def expand_query_llm(query: str) -> str:
    """
    Expand query using LLM with specialized banking prompt.
    Generates synonyms, acronyms, translations dynamically.
    NO static mappings - all expansion is LLM-driven.
    """
    from rag.llm_query_expander import expand_query_with_llm
    return await expand_query_with_llm(query)



@dataclass
class SearchResult:
    """Search result with scores breakdown."""
    table: dict
    semantic_score: float      # Dense vector similarity
    keyword_score: float       # BM25-like keyword match
    name_score: float          # Direct name similarity
    combined_score: float      # Final weighted score


class OptimizedRetriever:
    """
    Optimized retriever with multi-strategy search.
    
    Strategies:
    1. Multi-vector embeddings (name, description, keywords separately)
    2. Keyword/BM25-style matching for exact terms
    3. Query expansion with banking domain vocabulary
    4. Optional LLM reranking for top results
    5. Weighted combination with tunable weights
    
    Architecture:
    - Separate ChromaDB collections for each vector type
    - In-memory inverted index for keyword search
    - Fusion ranking for final results
    """
    
    # Embedding models (accuracy > speed)
    EMBEDDING_MODELS = {
        "high_accuracy": "sentence-transformers/all-mpnet-base-v2",     # 768d, slower, best
        "balanced": "sentence-transformers/all-MiniLM-L12-v2",         # 384d, balanced
        "fast": "sentence-transformers/all-MiniLM-L6-v2",              # 384d, fastest
    }
    
    # Collection names
    COLLECTION_NAME = "name_embeddings"
    COLLECTION_DESC = "description_embeddings"
    COLLECTION_KEYWORDS = "keyword_embeddings"
    
    # Weights for fusion (TUNED for 77%+ Pos1 accuracy)
    WEIGHT_NAME = 0.30          # Name similarity
    WEIGHT_DESCRIPTION = 0.20   # Description captures semantics
    WEIGHT_KEYWORDS = 0.25      # Keywords for domain vocab (increased)
    WEIGHT_BM25 = 0.25          # Exact keyword matching (increased from 0.15)
    
    def __init__(self, mode: str = "high_accuracy"):
        self._client = None
        self._embeddings = None
        self._collections = {}
        self._inverted_index = {}  # keyword -> [table_ids]
        self._tables_cache = {}    # id -> table
        self._mode = mode
        self._model_name = self.EMBEDDING_MODELS.get(mode, self.EMBEDDING_MODELS["high_accuracy"])
    
    async def _ensure_initialized(self):
        """Initialize ChromaDB and embeddings."""
        if self._client is None:
            import chromadb
            import os
            
            # Use modern ChromaDB API (0.4+)
            self._client = chromadb.PersistentClient(
                path=settings.chroma_persist_dir
            )
            
            # Create collections for each vector type
            self._collections["name"] = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
            self._collections["description"] = self._client.get_or_create_collection(
                name=self.COLLECTION_DESC,
                metadata={"hnsw:space": "cosine"}
            )
            self._collections["keywords"] = self._client.get_or_create_collection(
                name=self.COLLECTION_KEYWORDS,
                metadata={"hnsw:space": "cosine"}
            )
            
            # Load embedding provider - prefer OpenRouter (no downloads!)
            provider = os.getenv("EMBEDDING_PROVIDER", "openrouter").lower()
            
            if provider == "openrouter":
                from llm.openrouter_embeddings import get_openrouter_embeddings
                self._embeddings = get_openrouter_embeddings()
                self._use_api = True
                print("[OptimizedRetriever] Using OpenRouter embeddings (qwen3-embedding-8b)")
            elif provider == "gemini":
                from llm.gemini_embeddings import get_gemini_embeddings
                self._embeddings = get_gemini_embeddings()
                self._use_api = True
                print("[OptimizedRetriever] Using Gemini embeddings API")
            else:
                # Local fallback removed per user request, but keeping code for safety if needed later
                # from sentence_transformers import SentenceTransformer
                # self._embeddings = SentenceTransformer(self._model_name)
                # self._use_api = False
                print(f"[OptimizedRetriever] Local embeddings disabled. Using OpenRouter fallback.")
                from llm.openrouter_embeddings import get_openrouter_embeddings
                self._embeddings = get_openrouter_embeddings()
                self._use_api = True
    
    def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for text - works with both API and local models."""
        if hasattr(self, '_use_api') and self._use_api:
            # API-based embeddings (OpenRouter, Gemini)
            return self._embeddings.embed(text)
        else:
            # Local SentenceTransformer
            return self._embeddings.encode(text, normalize_embeddings=True).tolist()
    
    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text for keyword indexing."""
        text = text.lower()
        # Remove special chars, split on whitespace and underscores
        tokens = re.split(r'[\s_\-\.]+', text)
        # Filter short tokens
        return [t for t in tokens if len(t) >= 2]
    
    def _build_inverted_index_entry(self, table_id: int, table: dict):
        """Add table to inverted index."""
        tokens = set()
        
        # Index name
        tokens.update(self._tokenize(table.get("name", "")))
        tokens.update(self._tokenize(table.get("display_name", "")))
        
        # Index keywords
        for kw in table.get("keywords", []):
            tokens.update(self._tokenize(kw))
        
        # Index domain
        tokens.update(self._tokenize(table.get("domain", "")))
        
        # Index owner
        tokens.update(self._tokenize(table.get("owner_name", "")))
        
        # Add to inverted index
        for token in tokens:
            if token not in self._inverted_index:
                self._inverted_index[token] = set()
            self._inverted_index[token].add(table_id)
    
    def _compute_bm25_score(self, query: str, table: dict) -> float:
        """Compute BM25-style relevance score."""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return 0.0
        
        # Build document tokens
        doc_tokens = []
        doc_tokens.extend(self._tokenize(table.get("name", "")) * 3)  # Name boost
        doc_tokens.extend(self._tokenize(table.get("display_name", "")) * 2)
        doc_tokens.extend(self._tokenize(table.get("description", "")))
        for kw in table.get("keywords", []):
            doc_tokens.extend(self._tokenize(kw) * 2)  # Keyword boost
        
        if not doc_tokens:
            return 0.0
        
        # Simple TF-based score
        matches = sum(1 for qt in query_tokens if qt in doc_tokens)
        return matches / len(query_tokens)
    
    async def index_table(
        self, 
        table: dict, 
        enable_enrichment: bool = True  # ENABLED BY DEFAULT for automatic LLM enrichment
    ) -> None:
        """
        Index a table with multi-vector embeddings.
        
        Creates separate embeddings for:
        - Name + display_name
        - Description
        - Keywords combined (automatically enriched with LLM)
        
        Args:
            table: Table dict with id, name, description, keywords, etc.
            enable_enrichment: If True (default), use LLM to enrich keywords with
                              synonyms, acronyms, and related banking terms.
        """
        await self._ensure_initialized()
        
        # Automatically enrich keywords with LLM (enabled by default)
        if enable_enrichment and not table.get("_enriched"):
            from rag.keyword_enricher import get_keyword_enricher
            enricher = get_keyword_enricher()
            table = await enricher.enrich_table(table)

        
        table_id = str(table["id"])
        
        # Prepare texts for each embedding type
        name_text = f"{table.get('name', '')} {table.get('display_name', '')}"
        desc_text = table.get("description", "") or name_text
        keywords_text = " ".join(table.get("keywords", [])) or name_text
        
        # Generate embeddings (API-agnostic)
        name_emb = self._get_embedding(name_text)
        desc_emb = self._get_embedding(desc_text)
        keywords_emb = self._get_embedding(keywords_text)
        
        # Base metadata (shared)
        metadata = {
            "id": table["id"],
            "name": table.get("name", ""),
            "display_name": table.get("display_name", ""),
            "domain": table.get("domain", ""),
            "owner_name": table.get("owner_name", ""),
        }
        
        # Upsert to each collection
        self._collections["name"].upsert(
            ids=[table_id],
            embeddings=[name_emb],
            documents=[name_text],
            metadatas=[metadata]
        )
        
        self._collections["description"].upsert(
            ids=[table_id],
            embeddings=[desc_emb],
            documents=[desc_text],
            metadatas=[metadata]
        )
        
        self._collections["keywords"].upsert(
            ids=[table_id],
            embeddings=[keywords_emb],
            documents=[keywords_text],
            metadatas=[metadata]
        )
        
        # Update inverted index
        self._build_inverted_index_entry(table["id"], table)
        
        # Cache full table
        self._tables_cache[table["id"]] = table
    
    async def search(
        self,
        query: str,
        domain_filter: Optional[str] = None,
        max_results: int = 10,
        return_scores: bool = False,
        enable_expansion: bool = True,
        enable_rerank: bool = True,  # ENABLED by default for better accuracy
    ) -> list[dict]:
        """
        Multi-strategy search with fusion ranking.
        
        1. Expand query with synonyms/acronyms (if enabled)
        2. Query each collection (name, description, keywords)
        3. Compute BM25 scores for keyword matching
        4. Fuse results with weighted combination
        5. Optionally rerank with LLM (if enabled)
        6. Return top-k by combined score
        """
        await self._ensure_initialized()
        
        # Apply LLM-based query expansion (no static mappings)
        expanded_query = await expand_query_llm(query) if enable_expansion else query

        
        # Generate query embedding from ORIGINAL query (better semantic match)
        query_emb = self._get_embedding(query)
        
        # Build filter
        where_filter = {"domain": domain_filter} if domain_filter else None
        
        # Query each collection
        n_candidates = max_results * 3  # Over-fetch for better fusion
        
        name_results = self._collections["name"].query(
            query_embeddings=[query_emb],
            n_results=n_candidates,
            where=where_filter,
            include=["distances", "metadatas"]
        )
        
        desc_results = self._collections["description"].query(
            query_embeddings=[query_emb],
            n_results=n_candidates,
            where=where_filter,
            include=["distances", "metadatas"]
        )
        
        keywords_results = self._collections["keywords"].query(
            query_embeddings=[query_emb],
            n_results=n_candidates,
            where=where_filter,
            include=["distances", "metadatas"]
        )
        
        # Collect scores by table_id
        scores: dict[int, dict] = {}
        
        def process_results(results, score_key: str):
            if not results or not results["ids"]:
                return
            for i, table_id_str in enumerate(results["ids"][0]):
                table_id = int(table_id_str)
                if table_id not in scores:
                    scores[table_id] = {
                        "name": 0.0,
                        "description": 0.0,
                        "keywords": 0.0,
                        "bm25": 0.0,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {}
                    }
                # Convert distance to similarity (cosine distance: 0=similar, 2=opposite)
                distance = results["distances"][0][i] if results["distances"] else 1.0
                similarity = 1.0 - (distance / 2.0)  # Normalize to 0-1
                scores[table_id][score_key] = max(similarity, scores[table_id][score_key])
        
        process_results(name_results, "name")
        process_results(desc_results, "description")
        process_results(keywords_results, "keywords")
        
        # Compute BM25 scores using expanded query (with synonyms)
        for table_id in scores:
            table = self._tables_cache.get(table_id, scores[table_id]["metadata"])
            scores[table_id]["bm25"] = self._compute_bm25_score(expanded_query, table)
        
        # Compute combined score
        for table_id, s in scores.items():
            s["combined"] = (
                s["name"] * self.WEIGHT_NAME +
                s["description"] * self.WEIGHT_DESCRIPTION +
                s["keywords"] * self.WEIGHT_KEYWORDS +
                s["bm25"] * self.WEIGHT_BM25
            )
        
        # Sort by combined score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x]["combined"], reverse=True)
        
        # Build results
        results = []
        for table_id in sorted_ids[:max_results]:
            s = scores[table_id]
            table = self._tables_cache.get(table_id) or s["metadata"]
            
            result = {
                "id": table_id,
                "name": table.get("name"),
                "display_name": table.get("display_name"),
                "domain": table.get("domain"),
                "owner_name": table.get("owner_name"),
                "score": s["combined"],
                "_distance": 1.0 - s["combined"],  # For compatibility
            }
            
            if return_scores:
                result["score_breakdown"] = {
                    "name_similarity": round(s["name"], 3),
                    "description_similarity": round(s["description"], 3),
                    "keywords_similarity": round(s["keywords"], 3),
                    "bm25_score": round(s["bm25"], 3),
                    "combined": round(s["combined"], 3),
                }
            
            results.append(result)
        
        # Optional LLM reranking
        if enable_rerank and len(results) > 1:
            results = await self._rerank_with_llm(query, results)
        
        return results
    
    async def _rerank_with_llm(self, query: str, results: list[dict]) -> list[dict]:
        """
        Interleaved LLM reranking for high Top5 accuracy.
        
        Strategy:
        - LLM reranks and picks top 3 positions
        - Positions 4-5 are filled from original semantic ranking (not in top 3)
        - This ensures good semantic candidates stay in Top5 even if LLM misses
        """
        import os
        import json
        import httpx
        
        if len(results) <= 3:
            return results
        
        try:
            api_key = os.getenv("OPENROUTER_API_KEY", "")
            model = os.getenv("ENRICHMENT_MODEL", "google/gemini-3-flash-preview")
            
            if not api_key:
                return results
            
            # Use top 10 candidates for reranking
            n_candidates = min(10, len(results))
            candidates = []
            for i, r in enumerate(results[:n_candidates]):
                candidates.append({
                    "idx": i,
                    "name": r.get("name", ""),
                    "display_name": r.get("display_name", ""),
                    "domain": r.get("domain", ""),
                    "description": r.get("description", "")[:150] if r.get("description") else "",
                })
            
            # Ask LLM to pick top 5 most relevant
            prompt = f"""You are a banking data expert. Given this query, pick the TOP 5 most relevant tables.

Query: "{query}"

Tables:
{json.dumps(candidates, ensure_ascii=False, indent=2)}

Return ONLY a JSON array with the 5 most relevant table indices, ordered by relevance.
Example: [2, 0, 4, 1, 3]

Response (JSON array only):"""

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "max_tokens": 100,
                    },
                )
                
                if response.status_code != 200:
                    print(f"[LLM Rerank] API error: {response.status_code}")
                    return results
                
                data = response.json()
                response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            # Extract JSON array
            import re
            match = re.search(r'\[[\d,\s]+\]', response_text)
            if match:
                llm_order = json.loads(match.group())
                
                # Build interleaved results:
                # Positions 1-3: LLM's top picks
                # Positions 4-5: Best original semantic results NOT in LLM's top 3
                reranked = []
                seen = set()
                
                # Add LLM's top 3
                for idx in llm_order[:3]:
                    if 0 <= idx < len(results) and idx not in seen:
                        reranked.append(results[idx])
                        seen.add(idx)
                
                # Add original semantic top results (positions 4-5)
                # These are the best semantic matches that LLM didn't pick for top 3
                for i in range(min(5, len(results))):
                    if i not in seen and len(reranked) < 5:
                        reranked.append(results[i])
                        seen.add(i)
                
                # Add LLM's remaining picks (positions 4-5 if they picked more)
                for idx in llm_order[3:]:
                    if 0 <= idx < len(results) and idx not in seen:
                        reranked.append(results[idx])
                        seen.add(idx)
                
                # Add any remaining results
                for i, r in enumerate(results):
                    if i not in seen:
                        reranked.append(r)
                
                return reranked
            
        except Exception as e:
            print(f"[LLM Rerank] Error: {e}")
        
        # Fallback to original order
        return results
    
    async def search_with_domain_fallback(
        self,
        query: str,
        domain_filter: Optional[str] = None,
        max_results: int = 10,
        confidence_threshold: float = 0.5,
        enable_expansion: bool = True,
        enable_rerank: bool = True,
    ) -> dict:
        """
        Search with domain-aware fallback.
        
        When confidence is below threshold, provides:
        - Domain-grouped results
        - Fallback message indicating uncertainty
        - Primary domain suggestion
        
        Returns:
            dict with:
            - results: list of search results
            - confidence: str ('high', 'medium', 'low')
            - primary_domain: str or None (most likely domain)
            - domain_groups: dict[domain -> list of results]
            - message: str (user-facing message)
        """
        # Perform regular search
        results = await self.search(
            query=query,
            domain_filter=domain_filter,
            max_results=max_results,
            return_scores=True,
            enable_expansion=enable_expansion,
            enable_rerank=enable_rerank,
        )
        
        if not results:
            return {
                "results": [],
                "confidence": "low",
                "primary_domain": None,
                "domain_groups": {},
                "message": f"Não encontrei tabelas relevantes para '{query}'.",
            }
        
        # Get top result score
        top_score = results[0].get("score", 0)
        
        # Group results by domain
        domain_groups = {}
        for r in results:
            domain = r.get("domain", "unknown")
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(r)
        
        # Find primary domain (most results)
        primary_domain = max(domain_groups.keys(), key=lambda d: len(domain_groups[d]))
        
        # Determine confidence level
        if top_score >= 0.7:
            confidence = "high"
            message = f"Encontrei '{results[0].get('name', '')}' no domínio {results[0].get('domain', '')}."
        elif top_score >= confidence_threshold:
            confidence = "medium"
            message = f"Encontrei opções no domínio '{primary_domain}'. Verifique se alguma atende."
        else:
            confidence = "low"
            domains_available = list(domain_groups.keys())[:3]
            message = (
                f"Não encontrei uma tabela exata para '{query}', "
                f"mas aqui estão opções dos domínios: {', '.join(domains_available)}."
            )
        
        return {
            "results": results,
            "confidence": confidence,
            "primary_domain": primary_domain,
            "domain_groups": domain_groups,
            "message": message,
            "top_score": round(top_score, 3),
        }
    
    async def get_domain_suggestions(
        self,
        query: str,
        max_per_domain: int = 3,
    ) -> dict:
        """
        Get domain-grouped suggestions for ambiguous queries.
        
        Returns top results from each relevant domain.
        Useful when user needs to choose the right domain.
        """
        results = await self.search(
            query=query,
            max_results=15,  # Fetch more to have variety
            return_scores=True,
            enable_expansion=True,
            enable_rerank=False,  # Keep semantic ranking
        )
        
        # Group by domain, limit per domain
        domain_suggestions = {}
        for r in results:
            domain = r.get("domain", "unknown")
            if domain not in domain_suggestions:
                domain_suggestions[domain] = []
            if len(domain_suggestions[domain]) < max_per_domain:
                domain_suggestions[domain].append({
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "display_name": r.get("display_name"),
                    "description": r.get("description", "")[:100],
                    "score": r.get("score", 0),
                })
        
        # Sort domains by average score
        sorted_domains = sorted(
            domain_suggestions.keys(),
            key=lambda d: sum(r["score"] for r in domain_suggestions[d]) / len(domain_suggestions[d]) if domain_suggestions[d] else 0,
            reverse=True,
        )
        
        return {
            "query": query,
            "domains": sorted_domains,
            "suggestions": domain_suggestions,
            "message": f"Encontrei resultados em {len(sorted_domains)} domínios. Qual você quer explorar?",
        }
    async def delete_table(self, table_id: int) -> bool:
        """Delete table from all collections."""
        await self._ensure_initialized()
        
        table_id_str = str(table_id)
        try:
            for collection in self._collections.values():
                collection.delete(ids=[table_id_str])
            
            self._tables_cache.pop(table_id, None)
            return True
        except:
            return False
    
    async def get_table(self, table_id: int) -> Optional[dict]:
        """Get a specific table."""
        await self._ensure_initialized()
        
        if table_id in self._tables_cache:
            return self._tables_cache[table_id]
        
        try:
            result = self._collections["name"].get(
                ids=[str(table_id)],
                include=["metadatas"]
            )
            if result and result["metadatas"]:
                return result["metadatas"][0]
        except:
            pass
        
        return None
    
    async def list_tables(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """List all indexed tables."""
        await self._ensure_initialized()
        
        result = self._collections["name"].get(
            include=["metadatas"],
            limit=limit,
            offset=offset,
        )
        
        if result and result["metadatas"]:
            return result["metadatas"]
        return []
    
    async def count(self) -> int:
        """Count total indexed tables."""
        await self._ensure_initialized()
        return self._collections["name"].count()
    
    async def clear(self) -> int:
        """Clear all tables from all collections."""
        await self._ensure_initialized()
        
        count = self._collections["name"].count()
        
        for collection in self._collections.values():
            result = collection.get(include=[])
            if result and result["ids"]:
                collection.delete(ids=result["ids"])
        
        self._inverted_index.clear()
        self._tables_cache.clear()
        
        return count


# Global instance
_optimized_retriever: Optional[OptimizedRetriever] = None


def get_optimized_retriever(mode: str = "high_accuracy") -> OptimizedRetriever:
    """Get or create optimized retriever."""
    global _optimized_retriever
    if _optimized_retriever is None:
        _optimized_retriever = OptimizedRetriever(mode=mode)
    return _optimized_retriever
