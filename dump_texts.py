"""
The Council - Localization DB Parser & Dumper
Parses the proprietary Cyanide Studio DB format used for localization.
Extracts all null-terminated strings from the string pool at the end of each .db file.
"""
import os
import sys
import json
import struct
import glob


def find_string_pool(data):
    """
    Find the string pool in a .db file.
    The pool is at the end of the file, consisting of null-terminated strings.
    A uint32 pool_size is stored immediately before the pool.
    Returns (pool_start, pool_size) or (None, None) if not found.
    """
    for candidate_start in range(len(data) - 1, 100, -1):
        pool_size = len(data) - candidate_start
        if candidate_start >= 4:
            stored = struct.unpack('<I', data[candidate_start - 4:candidate_start])[0]
            if stored == pool_size and pool_size > 10:
                return candidate_start, pool_size
    return None, None


def extract_strings(data):
    """
    Extract all strings from a .db file's string pool.
    Returns a list of dicts with 'index', 'offset', 'text'.
    Also returns pool_start for re-packing purposes.
    """
    pool_start, pool_size = find_string_pool(data)
    if pool_start is None:
        return [], None, None

    pool = data[pool_start:]
    parts = pool.split(b'\x00')
    # Remove trailing empty string
    if parts and parts[-1] == b'':
        parts = parts[:-1]

    strings = []
    offset = 0
    for i, part in enumerate(parts):
        try:
            text = part.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text = part.decode('latin-1')
            except:
                text = part.decode('ascii', errors='replace')
        strings.append({
            'index': i,
            'pool_offset': offset,
            'text': text
        })
        offset += len(part) + 1  # +1 for null terminator

    return strings, pool_start, pool_size


def dump_all_db_files(extracted_dir, output_json_path):
    """
    Dump all strings from all .db files in the extracted directory to a JSON file.
    """
    db_files = sorted(glob.glob(os.path.join(extracted_dir, '**', '*.db'), recursive=True))
    result = {}
    total_strings = 0

    for db_path in db_files:
        rel_path = os.path.relpath(db_path, extracted_dir)
        db_name = os.path.basename(db_path)

        with open(db_path, 'rb') as f:
            data = f.read()

        strings, pool_start, pool_size = extract_strings(data)

        if not strings:
            print(f"  [SKIP] {db_name}: no string pool found")
            continue

        result[rel_path] = {
            'pool_start': pool_start,
            'pool_size': pool_size,
            'file_size': len(data),
            'string_count': len(strings),
            'strings': []
        }

        for s in strings:
            result[rel_path]['strings'].append({
                'index': s['index'],
                'pool_offset': s['pool_offset'],
                'original': s['text'],
                'translation': ''  # To be filled in Phase 2
            })

        total_strings += len(strings)
        print(f"  [OK] {db_name}: {len(strings)} strings extracted (pool at {pool_start}, size {pool_size})")

    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nTotal: {total_strings} strings from {len(result)} files")
    print(f"Output: {output_json_path}")
    return result


if __name__ == '__main__':
    extracted_dir = r'C:\Program Files\Steam\steamapps\common\The Council\Data\Packages\Extracted_Loc_En'
    output_json = r'C:\Program Files\Steam\steamapps\common\The Council\Data\Packages\localization_dump.json'

    print("=== The Council - Localization Text Dump ===\n")
    dump_all_db_files(extracted_dir, output_json)
