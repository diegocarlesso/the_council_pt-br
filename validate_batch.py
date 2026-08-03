"""
The Council - Validador de lote pt-BR (Fase 1, Etapa 4)

Le um ou mais arquivos de resultado gerados por translate_batch.py
(pt-br/batches/batch_*.json), roda QA automatica em cima de cada
traducao ANTES de aceitar (ver pt-br/docs/01-PIPELINE.md, Etapa 4), e:
  - o que PASSA vira entrada em translation_memory.json com
    status="draft" (pronto pra revisao humana - Etapa 5, nunca
    "approved" automaticamente);
  - o que FALHA vai para um arquivo de rejeitados (mesma pasta), com o
    motivo de cada falha, para retraducao (ex.: rodando translate_batch.py
    de novo so para esses ids, com --model claude-opus-5 para arbitragem).

Checagens (todas comparando original vs traducao):
  - placeholders de formatacao (%d, %s, %1...) - mesma contagem exata
  - tags (<color>, <sprite>...) - mesma contagem exata
  - comandos (|Nome(args)) - mesma contagem exata
  - quebras de linha reais (\n, \t, \r) - mesma contagem por tipo
  - string vazia onde o original nao era vazio
  - termos travados do glossario: se o original contem um termo (source),
    a traducao deve conter o target correspondente (comparacao literal,
    case-insensitive)
  - cluster de menu de boot (menu_boot_suspect): traducao deve ter
    EXATAMENTE o mesmo tamanho em bytes UTF-8 do original (ver
    docs/04-RISCOS_TECNICOS.md) - autocorrigido em vez de rejeitado, ja
    que e um ajuste mecanico deterministico, nao uma questao de qualidade
  - crescimento de tamanho anormal (>40% mais longo que o original) -
    warning, nao reprova sozinho (pt-BR legitimamente fica mais longo)
"""
import argparse
import glob
import json
import os
import re
import time
from collections import Counter

PREPROCESSED_PATH = "preprocessed.json"
TM_PATH = "pt-br/translation_memory.json"
GLOSSARY_PATH = "pt-br/glossary.json"
BATCHES_DIR = "pt-br/batches"

FORMAT_PLACEHOLDER_RE = re.compile(r"%[a-zA-Z0-9]+")
TAG_RE = re.compile(r"<[^>]+>")
COMMAND_RE = re.compile(r"\|\w+\([^)]*\)")
LINEBREAK_CHARS = ("\n", "\t", "\r")

LENGTH_GROWTH_WARNING_THRESHOLD = 1.40


def fit_to_byte_length(original: str, replacement: str) -> str:
    orig_len = len(original.encode("utf-8"))
    rep_bytes = replacement.encode("utf-8")
    if len(rep_bytes) > orig_len:
        rep_bytes = rep_bytes[:orig_len]
        while rep_bytes and (rep_bytes[-1] & 0xC0) == 0x80:
            rep_bytes = rep_bytes[:-1]
    else:
        rep_bytes = rep_bytes + b" " * (orig_len - len(rep_bytes))
    return rep_bytes.decode("utf-8", errors="ignore")


def check_item(original: str, translation: str, glossary_terms: list, menu_boot_suspect: bool):
    """Retorna (errors: list[str], warnings: list[str], fixed_translation: str)."""
    errors = []
    warnings = []
    fixed = translation

    if translation is None:
        return ["traducao ausente (id nao retornado ou erro no lote)"], [], None

    if original.strip() and not translation.strip():
        errors.append("tradução vazia para original não-vazio")
        return errors, warnings, fixed

    orig_placeholders = Counter(FORMAT_PLACEHOLDER_RE.findall(original))
    trans_placeholders = Counter(FORMAT_PLACEHOLDER_RE.findall(translation))
    if orig_placeholders != trans_placeholders:
        errors.append(f"placeholders divergem: original={dict(orig_placeholders)} tradução={dict(trans_placeholders)}")

    orig_tags = Counter(TAG_RE.findall(original))
    trans_tags = Counter(TAG_RE.findall(translation))
    if orig_tags != trans_tags:
        errors.append(f"tags divergem: original={dict(orig_tags)} tradução={dict(trans_tags)}")

    orig_commands = Counter(COMMAND_RE.findall(original))
    trans_commands = Counter(COMMAND_RE.findall(translation))
    if orig_commands != trans_commands:
        errors.append(f"comandos divergem: original={dict(orig_commands)} tradução={dict(trans_commands)}")

    for ch, label in zip(LINEBREAK_CHARS, ("\\n", "\\t", "\\r")):
        if original.count(ch) != translation.count(ch):
            errors.append(
                f"quebra de linha '{label}' diverge: original={original.count(ch)} "
                f"tradução={translation.count(ch)}"
            )

    original_lower = original.lower()
    translation_lower = translation.lower()
    for term in glossary_terms:
        source = term["source"]
        target = term["target"]
        if source.lower() in original_lower and target.lower() not in translation_lower:
            errors.append(f"termo travado '{source}' não respeitado (esperado '{target}' na tradução)")

    if menu_boot_suspect:
        orig_len = len(original.encode("utf-8"))
        trans_len = len(translation.encode("utf-8"))
        if trans_len != orig_len:
            fixed = fit_to_byte_length(original, translation)
            warnings.append(
                f"cluster de menu de boot: tamanho ajustado automaticamente "
                f"({trans_len}b -> {orig_len}b) para evitar o bug de offset fixo"
            )

    if original.strip():
        growth = len(translation) / max(1, len(original))
        if growth > LENGTH_GROWTH_WARNING_THRESHOLD:
            warnings.append(f"tradução {growth:.0%} do tamanho do original (acima do esperado ~15-20%)")

    return errors, warnings, fixed


def upsert_tm_entry(tm: dict, canonical_id: str, original: str, translation: str, category: str, usage_count: int):
    for entry in tm["entries"]:
        if entry.get("canonical_id") == canonical_id:
            if entry.get("status") == "approved":
                return False  # nunca sobrescreve algo ja aprovado por humano
            entry["target"] = translation
            entry["category"] = category
            entry["status"] = "draft"
            entry["usage_count"] = usage_count
            return True
    tm["entries"].append({
        "canonical_id": canonical_id,
        "source": original,
        "target": translation,
        "context": category,
        "category": category,
        "status": "draft",
        "usage_count": usage_count,
    })
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_files", nargs="*", help="Arquivos de lote específicos (padrão: todos em pt-br/batches/)")
    args = parser.parse_args()

    preprocessed = json.load(open(PREPROCESSED_PATH, encoding="utf-8"))
    canonical = preprocessed["_canonical"]
    glossary = json.load(open(GLOSSARY_PATH, encoding="utf-8"))
    glossary_terms = [t for t in glossary["terms"] if t.get("locked", True)]
    tm = json.load(open(TM_PATH, encoding="utf-8"))

    files = args.batch_files or sorted(glob.glob(os.path.join(BATCHES_DIR, "batch_*.json")))
    if not files:
        print(f"Nenhum arquivo de lote encontrado em {BATCHES_DIR}/ — rode translate_batch.py primeiro.")
        return

    total_pass = 0
    total_fail = 0
    total_warnings = 0
    rejected_all = []

    for path in files:
        batch = json.load(open(path, encoding="utf-8"))
        rejected = []

        for item in batch["results"]:
            cid = item["canonical_id"]
            entry = canonical.get(cid)
            if entry is None:
                rejected.append({**item, "errors": [f"canonical_id '{cid}' não existe em {PREPROCESSED_PATH}"]})
                total_fail += 1
                continue

            errors, warnings, fixed_translation = check_item(
                item["original"], item["translation"], glossary_terms, entry["menu_boot_suspect"]
            )

            if errors:
                rejected.append({**item, "errors": errors})
                total_fail += 1
                continue

            total_warnings += len(warnings)
            upsert_tm_entry(tm, cid, item["original"], fixed_translation, item["category"], entry["usage_count"])
            total_pass += 1

        if rejected:
            rejected_all.extend(rejected)

        print(f"{os.path.basename(path)}: {len(batch['results']) - len(rejected)} ok, {len(rejected)} rejeitados")

    with open(TM_PATH, "w", encoding="utf-8") as f:
        json.dump(tm, f, indent=2, ensure_ascii=False)

    if rejected_all:
        os.makedirs(BATCHES_DIR, exist_ok=True)
        rejected_path = os.path.join(BATCHES_DIR, f"rejected_{time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(rejected_path, "w", encoding="utf-8") as f:
            json.dump({"rejected": rejected_all}, f, indent=2, ensure_ascii=False)
        print(f"\n{len(rejected_all)} strings rejeitadas -> {rejected_path} (retraduzir)")

    print(f"\nTotal: {total_pass} aprovadas (status=draft na TM), {total_fail} rejeitadas, "
          f"{total_warnings} avisos (não bloqueiam, ex. crescimento de tamanho, ajuste de menu de boot).")


if __name__ == "__main__":
    main()
