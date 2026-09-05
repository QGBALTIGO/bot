# Source Baltigo Bot

Bot e WebApp do ecossistema **Source Baltigo**, construídos em Python para Telegram, com catálogo, cards, coleção, sistema de dados, jogos, ranking, mensagens e recursos administrativos.

## Stack

- Python 3.11+
- `python-telegram-bot`
- FastAPI + Uvicorn
- PostgreSQL com Psycopg 3 e pool de conexões
- HTTPX, Requests, Beautiful Soup e lxml
- Pillow para processamento de imagens
- Pytest, Ruff, Bandit e pip-audit no CI

## Estrutura principal

```text
bot.py                  Inicialização do Telegram e do runtime completo
webapp.py               Rotas FastAPI e APIs da MiniApp
webapp_entrypoint.py    Entrypoint de produção da WebApp + health routes
database.py             Persistência, migrações e operações PostgreSQL
commands/               Comandos e callbacks do Telegram
handlers/               Handlers de eventos e captura
utils/                  Autenticação, health, workers, locks e utilitários
premium_webapp_ui.py    Interface HTML/CSS/JS da MiniApp
tests/                  Testes automatizados e invariantes estruturais
.github/workflows/      CI e smoke automático da produção
```

## Configuração local

Crie um ambiente virtual e instale as dependências:

```bash
python -m venv .venv
```

No Linux/macOS:

```bash
source .venv/bin/activate
```

No Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Depois:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copie `.env.example` para `.env` e preencha os valores reais. O arquivo `.env` nunca deve ser enviado ao GitHub.

## Variáveis essenciais

| Variável | Finalidade |
|---|---|
| `BOT_TOKEN` | Token do bot fornecido pelo BotFather |
| `DATABASE_URL` | URL de conexão com PostgreSQL |
| `PORT` | Porta HTTP da WebApp; padrão `8000` |
| `BOT_OWNER_ID` | ID numérico do proprietário do bot |

Variáveis comuns adicionais:

| Variável | Finalidade |
|---|---|
| `REQUIRED_CHANNEL` | Canal obrigatório, por exemplo `@SourceBaltigo` |
| `REQUIRED_CHANNEL_URL` | Link público do canal obrigatório |
| `TERMS_VERSION` | Versão atual dos termos de uso |
| `ADMINS` | IDs numéricos autorizados no sistema de dados |
| `ADMIN_IDS` | IDs numéricos autorizados no spawn manual |
| `CARD_ADMIN_IDS` | IDs numéricos autorizados na administração de cards |
| `LOG_LEVEL` | Nível de log, como `INFO` ou `WARNING` |
| `WEBAPP_INITDATA_MAX_AGE_SECONDS` | Validade máxima da identidade assinada da MiniApp |
| `RATE_LIMITER_MAX_KEYS` | Limite de chaves mantidas pelo rate limiter em memória |
| `LOCK_MANAGER_MAX_KEYS` | Limite de locks nomeados mantidos em memória |
| `SOURCE_HEALTH_ALERTS_ENABLED` | Ativa o monitor de saúde do runtime do bot |
| `SOURCE_ALERT_CHAT_ID` | Destino opcional dos alertas; usa `BOT_OWNER_ID` se vazio |

Use sempre IDs numéricos para permissões administrativas. Evite depender exclusivamente de nomes de usuário, pois eles podem ser alterados.

## Executando o runtime completo

Para iniciar o bot Telegram e a WebApp no mesmo processo:

```bash
python bot.py
```

O processo inicia:

1. criação/validação das tabelas;
2. servidor FastAPI/Uvicorn;
3. polling do Telegram;
4. restauração dos estados persistentes;
5. workers de verificação, outbox, notícias e health.

## Executando apenas a WebApp

Em serviços dedicados à WebApp, como o serviço HTTP do Railway, use:

```bash
uvicorn webapp_entrypoint:app --host 0.0.0.0 --port $PORT
```

O `webapp_entrypoint.py` preserva todas as rotas existentes e adiciona os endpoints operacionais:

```text
GET /health
GET /api/health
```

Isso evita depender do bootstrap do bot Telegram para instalar rotas necessárias ao serviço HTTP.

## Validação antes de publicar

```bash
python -m compileall -q .
ruff check . --select E9,F63,F7,F82 --exclude data
python -m pytest -q
bandit -r . -x ./data,./tests -lll
pip-audit -r requirements.txt
```

A branch `main` também executa essas verificações automaticamente pelo GitHub Actions. Pull requests destinados à `main` são auditados antes do merge. Sintaxe inválida, símbolos duplicados e testes quebrados bloqueiam o audit.

Depois de pushes na `main`, o workflow de smoke aguarda a produção e valida o endpoint `/health` e a página raiz.

## Segurança da MiniApp

Endpoints privados não devem confiar em `uid` enviado pelo navegador. A identidade é obtida do `Telegram.WebApp.initData`, validada com HMAC/assinatura oficial do Telegram e comparada com qualquer ID informado pela página.

Boas práticas obrigatórias:

- nunca registrar `BOT_TOKEN`, senhas ou `DATABASE_URL` completa;
- nunca devolver exceções internas ao usuário;
- usar consultas SQL parametrizadas;
- definir timeout nas chamadas HTTP externas;
- executar operações bloqueantes de banco com `asyncio.to_thread` quando chamadas por handlers assíncronos;
- manter callbacks vinculados ao usuário que abriu a ação;
- aplicar rate limit em ações repetíveis e administrativas.

## Deploy

Para um serviço que executa **somente a WebApp**, use:

```bash
uvicorn webapp_entrypoint:app --host 0.0.0.0 --port $PORT
```

Para um host que executa o **bot Telegram completo**, use:

```bash
python bot.py
```

Configure as variáveis necessárias no provedor e confira `/health`, os logs de inicialização e os comandos `/start`, `/menu`, `/perfil`, `/ranking`, `/dado` e `/health`.

## Política de alterações

Mudanças na `main` devem ser pequenas, rastreáveis e acompanhadas por compilação e testes. Correções que alterem economia, saldo, recompensas, troca, duelo ou captura precisam preservar atomicidade no PostgreSQL e ser testadas contra cliques repetidos e requisições concorrentes.
