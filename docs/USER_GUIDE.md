# Guia de Uso: Assistente de Dados (Leandrinho)

Bem-vindo! Este guia vai te ensinar a usar o Leandrinho para encontrar dados na empresa sem dor de cabeça.

## O Que é o Leandrinho?

Imagine que ele é um bibliotecário que conhece todas as tabelas de dados da empresa. Você diz o que precisa (em português normal) e ele te diz onde encontrar.

---

## Como Fazer Perguntas (Boas Práticas)

O Leandrinho entende perguntas simples, mas quanto mais detalhes você der, melhor.

### ✅ Bons Exemplos

- "Preciso saber a inadimplência total por safra no varejo." (Ótimo! Tem métrica, quebra e segmento)
- "Quais tabelas têm dados de transações de cartão de crédito?"
- "Quem é o dono dos dados de RH?"

### ❌ Exemplos Ruins (E como corrigir)

- **"Vendas"** -> Muito vago. O Leandrinho vai te devolver centenas de tabelas.
  - _Melhor_: "Vendas diárias por loja em 2024".
- **"Tabela X"** -> Se você só digitar uma letra, ele não entende.
  - _Melhor_: "Existe alguma tabela chamada TB_CLIENTE_X?"

---

## Entendendo as Respostas

Quando o Leandrinho responde, ele pode te dar 3 tipos de retorno:

### 1. A Recomendação Certeira ("Alta Confiança")

> _"Encontrei a tabela perfeita: **TB_VENDAS_CONSOLIDADA**. Ela é Golden Source (oficial) e está atualizada."_

Isso significa que você pode usar sem medo. Ele verificou que é a tabela oficial.

### 2. A Sugestão com Cautela ("Confirmar com Dono")

> _"A melhor opção parece ser a **TB_TEMP_VENDAS**, mas ela não é oficial. Recomendo falar com o João Silva antes."_

Isso acontece quando não existe uma tabela "Oficial", ou quando o sistema só achou tabelas de teste. Siga o conselho e mande um email para o dono sugerido.

### 3. A Pergunta de Esclarecimento

> _"Você quis dizer Vendas de **Varejo** ou **Atacado**?"_

O Leandrinho percebeu que sua pergunta serve para duas áreas diferentes. Basta responder "Varejo" e ele continua a busca.

---

## O Que Significam os Termos?

- **Golden Source**: É o selo de qualidade máxima. Significa "Dado Oficial Aprovado pela Governança". Sempre prefira essas tabelas.
- **Data Owner (Dono)**: A pessoa responsável por garantir que aquele dado está certo. Se tiver dúvida, chame essa pessoa.
- **Stale (Desatualizada)**: Significa que a tabela parou de receber dados novos (ex: deveria carregar todo dia, mas travou semana passada). Cuidado!

## Dicas Extras

- **Feedbak**: Se o Leandrinho errar, diga! "Essa tabela não tem o que eu pedi". Ele aprende com o tempo.
- **Siglas**: Ele conhece a maioria das siglas do banco (CRI, LIG, PJ, PF). Pode usar à vontade.
