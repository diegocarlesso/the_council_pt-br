# Checkpoint de Progresso — Tradução PT-BR

> Gerado automaticamente por `progress_report.py` em 2026-08-17 14:51. Não edite à mão — rode o script de novo depois de cada lote validado.

## Leia isto primeiro se você é uma sessão nova

Contexto completo em `pt-br/docs/` (comece por `00-VISAO_GERAL.md` e `06-ROADMAP.md`). O que importa pra continuar agora mesmo:

- **Decisão de 2026-08-03**: sem API key separada da Anthropic — a tradução em lote (Etapa 3) é feita **diretamente por uma sessão de Claude Code** atuando como Tradutor de Lote, usando o plano Pro do usuário, não uma chamada de API paga à parte. `translate_batch.py` continua existindo e funcional (com `--dry-run`) só para *montar* os lotes — quem traduz o conteúdo é a própria sessão de Claude Code.
- **Fase 0 (repack) e Fase 1 (tooling) estão concluídas** — ver `06-ROADMAP.md`. Achado crítico da Fase 0: um pequeno cluster de strings de `common_loc_en_0.db` ligado ao menu de boot precisa manter o mesmo tamanho em bytes do original (`menu_boot_suspect` no preprocessed.json) — `validate_batch.py` já corrige isso automaticamente.

### Como traduzir o próximo lote (repita este ciclo)

```bash
# 1. Monta o próximo lote ainda não traduzido desta categoria
python translate_batch.py --category "Diálogo" --batch-size 60 --max-batches 1 --dry-run
# -> escreve pt-br/batches/batch_<timestamp>_000_<categoria>.json
# com translation:"" para cada item — a sessão de Claude Code
# lê esse arquivo e PREENCHE o campo translation de cada item
# (seguindo pt-br/prompts/translation_system_prompt.md).

# 2. Depois de preencher as traduções no mesmo arquivo:
python validate_batch.py pt-br/batches/batch_<timestamp>_000_<categoria>.json
# -> QA automática; aprova pra translation_memory.json (status draft)
#    ou escreve pt-br/batches/rejected_*.json pra retraduzir.

# 3. Atualiza este checkpoint
python progress_report.py
```

Batch size recomendado: 50–100 quando a tradução é feita por uma sessão de Claude Code (qualidade > velocidade); 300–500 só faria sentido se voltarmos a usar chamada de API direta.

## Números gerais

- Strings únicas traduzíveis: **21806**
- Já resolvidas (draft ou approved na TM): **18467** (84.7%)
- Restam: **3339**
- Por status: {'approved': 13, 'draft': 18398, 'needs_review': 56}
- Não-traduzíveis (fora desta conta, resolvidos automaticamente no merge final — placeholder/comando/puzzle/glossário exato): 30

## Progresso por categoria

| Categoria | Traduzíveis | Resolvidas | Restam | % |
|---|---|---|---|---|
| Diálogo | 19293 | 15977 | 3316 | 82.8% |
| Sistema | 1789 | 1789 | 0 | 100.0% |
| Item | 693 | 693 | 0 | 100.0% |
| Teste | 23 | 0 | 23 | 0.0% |
| Descontinuado | 8 | 8 | 0 | 100.0% |

## Próximo lote sugerido

**Diálogo** — 3316 strings pendentes nesta categoria. Comando:
```bash
python translate_batch.py --category "Diálogo" --batch-size 60 --max-batches 1 --dry-run
```
