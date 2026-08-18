# Estado do pipeline — 2026-08-18 01:15

> Nota manual (não é gerada por script, ao contrário de `PROGRESS.md`).
> Substitui a nota de pausa de 2026-08-14 (arquivada no histórico do
> git).

## ⚠️ BLOQUEADOR ATIVO E GRAVE: bug de offset fixo é mais amplo do que se pensava — build ao vivo revertida 100% pro inglês

**Escalada em duas etapas na mesma sessão (2026-08-18):**

**Etapa 1 — telas de menu quebradas.** Build completa (26 arquivos
traduzidos, incluindo `common_loc_en_0.db`) aplicada no jogo ao vivo —
os menus quebraram (texto sobreposto/cortado, "Sauvegarde 3" em
francês vazando de outra posição do pool). Confirma e amplia o risco
documentado em [04-RISCOS_TECNICOS.md](docs/04-RISCOS_TECNICOS.md#1-reinjeção):
um cluster de strings em `common_loc_en_0.db` é referenciado por
**offset fixo em bytes** a partir de outro arquivo (suspeita:
`Gui_Main_0.cpk`, nunca localizado com precisão). O Fase 0 só validou
4 strings seguras (`PLAY`, `Savegame 1/2/3`) — o alcance real nunca
foi confirmado. **Mitigação tentada**: excluir só `common_loc_en_0.db`
(mantido em inglês), manter os outros 25 arquivos traduzidos.

**Etapa 2 — o mesmo bug apareceu em `q1_loc_en_0.db` (arquivo de
missão, supostamente "seguro").** Com a mitigação da Etapa 1 aplicada,
o usuário iniciou um **novo jogo** e a cutscene pré-renderizada de
abertura mostrou a legenda errada: a fala certa pra aquele momento
("Stop! You're not getting anywhere with this, Von Borchert!",
`c_617629719c74`, índices 1483/1547 em `q1_loc_en_0.db`) foi
substituída na tela pela legenda de uma fala **anterior no mesmo
arquivo** ("Good Lord, Washington is wearing the emblem of the Grand
Master of the Golden Order!", `c_0f5b95d46039`, índices 1324/1417).
Índice mostrado (1324) < índice certo (1483) é exatamente o padrão
esperado se for o mesmo bug de offset fixo: como a tradução pt-BR é
mais longa que o inglês, o pool cresceu, e uma referência fixa em
bytes (provavelmente de `Cutscenes_Main_0.cpk`, sincronizando legenda
com a cutscene pré-renderizada) agora aponta pra uma posição mais
cedo do que devia.

**Isso muda o diagnóstico**: a Fase 0 só testou diálogo comum (roda de
diálogo, conversas normais do motor do jogo) — não cutscenes
pré-renderizadas, que aparentam usar um mecanismo de sincronização de
legenda diferente e vulnerável ao mesmo problema de offset fixo.
Cutscenes desse tipo podem estar espalhadas por **qualquer** um dos
24 arquivos de missão/capítulo, não só `q1`. Não temos hoje nenhuma
forma de enumerar quais strings especificamente pertencem a cutscenes
vs. diálogo comum seguro.

**Mitigação atual (aplicada, jogo ao vivo revertido)**: `Loca_en_Main_0.cpk`
voltou a ser **byte-idêntico ao `.orig_backup`** (100% inglês original,
zero tradução aplicada). Confirmado por checksum.

**Release público**: [v1.0.0-beta1](https://github.com/diegocarlesso/the_council_pt-br/releases/tag/v1.0.0-beta1)
foi **retirado de circulação** (`gh release edit --draft`, não fica
mais listado publicamente) — as notas do release documentam o motivo.

**Pendência real pra desbloquear qualquer tradução de missão/cutscene
de novo:**
1. Descobrir quais falas especificamente são ditas em cutscenes
   pré-renderizadas (vs. diálogo comum do motor, que segue confirmado
   seguro) — provavelmente precisa investigar `Cutscenes_Main_0.cpk`
   pra achar a tabela de sincronização legenda↔vídeo.
2. Localizar o offset fixo de verdade (a referência externa) pra,
   idealmente, poder recalculá-lo/atualizá-lo em vez de evitar mudar
   o tamanho das strings.
3. Alternativa mais simples se 1/2 não derem certo: tratar TODAS as
   strings de cutscene (uma vez identificadas) com ajuste de byte
   exato, como já foi validado pro cluster de boot do
   `common_loc_en_0.db`.
4. Sem 1, 2 ou 3, a única opção seria não traduzir NENHUM arquivo que
   contenha cutscenes — o que pode ser a maioria/todos os arquivos de
   missão, inviabilizando a abordagem atual quase por completo. Vale
   muito investir tempo em 1/2 antes de desistir dessa via.

Script de build: `build_full_pack.py` na raiz do repo (já commitado).
Hoje ele só exclui `common_loc_en_0.db` — **não é suficiente** dado o
achado da Etapa 2, precisa ser revisto antes de gerar qualquer build
nova pra teste.

## Marco: 21806/21806 traduzíveis com tradução (100%), 0 em needs_review

- `approved: 248`, `draft: 21558`, `needs_review: 0`.
- Pipeline local (`translator/`) parado, modelo descarregado do LM
  Studio (`lms unload --all`). Nada rodando em segundo plano.
- Tudo commitado e enviado para `origin/master`.
- **Mas o build jogável não usa 100% disso ainda** — ver bloqueador
  acima. O texto de `common_loc_en_0.db` está traduzido na TM/git, só
  não está sendo aplicado no `.cpk` até o offset ser resolvido.

## Classificador de qualidade (parcial, pausado)

Rodei o `gemma-3n-e4b` local como classificador (não gerador) sobre os
~1600 candidatos que o `langdetect` sinalizou como catalão/francês/
italiano/alemão/etc — achou ~20 frases inteiras em italiano que
tinham escapado da varredura de espanhol, mais alguns erros de
gênero/número/conjugação. 35 corrigidos (ver commit
`e6c7070`). Depois, comecei a rodar o mesmo classificador sobre TODAS
as ~21.5k strings `draft` restantes (script
`llm_verify_all_draft.py`, no scratchpad) — **pausei no lote ~15/1078**
a pedido do usuário (ia levar ~5h, priorizamos montar o build pro
jogo). Puro trabalho de classificação, sem geração — pode ser
retomado a qualquer momento, é só recarregar o modelo e rodar nesse
mesmo script apontando pro `translation_memory.json` atual.

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
