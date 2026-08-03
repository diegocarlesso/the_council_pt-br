import os
import struct

def unpack_cpk(cpk_path, out_dir):
    with open(cpk_path, 'rb') as f:
        magic = f.read(4)
        if magic != b'U\x98C\x01':
            print("Invalid magic!")
            return
            
        file_count, = struct.unpack('<I', f.read(4))
        print(f"Total files: {file_count}")
        
        # Read the root dir name (usually 260 or 512 bytes)
        root_dir = f.read(512)
        
        os.makedirs(out_dir, exist_ok=True)
        
        for i in range(file_count):
            entry_header = f.read(12)
            if not entry_header:
                break
                
            file_size, file_offset, unk = struct.unpack('<III', entry_header)
            
            # Read filename (null terminated, fixed size field)
            # The name field length might be 260.
            name_bytes = f.read(512)
            null_idx = name_bytes.find(b'\x00')
            if null_idx != -1:
                filename = name_bytes[:null_idx].decode('utf-8', errors='ignore')
            else:
                filename = name_bytes.decode('utf-8', errors='ignore')
                
            # If the filename is empty, maybe the record is padded to 276 instead of 272?
            # Let's check where we are
            
            print(f"File {i}: {filename} (Offset: {file_offset}, Size: {file_size})")
            
            if not filename:
                continue
                
            # Save current pos
            pos = f.tell()
            
            # Read and extract file
            f.seek(file_offset)
            file_data = f.read(file_size)
            
            out_filepath = os.path.join(out_dir, filename.replace('/', os.sep))
            os.makedirs(os.path.dirname(out_filepath), exist_ok=True)
            
            with open(out_filepath, 'wb') as out_f:
                out_f.write(file_data)
                
            # Restore pos
            f.seek(pos)

if __name__ == '__main__':
    unpack_cpk(
        r'C:\Program Files\Steam\steamapps\common\The Council\Data\Packages\Loca_en_Main_0.cpk',
        r'C:\Program Files\Steam\steamapps\common\The Council\Data\Packages\Extracted_Loc_En'
    )
