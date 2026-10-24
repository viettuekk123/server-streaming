# BVG Streaming — server

Đồ án video-on-demand: FastAPI + SQL Server, FFmpeg chuẩn bị media, player MSE/ABR nằm ở repo `web-streaming`. Code ưu tiên dễ đọc và giải thích cho đồ án sinh viên. Không có parser hay segmenter container tự viết.

## Yêu cầu Windows

- Python 3.12 x64, bật Add to PATH khi cài.
- Docker Desktop đang chạy Linux containers, đủ RAM cho SQL Server (nên cấp ít nhất 4 GB).
- FFmpeg và ffprobe trong PATH, build có libx264 và DASH muxer. Có thể cài `winget install Gyan.FFmpeg`; mở PowerShell mới sau khi cài. Kiểm tra `ffmpeg -version`, `ffprobe -version`.
- Microsoft ODBC Driver 18 for SQL Server x64, tải từ trang hướng dẫn Microsoft: https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server. Kiểm tra bằng `Get-OdbcDriver`.

## Cài và chạy

Chạy tại thư mục repo này:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
```

Sửa `.env`: đặt DB_PASSWORD đủ mạnh (chữ hoa, thường, số, ký tự đặc biệt). Không commit file này. Cùng mật khẩu được Compose và backend sử dụng. Nếu FFmpeg chưa có PATH, đặt FFMPEG_PATH và FFPROBE_PATH thành đường dẫn tuyệt đối tới hai file exe. Dùng cùng hostname `localhost` cho frontend/backend để session cookie hoạt động nhất quán.

```powershell
docker compose up -d --wait
.\.venv\Scripts\python.exe -X utf8 -m scripts.init_db
.\.venv\Scripts\python.exe -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Mở PowerShell thứ hai tại repo và chạy worker:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.worker
```

API docs: http://localhost:8000/docs. Health: http://localhost:8000/api/health. Frontend chạy riêng trên http://localhost:5173. Upload cần đăng nhập và worker; khách được xem/tìm video ready.

### Xem thử trước khi upload

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.prepare_demo --seconds 65
```

Mở `/demo` trên frontend. Lệnh tạo nguồn testsrc2 và âm thanh sine, không dùng nội dung có bản quyền. ID mặc định là demo; nếu tạo thêm mẫu dùng `--id short --seconds 2.3 --size 640x360 --no-audio` hoặc `--id portrait --size 720x1280`. Không ghi đè bộ demo cũ: muốn tạo lại hãy dùng ID mới hoặc đổi tên thư mục đầu ra cũ. Manifest mẫu nằm ở `/api/demo/{id}/manifest`.

### ODBC và lỗi thường gặp

- IM002: driver chưa cài hoặc DB_DRIVER sai tên. Mặc định dùng ODBC Driver 18. Có thể đặt tên driver 17 nếu máy đã cài phiên bản đó.
- Máy hiện tại dùng được driver `SQL Server` có sẵn khi chạy bằng tài khoản Windows chính; cấu hình này chỉ là phương án local cũ, ưu tiên cài Driver 18. Driver cũ dùng `use_setinputsizes=False` để tránh lỗi HY104.
- Trong môi trường sandbox, SEC_E_NO_CREDENTIALS/SSL Security error có thể do quyền Windows; chạy terminal bình thường bằng tài khoản máy để kiểm tra lại.
- 503/không kết nối database: kiểm tra `docker compose ps`, DB_PASSWORD và cổng 1433 có đang được ứng dụng khác dùng không.
- Video failed: xem log worker và processing_jobs.error; xác nhận ffmpeg/ffprobe chạy được.
- Tiếng Việt lỗi trên terminal: dùng `python -X utf8` như các lệnh ở trên.

## Test

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --basetemp=storage/test-temp
# Cần SQL Server và video mẫu đã tạo; test sẽ encode lại video nên mất thêm thời gian.
$env:BVG_RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --basetemp=storage/test-temp-db
```

Test database tạo tài khoản/video riêng rồi xóa record test. Các file test trong storage được giữ lại để debug. Không chạy integration test trong lúc worker khác đang claim cùng queue demo.

## Tổ chức và tài liệu

- `app/main.py`: cấu hình app và router.
- `auth.py`, `videos.py`, `progress.py`: API và logic theo tính năng.
- `database.py`, `models.py`, `schemas.py`: kết nối, model, validation.
- `media.py`, `media_api.py`: điều phối FFmpeg, manifest và truy cập asset.
- `worker.py`: claim, heartbeat và phục hồi job.
- `scripts/init_db.py`: khởi tạo database/schema, không xóa dữ liệu có sẵn.
- [Giải thích thuật toán và giới hạn](docs/STREAMING.md).
- [Kết quả kiểm chứng](docs/VERIFICATION.md).

`storage/`, `.env`, `.venv/` và `.tools/` bị Git ignore. Source/segment không push lên GitHub. `docker compose stop` dừng database, volume vẫn lưu dữ liệu.
