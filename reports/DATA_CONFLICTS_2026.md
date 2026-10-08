# DHV RAW data conflicts — 2026

Ngày audit: 15/09/2026  
Phạm vi: các nguồn `dhv.edu.vn` và subdomain chính thức được xem xét cho TASK M.  
Nguyên tắc xử lý: nguồn tuyển sinh trung tâm 2026 được ưu tiên cho fact answer-critical; nguồn khoa chỉ giữ vai trò bối cảnh khi không mâu thuẫn và không được dùng để ghi đè catalog/điểm/lịch trung tâm.

## CONF-001 — Địa chỉ cơ sở giữa nguồn trung tâm và trang khoa

| Nguồn | Nội dung quan sát được | Trạng thái |
|---|---|---|
| Nguồn tuyển sinh trung tâm 2026, cập nhật 04/07/2026: <https://dhv.edu.vn/truong-dai-hoc-hung-vuong-tp-ho-chi-minh-cong-bo-diem-san-xet-tuyen-nam-2026-trien-khai-quy-hoc-bong-75-ty-dong/> | Trụ sở chính 194 Lê Đức Thọ; cơ sở 1 là 736 Nguyễn Trãi; cơ sở 2 là 37 Kinh Dương Vương; cơ sở thực hành - nghiên cứu ở Công viên Phần mềm Quang Trung. | Nguồn ưu tiên cho tư vấn 2026; đã ingest trong `co_so_lien_he` và `thong_tin_truong`. |
| Trang liên hệ BAM hiện hành: <https://bam.dhv.edu.vn/contact> | Hiển thị trụ sở 194 Lê Đức Thọ, cơ sở 1 là 37 Kinh Dương Vương và cơ sở 2 là 736 Nguyễn Trãi. | Official nhưng thứ tự cơ sở khác nguồn trung tâm; không dùng để thay thế mapping 2026. |
| Trang liên hệ Khoa Ngôn ngữ: <https://lan.dhv.edu.vn/contact> | Hiển thị trụ sở 736 Nguyễn Trãi và cơ sở 1 tại 28-30 Ngô Quyền. | Official nhưng là thông tin theo đơn vị/khu vực và không được xác nhận là danh sách cơ sở tuyển sinh trung tâm 2026. |

**Quyết định:** không trộn các mapping trên. Câu hỏi địa chỉ/cơ sở chung dùng nguồn trung tâm 2026. Địa chỉ khoa chỉ được trả lời khi người dùng hỏi rõ khoa tương ứng và có evidence đúng entity.

## CONF-002 — Trang ngành có nội dung chương trình theo năm cũ

| Nguồn | Nội dung quan sát được | Trạng thái |
|---|---|---|
| Catalog tuyển sinh trung tâm 2026: <https://dhv.edu.vn/truong-dai-hoc-hung-vuong-tp-ho-chi-minh-cong-bo-diem-san-xet-tuyen-nam-2026-trien-khai-quy-hoc-bong-75-ty-dong/> | Danh mục ngành, mã ngành, chương trình và ngưỡng điểm 2026. | Nguồn authority cho catalog/điểm 2026; giữ ở `nganh_dao_tao` chuyên biệt. |
| Trang ngành CNTT của TEC: <https://tec.dhv.edu.vn/educational-program/cong-nghe-thong-tin?program=dai-hoc> | Phần chương trình học hiển thị các mốc năm 2023 và 2024. | Official, nhưng chưa có xác nhận rằng các bảng cũ là curriculum tuyển sinh 2026. |
| Bài giới thiệu CNTT của TEC ngày 21/03/2026: <https://tec.dhv.edu.vn/news-event/news/vi-sao-nen-lua-chon-nganh-cong-nghe-thong-tin-tai-khoa-ky-thuat-cong-nghe-truong-dai-hoc-hung-vuong-tp-hcm> | Mô tả định hướng ứng dụng, lĩnh vực học và cơ hội nghề nghiệp. | Official 2026; được capture vào RAW mới nhưng chỉ dùng cho mô tả/bối cảnh nghề nghiệp. |

**Quyết định:** không lấy bảng học phần 2023/2024 để sửa danh mục hoặc tạo fact tuyển sinh 2026. RAW mới ghi rõ ranh giới này; không đưa mã ngành, ngưỡng, học phí hay tỷ lệ việc làm vào từ bài mô tả nghề nghiệp.

## CONF-003 — Số điện thoại/email ở footer khoa và nguồn trung tâm

| Nguồn | Nội dung quan sát được | Trạng thái |
|---|---|---|
| Nguồn tuyển sinh trung tâm 2026 | Hotline `0287 1000 888`. | Số chính cho câu hỏi tuyển sinh chung. |
| Footer các trang khoa hiện hành, ví dụ TEC: <https://tec.dhv.edu.vn/> | Hiển thị `02871000888-0888158001` và `info@dhv.edu.vn`; TEC có thêm `tec@dhv.edu.vn`. | Official; số/email bổ sung theo footer/khoa, không coi là thay thế hotline trung tâm. |

**Quyết định:** câu hỏi liên hệ tuyển sinh chung dùng `0287 1000 888` và email chung `info@dhv.edu.vn` khi cần. `tec@dhv.edu.vn` chỉ dùng khi người dùng hỏi liên hệ Khoa Kỹ thuật Công nghệ. Không ingest email/số điện thoại cá nhân.

## CONF-004 — Ranh giới giữa các loại điểm và mốc tuyển sinh

Đây là guardrail dữ liệu, không phải mâu thuẫn cần giải quyết:

- Điểm sàn 04/07/2026 được giữ trong `nguong_dau_vao` và catalog; Luật/Luật Kinh tế vẫn là `-` trong bảng tại thời điểm công bố.
- Điểm trúng tuyển đợt 1 09/08/2026 được giữ riêng trong `diem_trung_tuyen`; không dùng nó để thay điểm sàn.
- Xét tuyển bổ sung 10/08/2026 được giữ riêng trong `xet_tuyen_bo_sung`; không gộp ngưỡng bổ sung vào điểm sàn hoặc điểm trúng tuyển.
- Công thức xét tuyển được giữ riêng trong `cach_tinh_diem`; không suy ra công thức từ ngưỡng điểm.

## Kết luận xử lý

Không có conflict nào được dùng để tự suy diễn hoặc ghi đè dữ liệu 2026. Các conflict trên đã được phản ánh trong RAW `thong_tin_truong`/mô tả CNTT và trong manifest bằng provenance theo từng PDF; answer-critical retrieval phải ưu tiên nguồn trung tâm 2026.
