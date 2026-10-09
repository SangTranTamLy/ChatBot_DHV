import sys
import json
import logging
import chromadb
from src.config.settings import settings
from src.chatbot.chat_service import ask_chatbot
from src.chatbot.query_analysis import ConversationState

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.ERROR)

def check_chroma():
    print("=== CHROMA VERIFICATION ===")
    client = chromadb.PersistentClient(path=str(settings.chroma_persist_dir))
    coll = client.get_collection(settings.chroma_collection)
    res = coll.get()
    metadatas = res['metadatas']
    print(f"Total chunks: {len(res['ids'])}")
    
    years = set()
    statuses = set()
    schools = set()
    doc_ids = set()
    categories = set()
    
    for m in metadatas:
        years.add(m.get('year'))
        statuses.add(m.get('status'))
        schools.add(m.get('school_code'))
        doc_ids.add(m.get('document_id'))
        c = m.get('category') or m.get('categories')
        if isinstance(c, list):
            categories.update(c)
        elif isinstance(c, str):
            if c.startswith("["):
                try:
                    c_list = json.loads(c.replace("'", '"'))
                    categories.update(c_list)
                except:
                    categories.add(c)
            else:
                categories.add(c)
                
    print(f"Years: {years}")
    print(f"Status: {statuses}")
    print(f"School: {schools}")
    print(f"Doc IDs: {doc_ids}")
    print(f"Categories: {categories}")
    print("============================\n")

def check_query(q):
    print(f"--- QUERY: {q} ---")
    result = ask_chatbot(q)
    print("Status:", result.get("status"))
    print("Answer:", result.get("answer"))
    if "trace" in result:
        trace = result["trace"]
        print("Intent:", trace.get("intent"))
        print("Scope:", trace.get("scope"))
        print("Router Categories:", trace.get("router", {}).get("categories"))
        print("Retrieved Docs Count:", trace.get("retrieved_docs_count"))
        print("Evidence Count:", trace.get("evidence_count"))
    print("\n")

def test_multiturn(dialogue):
    print(f"--- MULTI-TURN ---")
    state = ConversationState().to_dict()
    for q in dialogue:
        print(f"User: {q}")
        result = ask_chatbot(q, conversation_state=state)
        print("Bot:", result.get("answer"))
        if "state" in result:
            state = result["state"]
    print("\n")

if __name__ == "__main__":
    check_chroma()
    
    matrix = [
        "nhập học cần những gì",
        "hồ sơ nhập học gồm những gì",
        "nhập học cần giấy tờ gì",
        "thủ tục nhập học như thế nào",
        "tân sinh viên cần chuẩn bị gì",
        "phí nhập học bao nhiêu",
        "học liệu điện tử bao nhiêu",
        "nhập học khi nào",
        "cần làm gì để nhập học DHV",
        "hồ sơ xét tuyển gồm những gì",
        "DHV học phí bao nhiêu?",
        "DHV có học bổng gì?",
        "Hồ sơ xét tuyển cần gì?",
        "DHV xét tuyển bằng phương thức nào?",
        "Điểm chuẩn CNTT?",
        "Điểm sàn là bao nhiêu?",
        "DHV có những ngành nào?",
        "DHV có xét tuyển bổ sung không?",
        "Khi nào tuyển sinh?",
        "Điểm chuẩn Bách Khoa?",
        "Điểm chuẩn trường đại học khác?",
        "Điểm chuẩn Văn Hiến?",
        "So sánh DHV và Văn Hiến",
        "Giá vàng hôm nay?",
        "Thời tiết hôm nay?",
        "Học phí DHV 2027?",
        "Học phí DHV 2026?"
    ]
    
    for q in matrix:
        check_query(q)
        
    test_multiturn(["nhập học cần những gì", "còn phí thì sao?"])
    test_multiturn(["hồ sơ nhập học gồm những gì", "cần nộp khi nào?"])
    test_multiturn(["điểm chuẩn CNTT", "nhập học cần gì?"])
