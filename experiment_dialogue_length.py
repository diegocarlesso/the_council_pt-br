"""
Experimento de diagnostico (Fase 0) - parte 2: o bug de offset fixo afeta
SO os rotulos do menu principal, ou TAMBEM afeta textos de mecanica de
jogo (popups tipo "Vulnerability revealed") que aparecem durante o jogo
normal, fora do menu?

Estrategia: mantem as strings de MENU com o MESMO TAMANHO EM BYTES do
original (ja provado que funciona no experimento anterior), e traduz as
strings de MECANICA DE JOGO ("Character/Immunity/Vulnerability revealed",
"Character traits revealed") com texto em pt-BR livre, deliberadamente BEM
mais longo que o original - sem nenhuma restricao de tamanho.

Se essas strings de mecanica aparecerem corretas no jogo (mesmo mais
longas), confirma que o offset fixo e um caso especial do menu principal
(carregado antes do sistema normal de localizacao estar de pe) e NAO um
problema geral do jogo - ou seja, o resto da traducao (que e a imensa
maioria do corpus, falas de dialogo/quest) pode ser traduzido livremente.
"""
import json

from repack_db import read_db_parts, repack_db
from repack_cpk import repack_cpk, MAGIC

CPK_PATH = "Loca_en_Main_0.cpk"
TARGET_ENTRY = "data/localization/common_loc_en_0.db"
OUT_PATH = "Loca_en_Main_0_pt_test.cpk"

# Mesmas traducoes do menu, ja provadas funcionando (mesmo tamanho em bytes).
MENU_RAW_TRANSLATIONS = {
    "credits": "CREDITO",
    "continue": "CONTINUAR",
    "settings": "CONFIGURA",
    "new game": "JOGO NOVO",
    "options": "OPCOES ",
    "play": "JOGA",
    "savegame 1": "JOGO SALV1",
    "savegame 2": "JOGO SALV2",
    "savegame 3": "JOGO SALV3",
}

# Strings de MECANICA DE JOGO (aparecem durante conversas normais, nao no
# menu) - traduzidas livremente, BEM mais longas que o original de proposito.
GAMEPLAY_TRANSLATIONS = {
    "character revealed": "Personagem completamente revelado ao jogador",
    "immunity revealed": "Uma imunidade importante foi revelada agora",
    "vulnerability revealed": "Uma vulnerabilidade crucial foi revelada",
    "character traits revealed": "Todos os traços de personalidade do personagem foram revelados",
}


def fit_to_byte_length(original: str, replacement: str) -> str:
    orig_len = len(original.encode("utf-8"))
    rep_bytes = replacement.encode("utf-8")
    if len(rep_bytes) > orig_len:
        rep_bytes = rep_bytes[:orig_len]
    else:
        rep_bytes = rep_bytes + b" " * (orig_len - len(rep_bytes))
    return rep_bytes.decode("utf-8")


def main():
    dump = json.load(open("localization_dump.json", encoding="utf-8"))
    key = [k for k in dump if "common_loc_en_0" in k][0]
    info = dump[key]

    replacements = {}
    for s in info["strings"]:
        t = s["original"].strip().lower()
        if t in MENU_RAW_TRANSLATIONS:
            raw = MENU_RAW_TRANSLATIONS[t]
            text = raw if s["original"].isupper() or t.startswith("savegame") else raw.title()
            replacements[s["index"]] = fit_to_byte_length(s["original"], text)
        elif t in GAMEPLAY_TRANSLATIONS:
            replacements[s["index"]] = GAMEPLAY_TRANSLATIONS[t]

    print(f"Traduzindo {len(replacements)} strings ({len(MENU_RAW_TRANSLATIONS)} de menu, "
          f"tamanho fixo; {len(GAMEPLAY_TRANSLATIONS)} de mecanica de jogo, tamanho livre):")
    for idx, new_text in sorted(replacements.items()):
        orig = info["strings"][idx]["original"]
        tag = "MENU" if orig.strip().lower() in MENU_RAW_TRANSLATIONS else "JOGO"
        print(f"  [{tag}][{idx}] {orig!r} ({len(orig.encode('utf-8'))}b) -> "
              f"{new_text!r} ({len(new_text.encode('utf-8'))}b)")

    with open(f"Extracted_Loc_En/{TARGET_ENTRY}", "rb") as f:
        original_db = f.read()

    new_db = repack_db(original_db, replacements)

    _, original_parts = read_db_parts(original_db)
    _, new_parts = read_db_parts(new_db)
    assert len(original_parts) == len(new_parts), "contagem de strings mudou"

    new_cpk = repack_cpk(CPK_PATH, {TARGET_ENTRY: new_db})
    assert new_cpk[:4] == MAGIC

    with open(OUT_PATH, "wb") as f:
        f.write(new_cpk)

    print(f"\nOK: {OUT_PATH} gerado ({len(new_cpk)} bytes; original tinha "
          f"{len(open(CPK_PATH, 'rb').read())} bytes).")
    print("Menu deve continuar limpo (JOGA / JOGO SALV1/2/3).")
    print("Ao jogar normalmente e cruzar uma revelacao de vulnerabilidade/imunidade/traço,")
    print("o popup deve mostrar o texto em pt-BR mais longo, legivel e correto.")


if __name__ == "__main__":
    main()
