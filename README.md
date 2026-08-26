# Source Baltigo Bot

Bot Telegram + MiniApp FastAPI para catálogo de animes/mangás, cards, pedidos, progressão e experiências web do Source Baltigo.

> A auditoria técnica detalhada e o roadmap estão em [`AUDIT_REFACTOR.md`](AUDIT_REFACTOR.md).

## Estado atual desta refatoração

A branch `refactor/technical-foundation` corrige problemas de inicialização e cria uma camada de segurança/manutenção antes do redesign visual.

Principais mudanças:

- bootstrap do bot corrigido e logging padronizado;
- `/baltigoflix` recuperado e configurável por `BASE_URL`;
- sistema de mensagens incompleto isolado por feature flag;
- `/card` unificado com `cards_service` e seus overrides;
- gatekeeper aplicado a fluxos que antes o ignoravam;
- dados dinâmicos escapados em mensagens HTML refatoradas;
- autenticação server-side de `Telegram.WebApp.initData`;
- endpoints sensíveis da MiniApp protegidos contra falsificação de `user_id`;
- reload HTTP de cards protegido por token administrativo;
- arquivo `.session` removido da ponta da branch e bloqueado no `.gitignore`;
- testes unitários iniciais + GitHub Actions;
- `.env.example` com configuração documentada.

## Requisitos

- Python 3.11+ (CI usa Python 3.12)
- PostgreSQL
- domínio HTTPS público para a MiniApp
- bot Telegram configurado no BotFather

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copie a configuração de exemplo e preencha os segredos:

```bash
cp .env.example .env
```

Variáveis mínimas:

```env
BOT_TOKEN=...
DATABASE_URL=postgresql://...
BASE_URL=https://seu-dominio
```

O projeto lê variáveis do ambiente. Se usar um arquivo `.env` local, carregue-o pelo seu runtime/deploy ou exporte as variáveis antes de iniciar.

## Execução

```bash
python bot.py
```

O processo inicia:

1. tabelas/migrações legadas atuais;
2. WebApp FastAPI/Uvicorn em uma thread;
3. polling do bot Telegram.

A WebApp é servida através de `secure_webapp.py`, que envolve o `webapp.py` legado com validação de identidade e proteção de endpoints.

## MiniApp e autenticação

Não confie em `Telegram.WebApp.initDataUnsafe` no backend.

Nesta branch, chamadas same-origin da MiniApp enviam `Telegram.WebApp.initData` em `X-Telegram-Init-Data`. O servidor:

- valida a assinatura HMAC usando `BOT_TOKEN`;
- verifica idade de `auth_date`;
- extrai a identidade assinada;
- recusa `uid/user_id` divergente.

A validade padrão é 1 hora:

```env
WEBAPP_AUTH_MAX_AGE_SECONDS=3600
```

### Reload administrativo de cards

`/api/cards/reload` não é mais um endpoint público. Para permitir chamada administrativa HTTP, defina um segredo longo:

```env
WEBAPP_ADMIN_TOKEN=gere-um-segredo-forte
```

E envie-o exclusivamente no header `X-Admin-Token`.

## Sistema de mensagens

A implementação atual de `commands/messages.py` referencia uma camada de persistência que não está presente no `database.py` do repositório.

Por segurança e para não impedir a inicialização do restante do bot, ela fica desativada por padrão:

```env
ENABLE_MESSAGES=false
```

Não altere para `true` até o schema e as funções de perfil/nickname/coins/bloqueios/relay/denúncias serem reconstruídos e testados.

## Comandos principais

- `/start`
- `/anime`
- `/manga`
- `/cards`
- `/card`
- `/nivel`
- `/pedido`
- `/baltigoflix`

Os comandos administrativos de cards continuam protegidos por `CARD_ADMIN_IDS` e/ou `CARD_ADMIN_USERNAMES`.

```env
CARD_ADMIN_IDS=123456789,987654321
CARD_ADMIN_USERNAMES=admin1,admin2
```

## Testes

A suíte inicial usa `unittest` da biblioteca padrão:

```bash
python -m unittest discover -s tests -v
```

Cobertura inicial:

- validação de assinatura Telegram MiniApp;
- adulteração/expiração de `initData`;
- faixas de rank;
- barra de progresso;
- formatação de ranking.

O workflow `.github/workflows/tests.yml` executa esses testes em pushes e pull requests.

## Segurança operacional importante

Um arquivo `sessao_busca.session` já esteve versionado no repositório público. Ele foi removido desta branch e novos `.session` são ignorados, mas isso **não remove o arquivo do histórico Git**.

A sessão correspondente deve ser revogada/invalidada no serviço que a criou. Se o arquivo continha uma sessão real ainda válida, considere-a comprometida.

Nunca versione:

- `BOT_TOKEN`;
- `DATABASE_URL` com senha real;
- `.env`;
- arquivos `*.session`;
- tokens administrativos.

## Próximas etapas

Antes do redesign visual:

1. tornar operações críticas de banco atômicas;
2. separar migrações do startup;
3. dividir `webapp.py` em routers, templates e arquivos estáticos;
4. criar services/repositories;
5. ampliar testes de integração e smoke startup;
6. decidir/reconstruir o sistema de mensagens.

Depois disso entra a fase de design system, UI/UX, animações, responsividade, acessibilidade e performance visual descrita em `AUDIT_REFACTOR.md`.
