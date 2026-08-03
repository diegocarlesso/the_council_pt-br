"""
Experimento de diagnostico (Fase 0) - parte 3: teste decisivo.

Testa TODAS as falas de missao/dialogo (q1..q17, chapter2..5, deprecated,
qfpp, qsadams) de uma vez so, sem tocar em common_loc_en_0.db (que fica
100% original, para eliminar de vez a interferencia ja identificada nos
experimentos anteriores).

Cada string ganha um sufixo de teste visivelmente mais longo, para que
QUALQUER dialogo encontrado durante o jogo normal - nao importa em que
capitulo o jogador esteja - sirva como confirmacao visual, sem precisar
adivinhar qual arquivo esta ativo agora.

Se o dialogo aparecer corretamente (mesmo mais longo) durante o jogo
normal, confirma que o bug de offset fixo e exclusivo do common_loc_en_0.db
(reaproveitado por muitas telas de sistema/UI ao mesmo tempo) e NAO afeta
o restante do corpus - ou seja, a traducao real (85% do trabalho) pode
seguir livremente.
"""
import glob
import os

from repack_db import read_db_parts, build_db
from repack_cpk import read_cpk, build_cpk, MAGIC

CPK_PATH = "Loca_en_Main_0.cpk"
OUT_PATH = "Loca_en_Main_0_pt_test.cpk"
EXTRACTED_DIR = "Extracted_Loc_En"
SKIP_ENTRIES = {
    "data/localization/common_loc_en_0.db",  # fica 100% original neste teste
    "data/localization/test_loc_en_0.db",    # nao faz parte do jogo real
}
SUFFIX = " (traduzido pt-BR - teste de repack da Fase 0, string bem mais longa que o original)"


def translate_with_suffix(text: str) -> str:
    if not text.strip():
        return text  # nao mexe em string vazia
    return text + SUFFIX


def main():
    root_dir, entries, data_by_name = read_cpk(CPK_PATH)

    overrides = {}
    total_strings = 0
    for e in entries:
        name = e["name"]
        if name in SKIP_ENTRIES:
            continue
        original = data_by_name[name]
        header, parts = read_db_parts(original)
        new_parts = [translate_with_suffix(p.decode("utf-8", errors="replace")).encode("utf-8") for p in parts]
        new_db = build_db(header, new_parts)
        overrides[name] = new_db
        total_strings += len(parts)
        print(f"  {name}: {len(parts)} strings, {len(original)} -> {len(new_db)} bytes")

    print(f"\nTotal: {len(overrides)} arquivos de missao, {total_strings} strings com sufixo de teste.")
    print("common_loc_en_0.db mantido 100% original (nao esta nos overrides).")

    data_by_name = dict(data_by_name)
    data_by_name.update(overrides)
    new_cpk = build_cpk(root_dir, entries, data_by_name)
    assert new_cpk[:4] == MAGIC

    with open(OUT_PATH, "wb") as f:
        f.write(new_cpk)

    print(f"\nOK: {OUT_PATH} gerado ({len(new_cpk)} bytes; original tinha "
          f"{len(open(CPK_PATH, 'rb').read())} bytes).")
    print("Qualquer fala de dialogo que aparecer no jogo agora deve terminar com o sufixo de teste.")


if __name__ == "__main__":
    main()
