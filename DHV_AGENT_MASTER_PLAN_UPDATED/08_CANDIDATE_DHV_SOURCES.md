# Candidate official DHV sources — Agent phải tự verify trước ingest
- https://tuyensinh.dhv.edu.vn/ — tuyển sinh 2026, methods, scholarship/tuition, milestones.
- https://tuyensinh.dhv.edu.vn/dangky — hướng dẫn/quy tắc form; không ingest PII/submissions.
- https://tec.dhv.edu.vn/ — khoa Kỹ thuật Công nghệ; audit conflict với central 2026.
- https://tec.dhv.edu.vn/educational-program/cong-nghe-thong-tin?program=dai-hoc — mô tả/cơ hội nghề; có content theo năm, không ghi đè catalog 2026.
- https://tec.dhv.edu.vn/news-event/news/vi-sao-nen-lua-chon-nganh-cong-nghe-thong-tin-tai-khoa-ky-thuat-cong-nghe-truong-dai-hoc-hung-vuong-tp-hcm — bài CNTT 21/03/2026.
- https://law.dhv.edu.vn/ — thông tin khoa Luật; không dùng làm score authority nếu không phải notice 2026.
- https://bam.dhv.edu.vn/contact — cơ sở/liên hệ; đối chiếu nguồn trung tâm.

Ưu tiên: central admissions 2026 > official 2026 notice > current official faculty page > older official page.
Conflict → report + không dùng fact chưa verified cho answer-critical logic.

## Kết quả xác minh lần này

Ngày kiểm tra live: **15/09/2026**.

Phạm vi xác minh là **identity + quyền sử dụng + phạm vi fact**, không phải mặc
nhiên coi mọi nội dung marketing trên trang là fact answer-critical. Tất cả URL
dưới đây vượt policy kỹ thuật: `https`, host là `dhv.edu.vn` hoặc subdomain của
`dhv.edu.vn`, không có userinfo. Nội dung HTML không được đưa thẳng vào KB; nếu
được chấp nhận để ingest thì phải capture thành PDF RAW có provenance và đi qua
pipeline hiện tại.

| URL | Identity | Quyết định | Phạm vi được phép dùng | Ranh giới / xử lý |
|---|---|---|---|---|
| `https://tuyensinh.dhv.edu.vn/` | VERIFIED | ACCEPT — central admissions | Phương thức, học bổng/học phí, mốc tuyển sinh và nội dung tuyển sinh 2026 đang công khai | Trang có nhiều form/field động và nội dung cũ còn hiển thị; không ingest submission, field values, PII hoặc coi claim marketing không có phạm vi là quy tắc tuyển sinh. |
| `https://tuyensinh.dhv.edu.vn/dangky` | VERIFIED | LIMITED — registration guidance | Quy tắc form, phương thức, trường thông tin cần thiết cho hướng dẫn đăng ký | Không ingest dữ liệu thí sinh, số định danh, email, điện thoại, ngày sinh, điểm hoặc submission; không dùng form làm authority thay cho notice tuyển sinh. |
| `https://tec.dhv.edu.vn/` | VERIFIED | LIMITED — faculty context | Nhận diện Khoa Kỹ thuật Công nghệ và bối cảnh các ngành/chương trình thuộc khoa | Không dùng làm authority cho điểm, ngưỡng, học phí, học bổng hoặc catalog tuyển sinh 2026 nếu chưa có notice trung tâm tương ứng. |
| `https://tec.dhv.edu.vn/educational-program/cong-nghe-thong-tin?program=dai-hoc` | VERIFIED | LIMITED — programme/career context | Mô tả ngành và cơ hội nghề nghiệp khi hỏi rõ CNTT | Trang hiển thị nội dung chương trình theo năm 2023/2024; không import bảng học phần cũ, không ghi đè catalog 2026 và không suy diễn lương/tỷ lệ việc làm/điểm/điều kiện. |
| `https://tec.dhv.edu.vn/news-event/news/vi-sao-nen-lua-chon-nganh-cong-nghe-thong-tin-tai-khoa-ky-thuat-cong-nghe-truong-dai-hoc-hung-vuong-tp-hcm` | VERIFIED | ACCEPT — dated faculty description | Mô tả định hướng ứng dụng, lĩnh vực học, trải nghiệm và các vị trí nghề nghiệp được bài viết 21/03/2026 nêu | Đây là định hướng do khoa công bố, không phải cam kết việc làm hay nguồn điểm tuyển sinh; không suy diễn thêm fact ngoài bài. |
| `https://law.dhv.edu.vn/` | VERIFIED | LIMITED — faculty context | Nhận diện Khoa Luật và các chương trình được khoa giới thiệu | Không dùng làm score authority; không lấy nội dung khoa để trả điểm học bạ/điểm sàn/điểm chuẩn/bổ sung nếu không phải notice 2026 đã xác minh. |
| `https://bam.dhv.edu.vn/contact` | VERIFIED | LIMITED — contact cross-check | Đối chiếu email, hotline và địa chỉ khi người dùng hỏi rõ liên hệ BAM | Trang có mapping cơ sở khác nguồn trung tâm 2026; không dùng để thay thế mapping chung, không ingest PII hoặc tài khoản mạng xã hội. Conflict xem `reports/DATA_CONFLICTS_2026.md`. |

### Đối chiếu với corpus hiện tại

- Các capture PDF liên quan đã có trong `data/raw/` và được manifest kiểm tra
  `source_urls`, `sha256`, `collected_at`, `verification_status`.
- `tuyensinh.dhv.edu.vn/` và `/dangky` đã có capture ở các category chuyên biệt.
- Hai URL TEC đã được capture trong tài liệu mô tả CNTT với
  `data_role=description`; tài liệu này không được parse như catalog.
- `law.dhv.edu.vn/` và `bam.dhv.edu.vn/contact` chỉ được audit/cross-check trong
  task này; không thêm dữ liệu mới vào KB.
- Không dùng `reference_images/`, không thêm HTML trực tiếp vào RAG, không ingest
  PII từ form.

### Quy tắc vận hành sau xác minh

1. Mỗi lần recapture phải ghi ngày kiểm tra, URL nguồn, hash PDF, category,
   `verification_status` và phạm vi fact.
2. Fact answer-critical về tuyển sinh 2026 phải ưu tiên nguồn tuyển sinh trung
   tâm hoặc official notice 2026; nguồn khoa chỉ bổ sung bối cảnh đúng entity.
3. Khi phát hiện conflict hoặc nội dung không xác định năm, giữ tài liệu ở trạng
   thái audit-only/limited và không cho chạy vào logic điểm, catalog, lịch hoặc
   quyết định đậu-rớt.
4. Trang form chỉ được dùng để mô tả quy trình tối thiểu; không lưu dữ liệu gửi
   lên form và không đưa field PII vào prompt/RAG.

Chi tiết reproduce, bằng chứng đã quan sát và verdict được ghi tại
`reports/TASK_08_CANDIDATE_DHV_SOURCES_RESULT.md`.
