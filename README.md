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
bot.py                  Inicialização do Telegram e da WebApp
webapp.py               Rotas FastAPI e APIs da MiniApp
database.py             Persistência, migrações e operações PostgreSQL
commands/               Comandos e callbacks do Telegram
handlers/               Handlers de eventos e captura
utils/                  Autenticação, locks, rate limit e utilitários
premium_webapp_ui.py    Interface HTML/CSS/JS da MiniApp
tests/                  Testes automatizados e invariantes estruturais
.github/workflows/      Auditoria automática da branch main
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

Use sempre IDs numéricos para permissões administrativas. Evite depender exclusivamente de nomes de usuário, pois eles podem ser alterados.

## Integração com o AniNexus

O AniNexus é a camada pública de catálogo e a referência visual da MiniApp. O bot consome apenas os endpoints públicos permitidos por `utils/aninexus_client.py` e os reexpõe em `/api/aninexus/*`, com timeout, cache limitado, validação de resposta e fallback local no catálogo.

| Variável | Finalidade |
|---|---|
| `ANINEXUS_ENABLED` | Ativa o provedor AniNexus; padrão `true` |
| `ANINEXUS_API_BASE_URL` | Origem da API pública, sem caminho ou credenciais |
| `ANINEXUS_WEB_BASE_URL` | Origem usada para abrir páginas e assets do site |
| `ANINEXUS_API_TIMEOUT_SECONDS` | Timeout por chamada ao AniNexus |
| `ANINEXUS_CACHE_MAX_ENTRIES` | Limite do cache e dos locks de consulta em memória |
| `ANINEXUS_USER_AGENT` | Identificação HTTP do bot perante o AniNexus |

Contratos disponíveis no bot:

```text
GET /api/aninexus/status
GET /api/aninexus/home
GET /api/aninexus/catalog
GET /api/aninexus/reading
GET /api/aninexus/schedule
GET /api/aninexus/anime/{id}
GET /api/aninexus/manga/{id}
```

A interface usa o AniNexus primeiro para home e catálogo. Quando a API não responde, o catálogo antigo permanece como fallback, evitando uma tela vazia durante a migração.

## Executando

```bash
python bot.py
```

O processo inicia:

1. criação/validação das tabelas;
2. servidor FastAPI/Uvicorn;
3. polling do Telegram;
4. restauração dos estados persistentes;
5. workers supervisionados de verificação e outbox.

## Validação antes de publicar

```bash
python -m compileall -q .
ruff check . --select E9,F63,F7,F82 --exclude data
pytest -q
bandit -r . -x ./data,./tests -lll
pip-audit -r requirements.txt
```

A branch `main` também executa essas verificações automaticamente pelo GitHub Actions. Sintaxe inválida, símbolos duplicados e testes quebrados bloqueiam o audit.

## Segurança da MiniApp

Endpoints privados não devem confiar em `uid` enviado pelo navegador. A identidade é obtida do `Telegram.WebApp.initData`, validada com HMAC e comparada com qualquer ID informado pela página.

Boas práticas obrigatórias:

- nunca registrar `BOT_TOKEN`, senhas ou `DATABASE_URL` completa;
- nunca devolver exceções internas ao usuário;
- usar consultas SQL parametrizadas;
- definir timeout nas chamadas HTTP externas;
- executar operações bloqueantes de banco com `asyncio.to_thread` quando chamadas por handlers assíncronos;
- manter callbacks vinculados ao usuário que abriu a ação;
- aplicar rate limit em ações repetíveis e administrativas.

## Deploy

O comando de inicialização recomendado é:

```bash
python bot.py
```

Configure `BOT_TOKEN`, `DATABASE_URL`, `PORT` e as permissões administrativas no painel do provedor. Depois do deploy, confira os logs de inicialização, o endpoint da WebApp e os comandos `/start`, `/menu`, `/perfil`, `/ranking` e `/dado`.

## Política de alterações

Mudanças na `main` devem ser pequenas, rastreáveis e acompanhadas por compilação e testes. Correções que alterem economia, saldo, recompensas, troca, duelo ou captura precisam preservar atomicidade no PostgreSQL e ser testadas contra cliques repetidos e requisições concorrentes.
