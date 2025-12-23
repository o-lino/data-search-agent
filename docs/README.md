# Documentação do Projeto Leandrinho

Bem-vindo à documentação oficial do Agente de Busca de Dados.
Aqui você encontrará guias para usuários, arquitetos e desenvolvedores.

## Índice

### 📚 Para Usuários Finais

- **[Guia de Uso (Como Pesquisar)](USER_GUIDE.md)**: Aprenda a fazer perguntas eficientes e interpretar as respostas do agente. Ideal para analistas de dados e usuários de negócio.

### 🏗️ Para Arquitetos e Engenheiros

- **[Arquitetura Técnica](ARCHITECTURE.md)**: Visão profunda do funcionamento interno. Explica o grafo LangGraph, o pipeline de RAG híbrido e a ingestão de dados. Contém diagramas de fluxo.
- **[Lógica de Decisão e Ranking](DECISION_LOGIC.md)**: Detalha a matemática por trás da recomendação. Explica como os pesos (Semântica vs Qualidade) funcionam e as regras de desambiguação.

## Estrutura do Repositório

- `/graph.py`: O "cérebro" (Definição do Grafo).
- `/rag`: Motor de busca vetorial (Optimized Retriever).
- `/disambiguation`: Lógica de Scoring e Detecção de Conflitos.
- `/indexing`: Pipeline de ingestão e enriquecimento com LLM.
- `/nodes`: Implementação individual de cada passo do pensamento do agente.
