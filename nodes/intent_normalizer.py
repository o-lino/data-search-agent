"""
Intent Normalizer Node

Uses LLM to normalize varied user queries into canonical intent.
Maps synonyms, understands context, and extracts structured information.

V3 Features:
- Cache lookup before LLM call (80% reduction)
- Synonym expansion for better recall
- Metrics tracking
"""

from typing import Any
import json

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from ..state import AgentState, CanonicalIntent
from ..memory.intent_cache import get_intent_cache, generate_cache_key
from ..knowledge.synonyms import get_synonym_dictionary
from src.core.config import settings


# Intent extraction prompt
INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Você é um especialista em interpretar solicitações de dados.
Sua tarefa é normalizar a solicitação do usuário em um formato estruturado.

Extraia:
1. data_need: O que está sendo solicitado (vendas, clientes, transações, etc)
2. data_type: Tipo de dado (currency, count, text, date, etc)
3. target_entity: Entidade principal (cliente, produto, loja, etc)
4. target_segment: Segmento de negócio (varejo, corporate, PF, PJ, etc)
5. target_product: Produto específico (consignado, imobiliário, cartão, etc)
6. target_audience: Público específico mencionado
7. granularity: Periodicidade (diária, mensal, anual, transação)
8. time_reference: Referência temporal (últimos 12 meses, YTD, etc)
9. inferred_domains: Domínios de dados prováveis (vendas, clientes, produtos, crédito, risco)

IMPORTANTE:
- Normalize sinônimos (receita → vendas, faturamento → vendas)
- Se não tiver certeza de um campo, deixe null
- Retorne APENAS JSON válido

Exemplos de normalização:
- "faturamento mensal" → data_need: "vendas", granularity: "mensal"
- "clientes ativos do consig" → target_entity: "cliente", target_product: "consignado"
- "quantos PJs temos" → target_entity: "cliente", target_segment: "PJ", data_type: "count"
"""),
    ("human", """Solicitação: {query}

Contexto adicional:
- Nome da variável: {variable_name}
- Tipo da variável: {variable_type}
- Contexto: {context}

Retorne o JSON estruturado:""")
])


async def normalize_intent(state: AgentState) -> dict[str, Any]:
    """
    Node: Normalize user query into canonical intent.
    
    V3 Flow:
    1. Check cache for existing intent
    2. If miss, call LLM
    3. Cache result for future
    4. Expand with synonyms
    """
    # Build query from available inputs
    query_parts = []
    if state["raw_query"]:
        query_parts.append(state["raw_query"])
    if state["variable_name"]:
        query_parts.append(f"variável: {state['variable_name']}")
    
    full_query = " | ".join(query_parts) or "consulta não especificada"
    
    # Generate cache key
    cache_key = generate_cache_key(
        raw_query=full_query,
        variable_name=state.get("variable_name"),
        context=state.get("context"),
    )
    
    # Check cache first
    cache = get_intent_cache()
    cached_intent = cache.get(cache_key)
    
    if cached_intent:
        # Cache hit - update original query and return
        cached_intent = CanonicalIntent(
            **{**cached_intent.model_dump(), "original_query": full_query}
        )
        return {
            "canonical_intent": cached_intent,
            "current_step": "intent_normalized",
        }
    
    # Cache miss - call LLM
    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0,
            api_key=settings.openai_api_key,
        )
        
        chain = INTENT_PROMPT | llm | JsonOutputParser()
        
        result = await chain.ainvoke({
            "query": full_query,
            "variable_name": state.get("variable_name") or "não informado",
            "variable_type": state.get("variable_type") or "não informado",
            "context": json.dumps(state.get("context") or {}, ensure_ascii=False),
        })
        
        # Expand inferred_domains with synonyms
        synonym_dict = get_synonym_dictionary()
        inferred_domains = result.get("inferred_domains") or []
        
        # Add synonym-based domains
        for domain in list(inferred_domains):
            synonyms = synonym_dict.get_synonyms(domain)
            for syn in synonyms[:2]:
                if syn not in inferred_domains:
                    inferred_domains.append(syn)
        
        canonical_intent = CanonicalIntent(
            data_need=result.get("data_need", full_query),
            data_type=result.get("data_type"),
            target_entity=result.get("target_entity"),
            target_segment=result.get("target_segment"),
            target_product=result.get("target_product"),
            target_audience=result.get("target_audience"),
            granularity=result.get("granularity"),
            time_reference=result.get("time_reference"),
            inferred_domains=inferred_domains,
            original_query=full_query,
            extraction_confidence=0.85,
        )
        
        # Cache the result (also cache query variants)
        query_variants = synonym_dict.expand_query(full_query, max_expansions=3)
        cache.set(cache_key, canonical_intent, query_variants=query_variants)
        
        return {
            "canonical_intent": canonical_intent,
            "current_step": "intent_normalized",
        }
        
    except Exception as e:
        print(f"Warning: Intent extraction failed: {e}")
        
        fallback_intent = CanonicalIntent(
            data_need=state.get("variable_name") or state.get("raw_query", ""),
            original_query=full_query,
            extraction_confidence=0.3,
        )
        
        return {
            "canonical_intent": fallback_intent,
            "current_step": "intent_normalized",
            "error_message": f"Intent extraction fallback: {str(e)}",
        }

