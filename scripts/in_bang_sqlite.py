import json
import sqlite3
import sys
from pathlib import Path

# Thêm thư mục gốc vào đường dẫn hệ thống
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import settings
from src.ingestion.loader import load_verified_documents
from src.retrieval.structured_lookup import _document_kinds, _fold

def main():
    print("\nDang doc du lieu tuyen sinh va tao bang SQLite tren RAM...")
    
    # 1. Load các tài liệu tuyển sinh đã kiểm duyệt
    load_result = load_verified_documents(settings.processed_data_dir)
    docs = load_result.documents[:12]  # Lấy 12 tài liệu mẫu
    
    # 2. Xây dựng các dòng facts giống hệt file structured_lookup.py
    rows = []
    for index, document in enumerate(docs):
        metadata = document.metadata or {}
        for kind in _document_kinds(document):
            rows.append((index, "kind", kind, str(metadata.get("chunk_id") or index)))
        for key in ("major_name", "major_code", "parent_major", "parent_major_code", "program_name", "method", "method_number"):
            if metadata.get(key) is not None:
                rows.append((index, key, _fold(metadata[key]), ""))
        try:
            programs = json.loads(str(metadata.get("program_names") or "[]"))
        except (ValueError, TypeError):
            programs = []
        if isinstance(programs, list):
            rows.extend((index, "program_name", _fold(name), "") for name in programs if isinstance(name, str))

    # 3. Tạo bảng SQLite in-memory và nạp dữ liệu
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE facts (doc INTEGER, field TEXT, value TEXT, identity TEXT)")
    conn.executemany("INSERT INTO facts VALUES (?, ?, ?, ?)", rows)

    # 4. In bảng ra màn hình Terminal
    print("=" * 86)
    print(f"{'DOC':<5} | {'FIELD':<18} | {'VALUE':<32} | {'IDENTITY':<25}")
    print("=" * 86)
    
    cursor = conn.execute("SELECT doc, field, value, identity FROM facts LIMIT 25")
    for r in cursor.fetchall():
        doc_idx, field, val, ident = r
        val_str = (val[:29] + "...") if len(val) > 32 else val
        ident_str = (ident[:22] + "...") if len(ident) > 25 else ident
        print(f"{doc_idx:<5} | {field:<18} | {val_str:<32} | {ident_str:<25}")
        
    print("=" * 86)
    total = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    print(f"-> Tong cong co {total} dong facts dang nam tren bo nho RAM!")
    print("-> Day chinh la bang ma chatbot dung de tra cuu SQL chinh xac 100%.\n")
    conn.close()

if __name__ == "__main__":
    main()
