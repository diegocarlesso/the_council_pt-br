"""
The Council - Gera um Loca_en_Main_0.cpk de teste para a Fase 0 (visual)

Traduz um punhado de strings de MENU (NEW GAME/CONTINUE/OPTIONS/SETTINGS/
CREDITS) em common_loc_en_0.db — arquivo de sistema/UI reaproveitado no
jogo inteiro, sem risco de spoiler de historia — e reempacota um
Loca_en_Main_0.cpk inteiro com essa unica mudanca, para verificacao visual
manual no jogo (o motivo de escolher menu, nao dialogo: e a tela que
aparece imediatamente ao abrir o jogo, sem precisar avançar save nenhum).

NAO sobrescreve o .cpk original. Escreve em Loca_en_Main_0_pt_test.cpk ao
lado do original. O passo de backup + substituicao no jogo de verdade e
feito separadamente (ver instrucoes no chat), nunca automaticamente aqui.
"""
import json

from repack_db import read_db_parts, repack_db
from repack_cpk import read_cpk, repack_cpk, MAGIC

DUMP_PATH = "localization_dump.json"
TARGET_ENTRY = "data/localization/common_loc_en_0.db"
CPK_PATH = "Loca_en_Main_0.cpk"
OUT_PATH = "Loca_en_Main_0_pt_test.cpk"

# Traducoes de teste (so strings de menu curtas, sem placeholder algum).
# Atualizado apos confirmar visualmente que a tela de titulo real usa
# "PLAY" + "Savegame N", nao "NEW GAME"/"CONTINUE" (que devem aparecer em
# outra tela/estado do jogo) — mantidos os dois conjuntos.
TRANSLATIONS = {
    "credits": "CRÉDITOS",
    "continue": "CONTINUAR",
    "settings": "CONFIGURAÇÕES",
    "new game": "NOVO JOGO",
    "options": "OPÇÕES",
    "play": "JOGAR",
    "savegame 1": "Jogo Salvo 1",
    "savegame 2": "Jogo Salvo 2",
    "savegame 3": "Jogo Salvo 3",
}


def translated(original_text: str) -> str:
    key = original_text.strip().lower()
    text = TRANSLATIONS[key]
    if key.startswith("savegame"):
        return text
    return text if original_text.isupper() else text.title()


def main():
    dump = json.load(open(DUMP_PATH, encoding="utf-8"))
    key = [k for k in dump if "common_loc_en_0" in k][0]
    info = dump[key]

    replacements = {}
    for s in info["strings"]:
        t = s["original"].strip().lower()
        if t in TRANSLATIONS:
            replacements[s["index"]] = translated(s["original"])

    print(f"Traduzindo {len(replacements)} strings de menu em {TARGET_ENTRY}:")
    for idx, new_text in sorted(replacements.items()):
        print(f"  [{idx}] {info['strings'][idx]['original']!r} -> {new_text!r}")

    with open(f"Extracted_Loc_En/{TARGET_ENTRY}", "rb") as f:
        original_db = f.read()

    new_db = repack_db(original_db, replacements)

    # Confere round-trip: as strings NAO traduzidas continuam identicas.
    _, original_parts = read_db_parts(original_db)
    _, new_parts = read_db_parts(new_db)
    assert len(original_parts) == len(new_parts)
    for i, (orig, new) in enumerate(zip(original_parts, new_parts)):
        if i not in replacements:
            assert orig == new, f"string {i} mudou sem querer"

    new_cpk = repack_cpk(CPK_PATH, {TARGET_ENTRY: new_db})
    assert new_cpk[:4] == MAGIC

    with open(OUT_PATH, "wb") as f:
        f.write(new_cpk)

    # Verificacao estrutural final: reparseia o .cpk gerado do disco.
    root_dir, entries, data_by_name = read_cpk(OUT_PATH)
    _, orig_entries, orig_data = read_cpk(CPK_PATH)
    assert len(entries) == len(orig_entries) == 26
    changed = {TARGET_ENTRY}
    for e in entries:
        if e["name"] not in changed:
            assert data_by_name[e["name"]] == orig_data[e["name"]], f"{e['name']} mudou sem querer"

    print()
    print(f"OK: {OUT_PATH} gerado ({len(new_cpk)} bytes, original tinha "
          f"{len(open(CPK_PATH, 'rb').read())} bytes), 26 entradas, "
          f"25 outras entradas byte-identicas ao original.")


if __name__ == "__main__":
    main()
