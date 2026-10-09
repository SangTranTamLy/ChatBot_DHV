import chromadb
from src.config.settings import settings

client = chromadb.PersistentClient(path=str(settings.chroma_persist_dir))
coll = client.get_collection(settings.chroma_collection)
print('Count:', coll.count())
res = coll.get(where={'document_id': 'ho-so-nhap-hoc-day-du-dhv-2026'})
print('Matches ho_so_nhap_hoc:', len(res['ids']))
res = coll.get()
years = set([m.get('year') for m in res['metadatas']])
print('Years:', years)
cats = set([m.get('category') for m in res['metadatas']])
print('Categories:', cats)
