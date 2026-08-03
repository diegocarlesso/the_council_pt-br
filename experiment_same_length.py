"""
Experimento de diagnostico (Fase 0): sera que existe um offset fixo em bytes,
calculado em outro lugar (fora do .db), que aponta para as strings de menu?

Hipotese: se eu traduzir mantendo o MESMO NUMERO DE BYTES de cada string
original (cortando ou preenchendo com espaco em branco no final), o pool
inteiro do arquivo tem o MESMO TAMANHO TOTAL e cada string cai exatamente no
mesmo offset de antes. Se isso resolver o bug visual ("Vulnerability
revealed" aparecendo no lugar de "PLAY"/"Savegame N"), confirma que ha um
offset fixo (bakeado em outro arquivo, provavelmente Gui_Main_0.cpk ou um
cache gerado na build original) que nao e recalculado em runtime.

Nao usa acento (pra manter a aritmetica de bytes simples e exata neste
teste). Nao e a traducao final — e so pra isolar a causa.
"""
from repack_db import read_db_parts, repack_db
from repack_cpk import read_cpk, repack_cpk, MAGIC

CPK_PATH = "Loca_en_Main_0.cpk"
TARGET_ENTRY = "data/localization/common_loc_en_0.db"
OUT_PATH = "Loca_en_Main_0_pt_test.cpk"

# Mesmas strings do teste anterior, mas agora ajustadas por bytes para
# ocupar EXATAMENTE o mesmo espaco do original (corta ou preenche com
# espaco a direita).
RAW_TRANSLATIONS = {
    "credits": "CREDITO",       # 7 bytes, igual a "CREDITS"
    "continue": "CONTINUAR",    # 9 bytes, igual a "CONTINUE"
    "settings": "CONFIGURA",    # 8 bytes, igual a "SETTINGS"
    "new game": "JOGO NOVO",    # 8 bytes, igual a "NEW GAME"
    "options": "OPCOES ",       # 7 bytes, igual a "OPTIONS" (padded)
    "play": "JOGA",             # 4 bytes, igual a "PLAY"
    "savegame 1": "JOGO SALV1", # 10 bytes, igual a "Savegame 1"
    "savegame 2": "JOGO SALV2", # 10 bytes, igual a "Savegame 2"
    "savegame 3": "JOGO SALV3", # 10 bytes, igual a "Savegame 3"
}


def fit_to_byte_length(original: str, replacement: str) -> str:
    orig_len = len(original.encode("utf-8"))
    rep_bytes = replacement.encode("utf-8")
    if len(rep_bytes) > orig_len:
        rep_bytes = rep_bytes[:orig_len]
    else:
        rep_bytes = rep_bytes + b" " * (orig_len - len(rep_bytes))
    return rep_bytes.decode("utf-8")


def translated(original_text: str) -> str:
    key = original_text.strip().lower()
    raw = RAW_TRANSLATIONS[key]
    text = raw if original_text.isupper() or key.startswith("savegame") else raw.title()
    return fit_to_byte_length(original_text, text)


def main():
    import json
    dump = json.load(open("localization_dump.json", encoding="utf-8"))
    key = [k for k in dump if "common_loc_en_0" in k][0]
    info = dump[key]

    replacements = {}
    for s in info["strings"]:
        t = s["original"].strip().lower()
        if t in RAW_TRANSLATIONS:
            replacements[s["index"]] = translated(s["original"])

    with open(f"Extracted_Loc_En/{TARGET_ENTRY}", "rb") as f:
        original_db = f.read()

    print(f"Traduzindo {len(replacements)} strings, mesmo tamanho em bytes do original:")
    for idx, new_text in sorted(replacements.items()):
        orig = info["strings"][idx]["original"]
        print(
            f"  [{idx}] {orig!r} ({len(orig.encode('utf-8'))}b) -> "
            f"{new_text!r} ({len(new_text.encode('utf-8'))}b)"
        )
        assert len(orig.encode("utf-8")) == len(new_text.encode("utf-8")), "tamanho não bateu!"

    new_db = repack_db(original_db, replacements)
    assert len(new_db) == len(original_db), (
        f"tamanho do .db mudou! original={len(original_db)}, novo={len(new_db)} "
        f"— a hipotese de bytes exatos falhou na propria conta"
    )
    print(f"\nOK: .db tem exatamente o mesmo tamanho de antes ({len(new_db)} bytes).")

    new_cpk = repack_cpk(CPK_PATH, {TARGET_ENTRY: new_db})
    assert new_cpk[:4] == MAGIC
    assert len(new_cpk) == len(open(CPK_PATH, "rb").read()), "tamanho do .cpk mudou!"

    with open(OUT_PATH, "wb") as f:
        f.write(new_cpk)

    print(f"OK: {OUT_PATH} gerado, mesmo tamanho total do .cpk original.")
    print("Aplique no jogo e veja se o bug de 'Vulnerability revealed' sumiu.")


if __name__ == "__main__":
    main()
