# 00 – Khảo sát hiện trạng: bộ công cụ dữ liệu TTHC cho Callbot DC4.0

> Bản khảo sát đầu vào cho dự án **CMS quản lý dữ liệu Callbot TTHC**. Viết sau khi đọc README, các script và dữ liệu thô
> trong `D:\VNPT\tthc-laydulieu_callbot_DC4.0` (ngày 22/10/2026). Chưa có hướng dẫn cách làm của anh Hiệp – phần
> "Đề xuất" ở cuối chỉ là khung để anh chốt, chưa phải thiết kế.

## 1. Hệ thống đang làm gì

Bộ script Python (chạy tay hoặc theo lịch Windows) lấy thủ tục hành chính (TTHC) từ **Cổng Dịch vụ công Quốc gia**
(`https://dichvucong.gov.vn/api/v1`) cho từng tỉnh/thành, rồi xuất **file Excel 5 cột** để nạp vào tập train của callbot.

```
Cổng DVCQG (API công khai)
   │  collect_tthc.py  (danh sách theo cấp Tỉnh / Xã / đặc thù tỉnh  →  chi tiết từng TTHC, 4 luồng, thử lại 5 lần)
   ▼
data/<MÃ>_raw.json.gz          {fetchedAt, provinceCode, list{id:item}, details{id:detail}, failures}
   │  build_callbot_excel.py   (mỗi TTHC → ~25 dòng "Tiêu đề / Nội dung", địa phương hoá tên cơ quan, địa chỉ tiếp nhận)
   ▼
out/<PREFIX>_Noi_dung_callbot_<MÃ>.xlsx      Sheet0 – 5 cột → nạp tập train callbot
   │  update_tthc.py (hằng tháng, lịch 08:00 ngày 1)  so bản mới với bộ cũ (raw hoặc Excel)
   ▼
out/<PREFIX>_CapNhat_<MÃ>_<ngày>.xlsx       Sheet0 = chỉ dòng Mới + Thay đổi;  TongHop = Mới / Thay đổi / Đã gỡ
```

| Thành phần | Vai trò |
|---|---|
| `scripts/collect_tthc.py` | Thu thập. Phạm vi: TTHC chuẩn (STANDARD) + liên thông cấp Tỉnh/Xã + đặc thù do chính tỉnh công bố; tuỳ chọn TTHC nội bộ. `--resume`, `--limit`. |
| `scripts/build_callbot_excel.py` | Sinh nội dung callbot. Tuỳ chọn `--no-conditions`, `--with-questions` (câu hỏi mẫu theo luật), `--with-tags` (Lĩnh vực; Cấp), `--csv`. |
| `scripts/update_tthc.py` | Cập nhật hằng tháng: Mới / Thay đổi (kèm trường nào đổi) / Đã gỡ; **giữ Câu hỏi (C) + Tags (D) đã điền tay** ở bộ cũ. `--since`, `--full`. |
| `scripts/province_config.py`, `provinces.json` | Cấu hình 34 tỉnh/thành: tên hiển thị, tiền tố file, **địa chỉ Trung tâm Phục vụ HCC**. Tỉnh chưa có mục riêng → câu chung. |
| `scripts/browser_collector.js` | Phương án dự phòng khi Python bị chặn (403 / HTML): chạy trong Console trình duyệt. |
| `run_all.py`, `capnhat_hang_thang.bat`, `cai_lich_tu_dong.bat`, `tinh.txt` | Chạy trọn gói 1 tỉnh; lịch Task Scheduler hằng tháng cho các mã trong `tinh.txt` (hiện H19, H32). |

## 2. Dữ liệu hiện có (đo thật trên file raw)

| Tỉnh | Lấy lúc (UTC) | TTHC có chi tiết | Ghi chú |
|---|---|---|---|
| H19 – TP Đồng Nai | 2026-10-22 06:48 | 2.749 (2.708 chuẩn, 39 đặc thù, 2 liên thông) | Raw dạng trình duyệt: danh sách 4.899 mục, 2.150 mục không có chi tiết (1.986 đặc thù của tỉnh khác + 164 nội bộ) – bước xuất Excel tự lọc. |
| H32 – Khánh Hòa | 2026-10-22 07:10 | 2.754 (2.708 chuẩn, 44 đặc thù, 2 liên thông) | 0 lỗi tải. |

Mỗi TTHC → khoảng 25 dòng ⇒ **~70.000 dòng / tỉnh**. Trường sinh ra (cột A "Tiêu đề"): Địa phương ban hành, Mã, Tên TTHC, Cơ quan
công bố, Loại thủ tục, Mô tả đối tượng, Địa chỉ tiếp nhận, Mô tả cơ quan thực hiện / có thẩm quyền, Cơ quan thực hiện / có thẩm quyền /
được uỷ quyền / phối hợp, Trình tự thực hiện, Cấp thực hiện, Lĩnh vực, Cách thức thực hiện (mỗi hình thức nộp 1 dòng, kèm thời hạn + phí),
Đối tượng thực hiện, Thành phần hồ sơ (mỗi trường hợp 1 dòng), Kết quả, Yêu cầu điều kiện, Căn cứ pháp lý, TTHC liên quan, TTHC liên thông.
Cột E `IdentificationInfo` = `{"uri": <trang TTHC trên cổng>, "type": 3, "title": <tên TTHC>}` – khoá nhận diện để so sánh cập nhật.

## 3. Điểm đau – lý do cần CMS

1. **Mọi thứ là file**: raw `.json.gz` + Excel rời trong `out/`; không có nơi xem / tìm / sửa 1 TTHC, không biết bản nào đã nạp vào callbot.
2. **Câu hỏi mẫu (cột C) và Tags (cột D) điền tay trong Excel** – chỉ được giữ nếu lần cập nhật sau trỏ đúng file cũ; không có người sửa, lịch sử, duyệt.
3. **Không có trạng thái duyệt nội dung**: dòng Mới / Thay đổi đi thẳng từ script vào tập train; TTHC "Đã gỡ" phải xoá tay khỏi tập train.
4. **Địa chỉ tiếp nhận** chỉ đúng cho H19, H32; tỉnh khác dùng câu chung – cần chỗ nhập / duyệt cấu hình tỉnh thay vì sửa JSON.
5. **Vận hành phụ thuộc 1 máy Windows** (Task Scheduler, máy phải bật); lỗi chỉ nằm trong `logs/`, không ai được báo.
6. **Rủi ro nguồn**: cổng có thể chặn (403 / HTML) → phải chạy tay script trình duyệt; API cổng thay đổi là hỏng âm thầm.
7. Không có số liệu: bao nhiêu TTHC / tỉnh, bao nhiêu dòng đã có câu hỏi, lần cập nhật gần nhất, lỗi tải.

## 3b. Kiểm tra chạy thật trên máy (22/10/2026)

| Hạng mục | Kết quả |
|---|---|
| Python `py` 3.14 + `requests` 2.34 + `openpyxl` 3.1 | Có sẵn – các file `.bat` chạy được |
| Xuất Excel từ raw có sẵn (H32) | OK: 2.753 TTHC, **72.875 dòng** (bỏ 1 TTHC của tỉnh khác) |
| Cổng DVCQG | Truy cập được, không bị chặn 403 (~0,4 s / lệnh) |
| API danh sách + chi tiết TTHC (dùng khi thu thập) | `OK` (gọi thử 1 bản ghi mỗi API) |
| `collect_tthc.py --list-provinces` | **Hỏng do cổng đổi API**: body rỗng → `BAD_REQUEST`, nay bắt buộc `departmentLevel`, `departmentType`, `agencyType`. **Đã sửa** (`{"departmentLevel": "PROVINCE", "departmentType": "PROVINCE", "agencyType": "UBND_TINH"}`): ra 34 tỉnh, khớp 100% `provinces.json`; số TTHC đặc thù trên cổng H32 = 44, H19 = 39 – khớp dữ liệu đã tải |
| Lịch tự động hằng tháng | Chưa cài trên máy này |

Bài học cho CMS: API cổng **thay đổi không báo trước** → CMS cần kiểm tra sức khoẻ nguồn (gọi thử trước mỗi lần thu thập) và cảnh báo
khi cổng trả `BAD_REQUEST` / HTML, thay vì để script thử lại 5 lần rồi dừng âm thầm trong log.

## 4. Câu hỏi cần anh Hiệp chốt trước khi viết bộ tài liệu

1. Người dùng CMS là ai (đội nội dung callbot, admin tỉnh, VNPT tỉnh?) – có phân quyền theo tỉnh không?
2. CMS **nạp thẳng** vào callbot DC4.0 (API của nền tảng callbot) hay vẫn **xuất Excel 5 cột** để nạp tay?
3. Phạm vi tỉnh: chỉ H19, H32 hay cả 34 tỉnh/thành?
4. Có cần **duyệt nội dung** (biên tập → duyệt → xuất bản) trước khi vào tập train không? TTHC "Đã gỡ" xử lý thế nào?
5. Câu hỏi mẫu / tags: biên tập tay, sinh theo luật như script hiện tại, hay có dùng AI soạn nháp (người duyệt)?
6. Hạ tầng: chạy trên máy chủ VNPT / cloud nào, công nghệ ưu tiên (đội đang dùng Python), đăng nhập (SSO VNPT?).
7. Mẫu tài liệu: theo mẫu nào (VNPT / dự án DC4.0), định dạng nộp (Word / Excel / PDF), hạn nộp.

## 5. Đề xuất khung bộ tài liệu (chờ anh chốt cách làm)

| # | Tài liệu | Nội dung chính |
|---|---|---|
| 01 | Tài liệu yêu cầu (SRS / BRD) | Mục tiêu, người dùng + phân quyền, use case: thu thập, xem/tìm TTHC, biên tập câu hỏi/tags, duyệt, xuất bản / nạp callbot, cấu hình tỉnh, lịch cập nhật, báo cáo; yêu cầu phi chức năng. |
| 02 | Kiến trúc hệ thống | Thành phần (collector chạy nền, CMS web, CSDL, kho file, tích hợp callbot), luồng dữ liệu, triển khai, bảo mật. |
| 03 | Thiết kế CSDL | Tỉnh, TTHC (bản theo lần thu thập), dòng nội dung callbot, câu hỏi / tags, phiên bản & so sánh, lần thu thập, lô xuất bản, người dùng, nhật ký. |
| 04 | Đặc tả chức năng + giao diện | Danh sách màn hình, luồng biên tập → duyệt → xuất bản, màn so sánh Mới / Thay đổi / Đã gỡ. |
| 05 | Đặc tả API / tích hợp | API CMS, tích hợp nguồn Cổng DVCQG, định dạng xuất (Excel 5 cột hiện tại) / API nạp callbot. |
| 06 | Kế hoạch kiểm thử + tiêu chí nghiệm thu | Đối chiếu số TTHC / số dòng với script hiện tại (H19 2.749, H32 2.754), giữ câu hỏi tay khi cập nhật, ca lỗi nguồn 403. |
| 07 | Triển khai + vận hành | Cài đặt, lịch cập nhật, giám sát + cảnh báo lỗi, sao lưu, chuyển dữ liệu từ Excel/raw hiện có. |
| 08 | Kế hoạch dự án | Hạng mục, mốc, nhân sự, rủi ro. |

Nguyên tắc giữ nguyên từ bộ công cụ hiện tại: định dạng 5 cột + khoá `IdentificationInfo.uri`; chỉ lấy dữ liệu công khai của cổng,
tốc độ tải thấp (4 luồng, nghỉ khi bị chặn); không ghi đè câu hỏi / tags người đã biên tập.
