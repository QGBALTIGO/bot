# Source Baltigo Bot (Telegram + WebApp)

Sim: **as melhorias já foram aplicadas direto no código do bot**.
Você **não** precisa implementar do zero.

## O que já está aplicado

- Proteções de concorrência/rate limit em runtime (`utils/runtime_guard.py`):
  - `InMemoryRateLimiter`
  - `KeyedLockManager`
- Proteção de flood no `gatekeeper` (`utils/gatekeeper.py`)
- Proteção de spam/duplo clique no callback de card (`commands/card.py`)
- Refactor de bootstrap do bot (`bot.py`) com `build_application()`
- Correção de defaults:
  - `@SourceBaltigo` / `https://t.me/SourceBaltigo`
  - `CATALOG_PATH=data/catalogo_enriquecido.json`

## Primeira execução (passo a passo)

1. Instale dependências:

```bash
pip install -r requirements.txt
```

2. Configure variáveis de ambiente mínimas:

```bash
export BOT_TOKEN="..."
export DATABASE_URL="postgresql://..."
export BASE_URL="https://seu-dominio"
```

3. (Opcional) Ajuste limites de proteção:

```bash
export GATEKEEPER_RATE_LIMIT="8"
export GATEKEEPER_RATE_WINDOW_SECONDS="5"
export PROGRESS_RATE_LIMIT="1"
export PROGRESS_RATE_WINDOW_SECONDS="2.5"
export CARD_CALLBACK_RATE_LIMIT="4"
export CARD_CALLBACK_RATE_WINDOW_SECONDS="3"
```

4. Suba o bot:

```bash
python bot.py
```

## Se você está usando pela primeira vez

Você só precisa:

- configurar as variáveis de ambiente,
- executar `python bot.py`,
- validar os comandos no privado (`/start`, `/card`, `/nivel`, `/pedido`).

A parte de proteção contra spam/race condition já está no projeto.

## Checklist rápido de validação

- `/start` no privado responde normalmente.
- `/card` funciona e o botão de stats não dispara em spam infinito.
- Flood de comandos não degrada o bot imediatamente.
- WebApp sobe junto com o bot.

## Próximo nível (recomendado)

- Adicionar testes automatizados (`pytest`) para:
  - `normalize_media_title`
  - `get_rank_tag`
  - `build_progress_bar`
  - `format_rank_position`
- Criar pipeline CI para rodar esses testes em todo PR.


## Comandos admin (importante)

Se os comandos admin não responderem, configure pelo menos uma dessas variáveis antes de iniciar o bot:

```bash
export CARD_ADMIN_IDS="123456789,987654321"
# ou
export CARD_ADMIN_USERNAMES="seuuser1,seuuser2"
```

Dica: em grupos, use o comando com ou sem menção ao bot (`/card_addanime` ou `/card_addanime@SeuBot`) — ambos são aceitos.
