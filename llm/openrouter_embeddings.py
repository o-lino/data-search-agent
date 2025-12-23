"""
OpenRouter Embeddings Provider

Uses OpenRouter API for embeddings with qwen/qwen3-embedding-8b model.
No local downloads needed - everything is API-based.
"""

import os
import requests
from typing import Optional
import time


class OpenRouterEmbeddings:
    """
    OpenRouter-based embeddings using qwen/qwen3-embedding-8b.
    
    Model: qwen/qwen3-embedding-8b
    - 1024 dimensions
    - Fast API-based inference
    - No local model downloads
    - Supports batch processing
    """
    
    BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "google/gemini-embedding-001"
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        # Allow override via env var, then constructor arg, then default
        env_model = os.getenv("OPENROUTER_EMBEDDING_MODEL")
        self._model = model or env_model or self.DEFAULT_MODEL
        
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required")
        
        self._session = requests.Session()
        
        # Add retry logic for stability
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        
        self._session.headers.update({
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://gestao-cases.local",
            "X-Title": "Table Search Agent"
        })
        
        # Rate limiting
        self._last_request = 0
        self._min_delay = 0.1  # 100ms between requests
        
        print(f"[OpenRouterEmbeddings] Initialized with model: {self._model}")
    
    def _wait_for_rate_limit(self):
        """Ensure we don't exceed rate limits."""
        elapsed = time.time() - self._last_request
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        self._last_request = time.time()
    
    def embed(self, text: str) -> list[float]:
        """Embed single text."""
        self._wait_for_rate_limit()
        
        try:
            response = self._session.post(
                f"{self.BASE_URL}/embeddings",
                json={
                    "model": self._model,
                    "input": text
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["data"][0]["embedding"]
            else:
                print(f"[OpenRouterEmbeddings] Error {response.status_code}: {response.text[:200]}")
                raise Exception(f"OpenRouter API error: {response.status_code}")
                
        except Exception as e:
            print(f"[OpenRouterEmbeddings] Request failed: {e}")
            raise
    
    def embed_batch(self, texts: list[str], batch_size: int = 50) -> list[list[float]]:
        """
        Embed multiple texts.
        
        OpenRouter supports batch embedding in a single request.
        """
        if not texts:
            return []
        
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            self._wait_for_rate_limit()
            
            try:
                response = self._session.post(
                    f"{self.BASE_URL}/embeddings",
                    json={
                        "model": self._model,
                        "input": batch
                    },
                    timeout=60
                )
                
                if response.status_code == 200:
                    data = response.json()
                    for item in data["data"]:
                        all_embeddings.append(item["embedding"])
                else:
                    print(f"[OpenRouterEmbeddings] Batch error {response.status_code}: {response.text[:200]}")
                    # Fallback to individual requests
                    for text in batch:
                        all_embeddings.append(self.embed(text))
                        
            except Exception as e:
                print(f"[OpenRouterEmbeddings] Batch request failed: {e}")
                # Fallback to individual requests
                for text in batch:
                    try:
                        all_embeddings.append(self.embed(text))
                    except:
                        # Return zero vector on failure
                        all_embeddings.append([0.0] * 1024)
        
        return all_embeddings
    
    def embed_for_index(self, text: str) -> list[float]:
        """Embed text for indexing/document storage."""
        return self.embed(text)
    
    def embed_for_query(self, text: str) -> list[float]:
        """Embed text for search query."""
        return self.embed(text)
    
    async def aembed(self, text: str) -> list[float]:
        """Async embed single text."""
        import asyncio
        return await asyncio.to_thread(self.embed, text)
    
    async def aembed_batch(self, texts: list[str]) -> list[list[float]]:
        """Async embed batch."""
        import asyncio
        return await asyncio.to_thread(self.embed_batch, texts)


# Global instance
_openrouter_embeddings: Optional[OpenRouterEmbeddings] = None


def get_openrouter_embeddings() -> OpenRouterEmbeddings:
    """Get or create OpenRouter embeddings instance."""
    global _openrouter_embeddings
    if _openrouter_embeddings is None:
        _openrouter_embeddings = OpenRouterEmbeddings()
    return _openrouter_embeddings
