# Phase 5 canonical Q&A dataset

Phase 5 hiện chỉ sử dụng dataset do người dùng cung cấp:

`data/evaluation/raw/Nhóm 4_Thu_Thap_Q&A.xlsx`

Workbook có 500 dòng với bốn cột `TT`, `Câu hỏi`, `Trả lời`, `Nguồn`. File
gốc được giữ nguyên. Pipeline chỉ chuyển từng dòng sang JSONL để kiểm tra và
đánh giá; không sinh câu hỏi, không sinh câu trả lời và không trộn dataset cũ.

## File active

- `raw/Nhóm 4_Thu_Thap_Q&A.xlsx`: nguồn canonical, không chỉnh sửa.
- `qa_master_500.jsonl`: bản chuẩn hóa 500/500 dòng.
- `qa_master_500.lock`: SHA-256 của JSONL active.
- `qa_master_500.audit.json`: kết quả kiểm tra số dòng, ID, trường bắt buộc và trùng lặp.

## Quy tắc

- Không dùng lại `qa_master_1000`, `train_800`, `test_200` hoặc Q&A generated cũ.
- Không tạo split train/test mới khi chưa có yêu cầu chính thức về split.
- `reference_answer` được sao nguyên từ cột `Trả lời`; `source` được sao nguyên từ cột `Nguồn`.
- Dataset này dùng cho regression/evaluation, không dùng để fine-tune Qwen.

## Tạo lại dataset active

```powershell
python scripts/build_phase5_dataset.py
```

## Chạy audit/evaluation

Audit-only:

```powershell
python scripts/evaluate_phase5.py --skip-e2e
```

Chạy thêm chatbot trên toàn bộ 500 câu:

```powershell
python scripts/evaluate_phase5.py --split canonical
```

Các chỉ số lexical/numeric trong report là proxy để sàng lọc. Semantic
correctness của câu trả lời canonical vẫn cần review nội dung.
