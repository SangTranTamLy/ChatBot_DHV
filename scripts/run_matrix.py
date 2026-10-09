import sys
import logging
import json

sys.stdout.reconfigure(encoding='utf-8')

from src.chatbot.chat_service import ask_chatbot

logging.basicConfig(level=logging.ERROR)

queries = [
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
    
    # EXTERNAL SCHOOL
    "Điểm chuẩn Bách Khoa?",
    "Điểm chuẩn trường đại học khác?",
    "Giá vàng hôm nay?",
    "Điểm chuẩn CNTT?",
    
    # OTHER DOMAINS
    "DHV học phí bao nhiêu?",
    "Có học bổng nào?",
    "Hồ sơ xét tuyển cần gì?",
    "Khi nào tuyển sinh?",
    "DHV xét tuyển bằng phương thức nào?",
    "Điểm sàn là bao nhiêu?",
    "DHV có những ngành nào?",
    "Có xét tuyển bổ sung không?"
]

results = []

for q in queries:
    print(f"--- QUERY: {q} ---")
    result = ask_chatbot(q)
    print("Status:", result.get("status"))
    print("Answer:", result.get("answer"))
    if "trace" in result:
        trace = result["trace"]
        intent = trace.get("intent")
        cat = trace.get("router", {}).get("categories")
        ret_c = trace.get("retrieved_docs_count")
        ev_c = trace.get("evidence_count")
        scope = trace.get("scope", {}).get("in_scope")
        print(f"Intent: {intent}, Cat: {cat}, RetDocs: {ret_c}, EvCount: {ev_c}, InScope: {scope}")
    print("\n")
