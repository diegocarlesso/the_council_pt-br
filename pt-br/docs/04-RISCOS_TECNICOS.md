# Riscos Técnicos e Questões Abertas

Ordenado por impacto na viabilidade do projeto. Os dois primeiros itens
deveriam ser resolvidos **antes** de investir tempo/dinheiro traduzindo em
massa — de nada adianta ter 21.836 strings traduzidas se não houver como
colocá-las de volta no jogo.

## 1. Reinjeção — resolvida para diálogo/missão, com uma exceção confirmada em `common_loc_en_0.db`

**Status: Fase 0 concluída em 2026-08-03.** `repack_db.py` e `repack_cpk.py`
foram escritos e testados — round-trip sem alteração é byte-idêntico ao
original (`.db` e `.cpk`), e o formato é:

- `.db`: header fixo + `uint32` `pool_size` + pool de strings `\x00`-terminadas
  no fim absoluto do arquivo, em ordem fixa. Nenhuma tabela de offsets
  encontrada dentro do próprio `.db` referenciando o pool por posição em
  bytes — busca exaustiva feita e documentada em `repack_db.py`.
- `.cpk`: header (magic + contagem + tabela de entradas) + blocos de dados
  concatenados sem padding, na ordem da tabela. O campo `unk` da entrada é
  sempre `0` (não é checksum/hash). Offsets são contíguos e recalculáveis.
- `.cpkh` (companheiro): manifesto JSON de metadados de build (hash de
  path, campo `MD5` sempre vazio) — **não** contém offsets/tamanhos, não
  precisa ser regenerado.

**Teste real em jogo (não só estrutural) confirmou dois comportamentos
diferentes:**

- ✅ **Falas de missão/diálogo (`q1`–`q17`, `chapter2`–`chapter5`, etc. —
  ~85% do corpus real) toleram tradução de **qualquer tamanho**, sem
  corromper conteúdo.** Testado ao vivo: todas as 24 arquivos de missão
  traduzidos de uma vez (37.085 strings, cada uma com um sufixo bem mais
  longo que o original) e o diálogo apareceu correto e legível durante o
  jogo normal, só quebrando linha na caixa de legenda (comportamento
  normal de UI, não corrupção de dado).
- ⚠️ **Um grupo pequeno e específico de strings em `common_loc_en_0.db`
  ligadas à tela de boot/menu principal (`PLAY`, `Savegame 1/2/3`, e
  possivelmente outros rótulos dessa mesma tela) tem um offset fixo em
  bytes calculado em algum lugar fora do `.db`** (suspeita forte:
  `Gui_Main_0.cpk`, o pacote de interface, ainda não investigado a fundo).
  Mudar o *tamanho* de qualquer string **antes** dessas na pool desalinha
  esse offset e faz a tela mostrar o conteúdo de **outra string** (ex.:
  "PLAY" passou a mostrar "Vulnerability revealed", uma string completamente
  diferente que calhou de cair na posição de bytes certa) — clique
  continua funcionando (a navegação usa outra referência), só o texto
  exibido fica errado. **Mitigação validada**: preencher/cortar a tradução
  dessas strings específicas para ocupar **exatamente o mesmo número de
  bytes** do original elimina o problema (testado ao vivo, funcionou:
  "PLAY"→"JOGA", "Savegame 1"→"JOGO SALV1", etc.). Strings de mecânica de
  jogo que também moram em `common_loc_en_0.db` mas não são desse cluster
  de boot (ex. "Vulnerability revealed", usada durante conversas normais)
  **não** têm esse problema — testado com tradução livre e mais longa,
  apareceu correta.

**O que ainda não foi feito** (não bloqueia o início da tradução em massa,
mas vale investigar em paralelo):
- Confirmar o alcance exato do cluster afetado dentro de
  `common_loc_en_0.db` (só o punhado testado, ou mais rótulos da mesma
  tela?) — hoje a lista segura conhecida é: `PLAY`, `Savegame 1`,
  `Savegame 2`, `Savegame 3` (índices 1185–1187, 1474, 1771–1773, 2062).
- Localizar o offset fixo de verdade (provavelmente dentro de
  `Gui_Main_0.cpk`) para, no futuro, poder atualizá-lo também e remover a
  restrição de tamanho por completo nessas strings específicas.

**Ação recomendada — Fase 1**: seguir com tradução livre para todos os
arquivos de missão/diálogo (sem restrição de tamanho). Tratar o cluster de
boot do `common_loc_en_0.db` como um caso especial e pequeno: traduzir
essas poucas dezenas de strings com o mesmo número de bytes do original
(abreviação controlada), documentado como excecão no glossário/pipeline.

## 2. Como o jogo carrega idioma — investigado, caminho definido

`packagelist` (raiz do jogo) lista os pacotes de idioma disponíveis:

```
Loca_en_Main, Loca_de_Main, Loca_fr_Main, Loca_sp_Main, Loca_ru_Main, Loca_it_Main
```

**Não há `Loca_pt_Main`, e só `Loca_en_Main_0.cpk` está de fato instalado**
neste depot da Steam (os outros 5 idiomas listados não têm `.cpk` no disco
— provavelmente depots separados por idioma). Busca por strings `Loca_xx`
dentro de `The Council.exe` (15MB) não encontrou nenhuma ocorrência —
indício de que a lista de idiomas não está hardcoded no executável, e sim
vem de dados (`packagelist`/config), mas **não confirmado que adicionar
`Loca_pt_Main` faria o menu de opções mostrar "Português" como opção
selecionável** (a UI do menu pode ter sua própria lista fixa em
`Gui_Main_0.cpk`, não investigado).

**Caminho escolhido para a Fase 0 (e recomendado para o projeto): (a)
sobrescrever `Loca_en_Main`.** É o padrão usado pela maioria dos patches de
tradução de fã, testado e funcionando (ver item 1) — o jogo carrega
normalmente com o pacote `en` substituído por conteúdo pt-BR, sem precisar
mexer em `packagelist` nem investigar a lista de idiomas do menu. Custo:
perde a opção de jogar em inglês sem reverter o arquivo (mitigado por manter
sempre um backup do `.cpk` original, como já fazemos).

A opção (b) — criar `Loca_pt_Main` de verdade, aparecendo como idioma
selecionável — fica como possibilidade futura, não bloqueia o projeto.

## 3. Instabilidade de modelos gratuitos de IA
Já documentado em [03-MODELOS_IA_E_CUSTOS.md](03-MODELOS_IA_E_CUSTOS.md).
Risco de processo, não técnico: mitigar com fallback multi-modelo e nunca
depender de um único modelo `:free` como caminho crítico.

## 4. Expansão de texto (pt-BR costuma ser mais longo que inglês)
UI com caixas de texto de tamanho fixo (menus, HUD, legendas) pode
transbordar quando a tradução fica ~15–20% mais longa. Não dá pra saber
sem testar em jogo — por isso a Etapa 7 do pipeline (QA em jogo) não é
opcional, e por isso o validador de lote já sinaliza strings que crescem
muito além da média.

## 5. Volume alto de puzzles/códigos internos misturados com texto de jogo
Confirmado que existe pelo menos um puzzle com sequência de letras/comandos
misturada como strings comuns (`puzzle_codes.md`). Detecção automática
(Etapa 1 do pipeline) reduz o risco, mas vale um passo manual de
"sanity check" nos arquivos de quest com nomes menos óbvios antes de
liberar tradução automática em lote para eles — 300–500 strings por lote é
grande o bastante para um puzzle raro passar despercebido se a heurística
falhar.

## 6. Legal/distribuição (não bloqueia o trabalho de tradução, mas define como distribuir depois)
Ver [06-ROADMAP.md](06-ROADMAP.md#nota-legal-distribuição).
