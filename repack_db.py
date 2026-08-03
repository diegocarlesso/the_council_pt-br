"""
The Council - Localization DB Repacker (Fase 0)

Rebuilds a .db file's string pool from a (possibly translated) set of
strings, preserving every other byte of the file untouched.

Formato (reverso-engenheirado em dump_texts.py / list_strings.py, confirmado
por round-trip em Fase 0):
    [header: campos fixos + metadados de reflexao, nao referenciam o pool
     por offset em nenhum lugar (busca exaustiva feita em Fase 0 nao achou
     nenhuma tabela de offsets) ]
    [uint32 LE: pool_size]   <- ultimos 4 bytes do "header" de dump_texts.py
    [string pool: pool_size bytes, N strings terminadas em \x00, em ordem fixa]

Constraint provado seguro pelo teste de round-trip: o motor do jogo parseia
o pool sequencialmente ao carregar e casa as strings por POSICAO/INDICE, nao
por offset em bytes. Isso significa:
    - o COMPRIMENTO de cada string pode mudar livremente (traducao mais longa
      ou mais curta que o original nao quebra nada);
    - a CONTAGEM e a ORDEM das entradas devem permanecer identicas ao
      original — o formato nao suporta adicionar, remover ou reordenar
      entradas.
"""
import struct

from dump_texts import find_string_pool


def read_db_parts(data: bytes):
    """Retorna (header_sem_pool_size, partes_do_pool: list[bytes]).

    As partes sao mantidas como bytes crus (nao decodificadas) para garantir
    round-trip perfeito em qualquer conteudo, mesmo que nao seja UTF-8 valido.
    """
    pool_start, pool_size = find_string_pool(data)
    if pool_start is None:
        raise ValueError("string pool nao encontrado")

    header = data[:pool_start - 4]
    pool = data[pool_start:]
    parts = pool.split(b"\x00")
    if parts and parts[-1] == b"":
        parts = parts[:-1]
    return header, parts


def build_db(header: bytes, parts: list) -> bytes:
    """Reconstroi um .db a partir do header original + lista de partes do pool."""
    pool = b"\x00".join(parts) + b"\x00"
    return header + struct.pack("<I", len(pool)) + pool


def repack_db(original_data: bytes, replacements: dict) -> bytes:
    """Aplica traducoes a um .db, preservando tudo o mais byte a byte.

    replacements: {indice_da_string: novo_texto (str)}. Indices nao citados
    ficam inalterados (bytes originais, sem re-encode).

    Levanta ValueError se a contagem de strings do arquivo original mudasse
    (nunca deveria, pois nao adicionamos/removemos entradas aqui).
    """
    header, parts = read_db_parts(original_data)
    for idx, text in replacements.items():
        if idx < 0 or idx >= len(parts):
            raise IndexError(
                f"indice {idx} fora do intervalo (0..{len(parts) - 1}, "
                f"{len(parts)} strings no pool)"
            )
        parts[idx] = text.encode("utf-8")
    return build_db(header, parts)


if __name__ == "__main__":
    # Smoke test manual: round-trip sem alteracao deve ser byte-identico.
    path = r"Extracted_Loc_En/data/localization/test_loc_en_0.db"
    with open(path, "rb") as f:
        original = f.read()

    header, parts = read_db_parts(original)
    print(f"{len(parts)} strings no pool de {path}")

    rebuilt_unchanged = repack_db(original, {})
    assert rebuilt_unchanged == original, "round-trip sem alteracao NAO foi byte-identico!"
    print("OK: round-trip sem alteracao e byte-identico ao original.")
