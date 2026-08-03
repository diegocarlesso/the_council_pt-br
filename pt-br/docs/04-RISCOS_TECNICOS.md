# Riscos Técnicos e Questões Abertas

Ordenado por impacto na viabilidade do projeto. Os dois primeiros itens
deveriam ser resolvidos **antes** de investir tempo/dinheiro traduzindo em
massa — de nada adianta ter 21.836 strings traduzidas se não houver como
colocá-las de volta no jogo.

## 1. Não existe reinjeção (`.json` → `.db` → `.cpk`) — bloqueador nº 1

O que existe hoje é só o caminho de extração. `dump_texts.py` localiza o
pool de strings assim:

> varre o arquivo de trás para frente procurando um `uint32` que bata com
> o tamanho do resto do arquivo (`pool_size`); o que estiver depois desse
> `uint32` é o pool.

Isso sugere (mas não prova) que o pool de strings fica **no fim absoluto
do arquivo `.db`**, sem nada depois dele. Se for esse o caso, reinjetar é
"só":
1. Serializar a nova lista de strings (mesma ordem/índices) com
   `\x00` como separador.
2. Escrever esse novo pool a partir de `pool_start` (o resto do arquivo,
   antes do pool, fica intacto).
3. Atualizar o `uint32` de `pool_size` para o novo tamanho.
4. Repetir para o `.cpk`: atualizar a tabela de offsets/tamanhos de cada
   entry (`unpack_cpk.py` mostra o formato: header de 12 bytes por arquivo
   com `file_size, file_offset, unk`) — como os `.db` mudam de tamanho, o
   `.cpk` inteiro precisa ser remontado com offsets recalculados, não só
   ter os bytes trocados no lugar.

**Isso é uma hipótese, não um fato verificado.** Riscos concretos:
- Pode haver **outras estruturas no `.db`** (fora do pool) que referenciam
  strings por **offset absoluto no arquivo**, não só por índice. Se
  existirem, mudar o tamanho do pool quebra essas referências.
- O `.cpk` pode ter checksums/CRC por entrada ou um header global com
  tamanho total do arquivo que `unpack_cpk.py` não está lendo (o parser
  atual é bem simples — 4 bytes de magic, contagem, nome da pasta raiz,
  depois um loop de headers de 12 bytes + nome de 512 bytes). Se houver
  validação de integridade no engine, um `.cpk` remontado incorretamente
  pode simplesmente falhar ao carregar, ou pior, corromper o save.

**Ação recomendada — Fase 0 do roadmap, antes de qualquer tradução em
massa**: escrever `repack_db.py` e `repack_cpk.py`, fazer um teste de
**round-trip sem alterar nada** (extrair → reempacotar → comparar
byte-a-byte com o original; se não for idêntico, entender por quê) e
depois um teste **com uma única string alterada** (ex. trocar "Red
berries" por um texto mais longo) para confirmar que o jogo carrega e
mostra o texto corretamente, incluindo quando a string fica mais longa que
a original. Só depois disso vale traduzir em lote.

## 2. Não está confirmado como o jogo carregaria pt-BR

`packagelist` (raiz do jogo) lista os pacotes de idioma disponíveis:

```
Loca_en_Main, Loca_de_Main, Loca_fr_Main, Loca_sp_Main, Loca_ru_Main, Loca_it_Main
```

Não há `Loca_pt_Main`. Duas abordagens possíveis, cada uma com trade-offs:

- **(a) Sobrescrever `Loca_en_Main`**: mais simples tecnicamente (não
  precisa mexer no `packagelist`/seletor de idioma do jogo), mas remove a
  opção de jogar em inglês sem reverter o arquivo, e não se sabe ainda se
  o seletor de idioma do menu depende do nome do pacote carregado ou de
  outra flag interna.
- **(b) Criar `Loca_pt_Main` e registrar no `packagelist`**: mais correto
  (preserva o inglês, aparece como opção "de verdade"), mas precisa
  confirmar se o jogo aceita um pacote de idioma novo sem recompilar o
  executável — ou seja, se a lista de idiomas do menu vem só do
  `packagelist`/config, ou se está hardcoded em `The Council.exe`.

**Ação recomendada**: investigar isso em paralelo à Fase 0 (é
reverse-engineering leve: abrir o menu de opções do jogo, ver como a lista
de idiomas é montada, procurar strings tipo "Language" nos `.db` de
`Databases_PC_Main` ou `Engine_Main` para achar onde a lista é definida).
Não é bloqueador para começar a traduzir (a tradução em si independe
disso), mas é bloqueador para **jogar o resultado**, então vale resolver
cedo para não descobrir tarde que dá mais trabalho que o esperado.

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
