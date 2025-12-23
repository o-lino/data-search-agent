# Estratégias para Atingir Top-1 > 80%

Atualmente, sua acurácia de **Top-1 é 16%** e **Top-5 é 38%**. Para saltar para **>80%**, precisamos atacar as limitações da busca vetorial pura em cenários caóticos.

Aqui estão as 4 "Balas de Prata" ordenadas por impacto:

## 1. Ativar o LLM Reranking (Impacto: Alto 🚀)

**Onde estamos**: No benchmark atual, o `enable_rerank` foi definido como `False` para economizar tokens/tempo.
**Por que melhora**: A busca vetorial (Embeddings) é ótima para encontrar candidatos (Top 20), mas péssima para precisão fina (quem é o #1).
**Solução**:

- O Retriever busca os Top 20 candidatos.
- O LLM (Gemini Flash) recebe a query e os 20 candidatos e reordena: "Dada a pergunta do usuário, qual destas tabelas é a melhor resposta?".
- **Expectativa**: Isso sozinho costuma levar o Top-1 de 20% para ~60-70%.

## 2. Implementar Busca Híbrida (BM25 + Vetores) (Impacto: Alto 🔨)

**Onde estamos**: Usamos apenas busca semântica (vetores).
**Problema**: Em tabelas com códigos (`TBL_SYS01`) ou nomes exatos (`faturamento_2024`), vetores às vezes "alucinam" e trazem coisas parecidas semanticamente mas erradas (ex: `vendas_2024`).
**Solução**:

- **BM25 (Keyword Search)**: Busca exata por palavras-chave. Se digito "SYS01", ele só traz quem tem "SYS01".
- **Reciprocal Rank Fusion (RRF)**: Algoritmo que combina o ranking dos Vetores com o do BM25.
- **Expectativa**: Resolve quase 100% dos casos de "Easy" e queries com códigos técnicos.

## 3. Hard Filtering por Domínio (Impacto: Médio-Alto 🎯)

**Onde estamos**: Detectamos o domínio com **96.7%** de precisão, mas usamos isso apenas como "peso" no rerank ou nem usamos.
**Solução**:

- Se o classificador diz "Risco" (com >90% de confiança), **filtre** o ChromaDB para buscar APENAS em `domain='Risco'`.
- Isso elimina 85% do ruído (tabelas de Vendas, RH, etc, que poderiam confundir o modelo).
- **Expectativa**: Elimina falsos positivos groseiros.

## 4. Hypothetical Document Embeddings (HyDE) (Impacto: Médio 🧠)

**Problema**: A query do usuário é "preciso ver quanto vendemos". A tabela chama `fat_consol_loja`. Semanticamente distantes.
**Solução**:

- Antes de buscar, o LLM alucina uma tabela ideal: "Tabela contendo dados de vendas, faturamento consolidado por loja..."
- Vetorizamos essa "alucinação" e buscamos por ela.
- A chance de bater com `fat_consol_loja` aumenta drasticamente.

---

## 💡 Recomendação Imediata

O passo mais rápido e barato para testar é **ligar o Rerank** em um subconjunto de testes.
Você quer que eu re-execute um teste menor (ex: 30 casos) com o **Reranking ativado** para provar essa tese?
