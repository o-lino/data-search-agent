"""
Enhanced LLM Keyword Enrichment using OpenRouter API

Features:
1. Category-specific specialized prompts
2. Continuous learning from user corrections

Uses OpenRouter with gpt5-nano for keyword enrichment.
"""

import os
import json
import asyncio
import yaml
import re
import httpx
from pathlib import Path
from typing import Optional


# Category-specific prompt enhancements
CATEGORY_PROMPTS = {
    "credito": """
FOCO CRÉDITO: Priorize termos como:
- Acrônimos: PD, LGD, EAD, RWA, PCLD, SCR, CDC, consignado
- Conceitos: inadimplência, provisão, score, rating, limite, margem
- Produtos: consignado, CDC, imobiliário, veículo, pessoal
- Regulatório: Basileia, bacen, bureau, resolução 2682""",
    
    "cobranca": """
FOCO COBRANÇA: Priorize termos como:
- Acrônimos: aging, PDD, workout, NPL
- Conceitos: inadimplência, recuperação, renegociação, acordo
- Faixas: atraso, vencido, prejuízo, write-off
- Operações: negativação, protesto, assessoria, terceirizada""",
    
    "risco": """
FOCO RISCO: Priorize termos como:
- Acrônimos: VaR, PD, LGD, EAD, RWA, ICAAP, IRRBB
- Conceitos: exposição, rating, matriz, stress test, cenário
- Regulatório: Basileia, circular 3.869, PCLD, capital
- Modelos: score, PD, severidade, correlação""",
    
    "comercial": """
FOCO COMERCIAL: Priorize termos como:
- Conceitos: cliente, conta, carteira, gerente, agência
- Métricas: meta, venda, cross-sell, up-sell, ativação
- Segmentos: varejo, private, corporate, PF, PJ
- CRM: lead, funil, conversão, campanha""",
    
    "financeiro": """
FOCO FINANCEIRO/CONTÁBIL: Priorize termos como:
- Acrônimos: COSIF, DRE, DMPL, DVA, DOAR
- Conceitos: balancete, razão, lançamento, centro custo
- Regulatório: bacen, CVM, IFRS, provisão
- Fluxo: caixa, receita, despesa, resultado""",
    
    "pix": """
FOCO PIX/PAGAMENTOS: Priorize termos como:
- Acrônimos: TED, DOC, SPB, STR, SPI
- Conceitos: transferência, pagamento, boleto, QR code
- PIX: chave, devolução, MED, iniciador, ITP
- Canais: app, internet banking, agência""",
    
    "cartoes": """
FOCO CARTÕES: Priorize termos como:
- Acrônimos: BIN, PAN, CVV, EMV, NFC
- Conceitos: fatura, limite, transação, autorização
- Operações: chargeback, contestação, estorno, parcelamento
- Produtos: crédito, débito, pré-pago, virtual""",
    
    "investimentos": """
FOCO INVESTIMENTOS: Priorize termos como:
- Acrônimos: CDB, LCI, LCA, CRI, CRA, COE, FII
- Conceitos: aplicação, resgate, rentabilidade, custódia
- Fundos: renda fixa, multimercado, ações, come-cotas
- Regulatório: CVM, ANBIMA, suitability""",
    
    "compliance": """
FOCO COMPLIANCE: Priorize termos como:
- Acrônimos: KYC, PLD, AML, CFT, FATCA, CRS
- Conceitos: PEP, STR, UIF, diligência, sanções
- Regulatório: SISBACEN, CADOC, circular 3.978
- Processos: monitoramento, alerta, investigação""",
    
    "previdencia": """
FOCO PREVIDÊNCIA: Priorize termos como:
- Acrônimos: PGBL, VGBL, SUSEP, PREVIC
- Conceitos: contribuição, benefício, resgate, portabilidade
- Planos: aberta, fechada, individual, empresarial
- Fiscal: dedução, tributação, come-cotas""",
}


class OpenRouterKeywordEnricher:
    """
    Enhanced enricher using OpenRouter API with gpt5-nano.
    Features:
    1. Category-specific prompts
    2. Continuous learning
    """
    
    RATE_LIMIT_DELAY = 0.0  # No delay - OpenRouter has generous rate limits
    LEARNING_FILE = "/app/data/learned_keywords.yaml"
    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
    
    def __init__(self):
        self._api_key = os.getenv("OPENROUTER_API_KEY", "")
        self._model = os.getenv("ENRICHMENT_MODEL", "openai/gpt-4.1-nano")  # gpt5-nano
        self._enabled = bool(self._api_key)
        self._learned: dict[str, list[str]] = {}
        self._load_learned()
        
        if not self._enabled:
            print("[OpenRouterEnricher] No OPENROUTER_API_KEY found")
        else:
            print(f"[OpenRouterEnricher] Initialized with model: {self._model}")
    
    def _load_learned(self):
        """Load learned keywords from file (continuous learning)."""
        try:
            path = Path(self.LEARNING_FILE)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    self._learned = yaml.safe_load(f) or {}
                print(f"[OpenRouterEnricher] Loaded {len(self._learned)} learned terms")
        except Exception as e:
            print(f"[OpenRouterEnricher] Failed to load learned: {e}")
    
    def _save_learned(self):
        """Save learned keywords to file."""
        try:
            path = Path(self.LEARNING_FILE)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(self._learned, f, allow_unicode=True)
        except Exception as e:
            print(f"[OpenRouterEnricher] Failed to save: {e}")
    
    def learn_from_correction(self, table_name: str, keywords_to_add: list[str]) -> None:
        """Learn from user correction (continuous learning)."""
        key = table_name.lower().strip()
        if key not in self._learned:
            self._learned[key] = []
        
        for kw in keywords_to_add:
            if kw.lower() not in self._learned[key]:
                self._learned[key].append(kw.lower())
        
        self._save_learned()
        print(f"[OpenRouterEnricher] Learned for '{key}': {keywords_to_add}")
    
    def _detect_category(self, table_name: str, domain: str = "") -> Optional[str]:
        """Detect table category for specialized prompts."""
        text = f"{table_name} {domain}".lower()
        
        if any(term in text for term in ["pix", "pagamento", "ted", "doc", "boleto"]):
            return "pix"
        if any(term in text for term in ["cartao", "cartão", "card", "fatura", "bin"]):
            return "cartoes"
        if any(term in text for term in ["credito", "crédito", "emprestimo", "consignado", "cdc"]):
            return "credito"
        if any(term in text for term in ["cobranca", "cobrança", "inadimp", "aging", "atraso"]):
            return "cobranca"
        if any(term in text for term in ["risco", "var", "basileia", "capital", "rwa"]):
            return "risco"
        if any(term in text for term in ["invest", "fundo", "cdb", "lci", "lca", "custod"]):
            return "investimentos"
        if any(term in text for term in ["pld", "aml", "kyc", "compliance", "lavagem"]):
            return "compliance"
        if any(term in text for term in ["previd", "pgbl", "vgbl", "aposentad"]):
            return "previdencia"
        if any(term in text for term in ["contab", "cosif", "dre", "balanc"]):
            return "financeiro"
        if any(term in text for term in ["cliente", "conta", "agencia", "agência", "comercial"]):
            return "comercial"
        
        return None
    
    def _get_learned_keywords(self, table_name: str) -> list[str]:
        """Get learned keywords for this table."""
        key = table_name.lower().strip()
        
        if key in self._learned:
            return self._learned[key]
        
        for learned_key, keywords in self._learned.items():
            if learned_key in key or key in learned_key:
                return keywords[:5]
        
        return []
    
    async def enrich_keywords(
        self,
        table_name: str,
        domain: str = "",
        description: str = "",
        existing_keywords: list[str] = None
    ) -> list[str]:
        """
        Enrich table keywords using OpenRouter LLM.
        """
        if not self._enabled:
            return existing_keywords or []
        
        # Get learned keywords first
        learned_keywords = self._get_learned_keywords(table_name)
        
        # Detect category for specialized prompt
        category = self._detect_category(table_name, domain)
        category_prompt = CATEGORY_PROMPTS.get(category, "")
        
        # Build prompt
        prompt = f"""Você é um ESPECIALISTA em dados bancários brasileiros.

TAREFA: Gere keywords de ALTA QUALIDADE para esta tabela de dados.

TABELA: {table_name}
DOMÍNIO: {domain or 'Bancário'}
DESCRIÇÃO: {description or 'N/A'}
KEYWORDS ATUAIS: {', '.join(existing_keywords) if existing_keywords else 'Nenhuma'}
{f'APRENDIZADO ANTERIOR: {", ".join(learned_keywords)}' if learned_keywords else ''}
{category_prompt}

REGRAS:
1. Máximo 15 keywords de alta qualidade
2. Inclua ACRÔNIMOS bancários relevantes (PD, LGD, RWA, etc)
3. Inclua SINÔNIMOS e variações (cartão/cartao, crédito/credito)
4. Inclua termos TÉCNICOS do domínio bancário brasileiro
5. Pense em COMO um analista buscaria esta tabela

Retorne APENAS um JSON array com 10-15 keywords de alta qualidade:
["keyword1", "keyword2", ...]

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
                        "max_tokens": 500,
                        "temperature": 0.3,
                    }
                )
                
                if response.status_code != 200:
                    print(f"[OpenRouterEnricher] Error {response.status_code}: {response.text[:200]}")
                    return existing_keywords or []
                
                data = response.json()
                response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Parse JSON
                match = re.search(r'\[.*?\]', response_text, re.DOTALL)
                if match:
                    new_keywords = json.loads(match.group())
                    
                    # Combine all keywords
                    all_keywords = list(existing_keywords) if existing_keywords else []
                    
                    # Add learned keywords first
                    for kw in learned_keywords:
                        if kw.lower() not in [k.lower() for k in all_keywords]:
                            all_keywords.append(kw)
                    
                    # Add LLM-generated keywords
                    for kw in new_keywords:
                        if isinstance(kw, str) and kw.strip():
                            clean_kw = kw.strip().lower()
                            if clean_kw not in [k.lower() for k in all_keywords]:
                                all_keywords.append(clean_kw)
                    
                    return all_keywords[:35]
                    
        except Exception as e:
            print(f"[OpenRouterEnricher] Error: {e}")
        
        return existing_keywords or []
    
    async def enrich_table(self, table: dict) -> dict:
        """Enrich a table's keywords before indexing."""
        enriched_keywords = await self.enrich_keywords(
            table_name=table.get("name", ""),
            domain=table.get("domain", ""),
            description=table.get("description", ""),
            existing_keywords=table.get("keywords", [])
        )
        
        # Update table with enriched keywords
        table["keywords"] = enriched_keywords
        return table


# Singleton
_keyword_enricher: Optional[OpenRouterKeywordEnricher] = None


def get_keyword_enricher() -> OpenRouterKeywordEnricher:
    """Get or create keyword enricher singleton."""
    global _keyword_enricher
    if _keyword_enricher is None:
        _keyword_enricher = OpenRouterKeywordEnricher()
    return _keyword_enricher


async def enrich_table_keywords(table: dict) -> dict:
    """Convenience function to enrich a table's keywords."""
    enricher = get_keyword_enricher()
    return await enricher.enrich_table(table)
