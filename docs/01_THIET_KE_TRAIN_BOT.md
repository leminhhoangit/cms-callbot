# 01 – Thiết kế: Train callbot sau khi duyệt (lô train, job, trạng thái)

> Bối cảnh: tài liệu iCC hiện có ("[KDDI] Technical Integration Document", v1.0.2) chỉ mô tả **nhúng khung chat**, KHÔNG có API
> nạp dữ liệu / train / trạng thái job. Thiết kế này dùng **API giả lập** (`cms/mock_icc/`) có hình dạng hợp lý; khi iCC cung cấp
> API thật chỉ cần viết lại **bộ kết nối** (`TrainingProvider`) – mô hình dữ liệu, luồng duyệt, giao diện giữ nguyên.

## 1. Mục tiêu
1. Chỉ nội dung **đã duyệt** mới được đưa sang bot.
2. Biết chính xác **bot đang "biết" phiên bản nào** của từng thủ tục, và còn bao nhiêu thủ tục **cần train / cần xoá**.
3. Mỗi lần gửi là **một lô train** có trạng thái rõ ràng, biết **khi nào train xong**, lỗi gì, ai gửi.
4. Không gửi trùng: mỗi tỉnh (một kho tri thức) chỉ có **một lô đang chạy**.

## 2. Mô hình dữ liệu

```
procedures (đã có)                    training_batches                       training_items
 ├ review = APPROVED                   id  TB-<tỉnh>-<yyyymmdd>-<nnn>         batch_id, fid
 ├ content_hash  (băm nội dung hiện tại)  province, mode DELTA|FULL            action UPSERT|DELETE
 ├ trained_hash  (băm bản bot đang có)    status, progress 0..100               content_hash (lúc gửi)
 ├ trained_batch / trained_at            remote_job_id (mã job bên iCC)         rows
 └ status ACTIVE|REMOVED                 upserts, deletes, rows                 
                                         created_by/at, submitted_at,         training_events
                                         started_at, finished_at               batch_id, at, status, progress,
                                         error, attempt, parent_id (gửi lại)   source POLL|CALLBACK|USER|SYSTEM, message
```

**Băm nội dung** `content_hash` = SHA-256 của các dòng (Tiêu đề, Nội dung, Câu hỏi, Tags) – đúng thứ bot nhận. Từ đó suy ra:

| Trạng thái train của thủ tục | Điều kiện |
|---|---|
| **Đã train – đúng bản** | `review = APPROVED` và `trained_hash = content_hash` |
| **Cần train** | `review = APPROVED` và `trained_hash ≠ content_hash` (mới duyệt, sửa rồi duyệt lại) |
| **Chờ duyệt** (không gửi) | `review = NEED_REVIEW` – bot giữ bản cũ đã train (nếu có) |
| **Cần xoá khỏi bot** | `status = REMOVED` và `trained_hash` có giá trị |

## 3. Vòng đời lô train

```
 DRAFT ──gửi──▶ SUBMITTED ──▶ QUEUED ──▶ TRAINING (progress %) ──▶ SUCCEEDED
   │               │             │              │                    
   └─huỷ─▶ CANCELLED ◀───────────┴──────────────┘ (huỷ khi còn chờ)   └──▶ FAILED ──gửi lại──▶ lô mới (attempt+1)
```

| Trạng thái | Nghĩa | Ai / cái gì chuyển |
|---|---|---|
| DRAFT – Chờ gửi | Đã chốt danh sách (ảnh chụp nội dung lúc tạo) | Người tạo lô |
| SUBMITTED – Đã gửi | iCC nhận dữ liệu, trả `job_id` | Người bấm Gửi (bắt buộc tên) |
| QUEUED – Xếp hàng | Job chờ máy train | iCC (CMS hỏi định kỳ / callback) |
| TRAINING – Đang train | Có % tiến độ | iCC |
| SUCCEEDED – Train xong | Bot đã dùng dữ liệu mới → cập nhật `trained_hash` từng thủ tục | iCC → CMS |
| FAILED – Lỗi | Ghi lỗi; thủ tục giữ `trained_hash` cũ (bot vẫn bản cũ) | iCC → CMS |
| CANCELLED – Đã huỷ | Huỷ khi DRAFT / SUBMITTED / QUEUED | Người dùng |

Luật:
- Lô chỉ chứa thủ tục **Cần train** (UPSERT) và **Cần xoá** (DELETE) tại thời điểm tạo; nội dung **chụp lại** (`content_hash` + dòng) để
  sửa trong lúc train không làm lệch.
- Một tỉnh chỉ **một lô đang hoạt động** (SUBMITTED / QUEUED / TRAINING) – tránh hai job ghi đè nhau trên cùng kho tri thức.
- SUCCEEDED: mỗi mục trong lô → `trained_hash = content_hash của lô` (không phải của hiện tại – nếu đã sửa sau đó, thủ tục vẫn "Cần train").
- FAILED / CANCELLED: không đổi `trained_hash`. Gửi lại = tạo lô mới từ danh sách còn cần train (`parent_id`, `attempt+1`).
- Không có job nào "treo" vô hạn: quá `timeout` (mặc định 2 giờ) không có tiến triển → FAILED (`TIMEOUT`).

## 4. Theo dõi job – biết khi nào train xong
Hai đường, dùng cả hai cho chắc:
1. **Hỏi định kỳ (poll)**: luồng nền của CMS hỏi `GET job` mỗi 5 giây cho mọi lô đang hoạt động; nút "Cập nhật trạng thái" hỏi ngay.
2. **Callback**: khi gửi, CMS kèm `callback_url`; iCC gọi lại khi job đổi trạng thái. Callback có chữ ký HMAC (khoá bí mật dùng chung).
Mọi lần nhận trạng thái ghi `training_events` (nguồn POLL / CALLBACK) → dòng thời gian của lô.

## 5. Bộ kết nối (`TrainingProvider`)
```
submit(bot_id, items[{fid, action, rows[{title, content, questions, tags}]}], callback_url) -> job_id
status(job_id) -> {status: QUEUED|TRAINING|SUCCEEDED|FAILED|CANCELLED, progress, message, started_at, finished_at}
cancel(job_id)
```
- `MockIccProvider` – gọi API giả lập `cms/mock_icc` (cổng 8790).
- `IccProvider` – viết khi có tài liệu API thật. Cấu hình: `CMS_TRAIN_PROVIDER`, `CMS_TRAIN_URL`, `CMS_TRAIN_BOT_<MÃ TỈNH>`, khoá ở biến môi trường
  `CMS_TRAIN_API_KEY` (không lưu CSDL, không ghi log).

## 6. API giả lập iCC (`cms/mock_icc`)
| API | Mô tả |
|---|---|
| `POST /api/v1/bots/{bot_id}/train-jobs` | Nhận lô (upserts + deletes), trả `{job_id, status: QUEUED}` |
| `GET /api/v1/train-jobs/{job_id}` | `{status, progress, message, started_at, finished_at}` |
| `POST /api/v1/train-jobs/{job_id}/cancel` | Huỷ khi còn QUEUED |
| `GET /api/v1/bots/{bot_id}/knowledge` | Số thủ tục / dòng bot đang "biết" (để đối chiếu) |
Mô phỏng: xếp hàng vài giây, train theo tốc độ cấu hình (dòng/giây), tiến độ tăng dần, gọi callback; lỗi giả lập khi
thủ tục chứa chuỗi `[[FAIL]]` hoặc theo `MOCK_FAIL_RATE`; xác thực `X-Api-Key`.

## 7. Giao diện CMS – trang "Train bot" (theo tỉnh)
- Thẻ số liệu: Bot đang có (đúng bản) · **Cần train** · **Cần xoá khỏi bot** · Chờ duyệt.
- Nút **Tạo lô train** (xem trước số mục) → **Gửi train** (cần tên người thao tác).
- Bảng lô: mã, trạng thái (Steps), tiến độ %, số mục, người gửi, thời gian gửi → xong, lỗi.
- Chi tiết lô: danh sách mục, dòng thời gian sự kiện (poll / callback), nút Huỷ / Gửi lại phần lỗi.

## 8. Ngoài phạm vi (chờ API thật)
Kiểm tra chất lượng trả lời của bot sau train (gửi câu hỏi mẫu qua khung chat sandbox `stagicc-dayup.vnpt.vn`) – cần đồng ý vì gửi tin nhắn thật.

## 9. Đồng bộ chạy tay / theo lịch (`cms/app/sync.py`, trang "Đồng bộ & lịch")
Cấu hình theo **từng tỉnh**:

| Trường | Giá trị |
|---|---|
| Cách chạy | **Chạy tay** (chỉ khi bấm) · **Theo lịch** |
| Phạm vi mỗi lượt | **Chỉ train** – gửi phần đã duyệt chưa lên bot · **Đồng bộ đầy đủ** – kiểm tra cổng DVC → tải dữ liệu mới → nhập + so sánh → train phần đã duyệt |
| Lịch | Hằng ngày / hằng tuần (thứ) / hằng tháng (ngày; tháng ngắn → ngày cuối tháng) + giờ HH:MM |

Một lượt chạy (cùng quy trình cho chạy tay và theo lịch), mỗi bước ghi thời điểm + kết quả:
1. Bỏ qua (SKIPPED) nếu tỉnh đang có lượt đồng bộ khác, hoặc lô train Chờ gửi / đang chạy.
2. Kết nối bot (bộ kết nối iCC) – lỗi → FAILED.
3. (Đồng bộ đầy đủ) kiểm tra sức khoẻ cổng → tải → nhập + so sánh. Mới / Thay đổi → **Cần duyệt** (lịch không tự duyệt).
4. Không có gì đã duyệt cần train → NO_CHANGE (không tạo lô rỗng).
5. Tạo lô → gửi → theo dõi đến Train xong / Lỗi (tối đa 3 giờ trong lượt; sau đó lô vẫn được luồng nền theo dõi).

Hẹn giờ: kiểm tra mỗi 30 giây; đặt giờ kế tiếp **trước** khi chạy (không chạy trùng); CMS tắt lúc đến giờ → chạy bù 1 lần khi bật lại;
lượt đang chạy khi CMS tắt → đánh dấu FAILED lúc khởi động.

## 10. So sánh dữ liệu cổng không phụ thuộc thứ tự
Đo thật 22/10/2026 (Khánh Hòa, hai lần tải cách 3 giờ): so sánh nguyên văn báo **2.023** thủ tục "Thay đổi", trong đó **1.979 chỉ do cổng
trả danh sách (cơ quan, căn cứ pháp lý, đối tượng, kết quả…) theo thứ tự khác**; thay đổi thật = **44** (đổi mã giấy tờ, thêm văn bản, đổi tên kết quả).
CMS so sánh trên bản đã **chuẩn hoá thứ tự** (`procedures.cmp_hash`), còn nội dung lưu / xuất giữ **nguyên văn** (vẫn trùng file của bộ công cụ).
Thủ tục chỉ đổi thứ tự → "Không đổi": giữ nội dung, trạng thái duyệt và bản đã train.
Lưu ý: `scripts/update_tthc.py` của bộ công cụ cũ so sánh nguyên văn nên **file cập nhật hằng tháng của nó cũng báo nhầm** như trên.
