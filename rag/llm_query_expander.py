"""
Enhanced LLM Query Expander using OpenRouter API

Features:
1. Category-aware prompts
2. Continuous learning from search corrections

Uses OpenRouter with gpt5-nano for query expansion.
"""

import os
import asyncio
import json
import re
import yaml
import httpx
from pathlib import Path
from typing import Optional


class OpenRouterQueryExpander:
    """
    Enhanced query expander using OpenRouter API.
    Features:
    1. Category-aware prompts
    2. Learning from user corrections
    """
    
    RATE_LIMIT_DELAY = 0.0  # No delay - OpenRouter has generous rate limits
    LEARNING_FILE = "/app/data/learned_expansions.yaml"
    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
    
    def __init__(self):
        self._api_key = os.getenv("OPENROUTER_API_KEY", "")
        self._model = os.getenv("ENRICHMENT_MODEL", "openai/gpt-4.1-nano")
        self._enabled = bool(self._api_key)
        self._cache: dict[str, str] = {}
        self._learned: dict[str, list[str]] = {}
        self._load_learned()
        
        if not self._enabled:
            print("[OpenRouterExpander] No OPENROUTER_API_KEY found")
        else:
            print(f"[OpenRouterExpander] Initialized with model: {self._model}")
        
    def _load_learned(self):
        """Load learned expansions (continuous learning)."""
        try:
            path = Path(self.LEARNING_FILE)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    self._learned = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[OpenRouterExpander] Failed to load learned: {e}")
    
    def _save_learned(self):
        """Save learned expansions."""
        try:
            path = Path(self.LEARNING_FILE)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(self._learned, f, allow_unicode=True)
        except Exception as e:
            print(f"[OpenRouterExpander] Failed to save: {e}")
    
    def learn_from_correction(self, query: str, correct_table_name: str, 
                              table_keywords: list[str]) -> None:
        """Learn from user correction (continuous learning)."""
        key = query.lower().strip()
        if key not in self._learned:
            self._learned[key] = []
        
        for kw in table_keywords[:5]:
            if kw.lower() not in self._learned[key]:
                self._learned[key].append(kw.lower())
        
        self._cache.pop(key, None)
        
        self._save_learned()
        print(f"[OpenRouterExpander] Learned: '{key}' -> {self._learned[key][:5]}")
    
    def _get_learned_expansion(self, query: str) -> str:
        """Get any learned expansions for this query."""
        key = query.lower().strip()
        
        if key in self._learned:
            return f" {' '.join(self._learned[key])}"
        
        for learned_key, keywords in self._learned.items():
            if learned_key in key or key in learned_key:
                return f" {' '.join(keywords[:3])}"
        
        return ""
    
    async def expand_query(self, query: str, domain_hint: Optional[str] = None) -> str:
        """
        Expand query using OpenRouter LLM.
        """
        cache_key = query.lower().strip()
        
        learned_addition = self._get_learned_expansion(query)
        
        if cache_key in self._cache:
            return self._cache[cache_key] + learned_addition
        
        if not self._enabled:
            return query + learned_addition
        
        domain_context = ""
        if domain_hint:
            domain_context = f"\nCONTEXTO: Esta busca é provavelmente do domínio {domain_hint.upper()}."
            
        prompt = f"""Você é um ESPECIALISTA em busca de dados bancários brasileiros.

TAREFA: Expanda esta consulta para melhorar a recuperação de tabelas.

CONSULTA: "{query}"
{domain_context}

EXPANSÃO DEVE INCLUIR:
1. ACRÔNIMOS: Se identificar termos com acrônimos (ex: "prevenção lavagem" → "PLD AML")
2. EXPANSÕES: Se houver acrônimos, expanda (ex: "PD" → "probability default probabilidade inadimplência")
3. SINÔNIMOS: Termos equivalentes (ex: "aging" → "envelhecimento vencimento faixa atraso")
4. TÉCNICOS: Vocabulário bancário brasileiro relacionado
5. VARIAÇÕES: Acentos e abreviações (ex: "cartão" → "cartao")

REGRA: Mantenha a query original + adicione expansões relevantes.
Limite: máximo 8 termos adicionais.

Retorne APENAS JSON:
{{"expanded": "query original + termos adicionais"}}

JSON:"""

        try:
            await asyncio.sleep(self.RATE_LIMIT_DELAY)
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://table-search-agent.local",
                    },
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 200,
                        "temperature": 0.3,
                    }
                )
                
                if response.status_code != 200:
                    print(f"[OpenRouterExpander] Error {response.status_code}: {response.text[:200]}")
                    return query + learned_addition
                
                data = response.json()
                response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                match = re.search(r'\{.*?\}', response_text, re.DOTALL)
                if match:
                    result = json.loads(match.group())
                    expanded = result.get("expanded", query)
                    
                    self._cache[cache_key] = expanded
                    
                    return expanded + learned_addition
                    
        except Exception as e:
            print(f"[OpenRouterExpander] Error: {e}")
        
        return query + learned_addition


# Singleton
_query_expander: Optional[OpenRouterQueryExpander] = None


def get_query_expander() -> OpenRouterQueryExpander:
    """Get or create query expander singleton."""
    global _query_expander
    if _query_expander is None:
        _query_expander = OpenRouterQueryExpander()
    return _query_expander


async def expand_query_with_llm(query: str, domain_hint: Optional[str] = None) -> str:
    """Convenience function to expand query with OpenRouter."""
    expander = get_query_expander()
    return await expander.expand_query(query, domain_hint)
