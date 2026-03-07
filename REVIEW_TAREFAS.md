# Revisão rápida da base e tarefas sugeridas

Abaixo estão 4 tarefas objetivas, cada uma mapeada para um tipo de problema pedido.

## 1) Tarefa de correção de erro de digitação (typo)

**Problema encontrado**
- O identificador do canal padrão aparece como `@SourcerBaltigo` em múltiplos pontos, enquanto o naming do projeto e do bot usa `Source Baltigo`.
- Isso indica provável typo no handle padrão (`Sourcer` vs `Source`).

**Tarefa sugerida**
- Padronizar o handle padrão para `@SourceBaltigo` e a URL para `https://t.me/SourceBaltigo` em todos os pontos de configuração.
- Fazer uma varredura para garantir consistência de branding em mensagens/ENV docs.

**Critério de aceite**
- Nenhuma ocorrência de `@SourcerBaltigo` permanece no código.
- Defaults de `REQUIRED_CHANNEL` e `REQUIRED_CHANNEL_URL` ficam consistentes com o nome oficial.

---

## 2) Tarefa de correção de bug

**Problema encontrado**
- O `CATALOG_PATH` padrão em `webapp.py` é `catalogo_enriquecido.json`, mas o arquivo no repositório está em `data/catalogo_enriquecido.json`.
- Em ambiente sem `CATALOG_PATH` configurado, o catálogo pode iniciar vazio por não encontrar o arquivo.

**Tarefa sugerida**
- Alterar o default de `CATALOG_PATH` para `data/catalogo_enriquecido.json`.
- Adicionar log claro de fallback/erro quando o caminho não existir.

**Critério de aceite**
- Com ambiente “limpo” (sem `CATALOG_PATH`), o catálogo carrega dados reais.
- Endpoint de catálogo retorna itens sem exigir configuração adicional.

---

## 3) Tarefa para comentário/discrepância de documentação

**Problema encontrado**
- O cabeçalho de `webapp.py` contém comentário provisório (`SUBSTITUIR TUDO`) e instruções de ENV que não refletem completamente defaults atuais (ex.: caminhos em `data/` usados por outros catálogos).
- Isso reduz confiabilidade da documentação inline.

**Tarefa sugerida**
- Reescrever o bloco de comentário inicial para um “mini-README” fiel ao comportamento atual.
- Incluir tabela curta de variáveis obrigatórias vs opcionais com defaults reais.

**Critério de aceite**
- Comentário do topo do arquivo está alinhado às variáveis e paths realmente usados no código.
- Um novo colaborador consegue subir a app apenas lendo esse bloco + README.

---

## 4) Tarefa para melhorar teste

**Problema encontrado**
- Não há suíte de testes automatizados para funções de regra de negócio centrais (ex.: `normalize_media_title`, `build_progress_bar`, `get_rank_tag`).

**Tarefa sugerida**
- Criar suíte inicial com `pytest` para utilitários puros:
  - `database.normalize_media_title`
  - `level_system.get_rank_tag`
  - `level_system.build_progress_bar`
  - `level_system.format_rank_position`
- Cobrir casos de borda (acentos/pontuação, limites de nível, `current > total`, `pos <= 0`).

**Critério de aceite**
- Pipeline local roda `pytest` com sucesso.
- Testes garantem comportamento estável para regras de normalização e progressão.

---

## O que você pode fazer agora para melhorar (plano prático)

Se você quiser sair do “diagnóstico” e ir para execução, siga nesta ordem:

1. **Abra 4 issues separadas** (uma por tarefa) usando os critérios de aceite acima.
2. **Corrija primeiro o bug do `CATALOG_PATH`** (impacto funcional imediato).
3. **Corrija o typo de canal** para evitar configuração errada em produção.
4. **Atualize comentário/documentação** para reduzir dúvidas de quem vai manter o projeto.
5. **Crie a suíte inicial de testes** e configure para rodar em todo PR.

### Definição de prioridade sugerida
- **P1 (hoje):** bug do `CATALOG_PATH`.
- **P2 (hoje):** typo de `@SourcerBaltigo`.
- **P3 (esta semana):** documentação/comentários.
- **P4 (esta semana):** testes automatizados mínimos.

### Checklist de qualidade para cada PR
- [ ] alteração pequena e focada (1 assunto por PR);
- [ ] critério de aceite validado manualmente;
- [ ] se afetar comportamento, incluir/ajustar teste;
- [ ] atualizar docs quando mudar default de ENV;
- [ ] descrever risco e rollback no texto do PR.

### Métrica simples para saber se melhorou
- **Confiabilidade:** catálogo carrega sem ENV extra.
- **Manutenibilidade:** menos dúvidas por comentário desatualizado.
- **Segurança de mudança:** cobertura de testes para regras críticas.
- **Operação:** menos erro humano por typo de configuração.
