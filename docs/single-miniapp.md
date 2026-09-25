# Uma única MiniApp do Source

Todos os botões usam `utils.miniapp_links.miniapp_url` e a mesma URL HTTPS `/menu`.
A seção é um fragmento de navegação, não um frontend separado. IDs de usuário
não entram nos novos links; a autenticação continua exigindo initData assinado.
`SOURCE_MINIAPP_URL` prevalece sobre os endereços históricos. Configure-a com
`https://bot-production-1980.up.railway.app/menu` neste ambiente de produção.

O bot sincroniza o botão de menu padrão do Telegram na inicialização e corrige
overrides privados conforme os usuários voltam a conversar. Isso não consulta
banco, não envia mensagens e não espera rede no fluxo do comando. A fila tem
limite, deduplicação, duas operações concorrentes e pausa em falha. Na saída,
tarefas são canceladas. A confirmação via getChatMenuButton é registrada sem
expor tokens ou os parâmetros de URLs antigas.

Links históricos no mesmo serviço redirecionam para `/menu`, preservando a seção,
busca, obra e os dados assinados. Só rotas HTML explícitas do manifesto são
redirecionadas. APIs, pagamentos e webhooks não são alterados. O frontend também
normaliza aliases com replaceState, sem abrir outra janela ou acrescentar uma
entrada falsa ao histórico. O HTML e o diagnóstico de versão não são armazenados
em cache; JS/CSS com hash continuam usando cache immutable.

Cada build inclui `ui-version.json`, com hash determinístico do frontend. Ao
retomar uma MiniApp, uma consulta pública leve verifica a versão, no máximo uma
vez por minuto e sem consultar /me. Uma versão antiga gera um aviso de atualização.
Não há recarga automática que possa interromper uma compra, jogo ou formulário.

Uma janela que já estava aberta antes desta correção não pode receber código
novo sem recarregar. É necessário fechá-la uma vez. O Telegram controla suas
janelas minimizadas: não existe aqui tentativa de fechar outras janelas ou
promessa de reaproveitar uma instância nativa entre lançamentos independentes.
O botão "Abrir aplicativo" de uma Main Mini App configurado no BotFather é uma
configuração separada do MenuButton e não é alterado por setChatMenuButton.

## Verificação

- `pytest -q tests/test_single_miniapp.py tests/test_native_webapps.py`
- `python scripts/verify_single_miniapp_browser.py --output /tmp/single-miniapp`
- Regressões anteriores de perfil, fullscreen e navegação permanecem ativas.

Os testes de navegador usam APIs e identidade sintéticas; não fazem transações
em contas reais. Consultas de verificação de produção são GET/HEAD públicos.

Fontes: https://core.telegram.org/bots/api#setchatmenubutton e
https://core.telegram.org/bots/webapps#launching-mini-apps-from-the-menu-button
