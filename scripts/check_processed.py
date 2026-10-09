import json
from pathlib import Path

for p in Path('data/processed').rglob('*.json'):
    with open(p, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for chunk in data.get('chunks', []):
            if chunk.get('category') in ['co_so_lien_he', 'thong_tin_truong']:
                print(f"Found in {p.name}")
                break
