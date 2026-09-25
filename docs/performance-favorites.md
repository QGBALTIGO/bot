# Source: desempenho, controles e favorito (25/09/2026)

## Evidência inicial

Amostra dos logs de produção, não um percentil ou benchmark controlado:
`/api/v1_7b82/me` levou 6,06–6,38 s; `/api/collection/state`, 3,96 s;
`/api/v1_7b82/source-shop`, 1,96–2,59 s. Cada abertura nova ainda fazia
`/me` sem sessão, depois `secure_init` e outro `/me`.

## Correções

- Uma leitura conjunta de usuário, nível e preferências; o snapshot da coleção
  não é reconstruído duas vezes para a mesma resposta.
- Pets e ovos do perfil são lidos juntos. Leituras de preferências e progresso
  não fazem INSERT repetidamente; contas novas continuam sendo inicializadas.
- Atualizar o favorito não espera a recarga de `/me`, loja e todos os catálogos.
  O estado confirmado do favorito é aplicado no perfil e no cache de preferências.
- A autenticação inicial é compartilhada e antecede a primeira consulta de perfil.
- O carregamento inicial termina ao receber os dados, sem aguardar a animação.
  Dados já carregados não somem durante atualização do cache.
- Conversões de imagens do bot e recortes de retratos do WebApp são executados
  fora do event loop. O registro de XP passa a ser uma tarefa rastreada pelo PTB,
  após a validação de termos, canal e limite de requisições.
- JS/CSS com hash usam cache imutável; HTML permanece revalidável e APIs privadas
  não recebem cache público. A animação do Dado sobrepõe, em vez de somar, a espera da rede.
- Botões permitem quebra de texto, imagens mantêm proporção, ações de cards ficam
  alinhadas ao rodapé, e diálogos respeitam a área segura e a altura disponível.

## Favorito

Configurações → Personagem favorito → Escolher/Alterar. O seletor mostra somente
personagens da coleção, com busca, imagens e carregamento em lotes. A seleção
salva em `user_profile_settings.favorite_character_id`, o mesmo campo lido pelo
comando `/perfil`. O painel mostra o destaque e permite voltar diretamente à
configuração. O álbum continua permitindo definir o mesmo favorito.

A remoção exige `character_id: null` explícito; ID inválido não apaga nada.
O servidor verifica a identidade assinada e a posse atual antes de gravar.

## Validação e limites

`tests/test_source_performance_favorites.py` cobre a seleção/remoção, autorização,
contagem de consultas, preservação da carteira no upsert de identidade, recorte
fora do event loop e cache dos assets. `scripts/verify_native_browser.py` exercita
as rotas nativas, favorito e persistência, abertura inicial e tamanhos móveis/desktop
com respostas sintéticas. Não faz compras ou mutações em contas de produção.

O workflow de CI executa também a suíte completa e compila novamente o frontend.
As medições com fixtures não representam a latência real de rede/Telegram/PostgreSQL.

O serviço Railway executa o WebApp; uma instância separada de `python bot.py`
precisa carregar este commit para receber as correções dos comandos.
