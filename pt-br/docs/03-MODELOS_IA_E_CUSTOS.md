# Modelos de IA e Estratégia de Custo

## Números que definem o orçamento

Medidos direto em `localization_dump.json` (ver
[00-VISAO_GERAL.md](00-VISAO_GERAL.md#2-escala-real-do-trabalho)):

- 40.347 strings totais → **21.836 únicas** após dedup (45,9% de economia
  automática, antes de gastar um único token de IA).
- ~202.500 palavras / ~1,08M caracteres únicos ≈ **270k tokens de entrada**
  (estimativa 4 chars/token). Saída em pt-BR tende a ficar ~15–20% mais
  longa → estimar **~320k tokens de saída**.
- Isso é pequeno para padrões de LLM (um livro médio). O gargalo não é
  tamanho absoluto, é **estabilidade** (não travar o projeto na metade por
  causa de rate limit de modelo grátis) e **qualidade de tradução
  literária/de jogo** (não é texto técnico, é diálogo com tom, ironia,
  gírias de época — a instrução que você já deu de "não traduzir
  literalmente, priorizar naturalidade" é a parte difícil de garantir com
  modelo fraco).

## Por que separar "modelo para código" de "modelo para tradução"

São tarefas diferentes:
- **Manter o pipeline** (scripts Python de parse/preprocess/validate/repack)
  é trabalho de *codificação* — aqui o aider com um modelo de código
  (gratuito ou não) faz sentido, porque o output é revisável por diff e
  testável rodando o script.
- **Traduzir 21.836 strings** é trabalho de *geração de texto em lote com
  saída estruturada*. Aqui você quer: (a) JSON garantido na saída (schema/
  function calling), (b) baixo custo por token porque o volume é alto,
  (c) qualidade de escrita em pt-BR natural. O aider não ajuda em nenhum
  desses três pontos — ele foi feito para editar arquivos de código, não
  para rodar um loop de "lote de 400 strings → JSON de volta".

Recomendação: escreva um script pequeno (`translate_batch.py`) que chama a
API do provedor escolhido diretamente, manda o prompt de sistema +
glossário + lote de N strings, e valida a resposta contra um JSON schema
antes de aceitar. O aider continua útil só para você e eu mantermos esse
script.

## Modelos: tiers por custo/uso

**Preços do OpenRouter/Anthropic/OpenAI mudam com frequência — os valores
abaixo são posicionamento relativo, não cotação. Confira
`openrouter.ai/models` antes de decidir.**

### Tier 0 — Grátis (rascunho/primeira passada, não confiável sozinho)
- Modelos `:free` do OpenRouter (Nemotron, Qwen, Gemini Flash grátis quando
  disponível, DeepSeek quando disponível). Rotativo por natureza: hoje
  funciona, semana que vem pode sumir ou mudar de slug (já aconteceu com
  vocês no deepseek-r1).
- Uso recomendado: só como *fallback* ou para gerar rascunho de lotes
  não-críticos (ex.: textos de sistema curtos, UI simples), sempre com QA
  automática rígida antes de aceitar, nunca como única fonte de tradução
  narrativa.
- Ponto positivo real: como 45,9% do texto é duplicado, mesmo um modelo
  grátis instável, se conseguir traduzir os 21.836 únicos ao longo do
  tempo (em vários dias, rodando quando o limite libera), já cobre 100%
  das strings totais via TM.

### Tier 1 — Baixo custo, boa qualidade pt-BR (recomendado como motor principal)
- Modelos "mini/flash/haiku" de provedores grandes (ex. Claude Haiku,
  GPT-4o-mini/GPT-5-mini equivalente, Gemini Flash pago). Custo por
  milhão de tokens tipicamente na faixa de poucos dólares — para ~270k
  tokens de entrada + ~320k de saída do projeto inteiro, isso costuma cair
  na faixa de **poucos dólares no total**, não centenas, justamente porque
  o corpus real (após dedup) é pequeno.
- São a melhor relação custo/qualidade para lotes de diálogo/narrativa,
  onde tom e naturalidade importam e um modelo muito fraco erra.
- Suportam structured output/JSON schema de forma confiável, o que fecha o
  ciclo com o validador automático.

### Tier 2 — Premium (uso cirúrgico, não em massa)
- Modelos topo de linha (Claude Sonnet/Opus, GPT-5, etc.) — reservar para:
  - strings sinalizadas como ambíguas/importantes pela revisão humana
    (ex.: trocadilhos, decisões de tom que definem um personagem)
  - resolver divergências quando Tier 0/1 produziu traduções
    inconsistentes para o mesmo termo em contextos diferentes
  - a extração inicial de glossário a partir do corpus (uma vez só, não
    por lote)
- Caro demais para rodar em 21.836 strings, ótimo para os ~5% que
  realmente precisam de julgamento fino.

### Estratégia recomendada (cascata)
1. TM/glossário resolve o que já foi aprovado (custo zero).
2. Tier 0 (grátis) tenta lotes de baixo risco (UI, sistema, itens
   genéricos) — aceita se passar QA automática.
3. Tier 1 (barato) é o motor principal para diálogo/narrativa — a maior
   parte do orçamento real vai aqui, e ainda assim é barato pelo volume
   pequeno pós-dedup.
4. Tier 2 (premium) só para o que a revisão humana marcar como
   problemático ou para decisões de glossário/tom que valem a pena
   acertar uma vez e travar para sempre.

## Sobre aider especificamente

Continue usando aider para o desenvolvimento do pipeline (scripts), mas:
- Prefira um modelo pago barato e estável para isso também, se o `:free`
  continuar dando 404/instabilidade — é código de infraestrutura do
  projeto, vale a pena não perder tempo depurando falha de modelo em vez
  de bug real.
- Nunca use aider para gerar o relatório/glossário/tradução em si — como
  visto, isso já causou fragmentação de arquivos. Para esse tipo de saída,
  peça a mim (Claude Code) ou a um script direto de API, não ao aider em
  modo de edição de arquivo solto.

## Prompt caching (redução extra de custo)

O prompt de sistema (regras de não-tradução, glossário travado, exemplos)
se repete em **todos** os lotes. Provedores como Anthropic e OpenAI (e o
OpenRouter repassando isso) suportam *prompt caching*: a parte fixa do
prompt é cobrada uma vez e reaproveitada nas chamadas seguintes dentro da
janela de cache. Vale estruturar o prompt do `translate_batch.py` com o
conteúdo fixo (regras + glossário) no início e só o lote variável no final,
para aproveitar isso — pode cortar uma fatia relevante do custo em um
pipeline com centenas de chamadas.
