"""
The Council - CPK Repacker (Fase 0)

Reconstroi um arquivo .cpk a partir da tabela de entradas original (nomes e
ordem preservados) e dos dados de cada entrada — que podem ter sido
substituidos (ex.: um .db traduzido, de tamanho diferente do original).

Formato (reverso-engenheirado em unpack_cpk.py + analise de offsets, Fase 0):
    magic:       4 bytes, b'U\x98C\x01'
    file_count:  uint32 LE
    root_dir:    512 bytes (string com padding de nulos, ex. "./")
    entries[file_count]:
        file_size:   uint32 LE
        file_offset: uint32 LE  (offset absoluto desde o inicio do .cpk)
        unk:         uint32 LE  (sempre 0 em todas as entradas observadas —
                                 nao e checksum/hash, campo reservado)
        name:        512 bytes (path relativo em UTF-8, padding de nulos)
    data: bytes de cada entrada concatenados na ordem da tabela, sem padding
          entre entradas e sem gap apos a tabela (offset da entrada 0 ==
          fim da tabela de entradas; offset da entrada i+1 == offset da
          entrada i + tamanho da entrada i) — confirmado batendo os offsets
          reais de Loca_en_Main_0.cpk em Fase 0.

O arquivo .cpkh companheiro e um manifesto JSON em texto puro (hash do path,
path original, campo de MD5 de build sempre vazio "") e NAO contem offsets
nem tamanhos — nao precisa ser regenerado ao reempacotar o .cpk (verificado
por inspecao em Fase 0).
"""
import struct

MAGIC = b"U\x98C\x01"
ROOT_DIR_SIZE = 512
NAME_SIZE = 512
ENTRY_HEADER_SIZE = 12  # file_size + file_offset + unk, uint32 cada


def read_cpk(path: str):
    """Retorna (root_dir: bytes, entries: list[dict], data_by_name: dict[str, bytes])."""
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError(f"magic invalido: {magic!r}")

        file_count, = struct.unpack("<I", f.read(4))
        root_dir = f.read(ROOT_DIR_SIZE)

        raw_entries = []
        for _ in range(file_count):
            file_size, file_offset, unk = struct.unpack("<III", f.read(ENTRY_HEADER_SIZE))
            name_bytes = f.read(NAME_SIZE)
            null_idx = name_bytes.find(b"\x00")
            name = (name_bytes[:null_idx] if null_idx != -1 else name_bytes).decode("utf-8")
            raw_entries.append({"name": name, "size": file_size, "offset": file_offset, "unk": unk})

        data_by_name = {}
        for e in raw_entries:
            f.seek(e["offset"])
            data_by_name[e["name"]] = f.read(e["size"])

    return root_dir, raw_entries, data_by_name


def build_cpk(root_dir: bytes, entries: list, data_by_name: dict) -> bytes:
    """Reconstroi um .cpk. `entries` fixa nomes/ordem/unk; `data_by_name`
    fornece o conteudo atual (pode ter tamanho diferente do original) —
    offsets e tamanhos sao recalculados a partir dele."""
    file_count = len(entries)
    header_size = 4 + 4 + ROOT_DIR_SIZE + file_count * (ENTRY_HEADER_SIZE + NAME_SIZE)

    out = bytearray()
    out += MAGIC
    out += struct.pack("<I", file_count)
    out += root_dir.ljust(ROOT_DIR_SIZE, b"\x00")[:ROOT_DIR_SIZE]

    new_entries = []
    cursor = header_size
    for e in entries:
        data = data_by_name[e["name"]]
        new_entries.append({"name": e["name"], "size": len(data), "offset": cursor, "unk": e["unk"]})
        cursor += len(data)

    for e in new_entries:
        out += struct.pack("<III", e["size"], e["offset"], e["unk"])
        name_bytes = e["name"].encode("utf-8")
        if len(name_bytes) >= NAME_SIZE:
            raise ValueError(f"nome de arquivo excede {NAME_SIZE} bytes: {e['name']}")
        out += name_bytes.ljust(NAME_SIZE, b"\x00")

    assert len(out) == header_size, f"header calculado ({header_size}) != escrito ({len(out)})"

    for e in entries:
        out += data_by_name[e["name"]]

    return bytes(out)


def repack_cpk(original_cpk_path: str, overrides: dict) -> bytes:
    """overrides: {nome_da_entrada: novos_bytes}. Entradas nao citadas
    passam adiante com os bytes originais, inalterados."""
    root_dir, entries, data_by_name = read_cpk(original_cpk_path)
    data_by_name = dict(data_by_name)
    for name, new_data in overrides.items():
        if name not in data_by_name:
            raise KeyError(f"entrada nao encontrada no .cpk: {name}")
        data_by_name[name] = new_data
    return build_cpk(root_dir, entries, data_by_name)


if __name__ == "__main__":
    # Smoke test manual: round-trip sem alteracao deve ser byte-identico ao .cpk original.
    path = r"Loca_en_Main_0.cpk"
    with open(path, "rb") as f:
        original = f.read()

    rebuilt = repack_cpk(path, {})
    assert rebuilt == original, "round-trip de .cpk sem alteracao NAO foi byte-identico!"
    print(f"OK: round-trip de {path} ({len(original)} bytes) e byte-identico ao original.")
