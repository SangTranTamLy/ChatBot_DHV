# -*- coding: utf-8 -*-
"""
DHV Chatbot - Conversational Fast-track (Small Talk).

Detects pure social messages (greeting, thanks, goodbye, identity, capability
questions, short acknowledgements) so they are answered instantly WITHOUT
touching ChromaDB or Ollama.

Design rule: be conservative. A message is small talk only if, after removing
the social phrase and filler words, NOTHING substantive remains. "Xin chào,
trường có ngành Công nghệ thông tin không" is an admissions question, not small talk.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

__all__ = ["SmalltalkReply", "detect_smalltalk", "fold_vietnamese"]


@dataclass
class SmalltalkReply:
    intent: str  # greeting | thanks | goodbye | identity | capabilities | ack
    answer: str
    suggestions: List[str] = field(default_factory=list)


def fold_vietnamese(text: str) -> str:
    """Lowercase, strip diacritics (đ -> d), drop punctuation, collapse spaces."""
    t = unicodedata.normalize("NFD", (text or "").lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = t.replace("đ", "d")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Intent phrases (diacritic-free). Order inside each list: longest first.
_INTENT_PHRASES = {
    "corpus_scope": [
        "he thong co nhung thong tin gi", "tra cuu duoc gi ve truong",
        "co thong tin gi ve dhv", "co nhung thong tin nao",
    ],
    "identity": [
        "ban la ai", "ban ten la gi", "ban ten gi", "ten ban la gi", "ai tao ra ban",
        "ai phat trien ban", "ban la gi", "ban la bot gi", "gioi thieu ve ban", "gioi thieu ban than",
        "who are you", "may la ai", "may ten gi",
    ],
    "capabilities": [
        "ban co the lam duoc gi", "ban co the lam gi", "ban lam duoc gi", "ban giup duoc gi",
        "ban giup gi duoc", "ban ho tro duoc gi", "ban ho tro gi", "ban biet lam gi",
        "huong dan su dung", "cach su dung", "su dung the nao", "toi nen hoi gi", "hoi duoc gi",
        "what can you do", "help", "tro giup",
    ],
    "thanks": [
        "cam on rat nhieu", "cam on nhieu", "cam on ban", "cam on", "cam ta",
        "thank you", "thanks", "thank", "tks", "thx", "ty", "da cam on",
    ],
    "goodbye": ["tam biet", "hen gap lai", "goodbye", "bye bye", "bye", "pai", "chao tam biet"],
    "greeting": [
        "xin chao", "chao buoi sang", "chao buoi chieu", "chao buoi toi", "chao ban", "chao",
        "hello", "helo", "hi", "hey", "alo", "a lo", "hi ban", "hello bot", "ad oi", "bot oi",
    ],
    "ack": ["duoc roi", "hieu roi", "ro roi", "oke", "okay", "ok", "vang", "uh", "um", "da vang", "da ro"],
}

_PRIORITY = ["corpus_scope", "identity", "capabilities", "thanks", "goodbye", "greeting", "ack"]

# Words that carry no admissions substance in a social message.
_FILLERS = {
    "ban", "bot", "ad", "admin", "dhv", "ai", "tro", "ly", "oi", "nhe", "nha",
    "a", "ah", "da", "vay", "the", "nhieu", "rat", "lam", "qua", "minh", "toi", "em",
    "anh", "chi", "moi", "nguoi", "voi", "nhi", "ha", "hen", "roi",
    "cho", "hoi", "co", "khong", "ko", "k", "gi", "va", "ne", "nghe",
}

# Any of these means the user is actually asking about admissions/school.
_ADMISSION_SIGNALS = [
    "nganh", "hoc phi", "hoc bong", "diem", "xet tuyen", "thpt", "hoc ba", "dgnl", "h sca",
    "ho so", "nhap hoc", "lich", "thoi gian", "co so", "dia chi", "hotline", "website",
    "chuyen nganh", "chuong trinh", "tin chi", "mon", "to hop", "hoc ky", "hoc ki",
    "thanh lap", "lich su", "truong o dau", "phuong thuc", "san", "trung tuyen", "xet bo sung",
    "quy che", "hoc phi 1 nam", "nam hoc",
]

_DEFAULT_SUGGESTIONS = [
    "Trường có những ngành nào?",
    "Các phương thức xét tuyển năm 2026",
    "Học phí và chính sách học bổng của DHV",
]

_CAPABILITY_TEXT = (
    "Bạn có thể hỏi mình về một số thông tin tuyển sinh năm 2026 của **Trường Đại học Hùng Vương TP.HCM (DHV)** như:\n\n"
    "- 📚 **Ngành học & Chương trình đào tạo:** 20 ngành chính quy và hơn 50 chương trình đào tạo đa dạng.\n"
    "- 📝 **Phương thức xét tuyển:** 5 phương thức (Điểm thi THPT, Học bạ, ĐGNL ĐHQG-HCM, H-SCA và Trung cấp).\n"
    "- 🎯 **Điểm chuẩn & Ngưỡng đảm bảo chất lượng:** Điểm sàn và điểm chuẩn các năm.\n"
    "- 💰 **Học phí & Học bổng:** Học phí ổn định suốt khóa, học bổng 50% - 100% học phí.\n"
    "- 🏫 **Thông tin chung về trường:** Cơ sở đào tạo, thời gian đào tạo, thông tin liên hệ."
)


def _build_reply(intent: str, has_history: bool) -> SmalltalkReply:
    if intent == "identity":
        answer = (
            "Chào bạn! Mình là **Trợ lý tư vấn tuyển sinh AI** của **Trường Đại học Hùng Vương TP.HCM (DHV)** 🎓.\n\n"
            "Mình hỗ trợ tra cứu thông tin tuyển sinh DHV năm 2026 dựa trên dữ liệu đã được kiểm chứng. "
            "Nếu chưa tìm thấy thông tin phù hợp, mình sẽ nói rõ để bạn tiện kiểm tra thêm với nhà trường.\n\n"
            + _CAPABILITY_TEXT
        )
        return SmalltalkReply(intent=intent, answer=answer, suggestions=_DEFAULT_SUGGESTIONS.copy())

    if intent == "capabilities":
        answer = (
            _CAPABILITY_TEXT + "\n\n"
            "Bạn đang quan tâm đến ngành học, phương thức xét tuyển hay học bổng nào của DHV? "
            "Cứ nhắn cho mình biết nhé!"
        )
        return SmalltalkReply(intent=intent, answer=answer, suggestions=_DEFAULT_SUGGESTIONS.copy())

    if intent == "greeting":
        answer = (
            "Xin chào bạn! Rất vui được gặp bạn 🌸.\n\n"
            "Mình là Trợ lý tư vấn tuyển sinh của **Trường Đại học Hùng Vương TP.HCM (DHV)**. "
            "Bạn đang quan tâm đến ngành đào tạo, phương thức xét tuyển, điểm chuẩn hay học phí, học bổng năm 2026 của trường nè? "
            "Hãy nhắn cho mình câu hỏi của bạn nhé!"
        )
        return SmalltalkReply(intent=intent, answer=answer, suggestions=_DEFAULT_SUGGESTIONS.copy())

    if intent == "thanks":
        answer = (
            "Dạ không có chi nè! Rất vui vì đã hỗ trợ được cho bạn. "
            "Nếu bạn cần thêm thông tin gì về tuyển sinh DHV 2026, cứ nhắn cho mình bất cứ lúc nào nhé! 😊"
            if has_history
            else "Dạ không có chi! Bạn cần mình giải đáp thêm thông tin gì về Trường Đại học Hùng Vương TP.HCM (DHV) không nè?"
        )
        return SmalltalkReply(
            intent=intent,
            answer=answer,
            suggestions=["Trường có những ngành nào?", "Mức học phí năm 2026", "Chính sách học bổng"],
        )

    if intent == "goodbye":
        answer = (
            "Tạm biệt bạn nhé! Chúc bạn luôn tự tin, học tập tốt và đạt được kết quả như ý. "
            "Hẹn sớm gặp lại bạn tại Trường Đại học Hùng Vương TP.HCM (DHV) nha! 🎓"
        )
        return SmalltalkReply(intent=intent, answer=answer, suggestions=[])

    if intent == "ack":
        answer = (
            "Dạ vâng! Bạn cần mình giải đáp thêm thông tin gì về tuyển sinh DHV nữa không nè?"
            if has_history
            else "Dạ vâng! Bạn muốn tra cứu thông tin tuyển sinh nào của DHV ạ?"
        )
        return SmalltalkReply(intent=intent, answer=answer, suggestions=_DEFAULT_SUGGESTIONS.copy())

    else:
        answer = (
            "Cơ sở dữ liệu của mình chứa toàn bộ thông tin tuyển sinh chính thức năm 2026 của **Trường Đại học Hùng Vương TP.HCM (DHV)**, "
            "bao gồm 20 ngành đào tạo, 5 phương thức xét tuyển, biểu phí học tập và các gói học bổng hấp dẫn.\n\n"
            "Bạn có thể đặt câu hỏi về bất kỳ nội dung nào ở trên nhé!"
        )
        return SmalltalkReply(intent="corpus_scope", answer=answer, suggestions=_DEFAULT_SUGGESTIONS)


def detect_smalltalk(question: str, has_history: bool = False) -> Optional[SmalltalkReply]:
    """Detects whether a message is purely conversational small talk.

    Returns a SmalltalkReply if matched, or None if the message has substantive content.
    """
    if not question or not question.strip():
        return None

    raw_folded = fold_vietnamese(question)
    tokens = raw_folded.split()
    if not tokens:
        return None

    padded_question = f" {raw_folded} "

    # If any substantive admission signal is present, it is NOT small talk.
    for sig in _ADMISSION_SIGNALS:
        if f" {sig} " in padded_question:
            return None

    # Check each intent by priority
    for intent in _PRIORITY:
        for phrase in _INTENT_PHRASES[intent]:
            padded_phrase = f" {phrase} "
            if padded_phrase in padded_question:
                # Remove the phrase and check if remaining words are just fillers
                remainder = padded_question.replace(padded_phrase, " ")
                rem_tokens = [tok for tok in remainder.split() if tok not in _FILLERS]
                if not rem_tokens:
                    return _build_reply(intent, has_history)

    return None
