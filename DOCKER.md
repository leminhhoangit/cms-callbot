# Hướng dẫn đóng gói & chạy CMS Callbot bằng Docker

Tài liệu hướng dẫn triển khai hệ thống **CMS Dữ liệu Callbot TTHC** bằng Docker và Docker Compose.

---

## 1. Kiến trúc hệ thống trong Docker

Hệ thống được đóng gói thành 2 dịch vụ độc lập kết nối qua mạng nội bộ Docker (`callbot-net`):

| Dịch vụ | Cổng Host | Mô tả |
|---|---|---|
| **`cms`** | `8780` | Máy chủ FastAPI phục vụ Web UI (React/AntD build sẵn) & API quản trị dữ liệu, biên tập câu hỏi, đồng bộ lịch. |
| **`mock-icc`** | `8790` | API iCC giả lập phục vụ kiểm thử luồng tạo lô huấn luyện (training batch) và cập nhật trạng thái job. |

---

## 2. Yêu cầu môi trường

- Đã cài đặt **Docker Desktop** (hỗ trợ Windows 10/11 với WSL2 hoặc Hyper-V).
- Đảm bảo **Docker Desktop đang chạy** (biểu tượng cá voi màu xanh ở khay hệ thống Taskbar).

---

## 3. Khởi chạy nhanh

### Cách 1: Dùng kịch bản tự động (Khuyên dùng trên Windows)
- Nhấp đúp vào file **`docker-start.bat`**.
- Kịch bản sẽ kiểm tra Docker, tự động build image, khởi chạy container và mở trình duyệt tới `http://127.0.0.1:8780/`.
- Để dừng hệ thống: Nhấp đúp vào **`docker-stop.bat`**.

### Cách 2: Sử dụng dòng lệnh (CLI)

1. **Khởi chạy hệ thống (chạy nền):**
   ```bash
   docker-compose up -d --build
   ```

2. **Kiểm tra trạng thái container:**
   ```bash
   docker-compose ps
   ```

3. **Xem nhật ký (logs) theo thời gian thực:**
   ```bash
   # Xem tất cả log
   docker-compose logs -f

   # Hoặc chỉ xem log của CMS
   docker-compose logs -f cms
   ```

4. **Dừng hệ thống:**
   ```bash
   docker-compose down
   ```

---

## 4. Truy cập ứng dụng

- **Giao diện CMS Callbot:** [http://localhost:8780](http://localhost:8780)
- **API Swagger CMS:** [http://localhost:8780/docs](http://localhost:8780/docs)
- **API Swagger iCC Giả lập:** [http://localhost:8790/docs](http://localhost:8790/docs)

> **Lưu ý:** Khi vào giao diện CMS lần đầu, hãy điền tên tại ô **Người thao tác** (góc trên bên phải) trước khi thực hiện duyệt hoặc chỉnh sửa dữ liệu.

---

## 5. Lưu trữ & Dữ liệu bền vững (Persistence)

Hệ thống cấu hình các khối lưu trữ đảm bảo không mất dữ liệu khi restart hoặc nâng cấp image:

- **`cms_data` (Named Volume):** Lưu cơ sở dữ liệu SQLite (`cms.db`), file raw tải từ CMS, và các file Excel xuất nội bộ.
- **`./data` (Mount từ host):** Thư mục chứa dữ liệu thô ban đầu (ví dụ: `H19_raw.json.gz`, `H32_raw.json.gz`).
- **`./out` (Mount từ host):** Mọi file Excel tạo ra từ lệnh xuất hoặc script sẽ xuất hiện trực tiếp trong thư mục `out/` trên máy tính của bạn.
- **`./logs` (Mount từ host):** Log các lần thu thập, đồng bộ dữ liệu.

---

## 6. Chạy các kịch bản (Script) bên trong Container

Bạn không cần cài Python trên máy host, có thể gọi trực tiếp các script bên trong container CMS:

### 6.1. Thu thập dữ liệu tỉnh mới
```bash
docker-compose exec cms python ../scripts/collect_tthc.py --province H32 --out /app/data/H32_raw.json.gz
```

### 6.2. Xuất dữ liệu Excel cho Callbot
```bash
docker-compose exec cms python ../scripts/build_callbot_excel.py --raw /app/data/H32_raw.json.gz --province H32 --out /app/out/KHA_Noi_dung_callbot_H32.xlsx
```

### 6.3. Cập nhật dữ liệu hàng tháng (so sánh và lấy phần thay đổi)
```bash
docker-compose exec cms python ../scripts/update_tthc.py "Khánh Hòa"
```

### 6.4. Chạy kiểm thử tự động (Unit / Integration Tests)
```bash
docker-compose exec cms pytest -q tests
```

---

## 7. Tùy biến cấu hình (.env)

Bạn có thể tạo file `.env` (từ mẫu `.env.example`) để điều chỉnh:
- Đổi cổng web nếu bị trùng: `CMS_PORT=9000`
- Cấu hình API iCC thật khi kết nối thực tế:
  ```env
  CMS_TRAIN_PROVIDER=icc
  CMS_TRAIN_URL=https://icc-api.example.com
  CMS_TRAIN_API_KEY=your-production-key
  ```

