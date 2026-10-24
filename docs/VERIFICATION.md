# Kết quả kiểm chứng — 24/10/2026

## Môi trường thực tế

- Windows, Python 3.12.14, Node 20.20.2.
- SQL Server 2022 CU20 Docker: container healthy, volume dữ liệu hoạt động.
- FFmpeg Windows local (muxer DASH, libx264/AAC). Bản thử đầu sử dụng FFmpeg 4.1; bản FFmpeg mới hơn đang tải vào `.tools`, không đưa binary lên Git.
- Kết nối SQLAlchemy + pyodbc được kiểm tra với driver `SQL Server` có sẵn và use_setinputsizes=False, chạy bằng tài khoản Windows chính. Máy chưa cài thành công ODBC Driver 18; README hướng dẫn cài driver hiện đại. Không kết luận Driver 18 đã được kiểm tra.
- Player đã chạy trong Chromium của công cụ trình duyệt và Chrome headless cài trên máy.

## Đã chạy thành công

| Kiểm tra | Kết quả |
|---|---|
| npm test | 6 test pass: EWMA, tăng chậm, giảm khẩn cấp, cooldown, hysteresis, seek theo timeline và buffer có khoảng trống |
| npm run build | TypeScript strict và Vite production build pass |
| npm audit | 0 advisory tại thời điểm kiểm tra |
| Ruff | Pass với cấu hình trong pyproject.toml |
| pytest có SQL Server | 5 test pass; có một warning deprecation từ dependency TestClient |
| npm run test:e2e | 3 test pass trên Chrome: phát/đổi chất lượng/seek liên tiếp; retry503/ended; video ngắn không audio |
| Video 65 giây, 1920x1080, audio | 480p/720p/1080p, phát nhiều segment thật, buffer khoảng 20–24 giây |
| Video 2,3 giây, 640x360, không audio | Chỉ 360p, không upscale, phát tới ended |
| Video dọc 720x1280, 9,1 giây, audio | 480p và 720p, phát được; nhãn theo cạnh ngắn |
| Seek vùng chưa tải | Tua đến 46 giây, buffer mới bắt đầu gần đích |
| Seek liên tiếp | Tua 29 → 53 và quay về 2 giây, không lỗi giải mã |
| Chất lượng thủ công | Đổi 1080p khi pause, phát tiếp bình thường |
| Lỗi segment tạm thời | Giả lập503 ở lượt đầu, lượt thứ hai thành công |
| Mạng nhanh → chậm → nhanh | CDP throttle khoảng1,15Mbps/80ms: Auto hạ từ tải1080p về480p khi buffer dưới4 giây; hồi mạng buffer tăng lại, chờ tăng chậm |
| Auth/upload/worker từ UI | Đăng ký tài khoản demo, upload video, chờ ready, mở player và phát |
| Khôi phục tiến độ từ UI | Reload về3,008982 giây, sau đó6,511231 giây; Xem từ đầu về0 |
| Tiến độ SQL Server | Request sai thứ tự bị409; tua lùi lưu được; token tab cũ bị từ chối |
| Worker phục hồi | Lease hết hạn được claim với token mới và xử lý thành ready |
| Mobile | Viewport390px có scrollWidth390px, không tràn ngang ở trang chủ |

Các kết quả số cụ thể là quan sát của một lần chạy, không phải cam kết hiệu năng trên mọi máy. Đã lưu một tài khoản/video demo local để mở thử; media và mật khẩu cấu hình không nằm trên Git.

## Chưa kiểm chứng đầy đủ / giới hạn

- Chưa chạy toàn bộ ma trận trên Edge và Firefox; mục tiêu hiện tại Chrome/Edge desktop.
- Chưa kiểm tra memory/heap dài hàng giờ hoặc ép QuotaExceededError bằng bộ media lớn. Có cleanup và nhánh quota trong code nhưng chưa chứng minh không rò rỉ bằng profiler.
- Chưa stress nhiều worker, nhiều upload lớn và nhiều user đồng thời; logic claim được kiểm tra tình huống phục hồi một job.
- Chưa test toàn bộ định dạng/codec đầu vào; nguồn DRM hoặc FFmpeg không giải mã được bị từ chối/thất bại.
- Sample EWMA trên loopback có thể rất cao. Demo ABR cần throttling và video đủ dài; buffer cũ trì hoãn thay đổi chất lượng đang phát.
- Chưa tự dọn nguồn/generation failed; lưu lại để debug local.
- Chưa kiểm tra cài mới ODBC Driver18 trên Windows sạch. Không commit các đường dẫn `.tools` riêng của máy vào cấu hình mẫu.

Xem README của hai repo để tái lập. Tạo thêm demo theo ID bằng `scripts.prepare_demo`; đường dẫn frontend `/demo/{id}` cho phép mở từng mẫu.
