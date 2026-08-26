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
| Coleção | Sim (`colecao`, `cccolecao`) | Ausente | Recuperar como sistema V2 único |
| XCards/Union Arena | Sim | Ausente | Avaliar separadamente; dataset muito grande |
| XColeção | Sim | Ausente | Depende da decisão sobre XCards |
| Perfil | Sim | Ausente | Recuperar; centralizar identidade/privacidade/favorito |
| Menu do usuário | Sim | Ausente | Substituir por hub V2, não restaurar como ilha |
| Nível/XP | Sim | Sim | Integrar com recompensas e conquistas sem pay-to-win |
| Ranking | Sim | Ausente | Recuperar em cima de métricas V2 explícitas |
| Daily | Sim, incoerente | Ausente | Refeito na V2 com wallet real e streak |
| Dado | Sim | Ausente | Refeito na V2 com persistência e animação 3D |
| Giro | Só recompensa fantasma | Ausente | Criado como sistema real na V2 |
| Loja | Sim | Ausente | Recuperar depois de estabilizar economia |
| Captura/spawn | Sim | Ausente | Recuperar; revisar concorrência, abuso e economia |
| Trocas | Sim | Ausente | Recuperar com transação atômica e expiração |
| Duelo | Sim | Ausente | Recuperar após coleção; engine/repository/service existem na `main` |
| Memória | Sim | Ausente | Recuperar como minigame com UI V2 |
| Termo anime | Sim | Ausente | Recuperar; depende de `anime_words_365.json` |
| Pedidos | Sim | Sim | Manter; padronizar UI e estados |
| Mensagens privadas/anônimas | Sim | Incompleto/desativado | Reconstruir ou aposentar explicitamente |
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
5. operações legadas de coleção/economia precisam ser comparadas com a nova wallet antes de serem reativadas.
6. sistema de mensagens histórico precisa de decisão de produto e nova camada de persistência.
7. perfil histórico possui antiflood/locks próprios, duplicando infraestrutura global.
8. broadcast `/avisar all` histórico faz loop síncrono no handler e precisa de estratégia robusta antes de voltar.
9. arquivos administrativos antigos precisam de uma política única de autorização, auditoria e confirmação para ações destrutivas.
10. o histórico público ainda contém um arquivo de sessão Telegram que precisa ser invalidado operacionalmente.

## Próxima ordem de execução

1. fechar Game Center V2 com integração/smoke tests;
2. criar núcleo de perfil e coleção V2;
3. recuperar ranking/loja em cima do núcleo novo;
4. recuperar captura/spawn/troca/duelo com transações atômicas;
5. recuperar minigames (`memoria`, `termo`) usando design system V2;
6. decidir XCards e mensagens;
7. desmontar `webapp.py` legado em routers/services/templates/static;
8. trocar `/start` por um hub coerente com a V2;
9. auditoria final de comandos, callbacks, rotas, tabelas, env vars e textos;
10. somente então preparar merge/deploy.
