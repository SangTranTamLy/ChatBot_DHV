import os
import sys
import logging
import json

sys.stdout.reconfigure(encoding='utf-8')

from src.chatbot.chat_service import ask_chatbot

logging.basicConfig(level=logging.INFO)
result = ask_chatbot("nhập học cần những gì")
print("Status:", result.get("status"))
print("Answer:", result.get("answer"))
if "trace" in result:
    trace = result["trace"]
    print("Intent:", trace.get("intent"))
    print("Categories:", trace.get("router", {}).get("categories"))
    print("Retrieval docs count:", trace.get("retrieved_docs_count"))
    print("Evidence count:", trace.get("evidence_count"))
    print("Scope:", trace.get("scope"))
    if "multi_issue" in trace:
        print("Multi issue:")
        print(json.dumps(trace.get("multi_issue"), ensure_ascii=False, indent=2))
