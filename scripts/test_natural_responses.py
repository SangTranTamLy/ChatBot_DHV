from src.chatbot.chat_service import get_chat_service

def test_chatbot():
    svc = get_chat_service()
    
    questions = [
        "Website tuyển sinh của trường DHV là gì?",
        "Đăng ký xét tuyển như thế nào?",
        "Học phí 2026 của trường là bao nhiêu?",
        "Nhập học cần những giấy tờ gì?",
        "Em được 18.5 điểm thi, môn Toán 6 điểm thì xét tuyển vào Luật Kinh tế được không?",
        "Trường có bao nhiêu phương thức xét tuyển?"
    ]
    
    for i, q in enumerate(questions, 1):
        print(f"\n--- CÂU {i} ---")
        print(f"Hỏi: {q}")
        try:
            resp = svc.ask(q)
            print(f"Chatbot: {resp['answer']}")
        except Exception as e:
            print(f"Lỗi: {e}")

if __name__ == "__main__":
    test_chatbot()
