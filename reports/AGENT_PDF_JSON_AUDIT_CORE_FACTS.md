# Audit PDF ↔ JSON: Phương thức, Điểm trúng tuyển, Học phí

## 1. Phạm vi và phương pháp

Chỉ kiểm tra đúng ba PDF V1 hiện tại trong `data/raw` và JSON trùng tên trong `data/processed`; không đối chiếu PDF cũ, không sửa file nguồn, JSON, manifest, tests hoặc Chroma.

| Nhóm | PDF | JSON |
|---|---|---|
| Phương thức/học bổng | `data/raw/phuong_thuc_xet_tuyen/V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.pdf` | `data/processed/phuong_thuc_xet_tuyen/V1_PHUONG_THUC_XET_TUYEN_VA_HOC_BONG_DHV_2026.json` |
| Điểm trúng tuyển | `data/raw/diem_trung_tuyen/V1_DIEM_TRUNG_TUYEN_DHV_2026.pdf` | `data/processed/diem_trung_tuyen/V1_DIEM_TRUNG_TUYEN_DHV_2026.json` |
| Học phí | `data/raw/hoc_phi/V1_HOC_PHI_DHV_2024.pdf` | `data/processed/hoc_phi/V1_HOC_PHI_DHV_2024.json` |

Đã kiểm tra text theo từng trang, số trang, metadata/provenance, cấu trúc bảng/list trong JSON, records semantic; đồng thời render xem trực quan toàn bộ 11 trang. Với cả ba PDF, text native đọc được; không phát hiện ảnh nhúng cần OCR. So sánh text sau khi chuẩn hóa khoảng trắng/ngắt dòng cho kết quả khớp ở tất cả các trang. Việc đó xác nhận lớp `pages[].text`, nhưng không chứng minh lớp `records[]` được gán entity đúng.

## 2. Kết quả tổng quan

| Tài liệu | Trang PDF/JSON | Nội dung trang | Bảng/list có cấu trúc | Provenance | Verdict |
|---|---:|---|---|---|---|
| Phương thức/học bổng 2026 | 8/8 | Đủ theo đối chiếu text | Bảng ngành p.1–3 giữ header/row/cell; list và scholarship records còn thiếu/sai cấu trúc | Official URL, `verified=true` | **FAIL** |
| Điểm trúng tuyển 2026 | 2/2 | Đủ theo đối chiếu text | 23 rows/138 cells của bảng được giữ; records điểm thiếu/ghép sai entity | Official URL, `verified=true` | **FAIL** |
| Học phí 2024 | 1/1 | Đủ theo đối chiếu text | Danh sách thanh toán chỉ có trong text, không có list structure/record học phí chuyên biệt | `source_url=null`, `verified=false` | **FAIL** |

Không thấy trang PDF nào bị bỏ khỏi `pages[]` hoặc toàn bộ page text bị rỗng. Tuy nhiên, hiện chưa thể kết luận cả ba JSON đều đủ và chính xác để chatbot dùng an toàn: hai JSON có lỗi entity ở records; JSON học phí thiếu provenance verified.

## 3. Phát hiện — Phương thức xét tuyển và học bổng 2026

### M-01 — Tên ngành bị lấy nhầm từ tên chương trình trong semantic records — HIGH

Các bảng JSON giữ đúng quan hệ cột ở trang 1–3, nhưng nhiều `records[]`/catalog summary lấy tên chương trình ở cột thứ hai làm `major_name`, trong khi ghép mã ngành của cột thứ ba. Ví dụ:

- PDF p.1, bảng 1.1: ngành `Quản trị kinh doanh`, mã `7340101`; `Đổi mới sáng tạo` là một chương trình trong ô chương trình.
- JSON `$.pages[0].tables[0].rows[0].data`: vẫn biểu diễn đúng ba cột.
- JSON `$.records[0]` (`record_id=major_001`): `major_name="Đổi mới sáng tạo"`, `major_code="7340101"` — ghép sai ngành/chương trình.
- PDF p.1, hàng Marketing: `Marketing`, mã `7340115`; chương trình gồm `Truyền thông số`.
- JSON `$.records[2]` (`major_003`): `major_name="Truyền thông số"`, `major_code="7340115"` — tiếp tục ghép tên chương trình vào trường ngành.
- PDF p.2: `Công nghệ thông tin`, mã `7480201`; chương trình có `Phân tích dữ liệu lớn`.
- JSON `$.records[8]` (`major_009`): `major_name="Phân tích dữ liệu lớn"`, `major_code="7480201"`.

Danh sách `$.records[20].majors` và `$.records[20].major_rows` lặp lại các cặp tên/mã sai tương ứng. Nếu chatbot hoặc loader ưu tiên records thay vì bảng/page text, câu hỏi ngành–mã ngành có thể trả sai tên ngành. Không nên coi record catalog này là dữ liệu semantic đáng tin cậy trước khi sửa và trích xuất lại.

### M-02 — Scholarship records cắt cụt điều kiện/số tiền; page text vẫn còn — HIGH

PDF p.6 có các mức hỗ trợ kèm số tiền tương đương. Các record riêng lẻ kết thúc giữa câu:

- PDF p.6: `Tổng điểm 3 môn > 25,5 điểm → ... (tương đương 8.750.000 VNĐ)`.
- JSON `$.records[32].policy_text` (`scholarship_policy_007`): kết thúc ở `...(tương đương`, thiếu `8.750.000 VNĐ)`.
- PDF p.6: mức 50% ghi tương đương `6.250.000 VNĐ`; JSON `$.records[33].policy_text` kết thúc ở `...(tương`, không có số tiền.
- PDF p.6: nhóm ĐGNL ghi mức 60% tương đương `7.500.000 VNĐ`; JSON `$.records[37].policy_text` kết thúc ở `...(tương đương`, thiếu số tiền.
- JSON `$.records[25].summary_lines[6:16]` cũng chứa nhiều dòng rời/truncated, ví dụ dòng 6 kết thúc ở `tương đương` và dòng 14 kết thúc giữa tên ngành `Quản lý`.

Các chi tiết bị thiếu này có trong `$.pages[5].text`, nên đây là lỗi tầng records/semantic, không phải mất toàn bộ text của trang. Records bị cắt không đủ an toàn để trả lời điều kiện học bổng/số tiền nếu runtime dựa vào chúng.

### M-03 — List structure không phản ánh đầy đủ các list nhìn thấy trong PDF — MEDIUM

- PDF p.4 có các mục tổ hợp như `3. Toán + 2 môn điểm cao nhất`. JSON `$.pages[3].lists` chỉ có hai list, mỗi list đúng một item là nhãn `Ngành Ngôn ngữ Anh:` hoặc `Khối Kinh tế...`; các mục/điều kiện bên dưới không được giữ thành list items. Chúng vẫn còn trong `$.pages[3].text`.
- PDF p.5 có bullet `Quỹ học bổng Hào khí Hùng Vương - lên đến 75 tỷ đồng` cùng các bullet nhóm học bổng. JSON `$.pages[4].lists=[]`.
- PDF p.6 có nhiều bullet điều kiện/mức hỗ trợ; JSON `$.pages[5].lists[0].items` chỉ có một item `Điểm thi > 700 ... 10.000.000 VNĐ`; mục kế tiếp `Điểm thi từ 650 đến 700 ... 7.500.000 VNĐ` không được cấu trúc thành list item.
- PDF p.7 có danh sách đánh số 1–5 các chương trình được hoàn học phí, bắt đầu `1. Quản trị Logistics`. JSON `$.pages[6].lists=[]`.

Text gốc vẫn còn ở `pages[].text`, nhưng hệ thống downstream không thể dựa vào `lists[]` để bảo toàn thứ tự/đếm/truy vấn danh sách ở các trang này.

### M-04 — Warning `UNPARSED_TABLE` cần được đọc đúng phạm vi

JSON có warning `UNPARSED_TABLE` cho p.4–8 (`$.warnings[0:5]`). Kiểm tra trực quan các trang này cho thấy nội dung chủ yếu là đoạn văn, bullet và danh sách điều kiện/học bổng; page text được bảo toàn nhưng không có cấu trúc table tương ứng. Warning không chứng minh nội dung text bị mất, nhưng cùng với M-03 cho thấy lớp cấu trúc chưa mô hình hóa đầy đủ. Các bảng ngành thật trên p.1–3 lại có cấu trúc.

### M-05 — Provenance

JSON `$.source` trỏ đúng PDF V1 hiện tại, `source_url=https://tuyensinh.dhv.edu.vn/`, `status="verified"`, `verified=true`, `school_code="DHV"`, `year=2026`. Không phát hiện lệch tên/path nguồn trong cặp này.

## 4. Phát hiện — Điểm trúng tuyển 2026

### S-01 — Bảng JSON đúng, nhưng records điểm thiếu và ghép nhầm ngành — HIGH

Hai bảng trong PDF (p.1 có 17 hàng, p.2 có 6 hàng) được lưu ở `$.pages[0].tables[0]` và `$.pages[1].tables[0]`, tổng cộng 23 hàng/138 cells. Qua so sánh từng hàng, các header, mã, tên hiển thị và ba ngưỡng trong lớp bảng vẫn liên kết đúng. Tuy nhiên, records semantic chỉ có **60 `admission_score` records**, trong khi 23 hàng × 3 phương thức cần **69 facts**.

- PDF p.1, STT 10: `Marketing`, mã `7340115`, các điểm `15 / 18 / 600`. JSON `$.records[27:30]` có ba điểm nhưng `major_name` bị nối thành `Marketing 15 18 600 11 734011501 Truyền thông và Quan hệ công chúng`.
- PDF p.1, STT 11: mã `734011501`, tên `Truyền thông và Quan hệ công chúng`, các điểm `15 / 18 / 600`. Không có bộ records điểm khớp ngành/mã này; giá trị ở hàng này đã bị hút vào chuỗi `major_name` của Marketing phía trên.
- PDF p.2, STT 21–23 lần lượt là `Quản lý bệnh viện` (`7720802`), `Quản trị Dịch vụ Du lịch và Lữ hành` (`7810103`), `Quản trị Khách sạn` (`7810201`), mỗi hàng có `15 / 18 / 600`.
- JSON `$.records[57:60]` (`admission_score_058`–`060`) gắn mã `7720802` nhưng `major_name` chứa thêm `15 18 600 22 7810103 Quản trị Dịch vụ Du lịch và Lữ hành`.
- Không có admission-score records cho hai mã `7810103` và `7810201` dù hai hàng vẫn tồn tại đúng trong `$.pages[1].tables[0].rows[4:6]`.

Do vậy không nên dùng records điểm hiện tại làm nguồn xác định điểm theo ngành. Bảng trong `pages[].tables[]` và text trang giữ dữ liệu, nhưng không cứu được consumers chỉ đọc records.

### S-02 — Major catalog semantic record sai — HIGH

- PDF p.2, hàng STT 22: `Quản trị Dịch vụ Du lịch và Lữ hành`, mã `7810103`.
- JSON `$.records[60]` (`record_id=major_001`): `major_name="22"`, `major_code="7810103"`.
- JSON `$.records[61]` (`major_catalog_summary`): `major_count=1`, majors chỉ có `{"major_name":"22","major_code":"7810103"}`.

Catalog records này không thể dùng để liệt kê hoặc resolve tên ngành cho tài liệu điểm trúng tuyển.

### S-03 — Dấu `(*)` không đi vào raw score record — LOW/MEDIUM

PDF p.1, hàng Luật và Luật kinh tế, ô Học tập THPT hiển thị `20(*)`. JSON bảng giữ nguyên dấu này tại `$.pages[0].tables[0].rows[15]` và `$.pages[0].tables[0].rows[16]`, nhưng các records tương ứng lưu `raw_value="20"` (ví dụ `$.records[43]` và `$.records[46]`). Giá trị số 20 còn đúng; marker `(*)` chỉ được giữ ở page text/bảng, không có trong record. Nếu marker mang footnote/điều kiện, record đơn lẻ làm mất liên kết đó.

### S-04 — Warning đọc thứ tự trang 2

`$.warnings[0]` là `READING_ORDER_UNCERTAIN` cho p.2. Đã xem trực quan trang và kiểm tra bảng: 6 hàng STT 18–23 được dựng đúng trong `$.pages[1].tables[0]`; page text sau chuẩn hóa cũng khớp. Warning vẫn nên được giữ cho QA, nhưng trong cặp này nó không phải nguyên nhân của lỗi bảng có cấu trúc; lỗi nằm ở records semantic nêu trên.

### S-05 — Provenance

JSON `$.source` trỏ đúng file V1, có URL bài viết trên `dhv.edu.vn`, `status="verified"`, `verified=true`, `school_code="DHV"`, `source_date="09/08/2026"`. Không phát hiện lệch provenance trong cặp này.

## 5. Phát hiện — Học phí 2024

### T-01 — Page text đầy đủ, nhưng không có record học phí có cấu trúc — MEDIUM

PDF p.1 có các facts gồm `1.100.000 VNĐ/tín chỉ` (năm 2024), `3 học kỳ/năm`, tối thiểu `10 tín chỉ/học kỳ`, và hai phương thức thanh toán. JSON `$.pages[0].text` và `$.records[0].text` giữ các nội dung đó; số trang 1/1 khớp. Tuy vậy:

- `$.records` chỉ có `record_type="document_text"`, không có `tuition`/financial fact record cho mức phí 1.100.000 VNĐ/tín chỉ.
- PDF p.1 đánh số hai phương thức thanh toán 1 và 2; JSON `$.pages[0].lists=[]` và `$.pages[0].elements` lưu chúng trong đoạn paragraph thay vì ordered list.
- Warning `UNPARSED_TABLE` tại `$.warnings[0]` không tương ứng với bảng nhìn thấy: trang PDF là text/paragraph/numbered payment steps, không có bảng native. Nội dung vẫn còn trong page text.

### T-02 — Provenance chưa đạt điều kiện verified — HIGH / BLOCKER cho chatbot

JSON `$.source.raw_file` khớp PDF V1 và `year=2024`, nhưng `source_url=null`, `source_urls=[]`, `verified=false`, `status="missing_source_url"`, `source_type="unknown"`. Vì vậy dữ liệu có thể được nhận diện là thuộc năm 2024, nhưng hiện không có provenance đủ để cho phép dùng như factual verified evidence trong chatbot. Không dùng tài liệu này để trả lời học phí 2026; audit này không suy diễn rằng mức phí 2024 áp dụng cho 2026.

## 6. Phạm vi an toàn để sử dụng

- **Page text:** đủ ở cả ba tài liệu theo đối chiếu từng trang; chưa thấy silent drop ở text native.
- **Bảng:** bảng ngành p.1–3 của tài liệu phương thức và bảng điểm p.1–2 được giữ quan hệ header/row/cell trong `pages[].tables[]`.
- **Semantic records:** không an toàn ở records ngành/phương thức, điểm trúng tuyển và các policy học bổng đã nêu. Không nên coi records hiện tại là nguồn chuẩn cho câu hỏi theo ngành/mã/điểm/điều kiện.
- **Lists:** nhiều list trong phương thức/học bổng và danh sách thanh toán không được cấu trúc đủ, dù page text còn.
- **Học phí:** nội dung 2024 có trong JSON nhưng provenance unverified; không đủ căn cứ để chatbot trả như verified fact.

**Kết luận audit:** cả ba cặp là **FAIL** đối với tiêu chí “JSON đầy đủ, chính xác và sẵn sàng làm nguồn chatbot”. Không có bằng chứng rằng toàn bộ PDF text bị mất; lỗi tập trung ở semantic records, list structure, và provenance cho học phí 2024. Chưa kiểm tra/rebuild Chroma và không kết luận về vector database hay runtime.

## 7. Handoff / việc cần xử lý trước khi chatbot dùng

1. Sửa extraction/record mapping để tên ngành không bị lấy từ ô chương trình; thêm assertion đối chiếu code–major–program.
2. Sửa parsing score records để đủ 69 facts từ 23 hàng; giữ tên/mã độc lập, không hút STT/hàng kế tiếp vào `major_name`.
3. Không phát hành scholarship records bị cắt; khôi phục trọn điều kiện, % và số tiền tương đương từ page text; thêm kiểm tra record text không kết thúc giữa cụm như `tương đương`.
4. Khôi phục list/order cho điều kiện xét tuyển, các nhóm học bổng và phương thức thanh toán; page text phải tiếp tục được giữ làm fallback.
5. Đối với học phí 2024, xác minh provenance qua quy trình dữ liệu được duyệt trước khi đổi `verified`; không dùng nó làm dữ liệu năm 2026.
6. Sau khi sửa, trích xuất lại ba PDF V1, chạy lại đối chiếu QA độc lập. Chưa có bất kỳ thay đổi dữ liệu hay rebuild Chroma nào trong audit này.
