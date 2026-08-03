# Equipe, Papéis e Rodízio de Modelos Anthropic

> Decisão de 2026-08-03: abandonar a estratégia multi-provedor (OpenRouter
> `:free` + variados) descrita na versão original de
> [03-MODELOS_IA_E_CUSTOS.md](03-MODELOS_IA_E_CUSTOS.md) em favor de uma
> cascata **100% Anthropic** (Haiku 4.5 → Sonnet 5 → Opus 5), operada por dois
> CLIs — **aider** (manutenção de código) e **Claude Code** (orquestração,
> revisão, decisões de glossário) — cada um com o modelo certo para o papel.
> Preços e IDs de modelo abaixo conferidos na tabela oficial da Anthropic em
> 2026-08-03; **confira `anthropic.com/pricing` antes de rodar em produção**,
> especialmente porque o preço promocional do Sonnet 5 expira em
> **2026-08-31**.
>
> **Este documento é só estrutura de equipe/processo. Nenhum código de
> repack foi escrito. A Fase 0 do roadmap (`repack_db.py`/`repack_cpk.py`)
> continua sendo o próximo passo de execução, não coberto aqui — ver
> [06-ROADMAP.md](06-ROADMAP.md).**

## 1. Por que "equipe" mesmo sendo você + IA

Estruturar isso como papéis (não como "um prompt gigante que faz tudo")
resolve dois problemas reais já registrados nos outros documentos:

- **Fragmentação de saída** ([02-FERRAMENTAS_E_TOOLING.md](02-FERRAMENTAS_E_TOOLING.md)):
  usar a ferramenta errada para a tarefa (aider para gerar relatório em
  massa) já causou lixo no repo. Papéis bem definidos = ferramenta certa por
  natureza da tarefa.
- **Custo/qualidade** ([03-MODELOS_IA_E_CUSTOS.md](03-MODELOS_IA_E_CUSTOS.md)):
  gastar Opus em tradução de item de inventário é desperdício; gastar Haiku
  em arbitragem de tom de personagem é risco de qualidade. Papel → modelo
  fixo evita as duas pontas.

## 2. Papéis e responsabilidades

| Papel | Responsabilidade | Ferramenta | Modelo padrão |
|---|---|---|---|
| **Arquiteto/Tech Lead** | Mantém os scripts Python do pipeline (parser, pré-processador, validador, e futuramente o repacker) — trabalho de código revisável por diff | **aider** | Claude Sonnet 5 |
| **Tradutor de Lote** | Motor de tradução em massa — chamada de API direta com schema JSON, nunca edição de arquivo solto | script `translate_batch.py` (a construir na Fase 1) chamando a API Anthropic | Cascata Haiku 4.5 → Sonnet 5 → Opus 5 (ver §4) |
| **Revisor-Chefe / QA** | Arbitra divergências de tradução, decide tom/glossário para casos ambíguos, audita amostras | **Claude Code** (esta sessão/instância) | Claude Opus 5 |
| **Dev de Jogos Sênior** | Engenharia reversa do formato `.cpk`/`.db`, repack, integração com o carregamento de idioma do jogo — **Fase 0, ainda não iniciada** | **aider** ou **Claude Code**, conforme a etapa | Claude Sonnet 5 (padrão); escalar para Opus 5 só se o formato binário exigir raciocínio mais profundo |
| **Gerente de Projeto** | Orquestra as etapas, mantém roadmap/glossário atualizados, decide quando escalar para Opus 5 | **Claude Code** | Claude Opus 5 (poucas chamadas, decisões estruturais) |

## 3. Preços e IDs (conferido 2026-08-03)

| Modelo | ID exato | Contexto | Entrada / 1M tokens | Saída / 1M tokens |
|---|---|---|---|---|
| Claude Haiku 4.5 | `claude-haiku-4-5` | 200K | $1,00 | $5,00 |
| Claude Sonnet 5 | `claude-sonnet-5` | 1M | $3,00 (promo **$2,00 até 2026-08-31**) | $15,00 (promo **$10,00 até 2026-08-31**) |
| Claude Opus 5 | `claude-opus-5` | 1M | $5,00 | $25,00 |

Use sempre os IDs exatos acima — sem sufixo de data — tanto no aider quanto
em scripts que chamam a API diretamente.

## 4. Cascata de tradução em lote (papel "Tradutor de Lote")

Mesma lógica do documento original, só que toda dentro da Anthropic:

1. **TM/glossário primeiro** (custo zero) — `translation_memory.json`
   resolve o que já foi aprovado.
2. **Haiku 4.5** tenta lotes de baixo risco: textos de sistema/UI, itens
   genéricos, strings curtas sem carga dramática. Aceita se passar na QA
   automática (`validate_batch.py`, a construir na Fase 1).
3. **Sonnet 5** é o motor principal — diálogo e narrativa, onde tom e
   naturalidade importam. É aqui que a maior parte do orçamento real vai.
4. **Opus 5** só para o que a revisão humana ou o Revisor-Chefe marcar como
   problemático, e para a extração inicial de glossário a partir do corpus
   (uma vez só, não por lote).

### Estimativa de custo (corpus completo, uma passada)

Base: 21.836 strings únicas ≈ 270k tokens de entrada / ~320k tokens de saída
(números de [00-VISAO_GERAL.md](00-VISAO_GERAL.md)). Distribuição estimada:
15% Haiku, 75% Sonnet, 10% Opus.

| Modelo | Entrada | Saída | Custo entrada | Custo saída | Subtotal |
|---|---|---|---|---|---|
| Haiku 4.5 | 40,5k | 48k | $0,04 | $0,24 | **$0,28** |
| Sonnet 5 (preço promo) | 202,5k | 240k | $0,41 | $2,40 | **$2,81** |
| Opus 5 | 27k | 32k | $0,14 | $0,80 | **$0,94** |
| **Total (com promo Sonnet, até 2026-08-31)** | | | | | **≈ $4,00** |
| **Total (preço cheio do Sonnet, após 2026-08-31)** | | | | | **≈ $5,40** |

Isso é o custo de traduzir os 21.836 strings únicos **uma vez**. Com prompt
caching (glossário + regras fixas no início do prompt, lote variável no
fim — ver §5) o custo real fica ainda menor, porque o prefixo fixo é cobrado
uma vez e reaproveitado nas chamadas seguintes. Nem revisão humana nem
retrabalho estão incluídos — isso é o piso, não o teto.

## 5. Prompt caching — por que importa aqui

O prompt de sistema do `translate_batch.py` (regras de não-tradução,
glossário travado, exemplos, instruções de tom) se repete em **todas** as
centenas de chamadas de lote. Estruture assim:

```
system = [
    {"type": "text", "text": REGRAS_E_GLOSSARIO, "cache_control": {"type": "ephemeral"}}
]
messages = [{"role": "user", "content": LOTE_DE_300_A_500_STRINGS}]
```

- Cache mínimo: 512 tokens no Sonnet 5/Opus 5, 4096 no Haiku 4.5 — o
  glossário+regras deve passar disso facilmente uma vez populado.
- Verifique `usage.cache_read_input_tokens` na resposta para confirmar que
  está batendo cache; se ficar em zero em chamadas repetidas, algo no
  prefixo está variando (timestamp, ordem de JSON não determinística).
- Isso reduz o custo de entrada de cada lote depois do primeiro para ~10%
  do valor cheio.

## 6. Saída estruturada (JSON garantido)

`translate_batch.py` deve usar `output_config.format` (não a prefill de
assistant, que dá erro 400 nos modelos atuais) para garantir JSON válido de
volta — schema com `original`, `traducao`, `categoria`, `flags` (ex.
`nao_traduzivel`, `ambiguo`) por string do lote. Isso fecha o ciclo com o
`validate_batch.py` da Fase 1 sem parsing frágil de texto solto.

## 7. Como aider e Claude Code se revezam na prática

**Regra de ferramenta única, já validada por incidente real:** aider edita
código, Claude Code (eu) gera conteúdo de relatório/tradução/decisão. Nunca
o contrário — foi exatamente o contrário que fragmentou arquivos na sessão
anterior.

### aider — configuração por papel

```bash
# Arquiteto/Tech Lead — manutenção de pipeline.py, preprocess.py, validate.py
aider --model anthropic/claude-sonnet-5 preprocess.py validate_batch.py

# Dev de Jogos Sênior — repack_db.py / repack_cpk.py, quando a Fase 0 começar
aider --model anthropic/claude-sonnet-5 repack_db.py repack_cpk.py
```

Requer `ANTHROPIC_API_KEY` no ambiente. Confira a sintaxe exata de nome de
modelo na documentação do aider antes de rodar — CLIs de terceiros mudam o
prefixo (`anthropic/claude-sonnet-5` vs. atalhos como `--model sonnet`) com
mais frequência que a API em si.

### Claude Code — orquestração e julgamento

Uso direto (esta sessão ou outra instância) para:
- Revisão de lotes traduzidos sinalizados como ambíguos.
- Extração e travamento de novos termos de glossário.
- Decisões de arquitetura do roadmap (quando avançar de fase, quando um
  risco técnico bloqueia o resto).
- Geração de relatórios/documentação — nunca via aider.

### O que **não** vira papel de CLI algum

Tradução em lote não é "aider com modelo X" nem "pedir pro Claude Code
traduzir no chat" — é um script Python (`translate_batch.py`, Fase 1) que
chama a API Anthropic diretamente com schema JSON. Motivo já registrado em
[02-FERRAMENTAS_E_TOOLING.md](02-FERRAMENTAS_E_TOOLING.md): ferramenta de
edição de arquivo (aider) e sessão de chat manual não são desenhadas para
loop de "lote de 400 strings → JSON de volta", e isso já causou incidente.

## 8. Onde isso encaixa no roadmap

Este documento organiza **quem/o quê/com qual modelo**, não muda a ordem das
fases em [06-ROADMAP.md](06-ROADMAP.md). Sequência inalterada:

1. **Fase 0 (bloqueador)** — provar round-trip de repack. Papel: Dev de
   Jogos Sênior + aider/Sonnet 5. **Não iniciada nesta sessão.**
2. **Fase 1** — construir `translate_batch.py`/`validate_batch.py`. Papel:
   Arquiteto + aider/Sonnet 5.
3. **Fases 2–6** — glossário, tradução em massa, revisão humana, QA em
   jogo, empacotamento — conforme já descrito no roadmap.

## Próximo passo

Confirmar esta estrutura de equipe/modelos e, quando você autorizar,
começar a **Fase 0** (escrever `repack_db.py`/`repack_cpk.py` e provar o
round-trip) — isso ainda não foi feito nesta sessão.
