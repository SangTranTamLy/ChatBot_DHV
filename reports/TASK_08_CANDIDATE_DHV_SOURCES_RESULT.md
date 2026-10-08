# TASK 08 — Candidate official DHV sources

Ngày thực hiện: 15/09/2026  
Trạng thái: **PASS**

## Task và phạm vi

Xác minh 7 URL trong `DHV_AGENT_MASTER_PLAN_UPDATED/08_CANDIDATE_DHV_SOURCES.md`
trước khi coi chúng là nguồn ingest. Audit kiểm tra identity, phạm vi fact được
phép dùng, freshness hiển thị và các ranh giới privacy/authority. Không crawl hoặc
đưa HTML, ảnh, form submission hay dữ liệu PII vào KB.

Đã đọc master plan, candidate-source task, pipeline/manifest hiện có và phần
chuẩn bị dữ liệu RAG/quản trị nguồn trong `Tong_quan_xay_dung_chatbot_AI.pdf`
(tr. 36, 39, 48–50). Các điểm áp dụng là: catalog nguồn phải có provenance,
phiên bản/ngày kiểm tra/phạm vi; source conflict cần rule ưu tiên; chỉ trả lời từ
nguồn đã kiểm chứng; metadata/quyền truy cập là một phần của tính đúng.

## Baseline → expected → current

| Hạng mục | Baseline | Expected | Current |
|---|---|---|---|
| Candidate URLs | 7 URL chưa có audit outcome trong chính task file | Mỗi URL có identity, quyết định, phạm vi và ranh giới | 7/7 được live-check; 2 ACCEPT, 5 LIMITED, 0 REJECT |
| Official-host policy | Pipeline có validator nhưng candidate list chưa ghi quyết định | HTTPS + exact `dhv.edu.vn` hoặc subdomain; không userinfo/lookalike | 7/7 đạt policy |
| Central-vs-faculty authority | Có rule rải trong master/conflict report | Rule áp dụng cho từng URL | Central admissions 2026 giữ authority; faculty chỉ context/limited |
| Form/privacy boundary | Có ghi chú ở PDF đăng ký nhưng chưa có candidate audit | Không ingest submission/PII; chỉ giữ hướng dẫn tối thiểu | `/dangky` và form động bị giới hạn rõ; không thêm PII |
| Year boundary | Chưa thể hiện ngay trong candidate file | Không import nội dung cũ vào catalog 2026 | Trang CNTT 2023/2024 bị khóa ở context, không override catalog |

## Kết quả xác minh

### Cổng tuyển sinh trung tâm — ACCEPT

`https://tuyensinh.dhv.edu.vn/` là trang tuyển sinh chính thức. Nội dung live
hiển thị các nhóm phương thức xét tuyển, học bổng/học phí và mốc tuyển sinh 2026.
Đây là nguồn phù hợp cho fact tuyển sinh theo phạm vi đã xác minh và là lớp ưu
tiên cao hơn trang khoa khi có conflict.

Trang cũng render form tư vấn/đăng ký, bao gồm các field như họ tên, email, số
điện thoại, điểm và số định danh ở các phần khác nhau của trang. Vì vậy, chỉ giữ
fact hướng dẫn cần thiết; không lấy field values, submission, PII hay nội dung
form cũ làm dữ liệu RAG.

### Cổng `/dangky` — LIMITED

`https://tuyensinh.dhv.edu.vn/dangky` là form đăng ký chính thức đang hiển thị
nhãn đăng ký 2026 và hướng dẫn liên quan đến phương thức/tổ hợp. Đây là nguồn
phù hợp để mô tả quy tắc điền form ở mức tối thiểu. Đây không phải authority
riêng cho điểm, học bổng, catalog hay kết luận tuyển sinh.

Trang hiển thị các trường nhạy cảm như số CCCD/mã định danh, ngày sinh, email,
số điện thoại, điểm và số điện thoại người giới thiệu. Không lưu bất kỳ giá trị
thực tế nào và không đưa dữ liệu submit vào corpus.

### TEC — LIMITED

`https://tec.dhv.edu.vn/` xác nhận đây là Khoa Kỹ thuật Công nghệ thuộc DHV và
giới thiệu bối cảnh đào tạo/ngành thuộc khoa. Nó được dùng khi câu hỏi nói rõ
entity của khoa hoặc cần context ngành, không dùng để thay thế nguồn tuyển sinh
trung tâm cho điểm, ngưỡng, học phí, học bổng, lịch hoặc catalog 2026.

`https://tec.dhv.edu.vn/educational-program/cong-nghe-thong-tin?program=dai-hoc`
hiển thị mô tả CNTT/cơ hội nghề nghiệp, đồng thời phần “Chương trình học” có
mốc **2023**. Nội dung này không đủ để xác nhận curriculum tuyển sinh 2026.
Quyết định là giữ context mô tả nghề nghiệp, không ingest bảng học phần cũ
vào catalog và không suy diễn điểm, mã ngành, học phí, lương hoặc tỷ lệ việc làm.

### Bài CNTT ngày 21/03/2026 — ACCEPT có giới hạn

`https://tec.dhv.edu.vn/news-event/news/vi-sao-nen-lua-chon-nganh-cong-nghe-thong-tin-tai-khoa-ky-thuat-cong-nghe-truong-dai-hoc-hung-vuong-tp-hcm`
là bài viết chính thức của TEC, hiển thị ngày 21/03/2026. Bài nêu định hướng
ứng dụng, các lĩnh vực/kỹ năng, dự án/thực tập và một số vị trí nghề nghiệp.

Nó phù hợp làm evidence mô tả/bối cảnh đúng entity CNTT. Đây không phải cam kết
việc làm, không phải nguồn score authority và không được dùng để tạo fact về
mức lương, điều kiện đầu vào, mã ngành, ngưỡng, học phí hoặc chương trình tuyển
sinh 2026.

### Khoa Luật — LIMITED

`https://law.dhv.edu.vn/` là trang chính thức của Khoa Luật và giới thiệu Luật,
Luật Kinh tế cùng hoạt động của khoa. Có thể dùng làm context khoa khi entity
được hỏi rõ. Không dùng trang này làm score authority nếu không có notice 2026
độc lập, đặc biệt không suy ra điểm học bạ/điểm sàn/điểm chuẩn/bổ sung từ mô tả
khoa.

### BAM contact — LIMITED / cross-check only

`https://bam.dhv.edu.vn/contact` hiển thị email, hotline và địa chỉ liên hệ của
BAM. Đây là nguồn official để đối chiếu liên hệ đúng khoa. Tuy nhiên mapping cơ
sở trên trang có thứ tự khác nguồn tuyển sinh trung tâm 2026; do đó câu hỏi cơ
sở chung phải dùng mapping central 2026. Conflict đã có tại
`reports/DATA_CONFLICTS_2026.md`.

Không ingest thông tin mạng xã hội, form hay dữ liệu cá nhân. Hotline/email khoa
không thay thế kênh tuyển sinh trung tâm khi người dùng hỏi liên hệ chung.

## Architecture decisions

- Không tạo module runtime mới: source-policy validator và manifest hiện tại đã
  kiểm tra HTTPS/host, `source_urls`, hash, category, năm, status và privacy.
- Cập nhật candidate task file thành source registry có quyết định `ACCEPT` hoặc
  `LIMITED`; report này là audit trail, không phải corpus.
- Giữ dữ liệu capture hiện có. Không rebuild Chroma vì task không thêm/chỉnh RAW
  hoặc processed evidence.
- Central admissions 2026 > official 2026 notice > current official faculty page
  > older faculty page. Evidence Selection phải loại source ngoài intent/entity
  hoặc ngoài năm trước khi LLM nhìn thấy.
- Form là boundary dữ liệu: chỉ lưu hướng dẫn tối thiểu, không lưu PII/submission.
- Không dùng reference images và không copy brand/UI/text/source card.

## Files changed

- `DHV_AGENT_MASTER_PLAN_UPDATED/08_CANDIDATE_DHV_SOURCES.md`: thêm kết quả live
  audit, decision matrix, corpus alignment và quy tắc vận hành.
- `reports/TASK_08_CANDIDATE_DHV_SOURCES_RESULT.md`: báo cáo task này.
- `tests/test_task_08.py`: regression contract cho URL inventory, policy và audit
  boundaries; test không gọi live web.

Không sửa source code runtime, RAW, processed hoặc Chroma vì không có source mới
được phê duyệt để ingest trong task này.

## Sources/data mới, conflicts và unverified

- Không có data mới, không có PDF mới và không có PII mới.
- Live sources được kiểm tra ngày 15/09/2026:
  - `https://tuyensinh.dhv.edu.vn/`
  - `https://tuyensinh.dhv.edu.vn/dangky`
  - `https://tec.dhv.edu.vn/`
  - `https://tec.dhv.edu.vn/educational-program/cong-nghe-thong-tin?program=dai-hoc`
  - `https://tec.dhv.edu.vn/news-event/news/vi-sao-nen-lua-chon-nganh-cong-nghe-thong-tin-tai-khoa-ky-thuat-cong-nghe-truong-dai-hoc-hung-vuong-tp-hcm`
  - `https://law.dhv.edu.vn/`
  - `https://bam.dhv.edu.vn/contact`
- Conflict đã xác nhận: địa chỉ/cơ sở BAM khác mapping central 2026; TEC
  curriculum có mốc 2023/2024. Không dùng conflict để tự suy diễn và không ghi
  đè data 2026.
- Freshness của website là trạng thái tại ngày audit, không phải cam kết vĩnh
  viễn. Lần recapture tiếp theo phải lặp lại live verification và cập nhật hash/
  collected_at nếu nội dung thay đổi.

## Tests và kết quả

### Targeted

```text
tests.test_task_08: PASS
tests.test_task_m: PASS
```

`tests.test_task_08` chỉ kiểm tra artifact/contract offline: đủ 7 URL, tất cả
official-host, có ngày audit, có ACCEPT/LIMITED và có form/year/conflict boundary.

### Full regression

Full suite phải được chạy với temp directory writable trong môi trường Windows.
Kết quả chạy sau thay đổi:

```text
109 tests, 1 skipped — OK
```

Ngoài ra:

```text
compileall src tests: PASS
git diff --check: PASS
```

Không chạy rebuild/smoke Chroma vì corpus không đổi; đây là quyết định theo phạm
vi task và tránh biến audit-only thành ingest.

## Metrics và limitations

| Metric | Kết quả |
|---|---:|
| URL được kiểm tra | 7/7 |
| Official-host policy | 7/7 |
| ACCEPT | 2 |
| LIMITED | 5 |
| REJECT | 0 |
| Source/data mới ingest | 0 |
| PII mới ingest | 0 |

Audit chứng minh source identity và boundary tại thời điểm kiểm tra; nó không
thay thế content review cho từng claim sau này, không chứng minh mọi nội dung
trên website luôn đúng, và không đo chất lượng retrieval/generation. Những lần
website đổi nội dung cần recapture PDF, cập nhật manifest và chạy lại rebuild/
smoke theo task data tương ứng.

## Exact reproduce commands

Từ repository root:

```powershell
$env:PYTHONIOENCODING='utf-8'
& '.venv\Scripts\python.exe' -m unittest tests.test_task_08 -q
& '.venv\Scripts\python.exe' -m unittest tests.test_task_08 tests.test_task_m -q
& '.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py' -q
& '.venv\Scripts\python.exe' -m compileall -q src tests
git diff --check
```

Để tái kiểm tra policy và sinh manifest tạm (không đưa file tạm vào corpus):

```powershell
& '.venv\Scripts\python.exe' -m src.ingestion.raw_manifest `
  --raw-dir '.\data\raw' `
  --manifest '.\tmp\task08_manifest.json' `
  --audited-at '2026-09-15'
```

Live page verification phải mở lại đúng 7 URL trong candidate file tại ngày audit
mới; không coi URL hoặc HTML cũ là bằng chứng freshness hiện tại.

## PASS/FAIL

**PASS** — 7/7 candidate sources đã được xác minh identity; quyết định sử dụng,
authority, year boundary và privacy boundary được ghi rõ; không ingest source
chưa đủ điều kiện; targeted/full regression và static policy checks pass.
