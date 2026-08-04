# Pipeline de Localização — PT-BR

Evolução do desenho de uma linha em `pipeline.md`:

```
JSON Source → Parser → Dedup Engine → TM Lookup → Glossary Enforcement →
Translator → Reviewer → QA Validator → JSON Target
```

para um fluxo com donos, ferramentas e critérios de saída em cada etapa.

## Etapa 0 — Extração (já feita)
- `unpack_cpk.py` extrai os `.cpk` para pastas.
- `dump_texts.py` varre os `.db` e gera `localization_dump.json`
  (`{arquivo: {pool_start, pool_size, file_size, string_count, strings: [{index, pool_offset, original, translation}]}}`).
- **Saída**: um único JSON, já versionável, com `translation: ""` para tudo.

## Etapa 1 — Pré-processamento (a construir)
Um script novo (`preprocess.py`) que roda **uma vez** sobre o dump e produz:

1. **Deduplicação**: mapa `string_original → id_canônico`. Hoje 40.347 →
   21.836 únicas. Traduz-se só o canônico; todas as ocorrências idênticas
   herdam a tradução.
2. **Detecção de não-traduzível**: regex/heurística para
   - placeholders: `%d`, `%s`, `%1`, `%2`, `\n`, `\t`, `\r`
   - tags: `<color=...>`, `</color>`, `<sprite ...>`
   - comandos: `|ConvertChestCode(1,4)` e similares (padrão `|Nome(args)`)
   - sequências de puzzle (strings curtas tipo `"I"`, `"Z"`, `"Return"` em
     contexto de baú/código — já mapeadas em `puzzle_codes.md`, mas o
     script deve generalizar a detecção, não hardcodar só esse baú)
   - nomes próprios da lista travada em `glossary.json`
   Cada string ganha uma flag `translatable: bool` e, se não traduzível,
   `reason`.
3. **Categorização automática**: UI / Diálogo / Item / Descrição / Puzzle /
   Sistema / Conquista, por heurística de arquivo de origem + padrões de
   texto (ex.: `common_loc_en_0.db` → majoritariamente Sistema/UI;
   `q*_loc_en_0.db` → majoritariamente Diálogo/Narrativa).
4. **Extração de termos candidatos a glossário**: frequência de
   substantivos/expressões capitalizadas que se repetem (nomes de
   habilidades, organizações, itens-chave) — gera uma lista de sugestões
   para você revisar e travar manualmente, não um glossário automático sem
   curadoria.

**Saída**: `preprocessed.json` (mesmo shape do dump + campos `translatable`,
`reason`, `category`, `canonical_id`) e `glossary_candidates.json`.

## Etapa 2 — TM Lookup + Glossary Enforcement
Antes de qualquer chamada de IA:
- Toda string cujo texto já existe em `translation_memory.json` com
  `status: "approved"` é preenchida direto, sem gastar tokens.
- O glossário travado (`locked: true`) é injetado no prompt de cada lote
  como restrição, não como sugestão — o validador da Etapa 4 rejeita lotes
  que desobedecerem termos travados.

## Etapa 3 — Tradução em lote (IA)
- Lotes de 300–500 strings **únicas e traduzíveis**, agrupadas por
  categoria/arquivo (não misturar diálogo de quest com texto de UI no
  mesmo lote — contexto diferente, glossário parcialmente diferente).
- Cada lote é uma chamada de API com **saída estruturada** (JSON
  schema/function calling), não edição de arquivo via aider. Detalhes de
  qual modelo usar em
  [03-MODELOS_IA_E_CUSTOS.md](03-MODELOS_IA_E_CUSTOS.md).
- Prompt de sistema fixo, versionado em
  `pt-br/prompts/translation_system_prompt.md` (a extrair do que já está em
  `.aider.chat.history.md` — o conteúdo já é bom, só precisa parar de ser
  redigitado a cada sessão).

## Etapa 4 — QA automática (por lote, antes de aceitar)
Script `validate_batch.py` roda em cima da resposta da IA antes de gravar em
`translation_memory.json`:
- placeholders/tags/comandos idênticos aos do original (mesma contagem,
  mesma ordem)
- nenhuma string vazia onde o original não era vazio
- termos travados do glossário respeitados (comparação literal)
- sem crescimento de tamanho anormal (heurística: pt-BR costuma ficar
  ~15–20% mais longo que en; flag se um item específico passar de ~40%)
- encoding válido (UTF-8), sem caracteres de controle estranhos

Lotes que falham QA voltam para retradução (não vão para revisão humana
quebrados — poupa seu tempo).

## Etapa 5 — Revisão humana
- Você (ou revisores externos, se trouxer colaboradores) aprova/edita
  lote a lote. Aprovado → `status: "approved"` na TM, o que já propaga para
  todas as ocorrências duplicadas.
- Correções da revisão são a fonte mais valiosa de feedback: idealmente
  viram exemplos few-shot para os próximos lotes do mesmo tradutor/IA.

## Etapa 6 — Reinjeção
- Merge de `translation_memory.json` aprovada de volta no
  `preprocessed.json` → gera `localization_pt-br.json` completo.
- Repack `.json` → `.db` → `.cpk`. **Esta etapa não existe ainda como
  ferramenta e é o maior risco técnico do projeto** — ver
  [04-RISCOS_TECNICOS.md](04-RISCOS_TECNICOS.md). Não vale investir muito
  em tradução em massa antes de provar que a reinjeção funciona.

## Etapa 7 — QA em jogo
- Build de teste com o pacote pt-BR injetado, playtest dirigido por
  capítulo, atenção a overflow de texto em caixas de diálogo/UI de tamanho
  fixo e a strings que dependem de contexto visual (puzzles, HUD).

## Diagrama resumido

```
localization_dump.json (✅ existe)
        │
        ▼
  [Etapa 1] preprocess.py → preprocessed.json + glossary_candidates.json
        │
        ▼
  [Etapa 2] TM lookup + glossary enforcement (filtra o que já está pronto)
        │
        ▼
  [Etapa 3] tradução em lote via API (modelo conforme categoria/orçamento)
        │
        ▼
  [Etapa 4] validate_batch.py  ──(falha)──► volta pro lote
        │ (passa)
        ▼
  [Etapa 5] revisão humana → translation_memory.json (approved)
        │
        ▼
  [Etapa 6] merge → localization_pt-br.json → repack .db/.cpk (❌ a construir)
        │
        ▼
  [Etapa 7] QA em jogo
```
