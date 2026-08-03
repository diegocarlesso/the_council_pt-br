"""
The Council - Pre-processamento da localizacao PT-BR (Fase 1, Etapa 1)

Le localization_dump.json e produz:
  - preprocessed.json: mesmo formato do dump (por arquivo/indice), com os
    campos novos `translatable`, `reason`, `category`, `canonical_id` em
    cada string (ver pt-br/docs/01-PIPELINE.md, Etapa 1), mais metadados
    de validacao (placeholders/tags/comandos/quebras de linha) e um indice
    top-level `_canonical` com uma entrada por string UNICA (o que
    realmente precisa ser mandado pra traducao).
  - glossary_candidates.json: termos capitalizados frequentes que ainda
    nao estao em pt-br/glossary.json, para voce revisar e travar
    manualmente (nunca travados automaticamente).

Regras de deteccao de nao-traduzivel (ver 01-PIPELINE.md e
05-GLOSSARIO_E_MEMORIA.md):
  - placeholder_only / tag_only / command_only: a string, depois de
    remover placeholders de formatacao (%d, %s, %1...), tags (<color>,
    <sprite>...) e comandos (|Nome(args)), nao sobra nenhum caractere
    alfabetico - e so estrutura, nunca vai pra IA.
  - puzzle_suspect: string curta que parece codigo de puzzle (letra
    isolada, ou palavra de comando tipo "Return"/"Change first letter" -
    ver pt-br/puzzle_codes.md). Sinalizada, NUNCA traduzida
    automaticamente - fica para confirmacao manual.
  - glossary_exact_match: a string inteira (case-insensitive, trim) e
    identica a um termo travado em glossary.json - a traducao ja existe,
    nao precisa de IA. Populamos direto de glossary.json.

Quebras de linha reais (\n, \t, \r) e placeholders de formatacao NAO
tornam uma string traduzivel=False por si so (ex.: uma carta longa com
varios \n internos e uma string perfeitamente traduzivel) - so contam
para o validador (validate_batch.py) conferir que a contagem bate depois
da traducao.
"""
import glob
import hashlib
import json
import os
import re
from collections import Counter, defaultdict

DUMP_PATH = "localization_dump.json"
GLOSSARY_PATH = "pt-br/glossary.json"
OUT_PREPROCESSED = "preprocessed.json"
OUT_CANDIDATES = "glossary_candidates.json"

# Strings de menu de boot que provaram exigir o MESMO TAMANHO EM BYTES da
# original (ver docs/04-RISCOS_TECNICOS.md, achado da Fase 0 - offset fixo
# calculado fora do .db, provavelmente em Gui_Main_0.cpk). So se aplica a
# common_loc_en_0.db. Lista conservadora: inclui o cluster inteiro da tela
# de boot (2 confirmadas quebrando + as adjacentes do mesmo cluster, ainda
# nao comprovadas individualmente, tratadas com cautela).
MENU_BOOT_SUSPECT_TEXTS = {
    "play", "savegame 1", "savegame 2", "savegame 3",
    "credits", "continue", "options", "settings", "new game",
}

FORMAT_PLACEHOLDER_RE = re.compile(r"%[a-zA-Z0-9]+")
TAG_RE = re.compile(r"<[^>]+>")
COMMAND_RE = re.compile(r"\|\w+\([^)]*\)")
LINEBREAK_CHARS = ("\n", "\t", "\r")

# Heuristica de puzzle: letra isolada (maiuscula ou minuscula) ou palavras
# de comando conhecidas de pt-br/puzzle_codes.md.
PUZZLE_COMMAND_WORDS = {"return", "change first letter", "change second letter",
                         "change third letter", "change fourth letter"}


def category_for_file(filename: str) -> str:
    base = os.path.basename(filename).lower()
    if base.startswith("common_loc_en"):
        return "Sistema"
    if base.startswith("chapter"):
        return "Item"
    if base.startswith("deprecated"):
        return "Descontinuado"
    if base.startswith("test_loc_en"):
        return "Teste"
    if base.startswith("q"):
        return "Diálogo"
    return "Outro"


def canonical_id_for(text: str) -> str:
    return "c_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def strip_mechanical(text: str) -> str:
    """Remove placeholders/tags/comandos/quebras de linha; sobra so o que seria texto humano."""
    t = FORMAT_PLACEHOLDER_RE.sub("", text)
    t = TAG_RE.sub("", t)
    t = COMMAND_RE.sub("", t)
    for ch in LINEBREAK_CHARS:
        t = t.replace(ch, "")
    return t.strip()


def is_puzzle_suspect(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) == 1 and stripped.isalpha():
        return True
    if stripped.lower() in PUZZLE_COMMAND_WORDS:
        return True
    return False


def classify(text: str, glossary_sources_lower: dict) -> dict:
    """Retorna dict com translatable/reason/placeholders/tags/commands/etc."""
    placeholders = FORMAT_PLACEHOLDER_RE.findall(text)
    tags = TAG_RE.findall(text)
    commands = COMMAND_RE.findall(text)
    linebreaks = {ch: text.count(ch) for ch in LINEBREAK_CHARS if ch in text}

    key = text.strip().lower()
    glossary_match = glossary_sources_lower.get(key)

    if glossary_match is not None:
        return {
            "translatable": False,
            "reason": "glossary_exact_match",
            "glossary_term": glossary_match["source"],
            "resolved_translation": glossary_match["target"],
            "placeholders": placeholders,
            "tags": tags,
            "commands": commands,
            "linebreaks": linebreaks,
        }

    if is_puzzle_suspect(text):
        return {
            "translatable": False,
            "reason": "puzzle_suspect",
            "glossary_term": None,
            "resolved_translation": text,
            "placeholders": placeholders,
            "tags": tags,
            "commands": commands,
            "linebreaks": linebreaks,
        }

    remainder = strip_mechanical(text)
    if not remainder and (placeholders or tags or commands):
        if placeholders and not tags and not commands:
            reason = "placeholder_only"
        elif tags and not placeholders and not commands:
            reason = "tag_only"
        elif commands and not placeholders and not tags:
            reason = "command_only"
        else:
            reason = "mechanical_only"
        return {
            "translatable": False,
            "reason": reason,
            "glossary_term": None,
            "resolved_translation": text,
            "placeholders": placeholders,
            "tags": tags,
            "commands": commands,
            "linebreaks": linebreaks,
        }

    if not remainder:
        # string vazia ou so espaco/pontuacao - nao traduzivel, mas nao e
        # nenhum dos casos acima (ex.: string vazia "")
        return {
            "translatable": False,
            "reason": "empty_or_no_content",
            "glossary_term": None,
            "resolved_translation": text,
            "placeholders": placeholders,
            "tags": tags,
            "commands": commands,
            "linebreaks": linebreaks,
        }

    return {
        "translatable": True,
        "reason": None,
        "glossary_term": None,
        "resolved_translation": None,
        "placeholders": placeholders,
        "tags": tags,
        "commands": commands,
        "linebreaks": linebreaks,
    }


CAPITALIZED_PHRASE_RE = re.compile(
    r"\b[A-Z][a-zA-Z']*(?:\s+(?:of|the|de|do|da)?\s*[A-Z][a-zA-Z']*){0,3}\b"
)
# palavras comuns que capitalizam por estarem no inicio de frase - excluir
# do candidato a glossario (ruido demais senao)
COMMON_SENTENCE_STARTERS = {
    "the", "i", "you", "he", "she", "it", "we", "they", "this", "that",
    "these", "those", "there", "here", "what", "when", "where", "why",
    "how", "who", "if", "but", "and", "so", "yes", "no", "ok", "well",
    "look", "listen", "wait", "please", "sorry", "thank", "thanks",
}


def extract_glossary_candidates(translatable_texts, existing_glossary_lower, min_count=3, top_n=200):
    counter = Counter()
    examples = defaultdict(list)
    for text in translatable_texts:
        for match in CAPITALIZED_PHRASE_RE.finditer(text):
            phrase = match.group().strip()
            if not phrase or len(phrase) < 3:
                continue
            key = phrase.lower()
            if key in existing_glossary_lower:
                continue
            if key in COMMON_SENTENCE_STARTERS:
                continue
            counter[phrase] += 1
            if len(examples[phrase]) < 3:
                examples[phrase].append(text[:120])

    candidates = [
        {"phrase": phrase, "count": count, "examples": examples[phrase]}
        for phrase, count in counter.items()
        if count >= min_count
    ]
    candidates.sort(key=lambda c: c["count"], reverse=True)
    return candidates[:top_n]


def main():
    dump = json.load(open(DUMP_PATH, encoding="utf-8"))
    glossary = json.load(open(GLOSSARY_PATH, encoding="utf-8"))
    glossary_sources_lower = {t["source"].strip().lower(): t for t in glossary["terms"]}

    canonical = {}
    translatable_texts_for_candidates = []

    total_strings = 0
    for fname, info in dump.items():
        category = category_for_file(fname)
        for s in info["strings"]:
            total_strings += 1
            text = s["original"]
            cid = canonical_id_for(text)
            s["canonical_id"] = cid
            s["category"] = category

            if cid not in canonical:
                cls = classify(text, glossary_sources_lower)
                is_menu_boot_suspect = (
                    category == "Sistema" and text.strip().lower() in MENU_BOOT_SUSPECT_TEXTS
                )
                canonical[cid] = {
                    "text": text,
                    "usage_count": 0,
                    "occurrences": [],
                    "categories": [],
                    "menu_boot_suspect": is_menu_boot_suspect,
                    **cls,
                }
                if cls["translatable"]:
                    translatable_texts_for_candidates.append(text)

            entry = canonical[cid]
            entry["usage_count"] += 1
            entry["occurrences"].append({"file": fname, "index": s["index"]})
            if category not in entry["categories"]:
                entry["categories"].append(category)

            s["translatable"] = canonical[cid]["translatable"]
            s["reason"] = canonical[cid]["reason"]

    # primary_category = categoria mais frequente entre as ocorrencias
    for cid, entry in canonical.items():
        cat_counts = Counter(occ["file"] for occ in entry["occurrences"])
        file_categories = Counter(category_for_file(f) for f in cat_counts)
        entry["primary_category"] = file_categories.most_common(1)[0][0]

    translatable_count = sum(1 for e in canonical.values() if e["translatable"])
    non_translatable_count = len(canonical) - translatable_count
    by_category = Counter(e["primary_category"] for e in canonical.values())
    by_reason = Counter(e["reason"] for e in canonical.values() if not e["translatable"])

    output = {
        "_meta": {
            "generated_from": DUMP_PATH,
            "total_strings": total_strings,
            "unique_strings": len(canonical),
            "translatable_unique": translatable_count,
            "non_translatable_unique": non_translatable_count,
            "by_primary_category": dict(by_category),
            "non_translatable_by_reason": dict(by_reason),
            "menu_boot_suspect_count": sum(1 for e in canonical.values() if e["menu_boot_suspect"]),
        },
        "_canonical": canonical,
    }
    # anexa os arquivos originais (com os campos novos por string) preservando o shape do dump
    output.update(dump)

    with open(OUT_PREPROCESSED, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    candidates = extract_glossary_candidates(
        translatable_texts_for_candidates, set(glossary_sources_lower.keys())
    )
    with open(OUT_CANDIDATES, "w", encoding="utf-8") as f:
        json.dump({"candidates": candidates}, f, indent=2, ensure_ascii=False)

    print("=== Pré-processamento concluído ===")
    print(f"Total de strings: {total_strings}")
    print(f"Strings únicas (canonical): {len(canonical)}")
    print(f"  Traduzíveis: {translatable_count}")
    print(f"  Não-traduzíveis: {non_translatable_count} {dict(by_reason)}")
    print(f"  Suspeitas de offset fixo de menu (mesmo tamanho obrigatório): "
          f"{output['_meta']['menu_boot_suspect_count']}")
    print(f"Por categoria primária: {dict(by_category)}")
    print(f"Candidatos a glossário gerados: {len(candidates)} (ver {OUT_CANDIDATES})")
    print(f"Saída: {OUT_PREPROCESSED}")


if __name__ == "__main__":
    main()
