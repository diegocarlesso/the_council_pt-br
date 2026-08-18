# Estado do pipeline — 2026-08-17 19:10

> Nota manual (não é gerada por script, ao contrário de `PROGRESS.md`).
> Substitui a nota de pausa de 2026-08-14 (arquivada no histórico do
> git). Desta vez não é uma pausa no meio do trabalho: **a primeira
> passada de tradução está 100% completa**.

## Marco: 21806/21806 (100%), 0 em needs_review

- Todas as categorias traduzíveis (Diálogo, Sistema, Item, Teste,
  Descontinuado) em 100%.
- `approved: 213`, `draft: 21593`, `needs_review: 0`.
- Pipeline local (`translator/`) parado, modelo descarregado do LM
  Studio (`lms unload --all`). Nada rodando em segundo plano.
- Tudo commitado e enviado para `origin/master`.

## Revisão de qualidade das strings draft (sessão de 2026-08-17, à tarde)

Depois do marco de 100%, rodei uma varredura de qualidade sobre as
21731 strings `draft` (nunca revisadas por humano, só QA mecânica do
pipeline). **Não foi leitura exaustiva das 21.731** — foi: (1) checagem
automática mecânica+glossário reaproveitando `BatchValidator` em todo o
corpus, (2) heurísticas (target==source, repetição degenerada,
crescimento de tamanho >140%, marcadores de espanhol tipo ¿/¡/ñ/palavras
exclusivas), (3) amostragem manual aleatória de ~120 itens pra estimar
taxa de erro fora do que as heurísticas pegam.

Achados e corrigidos (110 itens, todos virados `approved`):
- **8 termos de glossário** que passaram despercebidos pela QA em tempo
  real (Lord Mortimer, Diversion->Distração, Questioning->Questionamento).
- **8 frases inteiras nunca traduzidas** (target idêntico ao source em
  inglês) - citações bíblicas, diálogo, um trecho de codex.
- **9 erros semânticos**: troca de gênero (he->ela), frase alucinada
  inserida sem correspondência no original, palavra errada (braço
  virou perna), palavra solta em inglês no meio de frase pt-BR.
- **~85 casos de contaminação por espanhol** - de pontuação solta (¿/¡)
  até parágrafos inteiros (inclusive citações bíblicas) saídos 100% em
  espanhol. Esse foi o achado mais significativo e o único que a QA
  mecânica do pipeline **não tinha como pegar** (não mexe com
  placeholder/tag/glossário, só troca de idioma inteiro).

**Confirmação com `langdetect` (mesma tarde, pedido explícito do
usuário: "roda o restante dos ~700 candidatos de espanhol")**: instalei
`langdetect` e rodei contra as ~21.6k strings `draft` pra checar a
estimativa de ~3% acima com número de verdade, não só amostra. Achado
importante: **`langdetect` sozinho tem MUITO falso positivo em frases
curtas em pt-BR** - frases 100% corretas como "Ele está morto?" batem
"espanhol" com 100% de confiança. Não dá pra usar o resultado bruto.

Processo: 853 candidatos flagados como `es`. Os 66 de texto longo
(>=60 chars, onde `langdetect` é confiável) foram todos lidos - achou 4
parágrafos genuinamente em espanhol que o filtro por palavras-chave
anterior tinha perdido. Os 787 candidatos curtos foram **todos lidos
manualmente** (impraticável confiar no score sozinho) - achou mais 21
problemas reais (a maioria frases inteiras em espanhol que não tinham
nenhuma das palavras-chave do filtro anterior tipo "los"/"las"/¿/¡, mais
alguns erros de concordância/conjugação que o `langdetect` também
pegou como ruído mas eram bugs de verdade por conta própria).

**Total da revisão de qualidade desta sessão: 124 strings corrigidas**
(110 da primeira passada + 28 desta confirmação, alguns sobrepostos).
Taxa real de contaminação por espanhol nas ~21.6k `draft`: ficou
abaixo da estimativa de 3% inicial depois de tirar o ruído do
`langdetect` - mais perto de ~0.5-0.6% no que foi coberto.

**O que NÃO foi coberto**: os candidatos que o `langdetect` flagou como
catalão/francês/italiano/alemão/romeno/etc (~1040 no total) - mesmo
padrão de falso positivo esperado (línguas românicas próximas
confundem o detector), não verificados individualmente por escopo. Se
quiser 100% de certeza, essa é a lacuna que falta.

## Como chegamos aqui (sessão de 2026-08-17, 10:51 → 19:10)

1. Retomado o pipeline de 69,3% com `google/gemma-3n-e4b` (mesma config
   documentada na nota anterior — ver histórico do git se precisar do
   contexto de hardware/GPU de 4GB).
2. Rodada principal terminou o worklist completo (100% de cobertura),
   mas **às 15:35 o motor de inferência do LM Studio travou
   transientemente** (`Engine protocol predict request failed: fetch
   failed` / `Model is unloaded`) durante um trecho de ~1 segundo,
   derrubando ~480 itens (12 lotes) direto pra `needs_review`. O
   processo Python não caiu, o LM Studio se recarregou sozinho e o
   pipeline seguiu.
3. Rodada de retentativa focada só nos itens `needs_review` com `target`
   vazio (480 → 440 recuperados automaticamente; 40 continuaram
   falhando com resposta vazia mesmo em tentativas isoladas — conteúdo
   específico desse lote parece ter algo que trava a geração local,
   nunca identificado exatamente o quê).
4. **Revisão manual** (eu, Claude, direto - não o modelo local) dos 62
   itens finais em `needs_review`:
   - 22 já tinham tradução, só violavam dois termos travados do
     glossário que o modelo local sistematicamente errava: "Lord
     Mortimer" (ele traduzia para "Lorde Mortimer") e "The Nightmare"/
     "O Pesadelo" (ele não capitalizava "Pesadelo" como termo travado).
     Corrigido só o termo, resto da tradução mantido.
   - 40 nunca tinham sido traduzidos (o lote que falhava
     persistentemente — trivia de genealogia da família Mortimer/
     história de "La Niña"/China). Traduzidos manualmente.
   - Todos marcados `status=approved`.

## Pendência conhecida pra próxima sessão

Nenhuma bloqueante. Itens pra considerar como próximo passo (ver
`pt-br/docs/06-ROADMAP.md` - Fases 4, 5, 6, ainda que o roteiro desse
doc esteja desatualizado quanto a *como* a tradução foi feita):

- **Fase 4 (revisão humana)**: mesmo depois da varredura de qualidade
  acima, ainda vale uma passada de revisão de tom/naturalidade nas
  ~21.6k strings em `draft` restantes antes de considerar o texto
  "final" - a varredura pegou erros estruturais e de idioma, não
  necessariamente nuance de tom/registro. As 185 `approved` já passaram
  por olho humano/Claude.
- **Fase 5 (QA em jogo)**: build de teste com o pacote pt-BR, playtest
  por capítulo, atenção a overflow de UI e ao cluster
  `menu_boot_suspect` (tamanho fixo em bytes, já tratado
  automaticamente pelo pipeline, mas vale conferir visualmente).
- **Fase 6 (empacotamento)**: gerar o `.cpk`/pacote `Loca_pt_Main`
  final. Repack (`repack_db.py`/`repack_cpk.py`) já testado e validado
  na Fase 0.

## Como retomar (se for pra rodar o pipeline de novo)

Não deveria ser necessário rodar `translator.translate` de novo a menos
que:
- surjam novas strings no jogo (atualização/DLC) — nesse caso,
  `preprocess.py` de novo e o pipeline só processa o que for novo
  (cache por `canonical_id`).
- alguém queira reprocessar `draft` -> `approved` em massa via IA (não
  recomendado - `upsert_many` nunca sobrescreve `approved`, mas também
  não tem um modo "força re-tradução de draft" pronto, seria preciso
  script novo).

Se precisar do LM Studio de novo:
```bash
lms load "google/gemma-3n-e4b" -y
TRANSLATOR_MODEL_NAME="google/gemma-3n-e4b" python -m translator.translate
```

Ver `pt-br/PROGRESS.md` para o checkpoint numérico sempre atualizado.
