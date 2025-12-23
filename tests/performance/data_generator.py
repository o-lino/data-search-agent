import random
import string
from typing import List, Dict, Tuple

# ==========================================
# CONFIGURATION
# ==========================================

DOMAINS = [
    {
        "id": "dom_vendas", 
        "name": "Vendas", 
        "keywords": ["vendas", "faturamento", "receita", "comercial", "lojas", "sell-out", "pdv", "meta", "forecast", "cupom"]
    },
    {
        "id": "dom_risco", 
        "name": "Risco", 
        "keywords": ["risco", "inadimplencia", "perda", "provisionamento", "atraso", "basileia", "serasa", "rating", "score", "fraude"]
    },
    {
        "id": "dom_cadastro", 
        "name": "Cadastro", 
        "keywords": ["cliente", "pf", "pj", "endereço", "dados cadastrais", "kyc", "biometria", "documento", "email", "telefone"]
    },
    {
        "id": "dom_rh", 
        "name": "Recursos Humanos", 
        "keywords": ["funcionarios", "folha", "salario", "banco de horas", "beneficios", "ferias", "recrutamento", "desligamento", "headcount", "ponto"]
    },
    {
        "id": "dom_juridico", 
        "name": "Jurídico", 
        "keywords": ["processos", "contratos", "liminares", "ações", "autuacoes", "tribunal", "advogado", "parecer", "compliance", "lgpd"]
    },
    {
        "id": "dom_logistica", 
        "name": "Logística", 
        "keywords": ["estoque", "deposito", "frete", "entrega", "roteirizacao", "frota", "sku", "picking", "packing", "transportadora"]
    },
    {
        "id": "dom_marketing", 
        "name": "Marketing", 
        "keywords": ["campanha", "leads", "conversao", "churn", "nps", "midia", "redes sociais", "email marketing", "branding", "persona"]
    },
    {
        "id": "dom_ti", 
        "name": "TI e Infra", 
        "keywords": ["servidor", "cloud", "aws", "azure", "kubernetes", "incidente", "chamado", "sla", "deploy", "api"]
    }
]

OWNERS = [f"Owner {i}" for i in range(1, 21)]

# ==========================================
# NAMING STRATEGIES
# ==========================================

class NamingStrategy:
    @staticmethod
    def legacy(base: str, suffix: str) -> str:
        # e.g., TBL_SYS01_CLI_CAD_V1
        code = "".join(random.choices(string.ascii_uppercase, k=3))
        num = random.randint(10, 99)
        clean_base = base.replace(" ", "_").upper()[:10]
        return f"TBL_{code}{num}_{clean_base}_{suffix}".upper()

    @staticmethod
    def datalake(base: str, suffix: str) -> str:
        # e.g., raw_zone.sales_daily_partitioned
        layer = random.choice(["bronze", "silver", "gold", "raw", "trusted"])
        clean_base = base.replace(" ", "_").lower()
        return f"{layer}_zone.{clean_base}_{suffix.lower()}"

    @staticmethod
    def modeling(base: str, suffix: str) -> str:
        # e.g., DimCustomer, FactSales
        prefix = random.choice(["Dim", "Fact", "Fato", "Dimensao"])
        clean_base = "".join(word.capitalize() for word in base.split())
        return f"{prefix}{clean_base}"

    @staticmethod
    def business(base: str, suffix: str) -> str:
        # e.g., Relatório Oficial de Vendas 2024
        year = random.randint(2020, 2025)
        return f"{base} {year} - Versão Final"

    @staticmethod
    def cryptic(base: str, suffix: str) -> str:
        # e.g., ZX_99_A
        return f"{random.choice(string.ascii_uppercase)}{random.choice(string.ascii_uppercase)}_{random.randint(100,999)}"

# ==========================================
# GENERATOR LOGIC
# ==========================================

def generate_column_list(count: int) -> List[str]:
    cols = ["id", "created_at", "updated_at"]
    common = ["nome", "valor", "data", "status", "tipo", "descricao", "codigo"]
    
    for i in range(count):
        if i < len(common):
            cols.append(common[i])
        else:
            cols.append(f"col_{i}_{random.randint(100,999)}")
    return cols

def generate_tables(count: int = 1500) -> List[Dict]:
    tables = []
    
    # Track generated data for test cases
    global _GENERATED_DATA
    _GENERATED_DATA = []

    print(f"[Generator] Creating {count} realistic tables across {len(DOMAINS)} domains...")
    
    # Fix seed for reproducibility/resume support
    random.seed(42)

    for i in range(count):
        domain_obj = random.choice(DOMAINS)
        domain = domain_obj["name"]
        
        # Select base keyword for table concept
        base_keyword = random.choice(domain_obj["keywords"])
        secondary_keyword = random.choice(domain_obj["keywords"])
        
        # Decide Naming Convention
        strategy = random.choices(
            [NamingStrategy.legacy, NamingStrategy.datalake, NamingStrategy.modeling, NamingStrategy.business, NamingStrategy.cryptic],
            weights=[0.2, 0.2, 0.2, 0.3, 0.1]
        )[0]
        
        # Generate Name
        suffix = f"{random.randint(1,9)}"
        name = strategy(f"{base_keyword} {secondary_keyword}", suffix)
        
        # Generate Description (Quality varies)
        quality = random.random()
        if quality < 0.2: # 20% no description
            description = ""
        elif quality < 0.4: # 20% bad description
            description = "tabela de dados sistema legado"
        else:
            description = f"Tabela contendo dados de {base_keyword} e {secondary_keyword} para análises de {domain}. Atualização diária."

        # Generate Columns (Variance from 5 to 350+)
        num_cols = random.choices([5, 20, 50, 150, 350], weights=[0.1, 0.4, 0.3, 0.1, 0.1])[0]
        columns = generate_column_list(num_cols)
        
        # Create Table Object
        table = {
            "id": i + 1000,
            "name": name,
            "display_name": name if quality < 0.5 else f"Base {base_keyword.capitalize()}",
            "description": description,
            "domain": domain,
            "owner_name": random.choice(OWNERS),
            "keywords": [base_keyword, secondary_keyword] if quality > 0.3 else [], # Some have no keywords
            "columns": columns, # Just for metadata richness
            "_generated_metadata": {
                "base_keyword": base_keyword,
                "strategy": strategy.__name__
            }
        }
        
        tables.append(table)
        _GENERATED_DATA.append(table) # Store for test generator

    return tables

# ==========================================
# TEST CASE GENERATOR
# ==========================================

def generate_test_cases(tables: List[Dict] = None) -> List[Dict]:
    """
    Generates 150 robust test cases based on the ACTUAL generated tables.
    Must be called after generate_tables.
    """
    if not tables and _GENERATED_DATA:
        tables = _GENERATED_DATA
    
    if not tables:
        raise ValueError("No tables generated to create tests from!")

    cases = []
    
    # Helper to find target
    def find_target(domain_name=None, strategy=None):
        candidates = [t for t in tables if 
                      (not domain_name or t["domain"] == domain_name) and 
                      (not strategy or t["_generated_metadata"]["strategy"] == strategy)]
        return random.choice(candidates) if candidates else random.choice(tables)

    # 1. EASY (50): Exact match or very close
    for _ in range(50):
        target = random.choice(tables)
        # Query is just the display name or clean name
        query = target["display_name"] if target["display_name"] != target["name"] else target["name"]
        
        # If cryptic, use the keyword (oracle-style search)
        if target["_generated_metadata"]["strategy"] == "cryptic":
            query = f"tabela {target['_generated_metadata']['base_keyword']}"
            
        cases.append({
            "query": query,
            "expected_id": target["id"],
            "difficulty": "easy",
            "expected_domain": target["domain"]
        })

    # 2. MEDIUM (50): Concept + Domain
    for _ in range(50):
        target = random.choice(tables)
        base = target["_generated_metadata"]["base_keyword"]
        
        qs = [
            f"preciso de dados de {base}",
            f"onde encontro {base} do {target['domain']}",
            f"base de {base} atualizada",
            f"tabela para analisar {base}"
        ]
        
        cases.append({
            "query": random.choice(qs),
            "expected_id": target["id"],
            "difficulty": "medium",
            "expected_domain": target["domain"]
        })

    # 3. HARD (50): Indirect, modeled, or legacy codes
    for _ in range(50):
        target = random.choice(tables)
        strategy = target["_generated_metadata"]["strategy"]
        base = target["_generated_metadata"]["base_keyword"]
        
        if strategy == "legacy":
            # User asks by code part "SYS01"
            parts = target["name"].split("_")
            q = f"tabela do sistema {parts[1] if len(parts)>1 else 'legado'}"
        elif strategy == "modeling":
            # User asks "dimensão cliente" for DimCustomer
            q = f"dimensão {base}" if "Dim" in target["name"] else f"fato {base}"
        elif strategy == "datalake":
            # User asks "silver zone vendas"
            q = f"dados da silver zone sobre {base}"
        else:
            # Vague query
            q = f"relatório anual de {base} para diretoria"
            
        cases.append({
            "query": q,
            "expected_id": target["id"],
            "difficulty": "hard",
            "expected_domain": target["domain"]
        })

    return cases
