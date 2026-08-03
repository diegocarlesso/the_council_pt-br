"""
The Council - Teste de Round-Trip de Repack (Fase 0)

Prova as duas condicoes de saida da Fase 0 do roadmap:
1. Round-trip sem alteracao: extrair -> reempacotar -> comparar com o
   original deve ser byte-identico (tanto no nivel .db quanto .cpk).
2. Round-trip com 1 string alterada (incluindo uma versao mais longa que a
   original): o .cpk resultante deve continuar estruturalmente valido —
   mesma contagem de entradas, todas as OUTRAS entradas byte-identicas ao
   original, e a string trocada deve ser lida de volta corretamente ao
   reparsear o .cpk gerado.

Este teste NAO substitui o criterio final do roadmap ("o jogo carrega e
exibe a string traduzida corretamente sem quebrar nada") — isso exige rodar
o jogo de verdade, fora do alcance de automacao aqui. Ver o aviso impresso
no final.
"""
import os
import struct

from repack_db import read_db_parts, repack_db
from repack_cpk import read_cpk, build_cpk, repack_cpk, MAGIC


CPK_PATH = "Loca_en_Main_0.cpk"
TARGET_ENTRY = "data/localization/test_loc_en_0.db"
TARGET_INDEX = 0
TRANSLATION = (
    "Uma tradução bem mais longa do que o texto original em inglês, para "
    "forçar o teste a provar que strings maiores não quebram o formato."
)


def test_db_roundtrip_unchanged():
    with open(f"Extracted_Loc_En/{TARGET_ENTRY}", "rb") as f:
        original = f.read()
    rebuilt = repack_db(original, {})
    assert rebuilt == original
    print("[1/4] OK — round-trip de .db sem alteracao e byte-identico.")


def test_cpk_roundtrip_unchanged():
    with open(CPK_PATH, "rb") as f:
        original = f.read()
    rebuilt = repack_cpk(CPK_PATH, {})
    assert rebuilt == original
    print("[2/4] OK — round-trip de .cpk sem alteracao e byte-identico.")


def test_db_translation_changes_only_target_string():
    with open(f"Extracted_Loc_En/{TARGET_ENTRY}", "rb") as f:
        original = f.read()

    header, original_parts = read_db_parts(original)
    original_text = original_parts[TARGET_INDEX].decode("utf-8")

    new_db = repack_db(original, {TARGET_INDEX: TRANSLATION})

    # Reparseia o .db gerado e confirma: mesma contagem de strings, só o
    # indice alvo mudou, e o texto lido de volta bate com a traducao.
    new_header, new_parts = read_db_parts(new_db)
    assert new_header == header, "header do .db mudou — nao deveria"
    assert len(new_parts) == len(original_parts), "contagem de strings mudou — nao deveria"

    for i, (orig, new) in enumerate(zip(original_parts, new_parts)):
        if i == TARGET_INDEX:
            assert new.decode("utf-8") == TRANSLATION
        else:
            assert new == orig, f"string {i} mudou sem querer"

    print(
        f"[3/4] OK — .db traduzido: '{original_text}' -> '{TRANSLATION}' "
        f"({len(original_text)} -> {len(TRANSLATION)} chars); "
        f"todas as outras {len(original_parts) - 1} strings permaneceram idênticas."
    )
    return new_db


def test_cpk_with_translated_db_stays_structurally_valid(new_db_bytes: bytes):
    root_dir, original_entries, original_data = read_cpk(CPK_PATH)

    new_cpk = repack_cpk(CPK_PATH, {TARGET_ENTRY: new_db_bytes})

    # Escreve em scratch para reparsear com read_cpk (que le de um path).
    scratch_path = os.path.join(
        os.environ.get("TEMP", "."), "the_council_test_translated.cpk"
    )
    with open(scratch_path, "wb") as f:
        f.write(new_cpk)

    try:
        new_root_dir, new_entries, new_data = read_cpk(scratch_path)

        assert new_cpk[:4] == MAGIC, "magic quebrado no .cpk reempacotado"
        assert len(new_entries) == len(original_entries), "contagem de entradas mudou"
        assert new_root_dir == root_dir, "root_dir mudou"

        # nomes/ordem/unk devem ser identicos; so offset/size da entrada
        # alvo (e das que vem depois dela, por deslocamento) podem diferir.
        names_original = [e["name"] for e in original_entries]
        names_new = [e["name"] for e in new_entries]
        assert names_original == names_new, "ordem/nomes das entradas mudou"

        for e in new_entries:
            assert e["unk"] == 0

        # Todas as OUTRAS entradas devem ter dados byte-identicos aos originais.
        changed = {TARGET_ENTRY}
        for name in names_original:
            if name not in changed:
                assert new_data[name] == original_data[name], f"{name} mudou sem querer"

        # A entrada traduzida deve reparsear com a string trocada no indice certo.
        _, translated_parts = read_db_parts(new_data[TARGET_ENTRY])
        assert translated_parts[TARGET_INDEX].decode("utf-8") == TRANSLATION

        # Offsets devem continuar contiguos e consistentes com os tamanhos.
        for i in range(len(new_entries) - 1):
            a, b = new_entries[i], new_entries[i + 1]
            assert a["offset"] + a["size"] == b["offset"], (
                f"gap ou sobreposicao entre '{a['name']}' e '{b['name']}'"
            )
        last = new_entries[-1]
        assert last["offset"] + last["size"] == len(new_cpk), (
            "ultima entrada nao bate com o tamanho total do .cpk"
        )

        print(
            f"[4/4] OK — .cpk reempacotado com '{TARGET_ENTRY}' traduzido "
            f"({len(original_data[TARGET_ENTRY])} -> {len(new_db_bytes)} bytes): "
            f"{len(new_entries)} entradas, offsets contiguos, "
            f"{len(names_original) - 1} outras entradas byte-identicas ao original."
        )
    finally:
        os.remove(scratch_path)


if __name__ == "__main__":
    test_db_roundtrip_unchanged()
    test_cpk_roundtrip_unchanged()
    new_db_bytes = test_db_translation_changes_only_target_string()
    test_cpk_with_translated_db_stays_structurally_valid(new_db_bytes)

    print()
    print("=" * 70)
    print("Todos os testes ESTRUTURAIS de round-trip passaram.")
    print()
    print("O que isso PROVA: o formato .db/.cpk pode ser reempacotado com")
    print("strings traduzidas (de qualquer tamanho) sem corromper a estrutura")
    print("do arquivo, preservando tudo o que nao foi traduzido byte a byte.")
    print()
    print("O que isso NAO prova ainda (criterio de saida real da Fase 0):")
    print("que O JOGO carrega esse .cpk modificado e exibe a string traduzida")
    print("corretamente na tela, sem quebrar nada. Isso exige rodar o jogo de")
    print("verdade — fora do alcance de automacao nesta sessao. Proximo passo:")
    print("gerar um .cpk de teste, fazer backup do original, trocar no jogo e")
    print("verificar visualmente (ver instrucoes que vou te passar no chat).")
    print("=" * 70)
