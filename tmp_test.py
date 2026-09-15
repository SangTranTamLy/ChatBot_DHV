from src.chatbot.rag_chain import ask_chatbot
import sys
import io

# Ensure utf-8 output encoding for Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def main():
    questions = [
        "ngành công nghệ thông tin có bao nhiêu chuyên ngành của trường đại học hùng vường tp hc",
        "danh sách các chuyên ngành của ngành Quản trị kinh doanh là gì",
        "ngành ngôn ngữ anh có những chuyên ngành nào"
    ]
    for q in questions:
        print(f"Q: {q}")
        response = ask_chatbot(q)
        print(f"A: {response.get('answer', 'No answer')}")
        print(f"Status: {response.get('status', 'No status')}")
        if 'catalog' in response:
            print(f"Catalog Info: {response['catalog']}")
        print("-" * 50)

if __name__ == "__main__":
    main()
