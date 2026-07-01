# Especially Turismo — Sistema de Atendimento com IA

Automação de atendimento com agente Sofia (Claude AI), chat widget e painel admin.

## Estrutura

```
especially-turismo/
├── backend/
│   ├── main.py          # FastAPI — rotas /chat /leads /stats /health
│   ├── agent.py         # Sofia: prompts, extração de dados, classificação
│   ├── database.py      # SQLite — conversas, leads, métricas
│   ├── config.py        # Configurações da agência
│   ├── alerts.py        # Monitor de saúde e notificações
│   ├── models.py        # Schemas Pydantic
│   └── requirements.txt
├── docs/
│   ├── chat/index.html  # Widget de chat (dark, estilo WhatsApp)
│   └── admin/index.html # Dashboard admin com métricas e leads
└── README.md
```

## Configuração

### 1. Chave da API Anthropic

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Linux/macOS
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 2. Editar config.py (opcional)

```python
AGENCIADOR_NOME       = "Seu Nome"
AGENCIADOR_WHATSAPP   = "5511999999999"
WEBHOOK_URL           = ""   # URL para alertas externos
ORCAMENTO_MINIMO_QUALIFICACAO = 3000
```

### 3. Instalar dependências

```bash
cd backend
pip install -r requirements.txt
```

### 4. Iniciar o servidor

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 5. Abrir os frontends

- **Chat:** abrir `docs/chat/index.html` no navegador
- **Admin:** abrir `docs/admin/index.html` no navegador

> Os arquivos HTML se conectam em `http://localhost:8000` por padrão.

## Rotas da API

| Método | Rota                    | Descrição                          |
|--------|-------------------------|------------------------------------|
| GET    | /health                 | Status do sistema                  |
| GET    | /iniciar                | Nova sessão + saudação da Sofia    |
| POST   | /chat                   | Enviar mensagem, receber resposta  |
| GET    | /leads                  | Lista de leads (filtro por status) |
| GET    | /conversas              | Histórico completo                 |
| GET    | /conversas/{session_id} | Histórico de uma sessão            |
| GET    | /stats                  | Métricas para o dashboard          |
| GET    | /alertas                | Alertas não lidos                  |
| GET    | /leads/exportar/csv     | Download CSV de leads              |

## Classificação de Leads

| Status       | Critério                                                  |
|--------------|-----------------------------------------------------------|
| EM_ANDAMENTO | Dados ainda sendo coletados                               |
| QUALIFICADO  | Todos os 4 dados + orçamento ≥ R$ 3.000                  |
| NURTURING    | Todos os 4 dados + orçamento < R$ 3.000                  |

## Dados coletados pela Sofia

1. **Destino** — para onde deseja viajar
2. **Datas** — período da viagem
3. **Número de pessoas** — tamanho do grupo
4. **Orçamento** — investimento disponível (R$)
