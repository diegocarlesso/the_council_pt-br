# -*- coding: utf-8 -*-
"""The Council - monta o Loca_en_Main_0.cpk traduzido completo (pt-BR)
a partir de preprocessed.json (mapa canonical_id -> ocorrencias
file+index) e pt-br/translation_memory.json (canonical_id -> texto
traduzido).

Nao sobrescreve o Loca_en_Main_0.cpk ao vivo sozinho - so gera
CANDIDATE_CPK ao lado do original. A troca do arquivo ao vivo do jogo
e feita manualmente (ou por outro passo explicito), nunca aqui.
"""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

from repack_db import read_db_parts, repack_db
from repack_cpk import read_cpk, repack_cpk, MAGIC
from translator.utils import fit_to_byte_length

CPK_PATH = PROJECT_ROOT / "Loca_en_Main_0.cpk"
CANDIDATE_CPK = PROJECT_ROOT / "Loca_en_Main_0_pt_SAFE.cpk"
EXTRACTED_DIR = PROJECT_ROOT / "Extracted_Loc_En"

# common_loc_en_0.db contem o cluster de boot/menu referenciado por offset
# fixo de bytes a partir de outro arquivo (suspeita: Gui_Main_0.cpk, nunca
# totalmente mapeado - ver docs/04-RISCOS_TECNICOS.md). Mudar o tamanho de
# QUALQUER string desse arquivo desalinha esse offset e corrompe a tela
# (mostra o conteudo de outra posicao do pool). Confirmado ao vivo em
# 2026-08-18: build completa (todos os 26 arquivos traduzidos) quebrou os
# menus. Ate o offset real ser localizado e corrigido (ver PAUSA.md),
# este arquivo fica de fora - mantido 100% no original em ingles.
EXCLUDE_FILES = {"data\\localization\\common_loc_en_0.db"}


def main() -> None:
    preprocessed = json.load(open(PROJECT_ROOT / "preprocessed.json", encoding="utf-8"))
    canonical = preprocessed["_canonical"]

    tm = json.load(open(PROJECT_ROOT / "pt-br" / "translation_memory.json", encoding="utf-8"))
    tm_by_id = {e["canonical_id"]: e for e in tm["entries"]}

    print(f"canonical: {len(canonical)} | translation_memory: {len(tm_by_id)}")

    # canonical_id -> texto final a gravar
    final_text: dict[str, str] = {}
    missing_translation = []
    for cid, info in canonical.items():
        if info["translatable"]:
            entry = tm_by_id.get(cid)
            if entry is None or not (entry.get("target") or "").strip():
                missing_translation.append(cid)
                final_text[cid] = info["text"]  # failsafe: mantem original
            else:
                final_text[cid] = entry["target"]
        else:
            final_text[cid] = info["resolved_translation"]

    if missing_translation:
        print(f"AVISO: {len(missing_translation)} canonical_id traduziveis sem tradução na TM (usando original como failsafe):")
        for cid in missing_translation[:20]:
            print("  ", cid, repr(canonical[cid]["text"][:60]))

    # rede de seguranca pro cluster de tamanho fixo (menu de boot) - so se
    # aplica de fato as 11 strings marcadas menu_boot_suspect que NAO
    # estiverem dentro de EXCLUDE_FILES (hoje, common_loc_en_0.db inteiro
    # ja fica de fora, entao isso e redundante ate a exclusao ser removida)
    fixed = 0
    for cid, info in canonical.items():
        if info.get("menu_boot_suspect"):
            orig = info["text"]
            cur = final_text[cid]
            if len(cur.encode("utf-8")) != len(orig.encode("utf-8")):
                final_text[cid] = fit_to_byte_length(orig, cur)
                fixed += 1
    if fixed:
        print(f"ajustados {fixed} itens do cluster de tamanho fixo (menu de boot)")

    # canonical_id -> texto final ; agora expande pra {file: {index: texto}}
    replacements_by_file: dict[str, dict[int, str]] = {}
    for cid, info in canonical.items():
        text = final_text[cid]
        for occ in info["occurrences"]:
            replacements_by_file.setdefault(occ["file"], {})[occ["index"]] = text

    print(f"arquivos .db afetados: {len(replacements_by_file)}")

    overrides: dict[str, bytes] = {}
    for db_rel_path, replacements in sorted(replacements_by_file.items()):
        if db_rel_path in EXCLUDE_FILES:
            print(f"  {db_rel_path}: PULADO (fica em ingles - risco de offset fixo)")
            continue
        db_file = EXTRACTED_DIR / db_rel_path
        original_bytes = db_file.read_bytes()
        new_bytes = repack_db(original_bytes, replacements)

        # paranoia: confere que indices NAO tocados continuam byte-identicos
        _, orig_parts = read_db_parts(original_bytes)
        _, new_parts = read_db_parts(new_bytes)
        assert len(orig_parts) == len(new_parts), f"{db_rel_path}: contagem de strings mudou!"
        for i, (o, n) in enumerate(zip(orig_parts, new_parts)):
            if i not in replacements:
                assert o == n, f"{db_rel_path}[{i}]: mudou sem estar no replacements!"

        entry_name = db_rel_path.replace("\\", "/")
        overrides[entry_name] = new_bytes
        print(f"  {entry_name}: {len(replacements)} strings substituidas, {len(new_bytes)} bytes (original {len(original_bytes)})")

    print(f"\nreempacotando {CPK_PATH.name} com {len(overrides)} entradas modificadas...")
    new_cpk = repack_cpk(str(CPK_PATH), overrides)
    assert new_cpk[:4] == MAGIC

    CANDIDATE_CPK.write_bytes(new_cpk)

    # verificacao estrutural final
    root_dir, entries, data_by_name = read_cpk(str(CANDIDATE_CPK))
    _, orig_entries, orig_data = read_cpk(str(CPK_PATH))
    assert len(entries) == len(orig_entries), "contagem de entradas do cpk mudou!"
    unchanged_ok = 0
    for e in entries:
        name = e["name"]
        if name not in overrides:
            assert data_by_name[name] == orig_data[name], f"{name} mudou sem querer!"
            unchanged_ok += 1

    print(f"\nOK: {CANDIDATE_CPK.name} gerado ({len(new_cpk)} bytes, original {CPK_PATH.stat().st_size} bytes)")
    print(f"    {len(entries)} entradas no total, {len(overrides)} modificadas, {unchanged_ok} confirmadas byte-identicas ao original")


if __name__ == "__main__":
    main()
