# Roadmap Faseado

## Fase 0 — Provar que a reinjeção funciona (bloqueador crítico) ✅ concluída em 2026-08-03
- ✅ `repack_db.py` e `repack_cpk.py` escritos e testados (round-trip
  byte-idêntico sem alteração; ver `test_repack_roundtrip.py`).
- ✅ Teste em jogo real com strings alteradas, incluindo versões mais
  longas que o original: falas de missão/diálogo (85% do corpus)
  carregam e exibem corretamente **sem restrição de tamanho**.
- ⚠️ Achado importante: um pequeno cluster de strings de
  `common_loc_en_0.db` ligado à tela de boot/menu (`PLAY`, `Savegame
  1/2/3`) precisa manter o mesmo tamanho em bytes do original — mitigação
  validada (preencher/cortar a tradução). Ver
  [04-RISCOS_TECNICOS.md](04-RISCOS_TECNICOS.md#1-reinjeção--resolvida-para-diálogomissão-com-uma-exceção-confirmada-em-common_loc_en_0db)
  para o detalhe completo.
- ✅ Idioma: caminho definido é sobrescrever `Loca_en_Main` (não existe
  `Loca_pt_Main`, ver [04-RISCOS_TECNICOS.md](04-RISCOS_TECNICOS.md#2-como-o-jogo-carrega-idioma--investigado-caminho-definido)).
- **Critério de saída da fase**: ✅ atingido — `.cpk` modificado carrega no
  jogo com strings visivelmente traduzidas (menu e diálogo), sem quebrar
  nada, restaurado ao original ao final do teste.

## Fase 1 — Tooling de produção ✅ construída e testada em 2026-08-03 (tradução real ainda não rodou)
- ✅ `preprocess.py`: dedup, detecção de não-traduzível, categorização,
  extração de candidatos a glossário. Rodado sobre o corpus real: 40.347 →
  21.836 únicas (bate com [00-VISAO_GERAL.md](00-VISAO_GERAL.md)); 21.806
  traduzíveis, 30 não-traduzíveis (2 comando, 26 suspeita de puzzle — foram
  além do baú já documentado em `puzzle_codes.md`, achou letras soltas em
  mais lugares —, 2 termo de glossário exato); 11 strings sinalizadas como
  `menu_boot_suspect` (cluster de tamanho fixo da Fase 0); 200 candidatos a
  glossário gerados em `glossary_candidates.json` para revisão manual.
- ✅ `translate_batch.py`: monta lotes por categoria (300–500, nunca mistura
  UI com diálogo), cascata Haiku 4.5 (Sistema/Teste) → Sonnet 5
  (Diálogo/Item), saída estruturada via `output_config.format`
  (JSON garantido), prompt cacheado (regras+glossário fixos). Testado com
  `--dry-run` (monta os 438 lotes do corpus real sem chamar API) e
  verificação manual da montagem do prompt de sistema (glossário injetado,
  seção de lote removida do prompt fixo para não invalidar o cache). Ainda
  **não rodou de verdade** — falta `pip install anthropic` +
  `ANTHROPIC_API_KEY`.
- ✅ `validate_batch.py`: QA automática por lote (placeholders, tags,
  comandos, quebras de linha, termos travados, ajuste automático do
  cluster de menu de boot, aviso de crescimento de tamanho). Testado com
  lote sintético cobrindo os 7 casos (aprovação normal, placeholder
  divergente, termo travado violado, ajuste de tamanho de menu, aviso de
  crescimento, tradução vazia, canonical_id inexistente) — todos os 7
  resultados bateram com o esperado.
- ✅ Prompt de sistema já estava consolidado em
  `pt-br/prompts/translation_system_prompt.md` desde o planejamento
  inicial — `translate_batch.py` extrai e usa o bloco "Tradutor de lote"
  direto do arquivo (nunca redigitado no script).
- **Próximo passo real**: configurar `ANTHROPIC_API_KEY` e rodar
  `translate_batch.py` sem `--dry-run` num lote pequeno (ex.
  `--max-batches 1 --batch-size 20`) para validar o loop de ponta a ponta
  antes de liberar tradução em massa (Fase 3).

## Fase 2 — Glossário e fundação
- Rodar extração de candidatos sobre o corpus completo, você revisa e
  trava os termos (expandir os 7 já existentes).
- Priorizar `common_loc_en_0.db` primeiro: é o arquivo de sistema/UI
  reaproveitado no jogo inteiro, então traduzi-lo cedo popula o glossário
  e testa o pipeline inteiro com baixo risco de spoiler de história.

## Fase 3 — Tradução em lote
- Rodar por capítulo/quest, lotes de 300–500 strings únicas.
- Cada lote: TM lookup → tradução → validação → fila de revisão.

## Fase 4 — Revisão humana
- Planilha ou ferramenta dedicada (ver
  [02-FERRAMENTAS_E_TOOLING.md](02-FERRAMENTAS_E_TOOLING.md#interface-de-revisão-humana-opcional-mas-recomendável-a-partir-de-5k-strings)).
- Aprovações alimentam a TM (`status: approved`), reduzindo o trabalho de
  lotes futuros via reaproveitamento de duplicatas.

## Fase 5 — QA em jogo
- Build de teste com o pacote pt-BR, playtest por capítulo.
- Atenção a overflow de UI e strings sensíveis a contexto (puzzles).

## Fase 6 — Empacotamento e distribuição
- Gerar o `.cpk` final (ou pacote `Loca_pt_Main`) pronto para instalar.

### Nota legal (distribuição)
The Council é um jogo comercial (Cyanide Studio/Big Bad Wolf, publicado
pela Focus Entertainment). Os assets extraídos (`.cpk`, `.db`, texto
original) são propriedade deles. Prática comum em projetos de tradução de
fã: distribuir **apenas o patch/diff** (o `.cpk` de idioma modificado, ou
um instalador que baixa o jogo original do usuário e aplica a alteração),
nunca os arquivos originais do jogo. Isso é relevante só na hora de
publicar o resultado, não afeta o trabalho de tradução em si — mas vale
decidir o formato de distribuição com isso em mente desde já.

## O que fica para depois desta rodada de planejamento
Esta rodada foi só análise, sem gerar tradução. Próximo passo natural,
quando você confirmar o direcionamento: começar pela **Fase 0** (repack),
porque todo o resto do investimento (tempo, créditos de IA) depende de
saber que existe um caminho de volta para o jogo.
