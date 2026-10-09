import json
from pathlib import Path
from typing import Set

def check_manifest():
    print("=== MANIFEST STATUS ===")
    with open('data/raw/manifest.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    for doc in data['documents']:
        print(f"[{doc['status']}] {doc['category']} - {doc['document_id']}")

def check_db_categories():
    print("\n=== VECTOR DB CATEGORIES ===")
    try:
        import chromadb
        client = chromadb.PersistentClient(path='chroma_db')
        collection = client.get_collection('dhv_admissions_2026')
        result = collection.get()
        metadatas = result['metadatas']
        categories = set()
        for m in metadatas:
            if 'category' in m:
                cat = m['category']
                if isinstance(cat, list): categories.update(cat)
                elif isinstance(cat, str): categories.add(cat)
        print(categories)
        return categories
    except Exception as e:
        print("Error checking DB:", e)
        return set()

def check_query_analysis(db_categories: Set[str]):
    print("\n=== QUERY ANALYSIS CATEGORIES MAP ===")
    # Extract mapped categories from query_analysis.py
    import re
    with open('src/chatbot/query_analysis.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We will just print the block where routing happens to see
    start = content.find('elif resolved.intent == "HOI_NGUONG_DAU_VAO":')
    end = content.find('parts = [analysis.question.strip()', start)
    print(content[start:end])

if __name__ == "__main__":
    check_manifest()
    db_cats = check_db_categories()
    check_query_analysis(db_cats)
