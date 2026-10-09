import sys
import logging
from src.chatbot.chat_service import ask_chatbot
from src.chatbot.query_analysis import ConversationState

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.ERROR)

def test_multiturn(dialogue):
    print(f"\n--- MULTI-TURN TEST ---")
    state = ConversationState().to_dict()
    for q in dialogue:
        print(f"User: {q}")
        result = ask_chatbot(q, conversation_state=state)
        print("Bot:", result.get("answer"))
        if "state" in result:
            state = result["state"]

test_multiturn(["nhập học cần những gì", "còn phí thì sao?"])
test_multiturn(["hồ sơ nhập học gồm những gì", "cần nộp khi nào?"])
test_multiturn(["điểm chuẩn CNTT", "nhập học cần gì?"])
