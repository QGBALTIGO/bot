# Auditoria técnica e plano de refatoração — Source Baltigo Bot

Data da revisão: 2026-08-26

Esta auditoria separa três objetivos que não devem ser misturados em um único salto:

1. restaurar confiabilidade e segurança da base atual;
2. reduzir dívida arquitetural e facilitar manutenção/testes;
3. redesenhar a experiência visual com uma fundação estável.

## Escala de prioridade

- **P0 — bloqueador/crítico:** impede inicialização, permite falsificação de identidade ou expõe credenciais.
- **P1 — alto:** pode gerar inconsistência de dados, abuso, indisponibilidade ou comportamento incorreto relevante.
- **P2 — médio:** dívida técnica, performance, observabilidade, manutenção ou UX funcional.
- **P3 — melhoria:** qualidade, consistência, acabamento e evolução futura.

---

## P0 — encontrados e tratados nesta branch

### 1. Bootstrap quebrado por import inexistente

**Antes:** `bot.py` importava `handlers.baltigoflix`, mas o módulo estava em `commands/baltigoflix.py`.

**Impacto:** o processo falhava antes de iniciar o polling.

**Status:** corrigido.

### 2. `/baltigoflix` dependia de módulos/funções inexistentes

O comando importava `config.BOT_BRAND` e `ensure_channel_membership`, que não existem na base atual.

**Impacto:** novo bloqueio de import/inicialização.

**Status:** refeito usando a configuração existente, `BASE_URL` e `gatekeeper`.

### 3. Sistema de mensagens importava uma camada de banco inexistente

`commands/messages.py` depende de funções de perfil, nickname, coins, bloqueios, relay e denúncias que não existem no `database.py` atual.

**Impacto:** importar o módulo derrubava todo o bot.

**Status atual:** isolado atrás de `ENABLE_MESSAGES=false` por padrão. O restante do bot pode iniciar sem importar a feature incompleta.

**Próxima decisão:** reconstruir a feature com schema e regras explícitas, ou removê-la definitivamente. Não habilitar em produção enquanto a camada de persistência não for implementada e testada.

### 4. Arquivo de sessão Telegram versionado em repositório público

`sessao_busca.session` estava commitado.

**Impacto:** arquivos de sessão podem funcionar como credenciais reutilizáveis.

**Status no branch:** removido e `*.session` bloqueado no `.gitignore`.

**Ação operacional obrigatória:** invalidar/revogar a sessão correspondente. A remoção do arquivo da ponta da branch não apaga versões anteriores do histórico Git.

### 5. MiniApp confiava em `uid/user_id` fornecido pelo navegador

Os endpoints de termos, canal e pedidos aceitavam a identidade enviada no JSON. O frontend lia `initDataUnsafe`, mas o servidor não validava a assinatura do Telegram.

**Impacto:** um cliente modificado poderia tentar operar em nome de outro `user_id`.

**Status:** criada camada de autenticação em `secure_webapp.py` + `utils/webapp_auth.py`:

- valida HMAC de `Telegram.WebApp.initData`;
- valida `auth_date` e expiração;
- compara identidade assinada com `uid/user_id` informado;
- substitui username/nome por dados assinados quando aplicável;
- exige sessão válida para endpoints de pedidos e limites;
- injeta `X-Telegram-Init-Data` automaticamente nas requisições same-origin da MiniApp existente.

### 6. Endpoint administrativo de reload era público

`GET /api/cards/reload` podia ser chamado sem autorização.

**Impacto:** superfície de abuso/DoS e operação administrativa exposta.

**Status:** protegido por `WEBAPP_ADMIN_TOKEN`; sem token correto responde como endpoint inexistente.

---

## P1 — encontrados e tratados nesta branch

### 7. `/card` usava uma base de personagens diferente da WebApp/admin

O comando carregava diretamente `personagens_anilist.txt`, enquanto o sistema administrativo usa `cards_service` e overrides.

**Impacto:** personagem removido/renomeado/adicionado pelo admin podia aparecer diferente no comando.

**Status:** `/card` agora usa a mesma fonte final de `cards_service`.

### 8. Estatística fictícia fixa no `/card`

O comando mostrava `total_rolls = 12483` como preview.

**Impacto:** dado incorreto apresentado como estatística real.

**Status:** removido até existir persistência real de giros.

### 9. Exceções internas eram exibidas diretamente ao usuário

Exemplo: `/card` e alguns endpoints retornavam texto de exceção.

**Impacto:** exposição de detalhes internos e UX ruim.

**Status parcial:** comandos alterados usam mensagem genérica + log interno. A camada segura da MiniApp substitui respostas HTTP 500 protegidas por erro genérico.

### 10. HTML dinâmico sem escape

Nome de usuário, busca de card e outros dados dinâmicos entravam em mensagens Telegram com `parse_mode=HTML`.

**Impacto:** quebra de formatação e possibilidade de conteúdo enganoso/injetado.

**Status:** corrigido nos fluxos refatorados de `/start`, `/card`, `/cards` e `/nivel`.

**Pendente:** corrigir também `commands/messages.py` caso a feature seja reconstruída.

### 11. `/nivel` não passava pelo gatekeeper

**Impacto:** bypass de termos/canal obrigatório.

**Status:** corrigido.

### 12. Consultar `/nivel` podia alimentar o próprio XP

O gatekeeper registrava progresso para quase todo comando.

**Impacto:** mecanismo de progressão facilmente inflável.

**Status:** `/nivel`, configuração/bloqueios de mensagens e comandos administrativos foram excluídos da progressão.

### 13. Verificação de membro ignorava usuário `restricted` que continua membro

**Status:** helper passou a aceitar `restricted` quando `is_member=true`.

### 14. Default de canal era inconsistente

`/start` usava `@SourceBaltigo`, mas o gatekeeper tinha default vazio.

**Impacto:** sem ENV explícita, o onboarding exigia canal e outros comandos poderiam não exigir.

**Status:** padronizado para `@SourceBaltigo`.

---

## P1/P2 — ainda pendentes para a próxima etapa técnica

### 15. Operações de banco com risco de race condition entre processos

Há sequências read-then-write em funções como remoção de cópia de card e progressão de XP.

Locks em memória protegem somente um processo Python. Eles não protegem duas instâncias/replicas concorrentes.

**Recomendação:** transformar alterações críticas em SQL atômico (`UPDATE ... RETURNING`, UPSERT/CTE ou transações com row lock conforme a regra de negócio).

### 16. Migrações estão acopladas ao startup

`create_tables()` executa `CREATE/ALTER` durante inicialização da aplicação.

**Riscos:**

- startup lento;
- dificuldade de rollback;
- evolução de schema sem histórico formal;
- concorrência de migração se houver múltiplas instâncias.

**Recomendação:** adotar Alembic ou mecanismo equivalente e separar `migrate` de `run`.

### 17. Pool de banco é criado no import do módulo

`database.py` exige `DATABASE_URL` e cria `ConnectionPool` ao importar.

**Impacto:** testes e ferramentas que só querem importar funções puras ficam dependentes de banco/configuração.

**Recomendação:** camada de configuração tipada + inicialização/lifespan explícito.

### 18. `webapp.py` concentra milhares de linhas de Python + HTML + CSS + JS

**Impacto:** alto acoplamento, revisão difícil, risco de regressão visual/funcional e baixa testabilidade.

**Recomendação para a próxima refatoração:**

```text
app/
  config.py
  db/
    pool.py
    repositories/
    migrations/
  telegram/
    bot.py
    commands/
    services/
  web/
    app.py
    routers/
      terms.py
      catalog.py
      cards.py
      pedidos.py
      baltigoflix.py
    services/
    templates/
    static/
      css/
      js/
      images/
  domain/
    cards/
    progression/
    requests/
  security/
    telegram_webapp.py
```

Não é necessário migrar tudo de uma vez. Mover um domínio por PR reduz risco.

### 19. Chamadas externas precisam de política comum

AniList e Bot API possuem timeouts/retries implementados de formas diferentes.

**Recomendação:** clientes reutilizáveis, timeout explícito, retry somente em falhas transitórias, logging estruturado e limite de concorrência.

### 20. Rate limit é local ao processo

O rate limiter foi melhorado para limpar entradas expiradas, mas continua in-memory.

**Impacto:** com múltiplas instâncias, cada réplica possui seu próprio limite.

**Recomendação futura:** Redis/Valkey para rate limits que realmente precisam ser globais.

### 21. Observabilidade ainda é básica

Foi introduzido `logging`, mas faltam:

- request/correlation ID;
- métricas de erro/latência;
- health/readiness separados;
- tracking de chamadas externas;
- alertas de falha do bot/WebApp.

---

## P2/P3 — qualidade e manutenção

### Testes

Adicionados inicialmente:

- assinatura e expiração do Telegram WebApp `initData`;
- adulteração de identidade/token;
- limites de rank;
- barra de progresso;
- posição no ranking.

Há workflow de CI em `.github/workflows/tests.yml`.

Próximos testes prioritários:

1. middleware da MiniApp;
2. gatekeeper;
3. comandos com mocks do Telegram;
4. cards_service e overrides;
5. repositórios de banco com PostgreSQL de teste;
6. contratos dos endpoints FastAPI;
7. smoke test de startup.

### Configuração

Criado `.env.example` e `.gitignore` para evitar segredos/sessões locais.

### Dependências

`httpx` passou a ser dependência direta explícita, pois é usado diretamente pela WebApp.

---

# Fase 2 — refatoração arquitetural recomendada

Ordem sugerida:

1. **Banco e migrações** — tornar XP/cards/pedidos atômicos.
2. **Config centralizada** — uma única fonte para ENV, URLs e defaults.
3. **Separar WebApp em routers/templates/static.**
4. **Services/repositories** — handlers deixam de conhecer SQL/HTTP diretamente.
5. **Testes de integração e smoke startup.**
6. **Observabilidade/health/readiness.**
7. **Reavaliar/reconstruir sistema de mensagens.**

A regra é preservar comportamento externo enquanto a estrutura interna muda.

---

# Fase 3 — redesign visual e experiência

Só depois da base acima, transformar a MiniApp em um sistema visual consistente.

## Design system

Criar tokens para:

- cores e superfícies;
- tipografia;
- spacing;
- radius;
- sombras;
- blur/glass;
- z-index;
- duração/easing de movimento;
- estados de hover/pressed/focus/disabled/loading/error/success.

## Integração nativa com Telegram

Usar variáveis de tema do Telegram e reagir a mudanças entre claro/escuro. Respeitar safe areas e viewport dinâmico.

## Motion

Animação deve comunicar estado, não apenas decorar:

- transições entre telas;
- entrada escalonada de cards;
- skeleton loading;
- feedback tátil/visual em botões;
- expansão de detalhes;
- filtros e busca com transição suave;
- modal/bottom sheet;
- animações de conquista/level-up/card raro;
- loading progressivo de imagens.

Sempre implementar `prefers-reduced-motion` e reduzir efeitos em dispositivos fracos.

## UX

- navegação consistente entre Catálogo, Cards, Mangás, Pedidos e BaltigoFlix;
- estados vazios úteis;
- erros recuperáveis;
- feedback instantâneo;
- busca com debounce;
- skeleton em vez de tela parada;
- acessibilidade de contraste/foco/labels;
- mobile-first;
- imagens responsivas e lazy loading;
- evitar layout shift.

## Performance visual

Meta sugerida:

- animações em 60 fps em aparelhos comuns;
- nenhum efeito pesado obrigatório;
- CSS/JS dividido e cacheável;
- imagens com tamanho adequado ao viewport;
- componentes carregados sob demanda quando fizer sentido.

---

# Critério para começar o redesign

A base estará pronta para a fase visual quando:

- o bot iniciar sem imports opcionais quebrados;
- CI estiver verde;
- endpoints com identidade validarem Telegram `initData`;
- segredos/sessões não estiverem versionados;
- operações críticas de banco estiverem atômicas;
- WebApp estiver separada o suficiente para CSS/JS/componentes não dependerem de editar um arquivo monolítico;
- existir smoke test mínimo para os principais fluxos.

A partir daí, o redesign pode ser agressivo visualmente sem comprometer a confiabilidade do produto.
