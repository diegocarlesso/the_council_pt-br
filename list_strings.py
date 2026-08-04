data = open(r'C:\Program Files\Steam\steamapps\common\The Council\Data\Packages\Extracted_Loc_En\data\localization\test_loc_en_0.db', 'rb').read()
pool = data[1849:]
strings = pool.split(b'\x00')
if strings[-1] == b'':
    strings = strings[:-1]
print(f'Number of strings: {len(strings)}')
for i, s in enumerate(strings):
    try:
        text = s.decode('utf-8')
    except:
        text = repr(s)
    print(f'  {i}: {text}')
