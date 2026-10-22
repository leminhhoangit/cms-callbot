# CMS dữ liệu Callbot TTHC (MVP)

Web quản lý nội dung huấn luyện callbot DC4.0 thay cho việc làm tay trên file Excel. Dùng lại script của bộ công cụ
(`../scripts/`), nên file Excel xuất ra **trùng khớp** với `build_callbot_excel.py` (đã kiểm: Khánh Hòa 72.875 / 72.875 dòng).

## Chạy
Nhấp đúp `start_cms.bat` → mở http://127.0.0.1:8780 (lần đầu tự cài thư viện). Nhập **Người thao tác** ở góc phải.
Dữ liệu CMS: `cms/data/` (`cms.db`, `exports/`, `logs/`) – đổi chỗ bằng biến `CMS_DATA_DIR`.

## Tính năng
| Màn | Làm gì |
|---|---|
| Tỉnh / thành | Thẻ từng tỉnh: số TTHC, số dòng, % dòng có câu hỏi, cần duyệt / đã duyệt / đã gỡ, lần nhập gần nhất |
| Thủ tục hành chính | Tìm theo tên / mã, lọc lĩnh vực / thay đổi / trạng thái duyệt; duyệt hàng loạt |
| Chi tiết TTHC | Nội dung từng dòng (sinh từ cổng), **biên tập Câu hỏi + Tags**, điền câu hỏi mẫu theo luật, duyệt / bỏ duyệt, lịch sử |
| Dữ liệu nguồn | Nhập file raw có sẵn; **thu thập mới** từ Cổng DVCQG (kiểm tra sức khoẻ cổng trước, chạy nền, có nhật ký); "chạy thử N TTHC" không nhập |
| Xuất Excel callbot | Bộ đầy đủ / chỉ đã duyệt / **bản cập nhật** (Mới + Thay đổi + sheet TongHop); danh sách TTHC đã gỡ cần xoá khỏi tập train |
| Cấu hình tỉnh | Tên, **địa chỉ tiếp nhận**, tiền tố file, có/không dòng điều kiện; "Dựng lại nội dung" áp dụng cho dữ liệu đã nhập |
| Sức khoẻ nguồn | Gọi thử các API của cổng (cổng từng đổi API không báo trước) |
| Nhật ký | Mọi thao tác ghi: ai, lúc nào, làm gì |

## Luật dữ liệu
- Mỗi lần nhập so với bộ đang có: **Mới / Thay đổi → Cần duyệt**; Không đổi giữ trạng thái duyệt; không còn trên cổng → **Đã gỡ** (không xoá, liệt kê để xoá khỏi tập train).
- **Câu hỏi / Tags biên tập tay luôn được giữ** qua các lần nhập (khớp theo TTHC + Tiêu đề). Sửa TTHC đã duyệt → Cần duyệt lại.
- Rào chắn: file tải dở (có lỗi) hoặc ít hơn 90% bộ đang có → **không** đánh dấu Đã gỡ (tránh gỡ nhầm hàng loạt).
- Câu hỏi mẫu sinh **theo luật** (giống `--with-questions`), không dùng AI; người đọc lại trước khi duyệt.

## Giả định của MVP (chờ anh Hiệp chốt – xem ../docs/00_KHAO_SAT_HIEN_TRANG.md mục 4)
1. Chạy 1 máy, chưa đăng nhập / phân quyền (tên người thao tác tự khai, ghi nhật ký).
2. Nạp callbot bằng **file Excel 5 cột** như hiện tại (chưa có API nền tảng callbot).
3. SQLite; chuyển PostgreSQL khi nhiều người dùng.
4. Lịch cập nhật hằng tháng vẫn dùng `capnhat_hang_thang.bat` (Task Scheduler); CMS nhập file raw mới / tự thu thập khi bấm.

## Test
`.venv\Scripts\python -m pytest -q tests` – chạy trên dữ liệu thật `data/H32_raw.json.gz`, gồm test so khớp toàn bộ với script gốc.
