# Roadmap Faseado

## Fase 0 — Provar que a reinjeção funciona (bloqueador crítico)
- Escrever `repack_db.py` (pool de strings → `.db`) e `repack_cpk.py`
  (recalcular offsets/tamanhos → `.cpk`).
- Teste round-trip sem alteração (extrair → reempacotar → comparar com o
  original).
- Teste com 1 string alterada (incluindo uma versão mais longa que a
  original) → confirmar que o jogo carrega e exibe corretamente.
- Investigar em paralelo como o jogo decide o idioma disponível
  (`packagelist`, menu de opções) para saber se dá para adicionar
  `Loca_pt_Main` ou se é preciso sobrescrever `Loca_en_Main`.
- **Critério de saída da fase**: um `.cpk` modificado carrega no jogo com
  pelo menos uma string visivelmente traduzida, sem quebrar nada.

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
