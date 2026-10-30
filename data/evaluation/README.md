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

## Dữ liệu hỏi đáp bổ sung

`data/supplement/hoi_dap_bo_sung_2026.json` chứa các dòng của workbook mà corpus
`data/processed` chưa có dữ liệu. Chatbot chỉ dùng file này khi pipeline chính trả
`no_data`/`out_of_scope`. `build_phase5_dataset.py` tự chép lại câu hỏi, đáp án,
nguồn của các ID trong file này từ workbook. Sau khi sửa file cần khởi động lại app
(file được đọc một lần, và cache câu trả lời giữ tối đa 6 giờ). Trong report,
`supplement_answered` là số câu trả lời lấy từ file này: các câu đó trùng đáp án
mẫu nên không phản ánh chất lượng truy xuất.

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

Chạy giống hệt app (Chroma + Ollama, cần Ollama đang chạy, khoảng 1 giờ):

```powershell
python scripts/evaluate_phase5.py --live
```

Chế độ mặc định dùng `EvidenceEchoLLM` (chép lại evidence) nên câu đi qua LLM hầu
như luôn `ok`; chỉ `--live` cho biết Qwen thật có bị validator từ chối hay không.

Các chỉ số lexical/numeric trong report là proxy để sàng lọc. Semantic
correctness của câu trả lời canonical vẫn cần review nội dung.
