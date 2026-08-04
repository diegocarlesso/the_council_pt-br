# The Council — Localização PT-BR — Visão Geral do Projeto

> Documento de planejamento. Nenhuma string foi traduzida ainda — este é o
> diagnóstico do estado atual e a base para as decisões de processo,
> ferramentas e modelos de IA descritas nos demais documentos desta pasta.

## 1. O que já existe (estado real, verificado em 2026-08-03)

| Item | Status |
|---|---|
| Parser de `.db` (`dump_texts.py`, `list_strings.py`) | ✅ Funcional. Extrai o pool de strings do fim de cada `.db`. |
| Unpacker de `.cpk` (`unpack_cpk.py`) | ✅ Funcional. Extrai `Loca_en_Main_0.cpk` → `Extracted_Loc_En/`. |
| Dump completo do texto em inglês (`localization_dump.json`) | ✅ Gerado. 40.347 strings, 26 arquivos `.db`. |
| Repacker de `.db` → `.cpk` (caminho de volta) | ❌ **Não existe.** Ver [03-RISCOS_TECNICOS.md](03-RISCOS_TECNICOS.md). |
| `glossary.json` | 🟡 Rascunho inicial, 7 termos travados (`locked`). |
| `translation_memory.json` | 🟡 Estrutura definida, 1 entrada de exemplo. |
| Pipeline documentada | 🟡 Só o desenho de alto nível (`pipeline.md`, uma linha). |
| Strings traduzidas | ❌ Zero. |
| Forma de o jogo carregar pt-BR | ❌ Não confirmada (ver riscos). |

Vários arquivos soltos na raiz de `Data/Packages/` (`1.2 Estrutura do JSON`,
`11.1 Pipeline Sugerida`, `3.3 Códigos de Puzzle (Críticos)`, `7.1
\`translation_memory.json`, `7.2 \`glossary.json\` (Extrato Inicial)`) são
lixo de uma sessão anterior do aider: o modelo gratuito usado gerou um
relatório em Markdown com cabeçalhos numerados, e o aider interpretou cada
cabeçalho como nome de arquivo. O conteúdo já está duplicado (corretamente)
dentro de `pt-br/`. Ver [02-FERRAMENTAS_E_TOOLING.md](02-FERRAMENTAS_E_TOOLING.md#lição-aprendida-fragmentação-de-saída)
para a lição tirada disso. Recomendo apagar esses 5 arquivos da raiz quando
você validar — não fiz isso ainda para não mexer em nada sem confirmação.

## 2. Escala real do trabalho

Medido diretamente em `localization_dump.json`:

- **40.347 strings totais**, em 26 arquivos `.db`.
- **21.836 strings únicas** (dedup ratio de **45,9%**) — quase metade do
  texto se repete literalmente (itens de inventário, respostas de diálogo
  reaproveitadas, textos de sistema). Isso confirma que o "Dedup Engine" já
  desenhado no pipeline não é opcional, é o que corta o trabalho pela metade.
- **~202.500 palavras únicas** / **~1.08M caracteres únicos** a traduzir de
  fato (~270k tokens de entrada, estimativa grosseira de 4 chars/token).
- Distribuição por arquivo: a maior parte do volume está nos arquivos de
  quest `q1`–`q17` (`q14_loc_en_0.db` sozinho tem 4.350 strings), mais
  `common_loc_en_0.db` (3.230 strings, provavelmente textos de sistema/UI
  reaproveitados em todo o jogo — bom candidato a traduzir primeiro, já que
  populam o glossário e testam o pipeline com baixo risco de spoiler).
- Também existe conteúdo que **não pode** ser traduzido: sequências de
  puzzle (ex. o baú com `"Change first letter", "I", "Z", "L", "O",
  "Return"` já capturado em `puzzle_codes.md`), placeholders (`%d`, `%s`,
  `%1`, `\n`), tags (`<color>`, `<sprite>`) e comandos internos
  (`|ConvertChestCode(1,4)`). Esses precisam ser **detectados
  automaticamente**, não filtrados manualmente — 40k strings é volume demais
  para revisão manual linha a linha.

## 3. Objetivo deste ciclo de planejamento

Definir, **antes de traduzir uma linha**:

1. Pipeline técnica (extração → tradução → QA → reinjeção) —
   [01-PIPELINE.md](01-PIPELINE.md)
2. Ferramentas e scripts que sustentam cada etapa —
   [02-FERRAMENTAS_E_TOOLING.md](02-FERRAMENTAS_E_TOOLING.md)
3. Estratégia de modelos de IA (aider vs. chamadas diretas de API, quais
   modelos usar para quê, como economizar créditos/limites) —
   [03-MODELOS_IA_E_CUSTOS.md](03-MODELOS_IA_E_CUSTOS.md)
4. Riscos técnicos abertos que podem inviabilizar o projeto se não forem
   resolvidos cedo — [04-RISCOS_TECNICOS.md](04-RISCOS_TECNICOS.md)
5. Convenções de glossário/memória de tradução —
   [05-GLOSSARIO_E_MEMORIA.md](05-GLOSSARIO_E_MEMORIA.md)
6. Roadmap faseado — [06-ROADMAP.md](06-ROADMAP.md)

## 4. Princípios que já estavam certos no prompt original

O prompt que você já vinha usando com o aider (visível em
`.aider.chat.history.md`) está tecnicamente bem pensado — deduplicação,
glossário travado, categorização, validação de placeholders, lotes de
300–500 strings, nomes próprios preservados. O problema não foi o
*conteúdo* do prompt, foi a **ferramenta**: usar um editor de código
(aider) como motor de tradução em massa, com modelos gratuitos instáveis,
sem structured output. Isso é detalhado em
[03-MODELOS_IA_E_CUSTOS.md](03-MODELOS_IA_E_CUSTOS.md).
