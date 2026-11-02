# ========================================================
# Dockerfile cho CMS Callbot TTHC
# ========================================================

# Base image Python 3.11 slim (Debian Bookworm)
FROM python:3.11-slim AS runtime

# Cấu hình môi trường Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    CMS_DATA_DIR=/app/cms/data \
    CMS_PORT=8780 \
    PYTHONPATH=/app:/app/cms:/app/scripts

# Cài đặt curl để hỗ trợ kiểm tra sức khỏe (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cài đặt thư viện Python
COPY cms/requirements.txt /app/cms/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/cms/requirements.txt pytest

# Sao chép mã nguồn dự án vào container
COPY scripts/ /app/scripts/
COPY data/ /app/data/
COPY cms/ /app/cms/

# Tạo các thư mục lưu trữ dữ liệu bền vững và xuất báo cáo
RUN mkdir -p /app/cms/data /app/out /app/logs

# Khai báo cổng dịch vụ
# 8780: CMS Web + API
# 8790: Mock iCC Simulator (khi chạy dịch vụ giả lập bot)
EXPOSE 8780 8790

# Thư mục làm việc mặc định khi chạy CMS
WORKDIR /app/cms

# Kiểm tra trạng thái hoạt động của ứng dụng
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('CMS_PORT', '8780') + '/api/health')" || exit 1

# Lệnh khởi chạy mặc định: FastAPI CMS Web & API
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${CMS_PORT:-8780}"]

