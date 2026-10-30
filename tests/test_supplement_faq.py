from src.chatbot.supplement_faq import lookup_supplement


def test_supplement_matches_exact_and_paraphrased_questions():
    assert lookup_supplement("bãi đỗ xe có tính phí không?")["supplement"]["id"] == "UQ0345"
    assert lookup_supplement("Website của Khoa Luật là gì?")["supplement"]["id"] == "UQ0141"


def test_supplement_ignores_unrelated_questions():
    for question in ("Thời tiết hôm nay thế nào?", "DHV có ký túc xá không?", ""):
        assert lookup_supplement(question) is None


def test_supplement_rejects_same_template_with_different_name():
    assert lookup_supplement("Website của Khoa Y DHV là gì?") is None
    assert lookup_supplement("Website của Viện Kinh tế DHV là gì?") is None


def test_supplement_rejects_other_year():
    assert lookup_supplement("Lễ ra quân Chiến dịch Mùa Hè Xanh 2027 của DHV được tổ chức vào ngày nào?") is None
    assert lookup_supplement("Lễ ra quân Chiến dịch Mùa Hè Xanh 2026 của DHV được tổ chức vào ngày nào?") is not None


def test_supplement_without_official_source_is_labelled():
    result = lookup_supplement("bãi đỗ xe có tính phí không?")
    assert result["sources"] == [] and "chưa có nguồn chính thức" in result["answer"]
    official = lookup_supplement("Viện IATAI của trường phụ trách những lĩnh vực đào tạo và nghiên cứu nào?")
    assert official["sources"] and "chưa có nguồn chính thức" not in official["answer"]


def test_other_school_question_keeps_refusal():
    from src.chatbot.rag_chain import ask_chatbot

    result = ask_chatbot("Ngành Trí tuệ nhân tạo tại UEH có những chuyên ngành nào?", retriever=object(), llm=object())
    assert result["status"] == "out_of_scope"
    assert "supplement" not in result["trace"]
