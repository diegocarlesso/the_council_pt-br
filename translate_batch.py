"""
The Council - Tradutor de lote pt-BR (Fase 1, Etapa 3)

Le preprocessed.json (Etapa 1) + translation_memory.json (o que ja esta
resolvido - Etapa 2) + glossary.json, monta lotes de strings UNICAS e
TRADUZIVEIS agrupadas por categoria (nunca mistura UI com dialogo no
mesmo lote - contextos diferentes), chama a API da Anthropic com saida
estruturada (JSON garantido via output_config.format) e escreve o
resultado em pt-br/batches/ para o validate_batch.py (Etapa 4) revisar
antes de ir para a translation_memory.json.

Cascata de modelo por categoria (ver pt-br/docs/07-EQUIPE_E_MODELOS_ANTHROPIC.md):
  Sistema/Teste/Descontinuado -> Haiku 4.5 (baixo risco, textos curtos)
  Diálogo/Item/Outro          -> Sonnet 5 (motor principal de narrativa)
Use --model para forcar um modelo especifico (ex.: reprocessar um lote
rejeitado com Opus 5 para arbitragem).

Requer `pip install anthropic` e ANTHROPIC_API_KEY no ambiente para rodar
de verdade. Sem isso (ou com --dry-run), o script ainda monta e valida os
lotes, so nao chama a API - util para testar a logica de lotes sem gastar
tokens.

NUNCA escreve direto em translation_memory.json - isso e trabalho do
validate_batch.py, depois de checar QA (Etapa 4 do pipeline).
"""
import argparse
import json
import os
import re
import time
from collections import defaultdict

PREPROCESSED_PATH = "preprocessed.json"
TM_PATH = "pt-br/translation_memory.json"
GLOSSARY_PATH = "pt-br/glossary.json"
PROMPT_PATH = "pt-br/prompts/translation_system_prompt.md"
BATCHES_DIR = "pt-br/batches"

DEFAULT_MODEL_BY_CATEGORY = {
    "Sistema": "claude-haiku-4-5",
    "Teste": "claude-haiku-4-5",
    "Descontinuado": "claude-haiku-4-5",
    "Item": "claude-sonnet-5",
    "Diálogo": "claude-sonnet-5",
    "Outro": "claude-sonnet-5",
}


def load_system_prompt_template() -> str:
    text = open(PROMPT_PATH, encoding="utf-8").read()
    marker = "## 2. Papel: Tradutor de lote"
    idx = text.index(marker)
    section = text[idx:]
    m = re.search(r"```\n(.*?)\n```", section, re.DOTALL)
    if not m:
        raise ValueError(f"não encontrei o bloco de prompt do tradutor de lote em {PROMPT_PATH}")
    return m.group(1)


def format_glossary_block(glossary: dict) -> str:
    lines = []
    for term in glossary["terms"]:
        if not term.get("locked", True):
            continue
        lines.append(f"- {term['source']} → {term['target']} ({term['category']}): {term['definition']}")
    return "\n".join(lines)


def fit_to_byte_length(original: str, replacement: str) -> str:
    """Corta ou preenche com espaço a direita para bater exatamente o
    tamanho em bytes UTF-8 do original — necessário para o cluster de
    menu de boot (ver docs/04-RISCOS_TECNICOS.md, achado da Fase 0)."""
    orig_len = len(original.encode("utf-8"))
    rep_bytes = replacement.encode("utf-8")
    if len(rep_bytes) > orig_len:
        rep_bytes = rep_bytes[:orig_len]
        # evita cortar no meio de um caractere multibyte
        while rep_bytes and (rep_bytes[-1] & 0xC0) == 0x80:
            rep_bytes = rep_bytes[:-1]
    else:
        rep_bytes = rep_bytes + b" " * (orig_len - len(rep_bytes))
    return rep_bytes.decode("utf-8", errors="ignore")


def build_worklist(preprocessed: dict, tm: dict, category_filter: str | None):
    canonical = preprocessed["_canonical"]
    resolved_ids = {e["canonical_id"] for e in tm.get("entries", []) if "canonical_id" in e}

    worklist = []
    for cid, entry in canonical.items():
        if not entry["translatable"]:
            continue
        if cid in resolved_ids:
            continue
        if category_filter and entry["primary_category"] != category_filter:
            continue
        worklist.append((cid, entry))
    return worklist


def chunk_by_category(worklist, batch_size: int):
    by_cat = defaultdict(list)
    for cid, entry in worklist:
        by_cat[entry["primary_category"]].append((cid, entry))

    batches = []
    for cat, items in by_cat.items():
        for i in range(0, len(items), batch_size):
            batches.append((cat, items[i:i + batch_size]))
    return batches


def build_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "translation": {"type": "string"},
                        "needs_review": {"type": "boolean"},
                    },
                    "required": ["id", "translation", "needs_review"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["translations"],
        "additionalProperties": False,
    }


def call_model(model: str, system_prompt: str, batch_items: list) -> tuple:
    import anthropic

    client = anthropic.Anthropic()
    lote = [{"id": cid, "text": entry["text"]} for cid, entry in batch_items]

    with client.messages.stream(
        model=model,
        max_tokens=64000,
        system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        output_config={"format": {"type": "json_schema", "schema": build_schema()}},
        messages=[{"role": "user", "content": json.dumps(lote, ensure_ascii=False)}],
    ) as stream:
        message = stream.get_final_message()

    text_block = next(b.text for b in message.content if b.type == "text")
    data = json.loads(text_block)
    return data["translations"], message.usage


def process_batch(category: str, items: list, model: str, system_prompt: str, dry_run: bool):
    by_id = dict(items)

    if dry_run:
        translations = [
            {"id": cid, "translation": "", "needs_review": True}
            for cid, _entry in items
        ]
        usage = None
    else:
        translations, usage = call_model(model, system_prompt, items)

    results = []
    for t in translations:
        cid = t["id"]
        entry = by_id.get(cid)
        if entry is None:
            continue  # id que a IA inventou/alterou - ignorado, sera detectado como faltante na validação
        translation = t["translation"]
        if entry["menu_boot_suspect"] and translation:
            translation = fit_to_byte_length(entry["text"], translation)
        results.append({
            "canonical_id": cid,
            "original": entry["text"],
            "translation": translation,
            "needs_review": t["needs_review"],
            "category": category,
            "model": model,
            "dry_run": dry_run,
        })

    # canonical_ids que a IA nao devolveu (resposta incompleta)
    returned_ids = {t["id"] for t in translations}
    for cid, entry in items:
        if cid not in returned_ids:
            results.append({
                "canonical_id": cid,
                "original": entry["text"],
                "translation": None,
                "needs_review": True,
                "category": category,
                "model": model,
                "dry_run": dry_run,
                "error": "id ausente na resposta do modelo",
            })

    return results, usage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", default=None, help="Só processa esta categoria primária")
    parser.add_argument("--batch-size", type=int, default=400)
    parser.add_argument("--max-batches", type=int, default=None, help="Limite de lotes (para teste)")
    parser.add_argument("--model", default=None, help="Força um modelo específico para todos os lotes")
    parser.add_argument("--dry-run", action="store_true", help="Monta os lotes mas não chama a API")
    args = parser.parse_args()

    preprocessed = json.load(open(PREPROCESSED_PATH, encoding="utf-8"))
    tm = json.load(open(TM_PATH, encoding="utf-8"))
    glossary = json.load(open(GLOSSARY_PATH, encoding="utf-8"))

    template = load_system_prompt_template()
    glossary_block = format_glossary_block(glossary)
    system_prompt = template.replace("{GLOSSARIO}", glossary_block)
    system_prompt = system_prompt.split("LOTE A TRADUZIR")[0].strip()

    worklist = build_worklist(preprocessed, tm, args.category)
    batches = chunk_by_category(worklist, args.batch_size)

    print(f"Worklist: {len(worklist)} strings únicas a traduzir, em {len(batches)} lote(s).")

    if args.max_batches is not None:
        batches = batches[:args.max_batches]

    os.makedirs(BATCHES_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    for i, (category, items) in enumerate(batches):
        model = args.model or DEFAULT_MODEL_BY_CATEGORY.get(category, "claude-sonnet-5")
        print(f"[lote {i + 1}/{len(batches)}] categoria={category} modelo={model} strings={len(items)}"
              f"{' (dry-run)' if args.dry_run else ''}")

        results, usage = process_batch(category, items, model, system_prompt, args.dry_run)

        out_path = os.path.join(BATCHES_DIR, f"batch_{timestamp}_{i:03d}_{category}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "category": category,
                "model": model,
                "dry_run": args.dry_run,
                "usage": dict(usage) if usage else None,
                "results": results,
            }, f, indent=2, ensure_ascii=False)
        print(f"  -> {out_path} ({len(results)} resultados)")

    if not batches:
        print("Nada a traduzir — worklist vazia (tudo já está na translation_memory.json ou filtro não bateu nada).")


if __name__ == "__main__":
    main()
