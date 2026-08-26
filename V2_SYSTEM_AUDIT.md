# Source Baltigo Bot V2 — auditoria sistêmica viva

Este documento acompanha a refatoração V2 e existe para impedir que recursos, comandos e WebApps se percam entre branches.

## Regra principal da V2

Nenhum texto, botão, recompensa, saldo ou promessa de interface pode existir sem uma implementação correspondente no backend/banco. Nenhum backend deve ficar sem uma entrada de usuário ou uso administrativo documentado. Todo recurso econômico deve ter origem, uso e histórico rastreável.

## Branches analisadas

- `refactor/technical-foundation`: base estabilizada e segura.
- `main`: versão histórica mais completa, usada como fonte para recuperar sistemas perdidos.
- `v2/system-overhaul`: implementação V2 em andamento.

## Achados P0/P1 já confirmados

### Dataset de personagens perdido

Na fundação técnica, `data/personagens_anilist.txt` havia sido reduzido para praticamente vazio, enquanto `main` contém o dataset completo. Isso quebrava silenciosamente cards, favoritos e qualquer sistema dependente de personagens. O blob completo já foi restaurado na V2.

### Daily prometia recurso inexistente

O `daily.py` histórico podia entregar `+1 giro`, mas `database.py` tinha `get_extra_dado()` retornando sempre `0` e `add_extra_dado()` sem implementação. A recompensa existia no texto, não no sistema. Na V2 `spins` é saldo persistido, tem histórico e uso real na roleta.

### Perfil V2 tinha import quebrado que compileall não detectava

`profile_service.py` importava `get_rank` de `level_system.py`, mas a função existente se chama `get_rank_tag`. O arquivo compilava, porém falharia em runtime durante o import da WebApp. Foi corrigido e a V2 ganhou `tests/test_local_import_contracts.py`, que varre imports nomeados entre módulos locais e verifica se o símbolo realmente existe.

### Sistema de mensagens da branch atual estava sem persistência

O novo teste de contratos encontrou 11 imports inexistentes em `commands/messages.py`: fila, entrega, falha, bloqueio, denúncia, configurações e lookup de perfil. O módulo não estava apenas parcialmente incompleto; ele dependia de uma camada inteira removida do `database.py`. A cópia quebrada foi retirada da branch V2 ativa e o sistema permanece preservado na `main` para reconstrução explícita, sem stubs falsos.

### Ranking histórico contém implementações duplicadas

`commands/ranking.py` na `main` define mais de uma vez `_ranking_kb`, `_format_rank_header`, `_build_general_ranking`, `_render_general_ranking` e `_render_ranking`. Em Python, a segunda definição substitui a primeira, deixando uma grande metade do arquivo como código morto. O ranking V2 foi refeito em módulos próprios.

### Loja cobrava por alteração de nickname que não era liberada

A loja histórica cobrava 3 coins por “alterar nickname”. Porém `set_profile_nickname()` bloqueava qualquer perfil que já tivesse nickname (`nickname_locked`), enquanto `buy_nickname_change()` apenas descontava coins e registrava a transação. Não existia ticket, flag, contador nem desbloqueio consumível. Era uma compra que podia cobrar e não conceder benefício algum.

### Venda histórica de personagem é vulnerável a corrida

A venda antiga faz `get_user_card_quantity()` → `remove_card_copy()` → `add_user_coins()` em operações separadas. Duas requisições concorrentes podem observar a mesma última cópia antes da remoção. Loja V2 deve travar wallet + propriedade e executar débito/crédito/ledger no mesmo commit.

### Progresso e remoção de cartas ainda têm read-modify-write legado

Na base atual, `add_progress_xp()` lê XP/nível/ações, calcula em Python e atualiza depois; `remove_card_copy()` lê quantidade e só depois decide UPDATE/DELETE. Locks em memória não resolvem concorrência entre processos/replicas. Esses caminhos precisam ser substituídos por operações transacionais/atômicas antes de captura, loja e sistemas competitivos dependerem deles.

### Spawn histórico pode ser forçado por spam de uma pessoa

`capture_message_handler()` incrementa atividade para praticamente qualquer mensagem de usuário não-bot. O contador do banco é transacional, mas não há cooldown por usuário, diversidade mínima de participantes nem filtro suficiente de spam/comandos. Um único usuário pode gerar mensagens até atingir `CAPTURE_SPAWN_EVERY`. A V2 deve medir atividade válida de grupo, não contagem bruta de mensagens.

### Duelo histórico depende de XCards, não dos cards normais

O duelo da `main` usa `xcards_service`, exige três XCARDs e resolve rodadas por BP. Portanto ele não pode ser “recuperado depois da coleção normal” sem uma decisão prévia sobre XCards/Union Arena. Se XCards forem mantidos, o engine/repository/service são candidatos a reaproveitamento; se forem fundidos/removidos, o duelo precisará de um novo sistema de atributos para cards comuns.

### Sistemas inteiros desapareceram da branch atual

A `main` possui uma superfície funcional muito maior que a fundação técnica. A V2 não deve considerar um sistema removido como “resolvido” sem decisão explícita de recuperar, substituir ou aposentar.

## Matriz de sistemas

| Sistema | `main` histórica | Fundação técnica | Direção V2 |
|---|---|---|---|
| `/start` e onboarding | Sim | Sim | Refatorar navegação e refletir recursos reais |
| Termos/canal obrigatório | Sim | Sim | Manter, modularizar e testar |
| Anime catálogo | Sim | Sim | Manter e padronizar WebApp |
| Manga catálogo | Sim | Sim | Manter e padronizar WebApp |
| Cards catálogo | Sim | Sim | Manter; remover rotas duplicadas e unificar UI |
| `/card` | Sim | Sim | Integrar com coleção/economia/progresso |
| Coleção | Sim (`colecao`, `cccolecao`) | Ausente | Recuperada na V2; continuar aprofundando filtros/detalhes |
| XCards/Union Arena | Sim | Ausente | Decisão obrigatória antes de restaurar duelo |
| XColeção | Sim | Ausente | Depende da decisão sobre XCards |
| Perfil | Sim | Ausente | Recuperado na V2 com identidade canônica |
| Menu do usuário | Sim | Ausente | Substituir por hub V2, não restaurar como ilha |
| Nível/XP | Sim | Sim | Tornar persistência atômica; integrar recompensas/conquistas sem pay-to-win |
| Ranking | Sim | Ausente | V2 criado: geral = progresso + coleção; coins separados; respeita privacidade |
| Daily | Sim, incoerente | Ausente | Refeito na V2 com wallet real e streak |
| Dado | Sim | Ausente | Refeito na V2 com persistência e animação 3D |
| Giro | Só recompensa fantasma | Ausente | Criado como sistema real na V2 |
| Loja | Sim, incoerente | Ausente | Reescrever sobre wallet V2; remover compra fantasma de nickname; transações atômicas |
| Captura/spawn | Sim | Ausente | Reaproveitar persistência/timers; refazer atividade anti-spam e economia |
| Trocas | Sim | Ausente | Reaproveitar swap atômico; validar propriedade na proposta e adicionar expiração |
| Duelo | Sim, baseado em XCards | Ausente | Bloqueado pela decisão de XCards; auditar wager e concorrência antes de portar |
| Memória | Sim | Ausente | Recuperar como minigame com UI V2 |
| Termo anime | Sim | Ausente | Recuperar; depende de `anime_words_365.json` |
| Pedidos | Sim | Sim | Manter; padronizar UI e estados |
| Mensagens privadas/anônimas | Sim | Quebrado/quarentenado | Reconstruir sobre identidade V2 + persistência própria, ou aposentar explicitamente |
| Tutorial de mensagens | Sim | Ausente | Só recuperar se mensagens forem reconstruídas |
| Contribuição de cards | Sim | Ausente | Recuperar com moderação e validação |
| Avisos/broadcast admin | Sim | Ausente | Recuperar com filas, limites e relatório seguro |
| Reset de usuários | Sim | Ausente | Admin-only; revisar escopo/destrutividade |
| Dado admin | Sim | Ausente | Substituir por comandos V2 de wallet/auditoria |
| Spawn admin | Sim | Ausente | Recuperar junto com captura |
| SafeBooru inline | Sim | Ausente | Auditar necessidade, dependência externa e política antes de restaurar |
| BaltigoFlix | Sim | Sim simplificado | Auditar fluxo comercial, webhooks e segurança separadamente |

## Economia V2 já implantada

A V2 introduz `game_wallets` com três recursos canônicos:

- `coins`: moeda geral;
- `dice`: tentativas do sistema de descoberta;
- `spins`: tentativas da roleta.

Toda movimentação relevante entra em `game_ledger`. Daily, dado e giro usam a mesma carteira. A migração importa saldos legados quando as colunas antigas existirem, sem sobrescrever wallets já migradas.

## Daily V2

- um claim por data de São Paulo;
- sequência contínua de 7 dias;
- recompensa sempre composta apenas por recursos que existem;
- atualização transacional da wallet;
- ledger separado por recurso;
- endpoint autenticado exclusivamente por `Telegram.WebApp.initData`.

## Dado V2

- saldo persistido;
- máximo de 24;
- recarga fixa nos horários 01:00, 04:00, 07:00, 10:00, 13:00, 16:00, 19:00 e 22:00 em `America/Sao_Paulo`;
- 1 dado consumido por roll;
- valor de 1 a 6 define a quantidade de obras apresentadas;
- opções vêm apenas de obras com personagens disponíveis no catálogo real;
- roll persistido, com token e expiração;
- usuário só pode escolher obra pertencente ao próprio roll;
- personagem sorteado é gravado em `user_card_collection` na mesma transação de resolução;
- animação 3D é visual; o resultado real vem do servidor.

## Giro V2

- saldo real de `spins`;
- cada giro custa 1;
- resultado é decidido no servidor;
- roleta do frontend apenas anima até o segmento decidido pelo backend;
- prêmio pode creditar coins, dados ou novo giro;
- histórico persistido em `game_spin_history`;
- custo e prêmio entram no ledger.

## Ranking V2

- usa `game_wallets`, `user_progress`, `user_card_collection` e `user_identity_v2` como fontes canônicas;
- perfis privados ficam fora dos placares públicos;
- ranking geral combina percentis de progresso (55%) e coleção (45%);
- coins aparecem apenas em ranking separado de fortuna e não alteram o placar geral;
- Termo e Memória só entram quando seus sistemas V2 existirem novamente;
- API pública para o MiniApp não precisa expor `user_id` dos participantes.

## WebApp V2 — padrão obrigatório

Todos os novos WebApps devem convergir para:

- identidade visual única;
- mobile-first;
- integração com Telegram WebApp;
- identidade do usuário obtida somente do `initData` assinado no backend;
- nenhum `uid` confiado ao navegador;
- rate limit por ação;
- loading, empty state, erro e sucesso explícitos;
- animações suaves e com propósito;
- `prefers-reduced-motion`;
- haptics quando disponíveis;
- mesmas tokens de tipografia, radius, superfícies, espaçamento e motion;
- nenhuma duplicação de HTML/CSS/JS gigantes por rota.

## Dívidas confirmadas ainda abertas

1. `webapp.py` continua monolítico e contém implementações/rotas duplicadas herdadas.
2. `cards_webapp.py` ainda representa uma segunda implementação visual de cards.
3. configuração ainda está espalhada por módulos e variáveis de ambiente.
4. migrações ainda são executadas junto ao startup em partes do projeto.
5. XP e decremento de coleção precisam abandonar read-modify-write legado.
6. loja histórica usa economia legada e contém produto de nickname sem entitlement real.
7. captura precisa trocar contagem bruta de mensagens por atividade válida e usar wallet/progresso V2.
8. trocas precisam de expiração e validação precoce, preservando swap atômico.
9. decisão de XCards é pré-requisito para o duelo atual.
10. sistema de mensagens histórico precisa de decisão de produto e nova camada de persistência.
11. broadcast `/avisar all` histórico faz loop no handler e precisa de estratégia robusta antes de voltar.
12. arquivos administrativos antigos precisam de política única de autorização, auditoria e confirmação para ações destrutivas.
13. o histórico público ainda contém um arquivo de sessão Telegram que precisa ser invalidado operacionalmente.
14. `main/webapp.py` (~346 KB) e `premium_webapp_ui.py` (~240 KB) confirmam duplicação/monólito visual que não deve ser portado inteiro.

## Próxima ordem de execução

1. fechar contratos de runtime/import e operações atômicas fundamentais;
2. concluir ranking V2 e reescrever loja em cima da wallet V2;
3. recuperar captura/spawn com atividade anti-spam e economia V2;
4. recuperar troca com expiração e transação atômica;
5. decidir XCards/XColeção e, a partir disso, portar ou redesenhar duelo;
6. recuperar minigames (`memoria`, `termo`) usando design system V2;
7. auditar contribuições de cards e comandos administrativos esquecidos;
8. reconstruir ou aposentar mensagens explicitamente;
9. auditar BaltigoFlix completo, webhooks, afiliados e pagamentos;
10. refazer visual/arquitetura de catálogo, pedidos e cards;
11. desmontar `webapp.py` legado em routers/services/templates/static;
12. auditoria final de comandos, callbacks, rotas, tabelas, env vars, textos e fluxos;
13. somente então preparar merge/deploy.
