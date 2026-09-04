# Source Baltigo Fusion

## Objetivo

Transformar o Source Baltigo em uma plataforma de coleção/gacha que preserve os dados atuais dos usuários, adote a experiência completa do frontend do Seal Your Waifu Bot e incorpore os melhores mecanismos observados em outros projetos públicos de gacha/catcher.

## Regra número 1: identidade é permanente

O `character_id` do Source é a identidade canônica do personagem.

Uma troca de arte, raridade visual, UI, backend ou origem de mídia **não pode criar um novo personagem quando o personagem já existe**.

Exemplo:

- Source já possui `Monkey D. Luffy`, `character_id=123`;
- a coleção de Kayky possui `(user_id, character_id=123, quantity=2)`;
- chega uma arte melhor;
- o importador atualiza apenas a imagem global de `character_id=123`;
- a coleção continua apontando para `123` e nenhuma posse é perdida.

## Upstream principal: Seal Your Waifu Bot

Frontend importado a partir de:

- https://github.com/bisug/seal-your-waifu-bot
- licença preservada em `THIRD_PARTY_LICENSES/SEAL_YOUR_WAIFU_LICENSE.txt`
- commit upstream registrado em `frontend/UPSTREAM.md`

A adaptação para Source deve preservar atribuição e não atribuir ao Source a autoria do código upstream.

## Frontend a preservar

- React + TypeScript + Vite
- Tailwind CSS v4
- React Query
- Framer Motion
- Lucide
- Outfit para UI
- JetBrains Mono para valores/estatísticas
- intro/loading do app
- Error Boundary
- deep-links por hash/startapp/tgWebAppStartParam
- Telegram BackButton
- Telegram haptics
- sincronização com tema do Telegram
- scroll individual por aba
- lazy loading de páginas
- modais/bottom sheets
- GachaReveal
- skeletons, shimmers e estados vazios
- cache/invalidação das queries

## Áreas do Seal a portar para o Source

1. Perfil
2. Galeria/arquivo de personagens
3. Loja
4. Exchange
5. Hatchery/incubação
6. Pet Shop
7. My Pets
8. Quests
9. Battle Pass/temporada
10. Achievements
11. Leaderboard
12. Referrals
13. Minigames
14. Trading
15. Upload de personagem
16. Staff/Admin

## Áreas exclusivas do Source que permanecem

- AniNexus
- catálogo de animes
- catálogo/leitor de mangás
- notícias
- Termo Anime
- Dado
- Cards/XCards existentes durante a migração
- BaltigoFlix
- música/anime themes quando aplicável
- Akira

## Sistemas a incorporar de outros projetos

### BasteArima/GachaBot

- pity system
- fragmentos de duplicata
- crafting/evolução
- sets e auras
- promo codes com recompensas estruturadas
- submissão de cards/personagens com moderação
- backups versionados
- migrations SQL

### YUKIWAFUS

- anti-farm de mensagens
- atividade real por usuários distintos para spawn
- rate limit por usuário
- cooldown de chat e global
- limpeza de estruturas temporárias
- favoritos/showcase

### Botifyx Catcher

- marketplace com escrow
- expiração segura de trades/duelos/gifts
- economia ligada à coleção

### Seal

- spawn adaptativo por atividade recente
- Golden Hour/event modifiers
- histórico de recompensas para reduzir repetição
- quests/progressão
- pets
- passe
- Redis/hot-path concepts adaptados à infraestrutura Source quando necessário
- scraper/importador com revisão administrativa e deduplicação

## Mídia de personagens

### Formato visual

Toda arte primária nova do Source deve ser apresentada em proporção **2:3**.

O pipeline existente `utils/portrait_image.py` produz JPEG 2:3 e o endpoint `/api/image-proxy?crop=portrait` entrega a versão normalizada.

### Matching

Ordem de correspondência de uma arte importada:

1. `character_id` explícito do Source;
2. alias previamente aprovado;
3. nome normalizado + obra normalizada;
4. nome normalizado apenas quando houver exatamente um resultado;
5. caso contrário: `ambiguous`/`unmatched`, nunca aplicar automaticamente.

### Arte e direitos

O código do upstream segue a licença registrada. Artes de personagens e mídia de terceiros devem possuir origem e crédito/condição de uso rastreáveis separadamente. O importador não presume que a licença do software cobre mídia externa armazenada no banco do upstream.

## Estratégia de migração

### Etapa A — Frontend upstream

Importar e manter o frontend compilável sem ativá-lo em produção.

### Etapa B — Compatibility API

Criar APIs Source compatíveis com as telas importadas, usando PostgreSQL e os serviços existentes.

### Etapa C — Perfil + Coleção

Conectar primeiro dados reais do usuário e coleção atual.

### Etapa D — Galeria + mídia 2:3

Substituir arte por `character_id` sem alterar ownership.

### Etapa E — Economia e progressão

Quests, achievements, exchange, referrals, leaderboards.

### Etapa F — Gacha

Pity, fragments, crafting, sets, duplicates, streaks e reveal.

### Etapa G — Trading/marketplace

Transações atômicas e escrow.

### Etapa H — Pets/Hatchery/Pass

Novos domínios com migrations isoladas.

### Etapa I — Admin

Upload, fila de revisão de arte/personagem, staff, métricas e auditoria.

## Regras de segurança de migração

- nenhuma atualização de arte escreve em `user_card_collection`;
- nenhuma mudança de nome pode alterar `character_id`;
- migrações econômicas precisam ser transacionais;
- imports de arte devem começar em dry-run;
- correspondências ambíguas não são aplicadas;
- toda escrita em massa gera relatório antes/depois;
- frontend novo só substitui o atual depois de smoke tests no Telegram WebView;
- `main` continua protegida por PR + CI durante a fusão.
