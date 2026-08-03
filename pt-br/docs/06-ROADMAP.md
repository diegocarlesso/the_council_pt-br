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

## Fase 1 — Tooling de produção
- `preprocess.py`: dedup, detecção de não-traduzível, categorização,
  extração de candidatos a glossário.
- `translate_batch.py`: chamada de API com saída estruturada, cascata de
  modelos (TM → Tier 0 → Tier 1 → Tier 2 conforme
  [03-MODELOS_IA_E_CUSTOS.md](03-MODELOS_IA_E_CUSTOS.md)).
- `validate_batch.py`: QA automática por lote.
- Consolidar prompt de sistema em `pt-br/prompts/translation_system_prompt.md`.

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
