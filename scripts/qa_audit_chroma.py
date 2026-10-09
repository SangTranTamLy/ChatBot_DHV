import os
import sys
import logging
import chromadb

# Ensure src can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.config.settings import settings

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.ERROR)

def audit_chroma():
    try:
        client = chromadb.PersistentClient(path=str(settings.chroma_persist_dir))
        collection = client.get_collection(name=settings.chroma_collection)
        data = collection.get()
        ids = data['ids']
        metadatas = data['metadatas']
        
        print(f"Total chunks in collection: {len(ids)}")
        
        years = set()
        statuses = set()
        schools = set()
        doc_ids = set()
        categories = set()
        
        for m in metadatas:
            if m:
                years.add(m.get('year'))
                statuses.add(m.get('status'))
                schools.add(m.get('school_code'))
                doc_ids.add(m.get('document_id'))
                if 'category' in m:
                    cat = m.get('category')
                    if isinstance(cat, list):
                        categories.update(cat)
                    elif isinstance(cat, str):
                        categories.add(cat)
                        
        print(f"Years: {years}")
        print(f"Statuses: {statuses}")
        print(f"Schools: {schools}")
        print(f"Categories: {categories}")
        print(f"Document IDs: {doc_ids}")
        
    except Exception as e:
        print(f"Error auditing chroma: {e}")

if __name__ == "__main__":
    audit_chroma()
