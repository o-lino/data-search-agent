"""
LLM Synonym Dictionary

Dynamic synonym expansion using LLM (no static mappings).
Supports learning from user corrections (stored externally).
"""

import os
import yaml
import json
import re
import asyncio
from pathlib import Path
from typing import Optional


class LLMSynonymDictionary:
    """
    Manages synonyms using LLM for dynamic expansion.
    
    Features:
    - LLM-driven synonym generation (no static mappings)
    - Learnable from user corrections (stored in YAML)
    - Caching for performance
    """
    
    RATE_LIMIT_DELAY = 0.3
    
    def __init__(self, learned_path: Optional[str] = None):
        self._client = None
        self._enabled = True
        self._learned: dict[str, set[str]] = {}
        self._cache: dict[str, list[str]] = {}
        
        # Load learned synonyms
        if learned_path:
            self._load_learned(learned_path)
    
    def _get_client(self):
        """Lazy initialization of Groq client."""
        if self._client is None:
            try:
                from groq import Groq
                api_key = os.getenv("GROQ_API_KEY", "")
                if api_key:
                    self._client = Groq(api_key=api_key)
                else:
                    self._enabled = False
            except ImportError:
                self._enabled = False
        return self._client
    
    def _load_learned(self, path: str):
        """Load learned synonyms from YAML."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            for term, syns in data.items():
                self._learned[term.lower()] = set(s.lower() for s in syns)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[LLMSynonymDictionary] Failed to load learned: {e}")
    
    async def get_synonyms(self, term: str) -> list[str]:
        """
        Get synonyms for a term using LLM.
        NO static mappings - all expansion is LLM-driven.
        """
        term_lower = term.lower().strip()
        
        # Check learned first
        if term_lower in self._learned:
            return list(self._learned[term_lower])
        
        # Check cache
        if term_lower in self._cache:
            return self._cache[term_lower]
        
        if not self._enabled:
            return []
            
        client = self._get_client()
        if not client:
            return []
        
        prompt = f"""Você é especialista em vocabulário bancário brasileiro.

TERMO: "{term}"

Gere sinônimos e termos relacionados em contexto bancário/financeiro.
Inclua:
1. Sinônimos em português
2. Traduções inglês/português
3. Variações e abreviações
4. Termos técnicos relacionados

Retorne APENAS um JSON array com máximo 6 sinônimos:
["sinônimo1", "sinônimo2", ...]

JSON:"""

        try:
            await asyncio.sleep(self.RATE_LIMIT_DELAY)
            
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=100,
            )
            
            response_text = response.choices[0].message.content.strip()
            match = re.search(r'\[.*?\]', response_text, re.DOTALL)
            if match:
                synonyms = json.loads(match.group())
                synonyms = [s.lower().strip() for s in synonyms if isinstance(s, str)]
                
                # Cache result
                self._cache[term_lower] = synonyms
                return synonyms
                
        except Exception as e:
            print(f"[LLMSynonymDictionary] Error: {e}")
        
        return []
    
    async def expand_query(self, query: str, max_expansions: int = 5) -> list[str]:
        """
        Expand query with LLM-generated synonyms.
        
        Returns original query plus expanded versions.
        """
        expansions = [query]
        words = query.lower().split()
        
        for word in words:
            if len(word) > 2:  # Skip short words
                synonyms = await self.get_synonyms(word)
                for syn in synonyms[:2]:  # Limit per word
                    expanded = query.lower().replace(word, syn)
                    if expanded not in expansions:
                        expansions.append(expanded)
                        if len(expansions) >= max_expansions + 1:
                            return expansions
        
        return expansions
    
    def learn(self, original_term: str, synonym: str) -> None:
        """
        Learn a new synonym from user correction.
        Stored for future use.
        """
        original = original_term.lower()
        syn = synonym.lower()
        
        if original not in self._learned:
            self._learned[original] = set()
        self._learned[original].add(syn)
        
        # Bidirectional
        if syn not in self._learned:
            self._learned[syn] = set()
        self._learned[syn].add(original)
        
        # Update cache
        self._cache.pop(original, None)
        self._cache.pop(syn, None)
    
    def save_learned(self, path: str) -> None:
        """Save learned synonyms to YAML file."""
        data = {k: list(v) for k, v in self._learned.items()}
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    
    @property
    def stats(self) -> dict:
        """Get dictionary statistics."""
        return {
            "learned_terms": len(self._learned),
            "cached_terms": len(self._cache),
            "total_learned_synonyms": sum(len(v) for v in self._learned.values()),
        }


# Global instance
_synonym_dict: Optional[LLMSynonymDictionary] = None


def get_synonym_dictionary() -> LLMSynonymDictionary:
    """Get or create global LLM synonym dictionary."""
    global _synonym_dict
    if _synonym_dict is None:
        # Try to load learned synonyms from data folder
        learned_path = Path(__file__).parent.parent.parent.parent / "data" / "learned_synonyms.yaml"
        _synonym_dict = LLMSynonymDictionary(str(learned_path) if learned_path.exists() else None)
    return _synonym_dict
