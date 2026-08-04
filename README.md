# The Council — Localização PT-BR

Projeto de tradução para Português do Brasil do jogo **The Council**
(Cyanide/Big Bad Wolf/Focus Entertainment, 2018), um jogo de mistério,
investigação, intriga política e ocultismo ambientado na França do
século XVIII.

Este repositório contém **apenas os artefatos de tradução** (memória de
tradução, glossário, documentação e ferramentas) — nenhum asset original
do jogo (`.cpk`, `.cpkh`, texturas, modelos, áudio) é versionado aqui.

## Status atual

> Ver [pt-br/PROGRESS.md](pt-br/PROGRESS.md) para o checkpoint completo e
> atualizado automaticamente após cada lote validado.

| Categoria | Traduzíveis | Resolvidas | % |
|---|---|---|---|
| Sistema | 1.789 | 1.789 | 100% ✅ |
| Item | 693 | 693 | 100% ✅ |
| Diálogo | 19.293 | 0 | 0% ⏳ |
| Teste | 23 | 0 | 0% ⏳ |
| Descontinuado | 8 | 0 | 0% ⏳ |
| **Total** | **21.806** | **2.482** | **11,4%** |

## Estrutura do projeto

```
Data/Packages/
├── pt-br/
│   ├── translation_memory.json   # Memória de tradução (fonte da verdade)
│   ├── glossary.json             # Termos travados (glossário obrigatório)
│   ├── PROGRESS.md               # Checkpoint auto-gerado
│   ├── prompts/
│   │   └── translation_system_prompt.md  # Prompt de sistema do tradutor
│   ├── docs/                     # Documentação de arquitetura da pipeline
│   │   ├── 00-VISAO_GERAL.md
│   │   ├── 01-PIPELINE.md
│   │   ├── 02-FERRAMENTAS_E_TOOLING.md
│   │   ├── 03-MODELOS_IA_E_CUSTOS.md
│   │   ├── 04-RISCOS_TECNICOS.md
│   │   ├── 05-GLOSSARIO_E_MEMORIA.md
│   │   ├── 06-ROADMAP.md
│   │   └── 07-EQUIPE_E_MODELOS_ANTHROPIC.md
│   └── batches/                  # (gitignored) lotes brutos em processamento
├── translate_batch.py            # Monta lotes de strings não traduzidas
├── validate_batch.py             # QA automática de lotes traduzidos
├── progress_report.py            # Atualiza PROGRESS.md
├── preprocess.py                 # Gera preprocessed.json a partir do dump
└── list_strings.py               # Utilitário de inspeção de .db extraído
```

## Pipeline

1. **Extração** — `unpack_cpk.py` + `dump_texts.py` geram
   `localization_dump.json` a partir dos `.cpk`/`.db` originais.
2. **Pré-processamento** — `preprocess.py` deduplica, categoriza e marca
   o que não é traduzível (placeholders, tags, comandos, códigos de
   puzzle) → `preprocessed.json`.
3. **Tradução em lote** — `translate_batch.py --dry-run` monta lotes de
   ~60 strings por categoria; uma sessão de Claude Code (ou humano)
   preenche o campo `translation` de cada item, seguindo
   `pt-br/prompts/translation_system_prompt.md` e o glossário travado.
4. **QA automática** — `validate_batch.py` valida placeholders, tags,
   comandos, contagem de quebras de linha, termos de glossário
   (word-boundary regex) e limites de bytes (menu de boot); lotes
   aprovados entram em `translation_memory.json` como `status: draft`.
5. **Revisão humana** — aprovação lote a lote promove `draft` →
   `approved`.
6. **Reinjeção** (não implementada ainda) — merge da TM aprovada de
   volta no dump e repack `.json` → `.db` → `.cpk`.
7. **QA em jogo** — playtest com o pacote pt-BR injetado.

Ver [pt-br/docs/01-PIPELINE.md](pt-br/docs/01-PIPELINE.md) para o
detalhamento completo de cada etapa.

## Glossário — termos travados (destaques)

Perícias (árvores Detetive/Diplomata/Ocultista): Agilidade, Erudição,
Etiqueta, Linguística, Manipulação, Ocultismo, Psicologia, Lógica,
Ciência, Vigilância, Subterfúgios, Distração (não confundir com
"diversão"), Questionamento (não confundir com "Interrogatório"),
Convicção.

Termos narrativos: The Nightmare → O Pesadelo · Holy Lance → Lança
Sagrada · Golden Order → Ordem Dourada · Daemon (mantido em inglês) ·
Ether → Éter.

Nomes próprios travados (nunca traduzir os títulos): Lord Mortimer,
Sir Gregory Holm.

Locais: Grand Hall → Grande Salão · Small Salon → Pequeno Salão ·
Conference Room → Sala de Conferências · Dining Room → Sala de Jantar ·
Portrait Gallery → Galeria de Retratos.

Registro: nunca usar a conjugação arcaica de "vós" mesmo em cartas
formais do século XVIII — sempre tratamento formal moderno
("você"/"o senhor"/"a senhora").

Lista completa e definições em
[pt-br/glossary.json](pt-br/glossary.json) e
[pt-br/docs/05-GLOSSARIO_E_MEMORIA.md](pt-br/docs/05-GLOSSARIO_E_MEMORIA.md).

## Como continuar a tradução

```bash
# 1. Monta o próximo lote da categoria
python translate_batch.py --category "Diálogo" --batch-size 60 --max-batches 1 --dry-run

# 2. Preenche translation:"" em cada item do lote gerado

# 3. Valida o lote
python validate_batch.py pt-br/batches/batch_<timestamp>_000_<categoria>.json

# 4. Atualiza o checkpoint
python progress_report.py
```

## Licença

Trabalho de tradução derivado de **The Council**
(© Cyanide/Big Bad Wolf/Focus Entertainment). Este repositório contém
somente a camada de artefatos de tradução — nenhum asset original,
código-fonte do jogo ou dado proprietário é distribuído aqui.
