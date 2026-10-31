from src.chatbot.supplement_faq import lookup_supplement


def test_supplement_matches_exact_and_paraphrased_questions():
    assert lookup_supplement("Viện IATAI phụ trách những lĩnh vực đào tạo và nghiên cứu nào?")["supplement"]["id"] == "UQ0108"
    assert lookup_supplement("Viện IATAI có kết nối đối tác trong lĩnh vực an toàn thông tin không?")["supplement"]["id"] == "UQ0333"


def test_supplement_ignores_unrelated_questions():
    for question in ("Thời tiết hôm nay thế nào?", "DHV có ký túc xá không?", ""):
        assert lookup_supplement(question) is None


def test_supplement_rejects_same_template_with_different_name():
    assert lookup_supplement("Website của Khoa Y DHV là gì?") is None
    assert lookup_supplement("Website của Viện Kinh tế DHV là gì?") is None


def test_supplement_rejects_other_year():
    assert lookup_supplement("Lễ ra quân Chiến dịch Mùa Hè Xanh 2027 của DHV được tổ chức vào ngày nào?") is None
    assert lookup_supplement("Lễ ra quân Chiến dịch Mùa Hè Xanh 27 của DHV được tổ chức vào ngày nào?") is None
    assert lookup_supplement("Lễ ra quân Chiến dịch Mùa Hè Xanh 2026 của DHV được tổ chức vào ngày nào?") is not None


def test_supplement_uses_only_official_sources():
    assert lookup_supplement("bãi đỗ xe có tính phí không?") is None
    assert lookup_supplement("Website của Khoa Luật DHV là gì?") is None
    official = lookup_supplement("Viện IATAI của trường phụ trách những lĩnh vực đào tạo và nghiên cứu nào?")
    assert official["sources"] == [{"title": "Nguồn DHV", "url": "https://iatai.dhv.edu.vn/"}]


def test_supplement_rejects_other_major():
    assert lookup_supplement("Sinh viên ngành Dược có được học các học phần thực hành nghề nghiệp trước khi tốt nghiệp không?") is None
    question = "Sinh viên ngành Kế toán có được học các học phần thực hành nghề nghiệp trước khi tốt nghiệp không?"
    assert lookup_supplement(question)["supplement"]["id"] == "UQ0066"
    follow_up = "Sinh viên có được học các học phần thực hành nghề nghiệp trước khi tốt nghiệp không?"
    assert lookup_supplement(follow_up, "Luật") is None
    assert lookup_supplement(follow_up, "Kế toán")["supplement"]["id"] == "UQ0066"


def test_supplement_wrapper_respects_incoming_state():
    from src.chatbot.rag_chain import ask_chatbot

    question = "Lễ ra quân Chiến dịch Mùa Hè Xanh của DHV vào ngày nào?"
    assert "supplement" not in ask_chatbot(question, retriever=object(), llm=object(), conversation_state={"current_year": 2025})["trace"]
    relative = "Lễ ra quân Chiến dịch Mùa Hè Xanh năm học tới của DHV được tổ chức vào ngày nào?"
    assert "supplement" not in ask_chatbot(relative, retriever=object(), llm=object())["trace"]
    soft_skills = "Sinh viên được rèn luyện những kỹ năng mềm gì?"
    assert "supplement" not in ask_chatbot(soft_skills, retriever=object(), llm=object(), conversation_state={"current_major": "Luật"})["trace"]


def test_other_school_question_keeps_refusal():
    from src.chatbot.rag_chain import ask_chatbot

    result = ask_chatbot("Ngành Trí tuệ nhân tạo tại UEH có những chuyên ngành nào?", retriever=object(), llm=object())
    assert result["status"] == "out_of_scope"
    assert "supplement" not in result["trace"]
