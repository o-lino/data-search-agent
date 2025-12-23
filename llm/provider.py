"""
LLM Provider - Groq Integration

Uses Groq's free API for LLM inference.
BGE-M3 embeddings for multilingual semantic search.
"""

from typing import Optional
import os


class GroqLLM:
    """
    Groq LLM client.
    
    Production models (Dec 2024):
    - openai/gpt-oss-120b (flagship, reasoning) ✅ RECOMMENDED
    - openai/gpt-oss-20b (smaller, faster)
    - llama-3.3-70b-versatile
    - llama-3.1-8b-instant
    """
    
    # GPT-OSS-120B: OpenAI's flagship open-weight model
    DEFAULT_MODEL = "openai/gpt-oss-120b"
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL", self.DEFAULT_MODEL)
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from groq import Groq
                self._client = Groq(api_key=self.api_key)
            except ImportError:
                raise ImportError("groq package not installed. Run: pip install groq")
        return self._client
    
    def complete(
        self, 
        prompt: str, 
        system_prompt: str = "",
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> str:
        """Generate completion."""
        client = self._get_client()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return response.choices[0].message.content
    
    async def acomplete(
        self, 
        prompt: str, 
        system_prompt: str = "",
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> str:
        """Async completion (runs sync in thread)."""
        import asyncio
        return await asyncio.to_thread(
            self.complete, prompt, system_prompt, temperature, max_tokens
        )


class LLMProvider:
    """LLM provider abstraction. Supports: groq, openai"""
    
    def __init__(self):
        self._llm = None
        self._provider = os.getenv("LLM_PROVIDER", "groq")
    
    def _get_llm(self):
        if self._llm is None:
            if self._provider == "groq":
                self._llm = GroqLLM()
            elif self._provider == "openai":
                from langchain_openai import ChatOpenAI
                self._llm = ChatOpenAI(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    temperature=0.1,
                )
            else:
                raise ValueError(f"Unknown LLM provider: {self._provider}")
        return self._llm
    
    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Generate text."""
        llm = self._get_llm()
        
        if isinstance(llm, GroqLLM):
            return await llm.acomplete(prompt, system_prompt)
        else:
            from langchain_core.messages import SystemMessage, HumanMessage
            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=prompt))
            response = await llm.ainvoke(messages)
            return response.content


# Global instance
_llm_provider: Optional[LLMProvider] = None


def get_llm() -> LLMProvider:
    """Get LLM provider."""
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = LLMProvider()
    return _llm_provider


# ============== Embeddings: BGE-M3 (Multilingual) ==============

class BGEM3Embeddings:
    """
    BGE-M3 Embeddings - Best multilingual embedding model (Dec 2024).
    
    Features:
    - 100+ languages including Portuguese
    - Up to 8192 tokens context
    - Dense, sparse, and multi-vector retrieval
    - Apache 2.0 license (free)
    
    Models:
    - BAAI/bge-m3 (full, 567M params)
    - BAAI/bge-small-en-v1.5 (faster fallback)
    """
    
    MODELS = {
        "bge-m3": "BAAI/bge-m3",                    # Best multilingual
        "bge-small": "BAAI/bge-small-en-v1.5",     # Faster fallback
        "bge-base": "BAAI/bge-base-en-v1.5",       # Balanced
    }
    
    def __init__(self, model: str = "bge-m3"):
        self._model = None
        self._model_name = self.MODELS.get(model, self.MODELS["bge-m3"])
    
    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            print(f"[Embeddings] Loaded: {self._model_name}")
        return self._model
    
    def embed(self, text: str) -> list[float]:
        """Embed single text."""
        model = self._get_model()
        return model.encode(text, normalize_embeddings=True).tolist()
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed batch of texts."""
        model = self._get_model()
        return model.encode(texts, normalize_embeddings=True).tolist()


_embeddings: Optional[BGEM3Embeddings] = None


def get_embeddings(model: str = "bge-m3") -> BGEM3Embeddings:
    """Get BGE-M3 embeddings."""
    global _embeddings
    if _embeddings is None:
        _embeddings = BGEM3Embeddings(model=model)
    return _embeddings

