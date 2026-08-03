"""
The Council - Checkpoint de progresso da tradução pt-BR

Le preprocessed.json + translation_memory.json e (re)gera
pt-br/PROGRESS.md - o "leia isto primeiro" para qualquer sessão nova
(Claude Code ou humana) retomar rapidamente sem precisar re-derivar o
estado do projeto lendo tudo de novo.

Rode depois de cada validate_batch.py bem-sucedido.
"""
import datetime
import json
from collections import Counter

PREPROCESSED_PATH = "preprocessed.json"
TM_PATH = "pt-br/translation_memory.json"
OUT_PATH = "pt-br/PROGRESS.md"

# Ordem recomendada de ataque por categoria (ver docs/06-ROADMAP.md Fase 2:
# Sistema primeiro - populariza glossário, baixo risco de spoiler).
CATEGORY_PRIORITY = ["Sistema", "Item", "Diálogo", "Outro", "Teste", "Descontinuado"]


def main():
    preprocessed = json.load(open(PREPROCESSED_PATH, encoding="utf-8"))
    canonical = preprocessed["_canonical"]
    tm = json.load(open(TM_PATH, encoding="utf-8"))
    tm_by_id = {e["canonical_id"]: e for e in tm["entries"] if "canonical_id" in e}

    by_category_translatable = Counter()
    by_category_done = Counter()
    status_counts = Counter()

    for cid, entry in canonical.items():
        if not entry["translatable"]:
            continue
        cat = entry["primary_category"]
        by_category_translatable[cat] += 1
        if cid in tm_by_id:
            by_category_done[cat] += 1
            status_counts[tm_by_id[cid]["status"]] += 1

    total_translatable = sum(by_category_translatable.values())
    total_done = sum(by_category_done.values())
    total_non_translatable = sum(1 for e in canonical.values() if not e["translatable"])

    next_cat, next_pending = None, 0
    for cat in CATEGORY_PRIORITY:
        pending = by_category_translatable.get(cat, 0) - by_category_done.get(cat, 0)
        if pending > 0:
            next_cat, next_pending = cat, pending
            break

    lines = [
        "# Checkpoint de Progresso — Tradução PT-BR",
        "",
        f"> Gerado automaticamente por `progress_report.py` em "
        f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}. Não edite à mão — "
        f"rode o script de novo depois de cada lote validado.",
        "",
        "## Leia isto primeiro se você é uma sessão nova",
        "",
        "Contexto completo em `pt-br/docs/` (comece por `00-VISAO_GERAL.md` e "
        "`06-ROADMAP.md`). O que importa pra continuar agora mesmo:",
        "",
        "- **Decisão de 2026-08-03**: sem API key separada da Anthropic — a tradução "
        "em lote (Etapa 3) é feita **diretamente por uma sessão de Claude Code** "
        "atuando como Tradutor de Lote, usando o plano Pro do usuário, não uma "
        "chamada de API paga à parte. `translate_batch.py` continua existindo e "
        "funcional (com `--dry-run`) só para *montar* os lotes — quem traduz o "
        "conteúdo é a própria sessão de Claude Code.",
        "- **Fase 0 (repack) e Fase 1 (tooling) estão concluídas** — ver `06-ROADMAP.md`. "
        "Achado crítico da Fase 0: um pequeno cluster de strings de "
        "`common_loc_en_0.db` ligado ao menu de boot precisa manter o mesmo "
        "tamanho em bytes do original (`menu_boot_suspect` no preprocessed.json) — "
        "`validate_batch.py` já corrige isso automaticamente.",
        "",
        "### Como traduzir o próximo lote (repita este ciclo)",
        "",
        "```bash",
        "# 1. Monta o próximo lote ainda não traduzido desta categoria\n"
        f"python translate_batch.py --category \"{next_cat or '<categoria>'}\" "
        "--batch-size 60 --max-batches 1 --dry-run",
        "# -> escreve pt-br/batches/batch_<timestamp>_000_<categoria>.json",
        "# com translation:\"\" para cada item — a sessão de Claude Code",
        "# lê esse arquivo e PREENCHE o campo translation de cada item",
        "# (seguindo pt-br/prompts/translation_system_prompt.md).",
        "",
        "# 2. Depois de preencher as traduções no mesmo arquivo:",
        "python validate_batch.py pt-br/batches/batch_<timestamp>_000_<categoria>.json",
        "# -> QA automática; aprova pra translation_memory.json (status draft)",
        "#    ou escreve pt-br/batches/rejected_*.json pra retraduzir.",
        "",
        "# 3. Atualiza este checkpoint",
        "python progress_report.py",
        "```",
        "",
        "Batch size recomendado: 50–100 quando a tradução é feita por uma sessão "
        "de Claude Code (qualidade > velocidade); 300–500 só faria sentido se "
        "voltarmos a usar chamada de API direta.",
        "",
        "## Números gerais",
        "",
        f"- Strings únicas traduzíveis: **{total_translatable}**",
        f"- Já resolvidas (draft ou approved na TM): **{total_done}** "
        f"({total_done / total_translatable:.1%})",
        f"- Restam: **{total_translatable - total_done}**",
        f"- Por status: {dict(status_counts)}",
        f"- Não-traduzíveis (fora desta conta, resolvidos automaticamente no merge "
        f"final — placeholder/comando/puzzle/glossário exato): {total_non_translatable}",
        "",
        "## Progresso por categoria",
        "",
        "| Categoria | Traduzíveis | Resolvidas | Restam | % |",
        "|---|---|---|---|---|",
    ]

    for cat in sorted(by_category_translatable, key=lambda c: -by_category_translatable[c]):
        trans = by_category_translatable[cat]
        done = by_category_done.get(cat, 0)
        pct = done / trans if trans else 0
        lines.append(f"| {cat} | {trans} | {done} | {trans - done} | {pct:.1%} |")

    lines += ["", "## Próximo lote sugerido", ""]
    if next_cat:
        lines.append(
            f"**{next_cat}** — {next_pending} strings pendentes nesta categoria. Comando:"
        )
        lines.append("```bash")
        lines.append(
            f'python translate_batch.py --category "{next_cat}" --batch-size 60 '
            f"--max-batches 1 --dry-run"
        )
        lines.append("```")
    else:
        lines.append(
            "Todas as categorias traduzíveis estão com trabalho de IA/sessão concluído! "
            "Hora de revisão humana (Etapa 5) e depois reinjeção (Etapa 6)."
        )

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Checkpoint atualizado: {OUT_PATH}")
    print(f"Total: {total_done}/{total_translatable} ({total_done / total_translatable:.1%})")
    if next_cat:
        print(f"Próxima categoria sugerida: {next_cat} ({next_pending} pendentes)")


if __name__ == "__main__":
    main()
