# Bộ công cụ thu thập dữ liệu TTHC cho callbot

## Triển khai nhanh qua Docker (Khuyên dùng)
Hệ thống đã được đóng gói hoàn chỉnh gồm **Web CMS** và **iCC Mock Server**:
```bash
docker-compose up -d --build
```
Hoặc trên Windows chỉ cần nhấp đúp file **`docker-start.bat`**.
- Truy cập CMS Web: [http://localhost:8780](http://localhost:8780)
- Mock iCC API: [http://localhost:8790/docs](http://localhost:8790/docs)
- Xem hướng dẫn chi tiết tại [DOCKER.md](file:///c:/Users/admin/Desktop/VNPT/cms-callbot/DOCKER.md).

---

## Chạy cho một tỉnh/thành bất kỳ — chỉ đổi tên tỉnh
```
pip install requests openpyxl
cd tthc-callbot-kit/skills/tthc-callbot-metadata/scripts

python run_all.py "Khánh Hòa"              # thu thập + xuất Excel
python run_all.py "Nghệ An" --limit 20     # chạy thử 20 thủ tục trước
python run_all.py "Khánh Hòa" --resume     # chạy tiếp nếu lần trước bị lỗi giữa chừng
```
Kết quả: `data/<MÃ>_raw.json.gz` (dữ liệu thô) và `out/<PREFIX>_Noi_dung_callbot_<MÃ>.xlsx`.

Tên tỉnh gõ có dấu, không dấu hay mã đều được: `"Khánh Hòa"`, `"khanh hoa"`, `H32`, `"TP Hồ Chí Minh"`.
Xem danh sách 34 tỉnh/thành và mã: `python collect_tthc.py --list-provinces`.

Tuỳ chọn thêm (truyền sau tên tỉnh):
- `--no-conditions` bỏ dòng "Yêu cầu, điều kiện thực hiện" để khớp 100% file mẫu
- `--with-questions` / `--with-tags` tự sinh câu hỏi mẫu (cột C) / tags (cột D)
- `--include-internal` lấy thêm TTHC nội bộ giữa các cơ quan nhà nước
- `--skip-collect` không tải lại, chỉ xuất lại Excel từ file raw đã có

## Địa chỉ tiếp nhận
Đã có địa chỉ thật cho: Đồng Nai (H19), Khánh Hòa (H32). Tỉnh khác sẽ dùng câu chung
"Trung tâm Phục vụ hành chính công <tỉnh>" — muốn chính xác, thêm mục vào `scripts/provinces.json`
theo mẫu H32 (sửa `center_address`).

## Nếu Python bị chặn (lỗi 403 / trả về HTML)
Mở https://dichvucong.gov.vn/co-quan trên trình duyệt → F12 → Console → dán `scripts/browser_collector.js`
(sửa dòng `PROVINCE = 'H32'`) → bấm nút đỏ tải file → đặt file vào `data/` rồi chạy
`python run_all.py "Khánh Hòa" --skip-collect`.

## Cài vào Claude Code (tuỳ chọn)
Copy `skills/tthc-callbot-metadata` vào `.claude/skills/` và `agents/tthc-metadata-collector.md`
vào `.claude/agents/`. Sau đó nói: "dùng agent tthc-metadata-collector cho Nghệ An".

## Cập nhật dữ liệu mới (chỉ lấy phần mới / thay đổi so với file Excel đã có)
```
python update_tthc.py "Khánh Hòa" --old "D:\duong\dan\KHA_Noi_dung_callbot_H32.xlsx"
python update_tthc.py "Khánh Hòa" --since 2026-11-01     # chỉ thay đổi cập nhật trên cổng từ ngày này
python update_tthc.py "Khánh Hòa" --full                 # xuất thêm bộ đầy đủ mới nhất
```
Kết quả: `out/<PREFIX>_CapNhat_<MÃ>_<ngày>.xlsx`
- Sheet `Sheet0`: chỉ các dòng của thủ tục MỚI và thủ tục THAY ĐỔI (đúng 5 cột, nạp thẳng vào tập train)
- Sheet `TongHop`: danh sách Mới / Thay đổi / Đã gỡ, ngày cập nhật trên cổng, trường nào thay đổi
Câu hỏi (cột C) và Tags (cột D) bạn đã điền tay trong file cũ được giữ lại.
Lần sau không cần `--old`: script tự lấy file raw mới nhất trong `data/` làm mốc.
