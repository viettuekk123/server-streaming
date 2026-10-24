# BVG Streaming — server

Đồ án video-on-demand: FastAPI + SQL Server, FFmpeg chuẩn bị media, player MSE/ABR nằm ở repo `web-streaming`. Code ưu tiên dễ đọc và giải thích cho đồ án sinh viên. Không có parser hay segmenter container tự viết.

Repo giao diện: [web-streaming](https://github.com/viettuekk123/web-streaming). Mục tiêu đồ án là thuật toán streaming và ABR: FFmpeg chuyển mã, căn keyframe/timeline, tạo initialization/media segment với thời lượng mục tiêu 4 giây, trích thumbnail và metadata. Python điều phối job/file, xây manifest từ đầu ra thực tế và cung cấp API.

## Yêu cầu Windows

- Python 3.12 x64, bật Add to PATH khi cài.
- Docker Desktop đang chạy Linux containers, đủ RAM cho SQL Server (nên cấp ít nhất 4 GB).
- FFmpeg và ffprobe trong PATH, build có libx264 và DASH muxer. Có thể cài `winget install Gyan.FFmpeg`; mở PowerShell mới sau khi cài. Kiểm tra `ffmpeg -version`, `ffprobe -version`.
- Microsoft ODBC Driver 18 for SQL Server x64, tải từ trang hướng dẫn Microsoft: https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server. Kiểm tra bằng `Get-OdbcDriver`.

## Cài và chạy

Mở PowerShell tại thư mục `server-streaming`. Chỉ thực hiện bước tạo môi trường khi cài lần đầu:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Sửa `.env`: đặt DB_PASSWORD đủ mạnh (chữ hoa, thường, số, ký tự đặc biệt). Không commit file này. Cùng mật khẩu được Compose và backend sử dụng. Nếu FFmpeg chưa có PATH, đặt FFMPEG_PATH và FFPROBE_PATH thành đường dẫn tuyệt đối tới hai file exe. Dùng cùng hostname `localhost` cho frontend/backend để session cookie hoạt động nhất quán.

Các cấu hình chính:

| Biến | Mặc định / ý nghĩa |
|---|---|
| `APP_ORIGIN` | `http://localhost:5173`, origin frontend được phép gửi request kèm cookie |
| `DB_HOST`, `DB_NAME`, `DB_USER` | `localhost,1433`, `bvg_streaming`, `sa` cho demo local |
| `DB_PASSWORD` | Tự đặt trong `.env`, dùng cùng mật khẩu SQL Server |
| `DB_DRIVER` | `ODBC Driver 18 for SQL Server`, phải đúng tên driver đã cài |
| `FFMPEG_PATH`, `FFPROBE_PATH` | `ffmpeg`, `ffprobe` trong PATH hoặc đường dẫn tuyệt đối |
| `STORAGE_DIR` | `storage`, đường dẫn tương đối tính từ repo server |
| `MAX_UPLOAD_MB` | `2048`, giới hạn dung lượng upload |
| `SEGMENT_SECONDS` | `4`, thời lượng segment mục tiêu |

Giữ `COOKIE_SECURE=false` cho HTTP local. Sau khi sửa `.env`, khởi động lại API và worker. Nếu SQL Server đã có dữ liệu trong volume, đổi `DB_PASSWORD` trong file không tự đổi mật khẩu tài khoản đã lưu trong database.

Terminal thứ nhất: khởi động SQL Server, tạo schema rồi chạy API. Giữ terminal này mở:

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

Terminal thứ ba: mở thư mục `web-streaming` và làm theo README frontend (`npm ci`, cấu hình `.env`, `npm run dev`). Tổng cộng cần giữ ba tiến trình API, worker và Vite; SQL Server chạy nền qua Docker.

Những lần khởi động sau: chạy lại `docker compose up -d --wait`, API, worker và Vite. Không cần tạo lại môi trường, sao chép `.env` hoặc chuẩn bị lại media. `scripts.init_db` có thể chạy lại để tạo database/bảng còn thiếu; script không tự sửa cấu trúc bảng đã tồn tại.

### Xem thử trước khi upload

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.prepare_demo --seconds 65
# Mẫu ngắn dùng cho E2E, không audio và không upscale.
.\.venv\Scripts\python.exe -X utf8 -m scripts.prepare_demo --id short --seconds 2.3 --size 640x360 --no-audio
# Tùy chọn: mẫu dọc để kiểm tra bố cục và audio.
.\.venv\Scripts\python.exe -X utf8 -m scripts.prepare_demo --id portrait --seconds 9.1 --size 720x1280
```

Mở `/demo` trên frontend. Lệnh tạo nguồn testsrc2 và âm thanh sine, không dùng nội dung có bản quyền. ID mặc định là `demo`; `--no-audio` bỏ âm thanh. Không ghi đè bộ demo cũ: muốn tạo lại hãy dùng ID mới hoặc đổi tên thư mục đầu ra cũ. Manifest mẫu nằm ở `/api/demo/{id}/manifest`.

Các đường dẫn frontend tương ứng là `/demo`, `/demo/short` và `/demo/portrait`. Chỉ chạy lệnh cho bộ mẫu chưa có; tạo media có thể mất thời gian tùy máy. Video mẫu không tự xuất hiện trong thư viện SQL; để thử upload/lưu tiến độ, đăng ký tài khoản trên web, upload video và đợi worker chuyển sang `ready`.

### Thử luồng đầy đủ

1. Đăng ký/đăng nhập ở web, upload video kèm tiêu đề/mô tả.
2. Mở **Video của tôi**, đợi `uploaded` → `processing` → `ready`, sau đó mở video.
3. Phát, tua vào vùng chưa tải, đổi chất lượng và bật **ABR Debug** để quan sát buffer/EWMA.
4. Xem vài giây rồi pause; tải lại trang để kiểm tra khôi phục tiến độ từ SQL Server. Trang `/demo` không lưu tiến độ tài khoản.
5. Muốn quan sát ABR, dùng DevTools → Network → Disable cache và đổi tốc độ mạng theo hướng dẫn README frontend.

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

## Dừng dự án

Nhấn `Ctrl+C` tại các terminal API, worker và Vite; tại repo server chạy `docker compose stop`. Để xem trạng thái database dùng `docker compose ps`, xem log bằng `docker compose logs --tail 100 sqlserver`. Giữ volume và thư mục `storage/` để lần chạy sau còn tài khoản, tiến độ và media.
