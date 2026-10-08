# Phase 5 dataset audit

- Total rows: 1000
- Split: {'test': 200, 'train': 800}
- Development split: {'dev': 160, 'train': 640}
- Unique IDs: True
- Exact duplicate questions: 0
- Normalized duplicate questions: 0
- Near-duplicate flags (cap 200): 0
- Train/test family overlap: 0
- Invalid evidence references: 0
- Unsupported factual rows: 0
- Wrong-year source labels: 0

## Runtime verified corpus

{"files_seen": 7, "verified_documents": 5, "skipped_unverified": 2, "skipped_internal": 0, "skipped_other_year": 0, "metadata_errors": 0}

## Category distribution

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

## Leakage conclusion

Dataset integrity checks pass: 1,000 rows, 800/200 split, 640/160 development split, no exact/normalized duplicate, no family overlap, and all factual evidence references resolve to verified 2026 records.
