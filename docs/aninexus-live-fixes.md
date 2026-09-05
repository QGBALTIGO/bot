# Correções de produção AniNexus

Esta leva corrige regressões observadas na MiniApp em produção e preserva as evoluções de Admin/mídia 2:3 já preparadas na branch.

Correções cobertas por testes:

- compra e cuidado de companheiros com parâmetros PostgreSQL tipados;
- missões de Dado compatíveis com `dice_rolls.created_at` legado em Unix timestamp;
- personagem obtido pelo Dado volta a ser entregue no chat privado após a gravação na coleção, com deduplicação por rolagem;
- tradução pt-BR por frase inteira, sem substituir pedaços de palavras;
- erros HTTP visíveis localizados em português;
- Ranking usa atualização HTTP periódica no runtime atual, sem WebSocket não suportado;
- Perfil e Incubadora com textos principais nativamente em português;
- raridades localizadas e fallback `SEM IMAGEM`;
- cards de Troca com proporção 2:3 explícita e passos exibidos na ordem correta.
