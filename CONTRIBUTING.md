# Guia de Contribuição

Obrigado por considerar contribuir para o Agente de Busca de Dados! 🎉

## 🚀 Como Contribuir

### 1. Fork e Clone

```bash
git clone https://github.com/SEU-USUARIO/data-search-agent.git
cd data-search-agent
```

### 2. Configure o Ambiente

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows

pip install -r requirements.txt
pip install ruff pytest pytest-cov
```

### 3. Crie uma Branch

```bash
git checkout -b feature/minha-nova-feature
# ou
git checkout -b fix/correcao-do-bug
```

### 4. Faça suas Mudanças

- Siga o estilo de código existente
- Adicione testes para novas funcionalidades
- Atualize a documentação se necessário

### 5. Rode os Testes

```bash
# Lint
ruff check .

# Testes
pytest tests/ -v
```

### 6. Commit e Push

Use mensagens de commit seguindo [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git commit -m "feat: adiciona busca por coluna"
git commit -m "fix: corrige timeout em queries longas"
git commit -m "docs: atualiza guia de instalação"
```

### 7. Abra um Pull Request

Vá até o repositório original e abra um PR da sua branch.

## 📋 Convenções de Código

- **Python**: Seguimos PEP 8 com linha máxima de 120 caracteres
- **Linter**: Utilizamos `ruff` para verificação de código
- **Type Hints**: Use type hints sempre que possível
- **Docstrings**: Use docstrings para documentar funções públicas

## 🧪 Testes

- Todos os PRs devem manter ou aumentar a cobertura de testes
- Use `pytest` para rodar os testes
- Organize testes em `tests/` seguindo a estrutura do código

## 📚 Documentação

- Atualize a documentação em `docs/` para mudanças significativas
- Mantenha o README atualizado
- Adicione exemplos de uso quando apropriado

## 🐛 Reportando Bugs

Use o template de issue para bugs, incluindo:

- Descrição clara do problema
- Passos para reproduzir
- Comportamento esperado vs atual
- Versão do Python e sistema operacional

## 💬 Dúvidas?

Abra uma issue com a label `question` para tirar dúvidas.

---

Novamente, obrigado por contribuir! 🙏
