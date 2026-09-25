# Evolução da coleção Source

## Uma aplicação, um saldo e uma autenticação

Esta integração estende o bot existente. Não instala bots de terceiros, não cria um novo frontend, não inicia outra instância de polling e não abre páginas de economia separadas. Todas as telas usam `/menu`, o `App` existente, cabeçalho, menu lateral, componentes compartilhados, autenticação assinada e regras de área segura/fullscreen.

Os recursos novos ficam em `source_features/` e `aninexus_frontend/src/features/collecting/`. O roteador é incluído no FastAPI existente, em `/api/v1_7b82/collecting`. Usa `_require_user`, o mesmo pool PostgreSQL e Coins reais da conta. Não confia em `user_id` recebido no corpo. Pedidos de mutação têm esquemas Pydantic estritos e limites; os tipos de requisição TypeScript são gerados desses esquemas por `scripts/generate_collecting_types.py`. Isso não é uma promessa de tipagem integral de todas as APIs legadas.

## Organização para o jogador

| Área na MiniApp | Implementação |
| --- | --- |
| Desejos e cofre | Lista de desejos, busca por nome/obra/ID, proteção de personagens, duplicatas, preferências e sugestões recíprocas de troca. |
| Meu álbum / Cards | Ações de desejar/proteger integradas; adicionar os personagens que faltam de uma obra aos desejos. |
| Trocas | Prévia de entrega/recebimento, alteração apenas do próprio lado e confirmações vinculadas à versão da proposta. |
| Oficina | Prévia de duplicatas a consumir, fragmentos e cosméticos próprios; equipar o cosmético no perfil existente. |
| Mercado | Anúncios de preço fixo e leilões em Coins, sem dinheiro real, saque ou nova moeda negociável. |
| Disponível agora | Atalhos de resgate diário, dados, propostas aguardando confirmação, incubadora, eventos e anúncios a concluir. Missões possuem atalho, não contagem de recompensas prontas. |
| Presença | Últimos sete dias, sequência real e emblema único ao atingir sete dias consecutivos. Usa o mesmo resgate diário do comando. |
| Eventos | Expedições comunitárias por personagens elegíveis, contribuição diária sem consumir a carta, progresso coletivo e cosmético por meta. |
| Dado | Regras reais e histórico; as probabilidades e recompensas do sorteio não foram alteradas. |
| Identificar anime | Envio voluntário de imagem ao trace.moe com consentimento explícito, normalização da imagem, resultado e acesso ao catálogo. |
| Ajuda | Oito tópicos em português no mesmo aplicativo. |

Atalhos do bot: `/colecionar`, `/cofre`, `/desejos`, `/mercado`, `/oficina`, `/eventos`, `/agora`, `/ajuda`, `/identificar`. São acessos à mesma MiniApp e não implementações paralelas das operações. Os comandos anteriores continuam existindo.

## Proteções e privacidade

- Favorito do perfil, desejado, protegido e reservado são estados distintos. Escolher um favorito continua usando a preferência original da conta.
- Proteção impede saídas de cartas normais também no banco; não depende apenas de desabilitar botões. O favorito é protegido enquanto estiver selecionado.
- Anúncios reservam o personagem. Enquanto o anúncio está aberto, esse personagem não pode ser vendido/reciclado/protegido/favoritado por caminhos concorrentes. A reserva é conservadora por personagem, não um inventário paralelo de cópias.
- A oficina sempre preserva a última cópia. A preferência de preservar uma cópia está ativada por padrão no mercado; a pessoa pode alterá-la conscientemente. Isso não reescreve todas as regras de venda individual legadas.
- Sugestões de troca só incluem pessoas que optaram por descoberta; não expõem a coleção inteira por padrão. Apenas excedentes não protegidos, não favoritos e não reservados entram nas sugestões.
- Vitrine inline está desativada por padrão para cada usuário. O handler só busca a coleção do solicitante autenticado, usa paginação e não envia dados de terceiros.
- O modo inline do Telegram precisa estar habilitado no BotFather (`/setinline`) para o bot. O código não modifica essa configuração da plataforma e a integração não afirma que ela já está habilitada na conta de produção.
- A identificação de cena só envia a imagem depois do consentimento. Limite próprio de 2 MB / 12 MP, reencodificação JPEG, remoção de metadados, no máximo duas solicitações por minuto por usuário. Usa endpoint fixo do provedor, não URLs arbitrárias. Nenhuma foto privada foi enviada para validar os testes.

## Integridade econômica

Anúncios, compras, lances, devoluções, reciclagem e cosméticos usam transações com bloqueios de inventário/conta. Mutação econômica usa chave de operação UUID vinculada a usuário, tipo e conteúdo; repetição após resposta perdida retorna o mesmo resultado, e reutilização com conteúdo diferente é rejeitada.

Preço inicial/compra de lote: 1 a 100.000 Coins; 1 a 20 cópias; prazo de 1 a 72 horas; no máximo dez anúncios ativos por dono. O preço é pelo lote, não uma multiplicação silenciosa por quantidade. Não há taxa nova, pagamentos externos ou conversão em dinheiro real.

Lances reservam Coins, devolvem o lance anterior e, ao elevar o próprio lance, debitam somente a diferença. O vendedor não pode dar lance no próprio anúncio. Leilão com lance não pode ser cancelado unilateralmente. Perto do fim há extensão de dois minutos limitada ao prazo original mais dez minutos. Encerramento transfere carta/Coins uma vez; o worker do bot conclui lotes de anúncios vencidos. Participantes também podem pedir conclusão após o prazo. Falha no histórico reverte movimentações.

Propostas de troca recebem `revision`, confirmação do remetente e do destinatário. Alterar o próprio lado incrementa a revisão e limpa ambas as confirmações. A confirmação usa a revisão exata. Botões legados sem revisão só são aceitos na versão inicial; não aprovam uma proposta alterada. A oferta inicial criada pelo remetente já constitui sua confirmação inicial, conforme o fluxo anterior.

## Administração de eventos

Somente a permissão administrativa existente permite preparar rascunhos e publicar. Eventos são dados validados (texto, IDs do catálogo, início/fim, meta e limite diário), não scripts executáveis. Publicação exige uma confirmação separada; o rascunho não aparece para jogadores comuns. Prazo máximo de trinta dias; personagem contribuído precisa pertencer ao jogador; limites e repetição são validados no servidor. Recompensa é cosmética e só participantes elegíveis a recebem uma vez.

Este primeiro sistema é comunitário/global. Não cria alianças/guildas, combate em tempo real ou uma nova engine de raids. O administrador precisa preparar/publicar eventos; nenhum evento real foi criado automaticamente no deploy. Não há sistema de pity ativado: mudar probabilidades permanece uma decisão econômica separada.

## Migração e implantação

`migrations/001_collecting.sql` é aditiva e registrada em `source_feature_migrations`, sob bloqueio de inicialização. Não remove coleções nem altera saldos existentes ao publicar. Acrescenta tabelas, índices, verificações e colunas de revisão às trocas. Os dois serviços existentes executam a inicialização de forma coordenada. Não usar as credenciais sintéticas dos testes em produção.

O deploy deve acontecer somente depois de build, testes PostgreSQL e regressões de navegador aprovados. Após publicar, verificar `/health`, `/menu`, versão do frontend e inicialização do worker de mercado. Testes econômicos permanecem no banco descartável.

Rollback exige compatibilidade com anúncios e lances já existentes. Não apagar tabelas ou reservas para voltar uma versão. Preservar a rotina de encerramento/devolução de escrow e a proteção no banco; caso haja incidente, fazer uma correção compatível e validar os saldos antes de desativar operações. Operações administrativas de exclusão/reset da conta não podem destruir escrow ativo.

## Testes efetivamente executados

Primeira validação: GitHub Actions `36197532609`. Os 400 testes Python e 28 cenários transacionais anteriores passaram. Os testes novos encontraram ambiguidade de busca numérica por ID e atraso visual em preferências. Ambos foram corrigidos; também foram melhoradas a consulta de sugestões recíprocas e a quebra das opções de coleção em tela estreita.

Segunda validação: GitHub Actions `36198239826`, artefato `10891720877` (`source-collecting-proof`), fonte de aplicação `954af08cf35ad4598d228adddbce72f47694a393`. Todos os gates aprovados:

- 400 testes Python.
- 28 cenários PostgreSQL existentes e 30 cenários novos de proteção, concorrência, rollback, mercado, leilões, trocas, calendário, eventos, privacidade e APIs.
- 32 verificações das oito telas novas em 320/390/768/1280 pixels e oito fluxos interativos.
- Regressões existentes: 165 verificações nativas/12 fluxos; 87 de fullscreen/10 fluxos; 20 cenários de perfil e edição/persistência/remoção do favorito; 50 verificações de entrada única/três fluxos.
- Tipos gerados, lint crítico, build e igualdade fonte/runtime. Agent-browser sobre o build compilado, com captura revisável.

A PR acompanha verificações finais adicionais. `source-collecting-regression.yml` mantém a bateria nova no CI e acrescenta os fluxos de leilão, autoria/revisão de eventos, reconfirmação de troca, falha de servidor e reversão de preferência rejeitada. A existência do script não equivale a aprovação: conferir o resultado da execução na PR.

Navegador usa APIs, SDK, contas e imagens sintéticos. PostgreSQL é real, mas descartável (`source_audit`); os scripts recusam banco de produção. Não houve compras, lances, criação de eventos, redefinições de usuários ou alterações nas coleções reais durante testes. Não houve teste de carga de produção nem validação em todos os aparelhos Telegram. A pesquisa inspirou funcionalidades; não foram incorporados motores de bots GPL/AGPL ou código remoto de terceiros.
