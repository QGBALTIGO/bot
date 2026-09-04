# AniNexus MiniApp

Frontend da MiniApp AniNexus, adaptado para o ecossistema Source Baltigo.

A base visual e componentes derivam do projeto Seal Your Waifu, de bisug, mantendo a atribuição exigida pela licença original em `LICENSE`.

## Fonte de verdade

A MiniApp não mantém uma economia ou coleção paralela. Ela usa os registros existentes do Source:

- personagens e propriedade: `user_card_collection`;
- Coins: `users.coins`;
- nível e XP: `user_progress`;
- Dados: saldo e recargas do sistema de Dado existente;
- ranking: Coleção, Coins, Nível, Termo e Memória existentes;
- XCards: ofertas diárias e coleção já existentes no bot.

## Sistemas AniNexus

A interface integra Dado, Memória Cifrada, Roleta AniNexus, Missões, Temporada, Ranking, Loja, Economia, Trocas, Indicações, Companheiros e Incubadora. Os módulos novos persistem apenas o estado específico que não existia anteriormente, sem substituir IDs de personagens ou a coleção atual dos usuários.

O diretório `aninexus_runtime/` é o build versionado servido em `/menu`. O workflow `AniNexus frontend` recompila `aninexus_frontend/` e falha se o runtime commitado estiver diferente do resultado do build.
