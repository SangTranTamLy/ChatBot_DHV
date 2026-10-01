"""Build the locked Phase 5 QA dataset from verified DHV Structured JSON.

The generator deliberately creates paraphrase families from corpus records instead of
copying an answer bank into the runtime.  Every factual row keeps the record/document
provenance that produced it.  Families, rather than individual rows, are assigned to
the 80/20 split to prevent train/test paraphrase leakage.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "data" / "evaluation"
TARGET_YEAR = 2026
TARGET_TOTAL = 1000
TEST_FAMILIES = 50


def fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("đ", "d")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def source_metadata(document: Mapping[str, Any]) -> dict[str, object]:
    source = document.get("source") or {}
    return {
        "document_id": document.get("document_id"),
        "title": document.get("title"),
        "category": document.get("category"),
        "year": document.get("year"),
        "status": source.get("status"),
        "verified": source.get("verified"),
        "source_type": source.get("source_type"),
        "source_url": source.get("source_url"),
        "source_date": source.get("source_date"),
    }


def load_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(PROCESSED.rglob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        source = document.get("source") or {}
        if (
            document.get("year") != TARGET_YEAR
            or source.get("verified") is not True
            or source.get("status") != "verified"
        ):
            continue
        for record in document.get("records") or []:
            if not isinstance(record, Mapping):
                continue
            item = dict(record)
            item["document_id"] = document.get("document_id")
            item["document_title"] = document.get("title")
            item["document_category"] = document.get("category")
            item["source_metadata"] = source_metadata(document)
            item["evidence_id"] = f"{document.get('document_id')}:{record.get('record_id')}"
            records.append(item)
    return records


def unique_by(items: Iterable[Mapping[str, Any]], key: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[object] = set()
    for item in items:
        value = key(item)
        if value in seen:
            continue
        seen.add(value)
        output.append(dict(item))
    return output


def fact_source(record: Mapping[str, Any]) -> tuple[list[str], list[str], list[dict[str, object]]]:
    return (
        [str(record["evidence_id"])],
        [str(record["document_id"])],
        [dict(record["source_metadata"])],
    )


def answer_policy(
    *,
    status: str,
    intent: str,
    required: Iterable[object] = (),
    forbidden: Iterable[object] = (),
) -> dict[str, object]:
    return {
        "status": status,
        "intent": intent,
        "required_facts": [str(item) for item in required if str(item).strip()],
        "forbidden_facts": [str(item) for item in forbidden if str(item).strip()],
    }


def record_family(
    *,
    family_id: str,
    questions: list[str],
    intent: str,
    semantic_intent: str,
    category: str,
    required: Iterable[object] = (),
    forbidden: Iterable[object] = (),
    status: str = "ok",
    answer_mode: str = "factual",
    records: Iterable[Mapping[str, Any]] = (),
    year: int = TARGET_YEAR,
    score_query_type: str | None = None,
    admission_method: str | None = None,
    major: str | None = None,
    program: str | None = None,
    conversation_id: str | None = None,
    turn_indexes: Iterable[int] | None = None,
    state_before: Mapping[str, object] | None = None,
    expected_state: Mapping[str, object] | None = None,
    row_overrides: list[Mapping[str, object]] | None = None,
    conversation_ids: Iterable[str | None] | None = None,
) -> dict[str, object]:
    evidence_ids: list[str] = []
    source_ids: list[str] = []
    sources: list[dict[str, object]] = []
    for record in records:
        ids, docs, metadata = fact_source(record)
        evidence_ids.extend(ids)
        source_ids.extend(docs)
        sources.extend(metadata)
    evidence_ids = list(dict.fromkeys(evidence_ids))
    source_ids = list(dict.fromkeys(source_ids))
    sources = list({json.dumps(value, ensure_ascii=False, sort_keys=True): value for value in sources}.values())
    turns = list(turn_indexes or [0] * len(questions))
    if len(turns) != len(questions):
        raise ValueError(f"turn_indexes length mismatch for {family_id}")
    rows: list[dict[str, object]] = []
    overrides = list(row_overrides or [{} for _ in questions])
    conv_ids = list(conversation_ids or [conversation_id] * len(questions))
    if len(overrides) != len(questions) or len(conv_ids) != len(questions):
        raise ValueError(f"per-row metadata length mismatch for {family_id}")
    for index, (question, turn_index) in enumerate(zip(questions, turns), start=1):
        override = dict(overrides[index - 1])
        row_records = override.pop("records", None)
        row_required = override.pop("required", required)
        row_forbidden = override.pop("forbidden", forbidden)
        row_intent = str(override.get("intent", intent))
        row_status = str(override.get("expected_status", status))
        row_evidence_ids = evidence_ids
        row_source_ids = source_ids
        row_sources = sources
        if row_records is not None:
            row_evidence_ids = []
            row_source_ids = []
            row_sources = []
            for row_record in row_records:  # type: ignore[union-attr]
                ids, docs, metadata = fact_source(row_record)
                row_evidence_ids.extend(ids)
                row_source_ids.extend(docs)
                row_sources.extend(metadata)
            row_evidence_ids = list(dict.fromkeys(row_evidence_ids))
            row_source_ids = list(dict.fromkeys(row_source_ids))
            row_sources = list({json.dumps(value, ensure_ascii=False, sort_keys=True): value for value in row_sources}.values())
        row = {
                "family_id": family_id,
                "variant_index": index,
                "question": question,
                "expected_answer": answer_policy(
                    status=row_status,
                    intent=row_intent,
                    required=row_required,
                    forbidden=row_forbidden,
                ),
                "intent": intent,
                "semantic_intent": semantic_intent,
                "category": category,
                "year": year,
                "expected_status": status,
                "answer_mode": answer_mode,
                "score_query_type": score_query_type,
                "admission_method": admission_method,
                "major": major,
                "program": program,
                "evidence_ids": row_evidence_ids,
                "source_document_ids": row_source_ids,
                "source_metadata": row_sources,
                "conversation_id": conv_ids[index - 1],
                "turn_index": turn_index,
                "state_before": dict(state_before or {}),
                "expected_state": dict(expected_state or {}),
            }
        row.update(override)
        rows.append(row)
    return {"family_id": family_id, "rows": rows}


def score_questions(name: str, major: str, method: str, value: object, kind: str) -> list[str]:
    labels = {"thpt": "thi tốt nghiệp THPT", "hoc_ba": "học bạ", "dgnl": "ĐGNL"}
    method_label = labels.get(method, method)
    value_text = str(value)
    if kind == "admission":
        return [
            f"Điểm chuẩn {name} theo {method_label} là bao nhiêu?",
            f"{name} điểm chuẩn {method_label} năm 2026 mức nào?",
            f"Cho em hỏi điểm chuẩn {name} theo {method_label}, mức nào vậy ạ?",
            f"{name} {method_label} điểm chuẩn bn?",
        ]
    if kind == "application":
        return [
            f"Ngưỡng đầu vào {name} theo {method_label} là bao nhiêu?",
            f"Điểm sàn để nộp {name} bằng {method_label} là mức nào?",
            f"Muốn đăng ký {name} theo {method_label} cần tối thiểu mấy điểm?",
            f"{name} {method_label} điểm nhận hồ sơ bn?",
        ]
    return [
        f"Xét tuyển bổ sung {name} bằng {method_label} cần bao nhiêu điểm?",
        f"Ngưỡng bổ sung của {name}, phương thức {method_label}, là bao nhiêu?",
        f"Đợt bổ sung {name} theo {method_label} lấy từ mức nào vậy?",
        f"{name} xét bs {method_label} bn điểm?",
    ]


def build_families(records: list[dict[str, Any]]) -> list[dict[str, object]]:
    families: list[dict[str, object]] = []
    by_type: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_type[str(record.get("record_type") or "")].append(record)

    admission = sorted(by_type["admission_score"], key=lambda r: str(r.get("evidence_id")))[:50]
    for i, record in enumerate(admission, start=1):
        method = str(record.get("method") or "")
        major = str(record.get("major_name") or "")
        families.append(
            record_family(
                family_id=f"F_ADMISSION_{i:03d}",
                questions=score_questions(major, major, method, record.get("raw_value"), "admission"),
                intent="HOI_DIEM_TRUNG_TUYEN",
                semantic_intent="admission_score_lookup",
                category="diem_trung_tuyen",
                required=[record.get("raw_value")],
                records=[record],
                score_query_type="admission_score_lookup",
                admission_method=method,
                major=major,
            )
        )

    all_applications = [r for r in by_type["application_threshold"] if r.get("major_name")]
    applications = list(all_applications)
    applications = sorted(applications, key=lambda r: str(r.get("evidence_id")))[:22]
    for i, record in enumerate(applications, start=1):
        method = str(record.get("method") or "")
        major = str(record.get("major_name") or "")
        families.append(
            record_family(
                family_id=f"F_THRESHOLD_{i:03d}",
                questions=score_questions(major, major, method, record.get("raw_value"), "application"),
                intent="HOI_NGUONG_DAU_VAO",
                semantic_intent="application_threshold_lookup",
                category="nguong_dau_vao",
                required=[record.get("raw_value")],
                records=[record],
                score_query_type="application_threshold_lookup",
                admission_method=method,
                major=major,
            )
        )

    supplementary = sorted(by_type["supplementary_threshold"], key=lambda r: str(r.get("evidence_id")))[:18]
    for i, record in enumerate(supplementary, start=1):
        method = str(record.get("method") or "")
        major = str(record.get("major_name") or "")
        families.append(
            record_family(
                family_id=f"F_SUPPLEMENTARY_{i:03d}",
                questions=score_questions(major, major, method, record.get("raw_value"), "supplementary"),
                intent="HOI_XET_TUYEN_BO_SUNG",
                semantic_intent="supplementary_threshold_lookup",
                category="xet_tuyen_bo_sung",
                required=[record.get("raw_value")],
                records=[record],
                score_query_type="supplementary_threshold_lookup",
                admission_method=method,
                major=major,
            )
        )

    tuition = next(iter(by_type["tuition"]), None)
    if tuition is None:
        raise ValueError("verified tuition record is required")
    tuition_claims = [
        ("per_credit", tuition.get("tuition_per_credit_vnd"), "mỗi tín chỉ", "mỗi tín chỉ"),
        ("semester_tuition", tuition.get("tuition_amount_vnd"), "học phí học kỳ I", "học phí kỳ I"),
        ("credits", tuition.get("credits"), "số tín chỉ tối thiểu học kỳ I", "tín chỉ tối thiểu"),
        ("admission_fee", tuition.get("admission_fee_vnd"), "phí nhập học", "phí nhập học"),
        ("elearning_fee", tuition.get("elearning_fee_vnd"), "phí e-learning", "phí e-learning"),
        ("english_fee", tuition.get("english_test_fee_vnd"), "phí kiểm tra tiếng Anh", "phí tiếng Anh"),
        ("total_cost", tuition.get("total_cost_breakdown"), "tổng chi phí học kỳ I", "tổng chi phí"),
    ]
    for i, (claim_key, value, label, short_label) in enumerate(tuition_claims * 2, start=1):
        audience = "phụ huynh" if i > len(tuition_claims) else "em"
        families.append(
            record_family(
                family_id=f"F_TUITION_{i:03d}",
                questions=[
                    f"{audience.capitalize()} cho hỏi {label} ở DHV là bao nhiêu?",
                    f"{audience.capitalize()} muốn biết {label} năm 2026 mức nào vậy?",
                    f"{audience.capitalize()} hỏi DHV {short_label} bao nhiêu ạ?",
                    f"{audience.capitalize()} cần biết {short_label} DHV bn?",
                ],
                intent="HOI_HOC_PHI",
                semantic_intent="tuition",
                category="hoc_phi",
                required=[value],
                records=[tuition],
                major=None,
            )
        )

    scholarship = []
    for record in by_type["scholarship_policy"] + by_type["scholarship_fund"]:
        text = record.get("policy_text") or record.get("raw_value") or record.get("fund_amount_vnd")
        if text:
            scholarship.append(record)
    scholarship = unique_by(scholarship, lambda r: fold(r.get("policy_text") or r.get("raw_value") or r.get("fund_amount_vnd")))
    for i, record in enumerate(scholarship[:24], start=1):
        fact = record.get("policy_text") or record.get("raw_value") or record.get("fund_amount_vnd")
        fact_text = str(fact)
        fact_tag = fact_text[:42].strip(" .")
        families.append(
            record_family(
                family_id=f"F_SCHOLARSHIP_{i:03d}",
                questions=[
                    f"DHV có thông tin học bổng mục tham chiếu {i} không?",
                    f"Cho em hỏi chính sách học bổng DHV mục {i}.",
                    f"Phụ huynh muốn biết gói học bổng tham chiếu {i} năm 2026.",
                    f"Hoc bong DHV muc tham chieu {i} sao ạ?",
                ],
                intent="HOI_HOC_BONG",
                semantic_intent="scholarship",
                category="hoc_bong",
                required=[fact_text[:55]],
                records=[record],
            )
        )

    enrollment = sorted(by_type["enrollment_document"], key=lambda r: str(r.get("evidence_id")))
    for i, record in enumerate(enrollment[:24], start=1):
        name = str(record.get("document_name") or "")
        families.append(
            record_family(
                family_id=f"F_DOCUMENT_{i:03d}",
                questions=[
                    f"Hồ sơ nhập học có cần {name} không?",
                    f"Cho em hỏi giấy tờ nhập học gồm {name} chứ ạ?",
                    f"Làm thủ tục DHV cần mang {name} không?",
                    f"Ho so nhap hoc can {fold(name)} khong?",
                ],
                intent="HOI_HO_SO",
                semantic_intent="enrollment_documents",
                category="ho_so",
                required=[name],
                records=[record],
            )
        )

    deadlines = sorted(by_type["deadline"], key=lambda r: str(r.get("evidence_id")))
    selected_enrollment = [
        r
        for r in enrollment
        if any(term in fold(r.get("document_name")) for term in ("co so", "huong dan", "ban chinh"))
    ]
    # Keep each enrollment family tied to a different structured record.  The
    # two deadline records are already different source facts; repeating the
    # same date would create cross-family duplicates without adding coverage.
    unique_enrollment = unique_by(enrollment, lambda r: fold(r.get("document_name")))
    preferred = selected_enrollment + [r for r in unique_enrollment if r not in selected_enrollment]
    nhap_records = deadlines[:2] + preferred[:12]
    for i, record in enumerate(nhap_records, start=1):
        is_deadline = record.get("record_type") == "deadline"
        if is_deadline:
            date = record.get("deadline_date")
            source_title = str(record.get("document_title") or "tài liệu DHV")
            questions = [
                f"Theo tài liệu {source_title}, hạn tuyển sinh/nhập học là ngày nào?",
                f"DHV nhận hồ sơ đến {date} theo tài liệu {source_title} phải không?",
                f"Cho mình hỏi mốc thời gian tuyển sinh DHV trong tài liệu {source_title}.",
                f"Han tuyen sinh DHV theo tai lieu {fold(source_title)} den ngay nao?",
            ]
            intent = "HOI_LICH_TUYEN_SINH"
            semantic = "deadline"
            category = "lich_tuyen_sinh"
            required = [date]
        else:
            name = str(record.get("document_name") or "")
            questions = [
                f"Làm thủ tục nhập học DHV có liên quan đến {name} thế nào?",
                f"Địa điểm/thành phần nhập học có ghi {name} không?",
                f"Khi nhập học trường có hướng dẫn {name} chứ?",
                f"Nhap hoc DHV: {fold(name)}?",
            ]
            intent = "HOI_NHAP_HOC"
            semantic = "enrollment"
            category = "nhap_hoc"
            required = [name]
        families.append(
            record_family(
                family_id=f"F_ENROLLMENT_{i:03d}",
                questions=questions,
                intent=intent,
                semantic_intent=semantic,
                category=category,
                required=required,
                records=[record],
            )
        )

    method_record = next(iter(by_type["admission_method"]), None)
    formulas = sorted(by_type["score_formula"], key=lambda r: str(r.get("evidence_id")))
    if method_record:
        families.append(
            record_family(
                family_id="F_METHOD_001",
                questions=[
                    "DHV năm 2026 có những phương thức xét tuyển nào?",
                    "Trường xét tuyển bằng thi tốt nghiệp THPT không ạ?",
                    "Cho em hỏi phương thức tuyển sinh DHV 2026.",
                    "DHV co xet diem thi THPT khong?",
                ],
                intent="HOI_PHUONG_THUC_XET_TUYEN",
                semantic_intent="admission_methods",
                category="phuong_thuc_xet_tuyen",
                required=[method_record.get("method_text") or "THPT"],
                records=[method_record],
            )
        )
    for i, record in enumerate(formulas, start=2):
        text = str(record.get("formula_text") or "")
        topic = text[:38].strip(" .")
        families.append(
            record_family(
                family_id=f"F_FORMULA_{i:03d}",
                questions=[
                    f"Điểm xét tuyển DHV được tính theo nội dung {topic} như thế nào?",
                    f"Cho em hỏi công thức tính điểm xét tuyển, phần {topic}.",
                    f"Cách quy đổi điểm vào DHV theo {topic} ra sao ạ?",
                    f"Cach tinh diem xet tuyen DHV theo {fold(topic)}?",
                ],
                intent="HOI_CACH_TINH_DIEM",
                semantic_intent="score_formula",
                category="cach_tinh_diem",
                required=[text[:60]],
                records=[record],
            )
        )
    method_rows = [r for r in applications if r.get("major_name")][:15]
    for i, record in enumerate(method_rows, start=5):
        major = str(record.get("major_name") or "")
        method = str(record.get("method") or "")
        method_label = {"thpt": "thi tốt nghiệp THPT", "hoc_ba": "học bạ", "dgnl": "ĐGNL"}.get(method, method)
        families.append(
            record_family(
                family_id=f"F_METHOD_{i:03d}",
                questions=[
                    f"{major} có xét theo {method_label} không?",
                    f"Phương thức {method_label} có áp dụng cho {major} chứ?",
                    f"Em muốn dùng {method_label} đăng ký {major} được không ạ?",
                    f"{major} xet {fold(method_label)} duoc khong?",
                ],
                intent="HOI_PHUONG_THUC_XET_TUYEN",
                semantic_intent="admission_method_mapping",
                category="phuong_thuc_xet_tuyen",
                required=[method_label, major],
                records=[record],
                admission_method=method,
                major=major,
            )
        )

    majors = unique_by(
        [r for r in by_type["major"] if r.get("document_id") == "tong-quan-tuyen-sinh-dhv-2026"],
        lambda r: r.get("major_code"),
    )
    for i, record in enumerate(majors[:20], start=1):
        major = str(record.get("major_name") or "")
        code = str(record.get("major_code") or "")
        families.append(
            record_family(
                family_id=f"F_MAJOR_{i:03d}",
                questions=[
                    f"Mã ngành {major} của DHV là bao nhiêu?",
                    f"Cho em hỏi ngành {major} mã nào ạ?",
                    f"{major} ở DHV là ngành gì, mã tuyển sinh bao nhiêu?",
                    f"Ma nganh {fold(major)} DHV?",
                ],
                intent="HOI_NGANH",
                semantic_intent="major_identity",
                category="nganh_dao_tao",
                required=[major, code],
                records=[record],
                major=major,
            )
        )
    program_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen_programs: set[str] = set()
    for record in majors:
        for program in record.get("programs") or []:
            name = str(program.get("program_name") or "")
            if not name or fold(name) in seen_programs:
                continue
            seen_programs.add(fold(name))
            program_rows.append((record, dict(program)))
    for i, (record, program) in enumerate(program_rows[:14], start=1):
        pname = str(program.get("program_name") or "")
        parent = str(program.get("parent_major") or record.get("major_name") or "")
        families.append(
            record_family(
                family_id=f"F_PROGRAM_{i:03d}",
                questions=[
                    f"{pname} thuộc ngành nào ở DHV?",
                    f"Cho em hỏi chương trình {pname} là của ngành nào?",
                    f"{pname} có phải là một ngành riêng không ạ?",
                    f"Chuong trinh {fold(pname)} thuoc nganh nao?",
                ],
                intent="HOI_CHUONG_TRINH",
                semantic_intent="major_program_relation",
                category="nganh_dao_tao",
                required=[pname, parent],
                records=[record],
                major=parent,
                program=pname,
            )
        )

    catalog = next(iter(by_type["major_catalog_summary"]), None)
    if catalog:
        for i, label in enumerate(("bao nhiêu ngành", "danh sách ngành", "ngành chính", "mã ngành", "ngành đào tạo", "toàn bộ ngành", "các ngành đang tuyển sinh", "danh mục ngành"), start=1):
            families.append(
                record_family(
                    family_id=f"F_SCHOOL_{i:03d}",
                    questions=[
                        f"DHV có {label} vậy?",
                        f"Cho mình hỏi {label} của trường.",
                        f"Thông tin cơ bản về {label} DHV 2026 là gì?",
                        f"DHV {fold(label)}?",
                    ],
                    intent="DANH_SACH_NGANH",
                    semantic_intent="school_basic_info" if i <= 2 else "major_catalog",
                    category="nganh_dao_tao",
                    required=[catalog.get("major_count") or "20"],
                    records=[catalog],
                )
            )

    edge_specs = [
        ("F_NODATA_001", "Học phí DHV năm 2027 bao nhiêu?", "HOI_HOC_PHI", "hoc_phi", 2027),
        ("F_NODATA_002", "Điểm chuẩn CNTT năm 2024 là bao nhiêu?", "HOI_DIEM_TRUNG_TUYEN", "diem_trung_tuyen", 2024),
        ("F_NODATA_003", "Điểm chuẩn ngành Y khoa DHV 2026?", "HOI_DIEM_TRUNG_TUYEN", "diem_trung_tuyen", 2026),
        ("F_NODATA_004", "Thông tin tuyển sinh DHV năm 2027", "SCHOOL_INFO", "thong_tin_truong", 2027),
        ("F_NODATA_005", "Học phí ngành CNTT năm 2024 có được xác nhận không?", "HOI_HOC_PHI", "hoc_phi", 2024),
    ]
    for fid, base, intent, category, year in edge_specs:
        families.append(
            record_family(
                family_id=fid,
                questions=[
                    base,
                    "Cho em biết giúp: " + base,
                    "Theo dữ liệu đang có, " + base,
                    "Với năm được hỏi, " + base,
                ],
                intent=intent,
                semantic_intent="in_scope_no_data",
                category=category,
                status="no_data",
                answer_mode="abstention",
                year=year,
            )
        )

    out_specs = [
        ("F_OUT_001", "Thời tiết hôm nay ở thành phố thế nào?"),
        ("F_OUT_002", "Công thức nấu phở bò như thế nào?"),
        ("F_OUT_003", "Cho em hỏi việc làm sau tốt nghiệp ở trường khác."),
        ("F_OUT_004", "Giá vàng hôm nay bao nhiêu?"),
        ("F_OUT_005", "Bạn tư vấn chuyện tình cảm giúp mình được không?"),
    ]
    for fid, base in out_specs:
        families.append(
            record_family(
                family_id=fid,
                questions=[
                    base,
                    "Cho mình hỏi: " + base,
                    "Bạn có thể trả lời giúp: " + base,
                    "Mình muốn biết, " + base,
                ],
                intent="OUT_OF_SCOPE",
                semantic_intent="out_of_scope",
                category="out_of_scope",
                status="out_of_scope",
                answer_mode="abstention",
            )
        )

    clarification_bases = [
        "Em được 18 điểm có đủ điều kiện nộp không?",
        "Em có 18 điểm, cho em hỏi có đủ không ạ?",
        "Em được 720 điểm, xét được không?",
        "18 điểm thì có thể đăng ký không?",
        "Điểm của em có đủ điều kiện nộp hồ sơ không?",
    ]
    for i, base in enumerate(clarification_bases, start=1):
        questions = [
            base,
            "Cho em biết giúp: " + base,
            "Theo kết quả này, " + base,
            "Năm 2026, " + base,
        ]
        families.append(
            record_family(
                family_id=f"F_CLARIFICATION_{i:03d}",
                questions=questions,
                intent="HOI_NGUONG_DAU_VAO",
                semantic_intent="clarification",
                category="clarification",
                status="clarification",
                answer_mode="clarification",
                score_query_type="personal_score_comparison",
            )
        )

    social = [
        ("F_SOCIAL_001", ["Xin chào", "Chào bạn", "Hello", "Alo"], "GREETING", "greeting", "ok"),
        ("F_SOCIAL_002", ["Cảm ơn bạn", "Em cảm ơn ạ", "Thanks nhé", "Cảm ơn nhiều nha"], "OUT_OF_SCOPE", "thanks", "out_of_scope"),
        ("F_SOCIAL_003", ["Tạm biệt", "Hẹn gặp lại", "Bye nhé", "Mình xin phép kết thúc"], "OUT_OF_SCOPE", "goodbye", "out_of_scope"),
    ]
    for fid, questions, intent, semantic, status in social:
        families.append(
            record_family(
                family_id=fid,
                questions=questions,
                intent=intent,
                semantic_intent=semantic,
                category="system/small_talk",
                status=status,
                answer_mode="system" if status == "ok" else "abstention",
            )
        )

    multi_majors = [
        ("Công nghệ thông tin", "dgnl", "720"),
        ("Marketing", "thpt", "16"),
        ("Quản trị kinh doanh", "hoc_ba", "19"),
        ("Luật", "thpt", "18"),
        ("Trí tuệ nhân tạo", "dgnl", "650"),
    ]
    for i, (major, method, score) in enumerate(multi_majors, start=1):
        method_label = {"dgnl": "ĐGNL", "thpt": "thi tốt nghiệp THPT", "hoc_ba": "học bạ"}[method]
        score_record = next(
            (
                record
                for record in all_applications
                if str(record.get("major_name") or "") == major
                and str(record.get("method") or "") == method
            ),
            applications[0],
        )
        turn_one = [
            f"Em xét {method_label} được {score} điểm cho {major}",
            f"Em có {score} điểm {method_label}, đang tính vào {major}",
        ]
        turn_two = [
            f"Còn học phí năm 2026 cho lựa chọn số {i} thì sao?",
            f"Vậy khoản học phí năm nay của lựa chọn {i} bao nhiêu?",
        ]
        q = [turn_one[0], turn_two[0], turn_one[1], turn_two[1]]
        row_overrides = [
            {
                "intent": "HOI_NGUONG_DAU_VAO",
                "semantic_intent": "multi_turn_score_context",
                "category": "multi_turn",
                "required": [score],
                "records": [score_record],
            },
            {
                "intent": "HOI_HOC_PHI",
                "semantic_intent": "multi_turn_tuition_followup",
                "category": "multi_turn",
                "score_query_type": None,
                "admission_method": None,
                "major": None,
                "required": [tuition.get("tuition_per_credit_vnd")],
                "records": [tuition],
            },
            {
                "intent": "HOI_NGUONG_DAU_VAO",
                "semantic_intent": "multi_turn_score_context",
                "category": "multi_turn",
                "required": [score],
                "records": [score_record],
            },
            {
                "intent": "HOI_HOC_PHI",
                "semantic_intent": "multi_turn_tuition_followup",
                "category": "multi_turn",
                "score_query_type": None,
                "admission_method": None,
                "major": None,
                "required": [tuition.get("tuition_per_credit_vnd")],
                "records": [tuition],
            },
        ]
        families.append(
            record_family(
                family_id=f"F_MULTITURN_{i:03d}",
                questions=q,
                intent="HOI_NGUONG_DAU_VAO" if i else "HOI_NGUONG_DAU_VAO",
                semantic_intent="multi_turn_score_then_tuition",
                category="multi_turn",
                required=[major, score],
                status="ok",
                answer_mode="multi_turn",
                admission_method=method,
                major=major,
                score_query_type="personal_score_comparison",
                conversation_id=f"C{i:03d}A",
                turn_indexes=[1, 2, 1, 2],
                expected_state={"current_major": major, "current_method": method, "score": score},
                row_overrides=row_overrides,
                conversation_ids=[f"C{i:03d}A", f"C{i:03d}A", f"C{i:03d}B", f"C{i:03d}B"],
            )
        )

    return families


def flatten_and_split(families: list[dict[str, object]]) -> list[dict[str, object]]:
    if len(families) != 250:
        raise ValueError(f"Expected 250 semantic families, got {len(families)}")
    rows: list[dict[str, object]] = []
    family_index = {str(family["family_id"]): index for index, family in enumerate(families)}
    development_family_index = 0
    for family in families:
        fid = str(family["family_id"])
        index = family_index[fid]
        split = "test" if index % 5 == 0 else "train"
        development_split = "train"
        if split == "train":
            development_split = "dev" if development_family_index % 5 == 0 else "train"
            development_family_index += 1
        for row in family["rows"]:  # type: ignore[index]
            item = dict(row)
            item["split"] = split
            item["development_split"] = development_split if split == "train" else None
            rows.append(item)
    if len(rows) != TARGET_TOTAL:
        raise ValueError(f"Expected {TARGET_TOTAL} rows, got {len(rows)}")
    rows.sort(key=lambda row: str(row["family_id"]))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"Q{index:04d}"
    return rows


def normalized_duplicate_keys(rows: Iterable[Mapping[str, object]]) -> Counter[str]:
    return Counter(fold(row.get("question")) for row in rows)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_readme(rows: list[dict[str, object]], records: list[dict[str, Any]]) -> None:
    counts = Counter(str(row["category"]) for row in rows)
    intents = Counter(str(row["intent"]) for row in rows)
    lines = [
        "# Phase 5 evaluation dataset",
        "",
        "This dataset is generated only from verified DHV Structured JSON records.",
        "It is evaluation data, not Qwen fine-tuning data.",
        "",
        "## Files",
        "",
        "- `qa_master_1000.jsonl`: immutable master with 1,000 rows.",
        "- `train_800.jsonl`: development pool; `development_split` further marks 640 train / 160 dev.",
        "- `test_200.jsonl`: final holdout; semantic families stay entirely within one split.",
        "- `test_200.lock`: SHA-256 lock created at dataset generation time.",
        "",
        "## Runtime taxonomy mapping",
        "",
        "The runtime currently uses `HOI_*`, `SCHOOL_INFO`, `GREETING`, and `OUT_OF_SCOPE`.",
        "`semantic_intent` retains the Phase 5 meaning (for example `thanks` or `goodbye`)",
        "without inventing a new runtime intent label.",
        "",
        f"Verified 2026 records referenced: {len(records)}.",
        "",
        "## Distribution",
        "",
        "| Category | Rows |",
        "|---|---:|",
    ]
    lines.extend(f"| {category} | {count} |" for category, count in sorted(counts.items()))
    lines.extend(["", "## Intent distribution", "", "| Intent | Rows |", "|---|---:|"])
    lines.extend(f"| {intent} | {count} |" for intent, count in sorted(intents.items()))
    lines.extend(
        [
            "",
            "The final test file is locked after creation. If a test label is ever proven wrong, record the old label, new label, reason and evidence in the Phase 5 report before making a separately versioned dataset change.",
            "",
        ]
    )
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    records = load_records()
    families = build_families(records)
    rows = flatten_and_split(families)
    if Counter(row["split"] for row in rows) != Counter({"train": 800, "test": 200}):
        raise ValueError("split count is not 800/200")
    duplicate_counts = normalized_duplicate_keys(rows)
    duplicates = {key: count for key, count in duplicate_counts.items() if count > 1}
    if duplicates:
        raise ValueError(f"normalized duplicate questions found: {list(duplicates.items())[:5]}")
    master = OUT / "qa_master_1000.jsonl"
    train = OUT / "train_800.jsonl"
    test = OUT / "test_200.jsonl"
    lock = OUT / "test_200.lock"
    if test.exists() and lock.exists() and "--regenerate" not in sys.argv:
        existing_hash = hashlib.sha256(test.read_bytes()).hexdigest()
        locked_hash = lock.read_text(encoding="utf-8").strip()
        if existing_hash != locked_hash:
            raise RuntimeError("test_200.jsonl exists but does not match test_200.lock")
        raise RuntimeError("locked test_200.jsonl already exists; refusing to overwrite it")
    write_jsonl(master, rows)
    write_jsonl(train, [row for row in rows if row["split"] == "train"])
    write_jsonl(test, [row for row in rows if row["split"] == "test"])
    lock.write_text(hashlib.sha256(test.read_bytes()).hexdigest() + "\n", encoding="utf-8")
    write_readme(rows, records)
    print(json.dumps({
        "total": len(rows),
        "train": sum(row["split"] == "train" for row in rows),
        "test": sum(row["split"] == "test" for row in rows),
        "families": len(families),
        "categories": Counter(row["category"] for row in rows),
        "intents": Counter(row["intent"] for row in rows),
        "test_sha256": hashlib.sha256(test.read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=2, default=dict))


if __name__ == "__main__":
    main()
