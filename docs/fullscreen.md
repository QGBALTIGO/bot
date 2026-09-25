# Source: fullscreen nativo e áreas seguras

A MiniApp chama `Telegram.WebApp.requestFullscreen()` uma vez na abertura,
antes de renderizar a aplicação, sem aguardar dados de conta. Requer Bot API 8.0+
no cliente. `expand()` sozinho aumenta a janela, mas não ativa fullscreen.

Todas as entradas de `src/native/routes.json` usam o mesmo controlador
`src/telegram/viewport.ts`. Navegar, atualizar dados ou abrir um modal não faz
novos pedidos de fullscreen. A saída manual do usuário é respeitada.
Falhas, versões antigas e bridges sem resposta não bloqueiam a navegação.
Fora do Telegram não é solicitado fullscreen do navegador.

## Layout

O fundo ocupa a tela; o conteúdo respeita, em cada borda,
`max(env(safe-area-inset-*), safeAreaInset.*) + contentSafeAreaInset.*`.
A primeira margem é do sistema (notch/barra de gestos); a segunda é dos controles
do Telegram. Isso evita contar o recorte do sistema duas vezes e reserva espaço
para Fechar/Voltar/menu sem escondê-los ou tentar reposicioná-los.

O root aplica esses limites uma vez. Portais, menu lateral, personagens,
companheiros, recompensas, loading e toasts usam o mesmo retângulo seguro.
`viewportStableHeight` mantém a altura estável; resize do visualViewport só reduz
a área para teclado quando um campo está em edição, não durante pinch zoom.
Eventos nativos atualizam margens/rotação sem recarregar a aplicação.

Existe uma reserva temporária de 56px durante o handshake fullscreen mobile
quando o conteúdo ainda não informou sua margem. Valores reportados, inclusive
zero, substituem essa reserva. Um pedido ignorado não deixa uma espera infinita.

## Verificação reproduzível

- `python -m pytest -q tests/test_fullscreen_viewport.py`
- `cd aninexus_frontend && bun run build`
- `python scripts/verify_fullscreen_browser.py --output /tmp/fullscreen-proof`
- `python scripts/verify_native_browser.py --test --output /tmp/native-proof`

Os testes renderizam o build real com contas/APIs sintéticas; simulam áreas
seguras, teclado, rotação, saída manual e clientes antigos. As capturas com
"TELEGRAM · SIMULAÇÃO" não são capturas de um aparelho Telegram autenticado.
Não representam garantia de suporte em todo cliente ou versão do Telegram.

## Fontes oficiais consultadas em 25/09/2026

- https://core.telegram.org/bots/webapps#initializing-mini-apps
- https://core.telegram.org/bots/webapps#safeareainset
- https://core.telegram.org/bots/webapps#contentsafeareainset
- https://core.telegram.org/bots/webapps#events-available-for-mini-apps
- https://core.telegram.org/api/bots/webapps

Links diretos MiniApp admitem `mode=fullscreen`; o Source utiliza principalmente
botões WebApp e pede fullscreen pela API, cobrindo também URLs históricas sem
modificar parâmetros de autenticação ou de navegação.
