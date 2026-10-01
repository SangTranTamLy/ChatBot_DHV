# Phase 5 evaluation dataset

This dataset is generated only from verified DHV Structured JSON records.
It is evaluation data, not Qwen fine-tuning data.

## Files

- `qa_master_1000.jsonl`: immutable master with 1,000 rows.
- `train_800.jsonl`: development pool; `development_split` further marks 640 train / 160 dev.
- `test_200.jsonl`: final holdout; semantic families stay entirely within one split.
- `test_200.lock`: SHA-256 lock created at dataset generation time.

## Runtime taxonomy mapping

The runtime currently uses `HOI_*`, `SCHOOL_INFO`, `GREETING`, and `OUT_OF_SCOPE`.
`semantic_intent` retains the Phase 5 meaning (for example `thanks` or `goodbye`)
without inventing a new runtime intent label.

Verified 2026 records referenced: 247.

## Distribution

| Category | Rows |
|---|---:|
| cach_tinh_diem | 12 |
| clarification | 20 |
| diem_trung_tuyen | 208 |
| ho_so | 96 |
| hoc_bong | 96 |
| hoc_phi | 64 |
| lich_tuyen_sinh | 8 |
| multi_turn | 20 |
| nganh_dao_tao | 168 |
| nguong_dau_vao | 88 |
| nhap_hoc | 48 |
| out_of_scope | 20 |
| phuong_thuc_xet_tuyen | 64 |
| system/small_talk | 12 |
| thong_tin_truong | 4 |
| xet_tuyen_bo_sung | 72 |

## Intent distribution

| Intent | Rows |
|---|---:|
| DANH_SACH_NGANH | 32 |
| GREETING | 4 |
| HOI_CACH_TINH_DIEM | 12 |
| HOI_CHUONG_TRINH | 56 |
| HOI_DIEM_TRUNG_TUYEN | 208 |
| HOI_HOC_BONG | 96 |
| HOI_HOC_PHI | 74 |
| HOI_HO_SO | 96 |
| HOI_LICH_TUYEN_SINH | 8 |
| HOI_NGANH | 80 |
| HOI_NGUONG_DAU_VAO | 118 |
| HOI_NHAP_HOC | 48 |
| HOI_PHUONG_THUC_XET_TUYEN | 64 |
| HOI_XET_TUYEN_BO_SUNG | 72 |
| OUT_OF_SCOPE | 28 |
| SCHOOL_INFO | 4 |

The final test file is locked after creation. If a test label is ever proven wrong, record the old label, new label, reason and evidence in the Phase 5 report before making a separately versioned dataset change.
