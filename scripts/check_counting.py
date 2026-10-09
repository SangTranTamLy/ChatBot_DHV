import json
from src.chatbot.chat_service import get_chat_service

def run():
    svc = get_chat_service()
    queries = [
        "DHV có mấy phương thức xét tuyển?",
        "liệt kê toàn bộ các phương thức xét tuyển của trường",
        "hồ sơ nhập học gồm những gì",
        "trường có những loại học bổng nào",
        "có bao nhiêu mốc lịch tuyển sinh",
        "có bao nhiêu ngành"
    ]
    for q in queries:
        resp = svc.ask(q)
        print("===" * 20)
        print("QUERY:", q)
        print("ANSWER:\n", resp["answer"])

if __name__ == "__main__":
    run()
