# Đăng nhập, đăng ký và hồ sơ người dùng bằng Supabase

> Trạng thái: phần tích hợp ứng dụng, migration và dependency đã được thêm; Supabase Python SDK đã cài trong môi trường dự án. Để chạy với tài khoản thật cần cấu hình project và áp dụng migration.

## Mục tiêu

Nối giao diện Streamlit đăng nhập/đăng ký hiện có với Supabase Auth. Sau khi đăng nhập, người dùng xem tên, email và đổi mật khẩu trong khu vực tài khoản ở sidebar.

Chỉ tài khoản và hồ sơ được lưu lâu dài trên Supabase. Lịch sử chat tiếp tục được lưu theo phiên Streamlit như hiện tại.

## Phạm vi tính năng

- Đăng ký bằng tên, email, mật khẩu và nhập lại mật khẩu.
- Đăng nhập bằng email và mật khẩu.
- Xem tên và email của tài khoản đang đăng nhập.
- Đổi mật khẩu bằng mật khẩu hiện tại, mật khẩu mới và xác nhận mật khẩu mới.
- Đăng xuất và khôi phục phiên đăng nhập khi ứng dụng chạy lại.
- Không triển khai OTP, xác nhận email, quên mật khẩu, chỉnh sửa tên, vai trò quản trị hoặc lưu lịch sử chat lên Supabase.

Sau đăng ký, hiển thị thông báo thành công và để người dùng đăng nhập thủ công. Supabase có thể trả về session khi tắt xác nhận email; không lưu session đó vào trạng thái Streamlit.

## Giới hạn và kiểm tra đầu vào

| Trường | Quy tắc |
|---|---|
| Tên | 2–50 ký tự Unicode sau chuẩn hóa NFC và bỏ khoảng trắng đầu/cuối. Chỉ cho phép chữ cái Unicode, dấu kết hợp cần thiết cho dấu tiếng Việt và dấu cách. Từ chối số, dấu câu, ký hiệu và emoji. Cho phép trùng tên. |
| Email | Tối đa 254 ký tự. Bỏ khoảng trắng đầu/cuối, chuẩn hóa chữ thường, kiểm tra định dạng cơ bản rồi để Supabase Auth xác thực. |
| Mật khẩu | Tối thiểu 8 ký tự, tối đa 72 byte UTF-8. Không cắt, bỏ khoảng trắng hoặc chuẩn hóa mật khẩu. Không bắt buộc kiểu chữ/số/ký hiệu. |
| Nhập lại mật khẩu | So sánh chính xác với mật khẩu; áp dụng cùng giới hạn khi đăng ký và đổi mật khẩu. |

Với mật khẩu tiếng Việt hoặc emoji, giới hạn 72 byte có thể đạt trước 72 ký tự nhìn thấy. Cần kiểm tra giới hạn byte ở backend ứng dụng trước khi gửi request. Supabase Auth tự băm mật khẩu bằng bcrypt kèm salt; ứng dụng không tự băm, lưu hoặc hiển thị mật khẩu/hash. [Tài liệu bảo mật mật khẩu Supabase](https://supabase.com/docs/guides/auth/password-security), [giới hạn mật khẩu của Supabase Auth](https://github.com/supabase/auth/blob/master/internal/api/password.go).

## Kiến trúc Supabase

### Xác thực

- Dùng Supabase Auth email/password làm nguồn chân lý cho tài khoản và mật khẩu.
- Thêm Supabase Python SDK phiên bản 2.x. Khi đổi mật khẩu, xác thực mật khẩu hiện tại qua Auth rồi gửi cả current_password và mật khẩu mới tới Auth.
- Chuẩn hóa email trước đăng ký/đăng nhập; dùng thông báo chung khi đăng nhập thất bại để không tiết lộ tài khoản có tồn tại hay không.
- Chuyển lỗi nhà cung cấp thành thông báo tiếng Việt an toàn; không hiển thị traceback, token, mật khẩu hoặc payload request.

### Bảng hồ sơ và RLS

Tạo migration cho bảng public.profiles:

- id: UUID, khóa chính và khóa ngoại tới auth.users.id, xóa theo tài khoản.
- display_name: tên hiển thị, bắt buộc, dài tối đa 50 ký tự.
- created_at: thời điểm tạo hồ sơ.

Migration cần bật RLS, thu hồi quyền của anon và chỉ cấp quyền đọc cần thiết cho authenticated. Chính sách SELECT chỉ cho phép hàng có id bằng auth.uid(). Không cấp quyền INSERT/UPDATE/DELETE hồ sơ từ ứng dụng.

Tạo trigger an toàn trên auth.users để tạo hồ sơ từ user metadata khi signup. Trigger cần kiểm tra tên theo cùng quy tắc; nếu tạo hồ sơ lỗi, signup phải thất bại để không có tài khoản thiếu hồ sơ. Đặt search_path cố định và chỉ dùng quyền cần thiết trong hàm trigger.

Email hiển thị lấy từ user đã được xác thực bởi Auth, không lưu trùng trong profiles. Không truy vấn auth.users trực tiếp qua API.

### Cài đặt Auth của Supabase

Trong môi trường Supabase của ứng dụng:

1. Bật signup email/password.
2. Tắt Confirm email theo yêu cầu không OTP/email xác nhận.
3. Bật Require current password when changing password.

Tắt Confirm email sẽ khiến Supabase coi email là đã xác nhận dù người đăng ký chưa chứng minh quyền sở hữu địa chỉ đó. [Supabase Auth configuration](https://supabase.com/docs/guides/auth/general-configuration).

## Tích hợp Streamlit

- Tạo service riêng, ví dụ src/supabase_auth.py, gom cấu hình, validators, signup, login, lấy hồ sơ, đổi mật khẩu, refresh và logout.
- Cấu hình lấy từ Streamlit secrets hoặc biến môi trường: SUPABASE_URL và SUPABASE_PUBLISHABLE_KEY; hỗ trợ SUPABASE_ANON_KEY làm tên thay thế.
- Khai báo tên biến trống trong .env.example. .gitignore hiện đã bỏ qua .env và .streamlit/secrets.toml.
- Không dùng service-role/secret key trong luồng người dùng.
- Không chia sẻ client Supabase có trạng thái Auth giữa các phiên Streamlit. Mỗi phiên dùng client riêng hoặc client theo request gắn đúng token người dùng.
- Chỉ giữ access token, refresh token, thời hạn token và thông tin hồ sơ đã xác thực trong st.session_state. Không lưu mật khẩu, không đưa token vào URL, log hoặc client-side storage.
- Khi khôi phục phiên, nạp token bằng API set_session; nếu hết hạn thì refresh và lưu cặp token mới. Nếu refresh thất bại, xóa phiên xác thực và yêu cầu đăng nhập lại. Xem [Python set_session](https://supabase.com/docs/reference/python/auth-setsession) và [Python refresh_session](https://supabase.com/docs/reference/python/auth-refreshsession).
- Khi logout, gọi Supabase sign_out nếu có thể, sau đó luôn xóa token, auth_user và các giá trị password trong session.
- Giữ nguyên lịch sử chat theo phiên và cơ chế cô lập chat hiện có.

### Giao diện

- Trong src/ui_auth.py, thay session-only auth_accounts/register_account/authenticate bằng lời gọi service Supabase.
- Giữ modal đăng nhập/đăng ký; đổi trường đăng nhập thành email.
- Gỡ hoàn toàn liên kết và màn hình quên mật khẩu đang có trong prototype.
- Trong account menu của sidebar, hiển thị tên/email và form đổi mật khẩu gồm ba ô password.
- Dùng form clear_on_submit; xóa các giá trị password khỏi session sau mọi lần gửi.
- Khi ứng dụng thiếu cấu hình Supabase, báo cấu hình chưa sẵn sàng thay vì làm crash ứng dụng.

Trong app.py, khôi phục auth session trước khi khởi tạo chat owner để giữ nguyên phân vùng lịch sử chat theo tài khoản.

## Kiểm thử và nghiệm thu

### Kiểm tra validators và service

- Tên: kiểm tra độ dài 1/2/50/51, tên tiếng Việt và chữ Unicode hợp lệ; từ chối số, dấu câu, ký hiệu, emoji và tên chỉ có khoảng trắng.
- Email: kiểm tra trim/lowercase, định dạng cơ bản, độ dài 254/255 và email không hợp lệ.
- Mật khẩu: kiểm tra 7/8 ký tự, 72 byte, 73 byte, mật khẩu tiếng Việt, xác nhận không khớp và đảm bảo không có password trong dữ liệu hồ sơ/session user.
- Dùng mock Supabase để kiểm tra signup metadata, login email, cập nhật password có current_password, refresh, logout, lỗi mạng và lỗi xác thực.

### Kiểm tra giao diện

- Signup hợp lệ báo thành công nhưng không tự đăng nhập; signup sai không tạo hồ sơ.
- Login thành công hiển thị đúng tên/email; login sai giữ nguyên modal và báo lỗi chung.
- Hồ sơ hiển thị sau login; đổi mật khẩu từ chối current password sai, mật khẩu mới không hợp lệ hoặc xác nhận sai.
- Logout và refresh token không hợp lệ xóa auth state; khách vẫn chat được.
- Kiểm tra chat của các user tiếp tục được cô lập và không ghi vào Supabase.

### Kiểm tra migration/RLS

Trong Supabase local hoặc môi trường thử nghiệm, xác nhận:

- Signup tạo đúng một profiles row cùng user id; xóa Auth user sẽ xóa hồ sơ.
- User chỉ đọc được profile của mình; anon và user khác không đọc được.
- User không thể ghi hoặc sửa profile trực tiếp qua API.
- Tài khoản Auth không lưu mật khẩu dạng plaintext; profiles không có cột mật khẩu/hash.

## Phạm vi triển khai

Các khu vực chính cần cập nhật là src/ui_auth.py, app.py, requirements.txt và migration SQL mới trong supabase/migrations/. Cập nhật tests/test_ui_auth.py và thêm kiểm thử service/migration phù hợp.

Tài khoản prototype hiện chỉ tồn tại trong Streamlit session nên không có dữ liệu bền vững để chuyển đổi; người dùng sẽ cần đăng ký lại.

## Cấu hình để chạy tính năng

1. Tạo một project Supabase hoặc mở project dùng cho ứng dụng.
2. Trong **SQL Editor**, chạy nội dung của [`supabase/migrations/20261024000000_create_profiles.sql`](supabase/migrations/20261024000000_create_profiles.sql).
3. Trong cấu hình **Authentication**, bật đăng ký email/password, tắt **Confirm email**, và bật yêu cầu mật khẩu hiện tại khi đổi mật khẩu.
4. Lấy Project URL và **publishable key** trong hộp thoại **Connect** hoặc **Settings → API Keys**. Không dùng `sb_secret_...` hoặc `service_role` key.
5. Tạo `.streamlit/secrets.toml` trong thư mục dự án với nội dung:

   ```toml
   SUPABASE_URL = "https://<project-ref>.supabase.co"
   SUPABASE_PUBLISHABLE_KEY = "sb_publishable_..."
   ```

   Tệp secrets này đã được `.gitignore` loại khỏi Git. Có thể dùng `SUPABASE_ANON_KEY` cho project còn dùng key cũ.
6. Cài dependencies trong `requirements.txt`, sau đó khởi động lại ứng dụng Streamlit.

Supabase đặt URL và publishable key trong dashboard; publishable key dành cho kết nối ứng dụng có RLS. Tắt Confirm email đồng nghĩa Supabase xem địa chỉ đăng ký là đã xác nhận dù người dùng chưa chứng minh quyền sở hữu. Tham khảo [lấy API keys](https://supabase.com/docs/guides/getting-started/api-keys), [cấu hình Auth](https://supabase.com/docs/guides/auth/general-configuration) và [bảo mật mật khẩu](https://supabase.com/docs/guides/auth/password-security).
