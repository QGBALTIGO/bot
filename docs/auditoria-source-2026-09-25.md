# Auditoria do Source — 25/09/2026

## Escopo e evidência

Repositório: QGBALTIGO/bot. Base de produção: `253f4ddd0a72dd4d1a83fb5712db1a10fd40635d` (PR #66). Fonte corrigida e compilada: `9d945b78572778face85a6ab8d511e812e9cee78`.

Validação completa: GitHub Actions `36187224642`, artefato `source-deep-audit-proof` (`10886298424`). Todos os gates executados terminaram com sucesso. A integração/publicação é acompanhada na PR, separadamente desta evidência de laboratório.

Os testes com saldo, cartas e pagamentos internos usaram exclusivamente um PostgreSQL descartável chamado `source_audit`, com identidades sintéticas. Os scripts recusam endereços de banco de produção. Transportes externos são bloqueados nos testes de comandos e HTTP. Não foram feitas compras, retiradas de cartas, resets ou alterações em contas reais.

## Resultado mensurado

| Verificação | Resultado e limite |
|---|---|
| Inventário estático | 124 arquivos Python, 1.438 funções, 160 declarações de rotas, 62 registros de comandos, 20 registros de callbacks e 23 módulos de páginas frontend. Inventariar não significa executar todos os caminhos. |
| Testes Python | 359 aprovados; dois avisos de depreciação de ferramentas de teste, sem falha. |
| Cobertura da suíte Python | 4.675 de 14.932 instruções, 31,31%. Os scripts de integração e testes de navegador são execuções separadas, não somados artificialmente a essa cobertura. |
| HTTP real da aplicação em laboratório | 487 requisições, 144 pares distintos de método/rota; autenticação ausente, inválida, válida sintética e campos malformados. Zero respostas 500 após as correções. Isso não prova que todos os cenários de cada rota foram executados. |
| Comandos registrados | 124 casos: cada um dos 62 registros sem argumentos, em privado e supergrupo. 120 responderam, quatro foram bloqueados silenciosamente pela política existente de grupos; zero exceções não tratadas. Não representa todos os argumentos nem operações administrativas destrutivas. |
| Callbacks | 40 casos negativos em 20 registros: dados inválidos e identificadores inexistentes/de outro dono; todos reconheceram o acionamento. Não equivale a todos os fluxos positivos. |
| Concorrência e rollback | 28 cenários aprovados em PostgreSQL real descartável, incluindo saldo, loja, recompra, trocas, nickname, energia, companheiros, ovos e dica do Termo. |
| Navegador — telas nativas | 165 verificações de entrada/layout e 12 fluxos, aprovados. |
| Navegador — tela cheia | 87 verificações e 10 grupos de fluxos, aprovados. |
| Navegador — perfil | 20 cenários e fluxo de troca/persistência/remoção de favorito, aprovados. |
| Navegador — aplicativo único | 50 verificações de entrada e três fluxos de navegação/aviso/atualização, aprovados. |
| Imagens externas | Duas verificações de imagem pública e TLS, incluindo caminho alternativo HTTP/1 com endereço fixado. Não verifica todas as imagens do catálogo. |
| Dependências | `pip-audit` e `bun audit` concluíram sem avisos conhecidos no conjunto corrigido consultado. Isso não prova ausência de vulnerabilidades desconhecidas. |

Distribuição HTTP final: 114 respostas 200, 72 redirecionamentos 307, 39 respostas 400, 198 respostas 401, sete 403, quatro 404, 33 respostas 409, quatro 410, nove 422, uma 429 e seis 503. Rejeitar pedidos inválidos/não autenticados é esperado; não é erro só por não retornar 200.

Os seis 503 correspondem a duas rotas internas (`/api/cards/reload` e `/api/channel/selftest`) em três formas de autenticação, com o segredo interno deliberadamente não configurado no laboratório. É bloqueio seguro de configuração, não evidência de indisponibilidade pública de produção.

## Correções de segurança e integridade

### Loja, Coins, dados e recompra

Vendas, crédito, registro de recompra e histórico passaram a compor uma única transação. Requisições concorrentes não podem vender uma única cópia repetidamente ou deixar crédito sem remoção da carta. Falha na escrita do histórico reverte a operação.

A recompra verifica o dono, o prazo e o saldo sob bloqueio, consome o direito à recompra uma única vez e atualiza carta/saldo/histórico juntos. O caminho antigo e a MiniApp usam a mesma implementação.

A compra de dados calcula a recarga natural antes da cobrança, respeita saldo e capacidade e serializa pedidos concorrentes. A inicialização de dados para usuário novo também foi protegida contra criação concorrente.

### Trocas e nickname

O comando de troca e o WebApp compartilham a mesma transação e bloqueios de inventário em ordem estável. A aceitação verifica posse e destinatário; trocas rejeitadas ou expiradas não voltam a ser válidas. Cartas reservadas não são vendidas pelo caminho da loja. Entrega incompleta reverte a transação.

A escolha gratuita e a alteração paga de nickname coordenam a unicidade sem distinção entre maiúsculas e minúsculas. Requisições vazias não cobram; duas solicitações simultâneas não duplicam o benefício gratuito.

### Jogos, companheiros e ovos

A criação simultânea de uma partida não consome energia duas vezes para a mesma sessão. Recompensas permanecem vinculadas ao dono e não são creditadas de novo ao repetir a conclusão. Foram corrigidos parâmetros SQL sem tipo explícito em registros JSON do histórico.

Compras/ativação/cuidados de companheiros e incubação/venda/eclosão de ovos compartilham bloqueios por usuário. A validação cobre cooldown, posse, uma única utilização e disputa por uma mesma vaga de incubação.

### Dica do Termo

O caminho anterior debitava Coins sem verificar o resultado da cobrança. Agora a compra da dica verifica saldo, dono, modo diário, estado e prazo da partida, e faz débito e histórico na mesma transação. Uma partida só é cobrada uma vez, inclusive com requisições simultâneas. Falha no histórico não deixa débito parcial. Saldo insuficiente não libera a dica.

Nos logs de produção anteriores à correção foi observado `Query is too old` em `commands/termo.py`. O callback agora trata especificamente consultas expiradas/identificadores de consulta inválidos antes de realizar mudanças. Outros erros não são mascarados por um `except` genérico.

## Erros de validação e respostas

Foram reproduzidos dois erros HTTP 500 com entrada inválida: identificador de personagem em contribuição de imagem e tempo/movimentos no jogo da memória. Depois da correção, dados malformados são rejeitados como erro de entrada, sem exceção interna.

A validação de inteiros diferencia booleanos, decimais, listas, objetos e valores excessivos de inteiros válidos. Outros endpoints auditados também usam a validação compartilhada. URLs de imagens malformadas são rejeitadas com mensagem apropriada.

Callbacks de coleção, coleção especial e navegação de cards tratam identificadores malformados em vez de encerrar com exceção. O frontend passou a aproveitar a mensagem de erro fornecida pela API, incluindo o campo `detail`, evitando respostas genéricas em casos conhecidos.

## Desempenho e experiência

Consultas de banco em caminhos de comandos como loja, dado e callbacks do Termo foram transferidas para execução fora do loop principal. Isso evita que a espera síncrona dessas consultas bloqueie outras respostas; não representa uma redução percentual de latência medida em aparelhos reais.

O proxy de imagens possui cache curto com limite de memória, limite de entradas, compartilhamento de requisições simultâneas para a mesma imagem e limite de concorrência. Erros não são armazenados como imagens válidas. O objetivo é evitar downloads duplicados sem cache ilimitado.

As opções Companheiro e Incubadora no perfil pareciam clicáveis, mas não tinham ação. Agora abrem as respectivas telas e respondem também ao teclado. O perfil mantém favorito integrado, título da conta, passe e experiência.

O cálculo de experiência passou a apresentar o progresso dentro do nível em vez de comparar o total acumulado da conta com uma meta relativa. Saldo, nível e histórico não são reescritos para corrigir a apresentação.

O contrato de uma única MiniApp foi preservado após a atualização do FastAPI: `/menu` serve o frontend compilado e as 24 entradas históricas redirecionam. A adaptação considera roteadores incluídos que agora podem ser resolvidos de forma adiada. Fullscreen, áreas seguras, favorito e aviso de nova versão passaram nas regressões.

A sincronização do menu persistente ganhou registro de escopo nas falhas e nova tentativa do menu padrão em interação posterior. Mensagens de sincronização bem-sucedida deixaram de ser registradas como erro.

Métricas de produção consultadas nesta retomada, janela de três horas: pico de memória aproximado de 0,187 GB no serviço do bot e 0,270 GB no WebApp, ambos com limite de 8 GB; CPU amostrada também permaneceu baixa. Não há sinal de saturação de CPU/RAM nesse intervalo. Isso não exclui lentidão de banco, rede, serviços externos ou eventos entre amostras.

## Proxy de imagens e dependências

O proxy valida destinos públicos e fixa o endereço aprovado durante a conexão, preservando Host e validação TLS. Cada redirecionamento passa por nova validação. Há limites de tamanho e de redirecionamentos; HTML/SVG não são aceitos como imagem nesse caminho. A resposta usa proteção contra interpretação de conteúdo com tipo diferente do declarado. Essa revisão é específica do proxy; não deve ser apresentada como auditoria completa de todos os acessos externos do projeto.

Versões adotadas: FastAPI 0.141.1, Starlette 1.6.0, Pillow 12.3.0 e cryptography 50.0.1. A resolução dos requisitos anteriores retornou 29 identificadores únicos de avisos conhecidos, distribuídos em Pillow, cryptography e Starlette. Foram deduplicados os identificadores repetidos pelo scanner. Aviso em dependência não significa exploração comprovada no bot. No conjunto corrigido o scanner não retornou avisos conhecidos na consulta realizada.

## O que não foi escondido ou chamado de resolvido

1. Os quatro casos sem resposta foram `/cards`, `/ranking`, `/memoria` e `/memory` em supergrupo, por política explícita do `gatekeeper`; no privado responderam. A regra não foi desativada para fazer o relatório ficar verde. Uma mensagem orientando abrir no privado é uma melhoria de experiência ainda pendente.
2. A cobertura da suíte Python é 31,31%, não 100%. As 1.438 funções foram inventariadas, mas não foi demonstrada a execução de todos os ramos de cada uma.
3. Navegador usou o build real com contas, imagens, SDK e APIs sintéticas. Não equivale a uma sessão autenticada em todos os aparelhos Telegram.
4. Confirmações reais de pagamento, provedores externos, permissões reais em canais/grupos, migração/restauração de backup e operações destrutivas de administrador não foram acionadas em produção.
5. Não foi executado teste de carga destrutivo em produção. Tempos do banco descartável e do navegador com fixtures não são latências de clientes reais, nem estimativa de capacidade para milhares de usuários.
6. A validação de placares da memória ainda recebe tempo/movimentos do cliente. Tipagem, limites e posse não constituem sozinhos um sistema completo contra automação ou trapaça; sessões emitidas pelo servidor e validação temporal mais forte continuam recomendadas.
7. A revisão de textos e retornos foi pontual, nos caminhos alterados. Não houve revisão linguística integral de cada mensagem, tradução ou vírgula do acervo.
8. Dois avisos de depreciação de ferramentas de teste permanecem registrados; não foram suprimidos para aparentar ausência de avisos.

## Regressão permanente

`source-security-regression.yml` executa testes Python, transações reais em PostgreSQL descartável, entradas HTTP/comandos/callbacks e verificação de avisos conhecidos de dependências. Falhas impedem sucesso do job. O workflow existente de MiniApps continua responsável pelos testes de build e navegador. Workflows temporários de recuperação foram removidos.

Documentação técnica consultada: Telegram Mini Apps (validação de initData e eventos), notas oficiais do FastAPI (roteadores incluídos) e guias OWASP de SSRF e cabeçalhos HTTP. Resultados específicos do Source vêm dos artefatos de teste e da inspeção do código, não dessas referências gerais.
