import sys
import json
data = json.load(open('data/processed/phuong_thuc_xet_tuyen/PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.json', encoding='utf-8'))
with open('methods_output.txt', 'w', encoding='utf-8') as f:
    for p in data['pages']:
        for b in p.get('native_blocks', []):
            f.write(b.get('text', '') + '\n')
