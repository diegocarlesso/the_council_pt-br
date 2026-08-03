# Glossário e Memória de Tradução

## O que já existe
`pt-br/glossary.json` tem 7 termos travados (`locked: true`):
Effort Point, Conviction, The Nightmare, Holy Lance, Golden Order, Daemon
(mantido em inglês de propósito), Ether. `pt-br/translation_memory.json`
tem o schema definido (`source`, `target`, `context`, `category`, `status`,
`usage_count`) com 1 entrada de exemplo.

O schema está bom. O que falta é processo e escala.

## Convenção proposta

### `glossary.json` — termos que não podem variar
- Só entra aqui o que **precisa** ser sempre traduzido da mesma forma:
  nomes próprios, habilidades do sistema de jogo, organizações, itens
  narrativos-chave, termos de jogabilidade (o que já está lá é o padrão
  certo).
- `locked: true` significa "o validador de lote rejeita qualquer tradução
  que desvie disso". `locked: false` (a adicionar como opção) pode
  representar sugestões ainda não confirmadas por você.
- Fonte de novos candidatos: a extração automática de termos frequentes
  descrita em [01-PIPELINE.md](01-PIPELINE.md#etapa-1--pré-processamento-a-construir).
  Você aprova/edita, a IA nunca trava um termo sozinha.

### `translation_memory.json` — todo par original→tradução já resolvido
- Uma entrada por **string única** (usa o `canonical_id` da etapa de
  dedup), não por ocorrência — é assim que os 45,9% de duplicação viram
  economia de custo e de esforço de revisão.
- `status`: `draft` (saiu da IA, não revisado) → `approved` (revisado por
  você) → opcionalmente `flagged` (revisão humana pediu retradução).
  Só `approved` é usado para preencher a Etapa 2 (TM Lookup) em lotes
  futuros — nunca reaplicar automaticamente um `draft`.
- `usage_count`: útil para priorizar revisão — strings usadas 50 vezes
  valem mais atenção que strings usadas 1 vez.

## Por que considerar SQLite como fonte da verdade (a partir de certo volume)

Com 21.836 entradas, um `translation_memory.json` único vai ficar grande
(dezenas de MB) e cada tradução aprovada gera um diff gigante no git (JSON
não é feito para edição parcial eficiente). Duas opções:

1. **Manter JSON, mas particionado por categoria/arquivo** (ex.
   `tm/common.json`, `tm/q1.json`...) — mais simples, ainda git-friendly,
   resolve boa parte do problema de diff gigante.
2. **SQLite como fonte da verdade** (`translation.db`), com um script de
   export que gera os JSONs versionados a partir dele — update mais
   rápido, consultas (`WHERE status='draft'`, `WHERE usage_count>10`)
   triviais, e o JSON exportado serve só como snapshot legível/versionável.
   Overhead: mais uma peça de infraestrutura para manter.

Para o volume atual (~22k entradas), a opção 1 (JSON particionado por
arquivo/capítulo) já resolve o problema prático sem adicionar
infraestrutura. Migrar para SQLite só se o projeto crescer (ex. abrir para
colaboradores simultâneos, o que precisa de escrita concorrente que JSON
não oferece bem).

## Consolidação pendente

Os 5 arquivos soltos na raiz de `Data/Packages/` (originados do bug de
fragmentação do aider, ver
[02-FERRAMENTAS_E_TOOLING.md](02-FERRAMENTAS_E_TOOLING.md#lição-aprendida-fragmentação-de-saída))
duplicam conteúdo que já está correto em `pt-br/glossary.json`,
`pt-br/translation_memory.json`, `pt-br/pipeline.md`,
`pt-br/puzzle_codes.md` e `pt-br/json_structure.json`. Não apaguei esses
arquivos — é uma limpeza de housekeeping de baixo risco, mas prefiro que
você confirme antes de eu remover algo do histórico de trabalho, mesmo que
duplicado.
