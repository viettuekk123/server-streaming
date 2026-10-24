# Giải thích đồ án

## Luồng dữ liệu

Upload được ghi theo khối 1 MiB. ffprobe xác nhận file có video và duration hợp lệ. API tạo video/job trong một transaction. Worker gọi FFmpeg để chuẩn bị H.264/AAC và dùng DASH muxer tạo init/media segment. Python đọc MPD XML (không đọc container MP4) và tạo manifest JSON riêng. Trình duyệt chỉ đọc JSON và tải từng file bằng Axios; không dùng thư viện phát DASH.

Mỗi rendition có track video riêng, audio dùng chung. Các video rendition được chuẩn hóa 30 fps, H.264 High Level 4.1, yuv420p, GOP và keyframe mốc 4 giây. Cạnh ngắn quyết định nhãn: video dọc 720x1280 là 720p. Nguồn dưới 480p giữ kích thước gần nguồn và làm tròn chẵn. Không upscale. Audio AAC 48 kHz stereo có timeline riêng; một AAC frame không bắt buộc khớp chính xác mốc video.

Manifest lấy codec/timescale/timeline từ MPD và byte size từ file thật. Bitrate ABR của rendition gồm video và audio. Thời lượng segment cuối có thể ngắn hơn. Các mốc video giữa rendition được đối chiếu trước khi ghi manifest. Đây là bước chuẩn bị dữ liệu, không phải phần thuật toán chính của đồ án.

## Buffer và seek

SourceQueue nối các thao tác bằng Promise và đợi updateend. Engine không append/remove cùng lúc trên một SourceBuffer. Engine tải thêm mỗi khi buffer trước dưới 20 giây, có thể vượt nhẹ do tải nguyên segment. Chỉ đo vùng buffered liên tục chứa currentTime. Sau 12 giây dữ liệu cũ được dọn. Nếu đầy quota, thử dọn mạnh hơn một lần rồi báo lỗi có thể khôi phục bằng tải lại.

Seek đang có buffer giữ dữ liệu. Seek chưa có buffer tăng generation, hủy request, chờ append cũ kết thúc, xóa buffer và tìm segment theo start/duration trong manifest. Audio tìm riêng theo timeline. Response thuộc generation cũ không được append sau khi kiểm tra. Nội dung ở đoạn trước vị trí tua không cần tải lại. Seek gần cuối được giới hạn trong duration.

## Chuyển chất lượng

Video rendition dùng codec tương thích và chung ranh giới keyframe. Khi rendition thay đổi, engine append init mới rồi media segment tiếp theo, dùng cùng SourceBuffer và MediaSource. Buffer cũ vẫn còn; vì thế chất lượng đang tải có thể khác chất lượng đang phát. Engine ghi các khoảng timeline đã append để UI biết rendition thực sự tại currentTime. Chọn thủ công sẽ bỏ qua ABR cho tới khi bật Auto.

## Thuật toán ABR

Mẫu throughput = số byte tải thành công * 8 / số giây tải. Chỉ media segment video hoàn tất mới cập nhật estimator; init, request hủy và cache không được dùng như mẫu mạng. Request demo có query duy nhất và API trả Cache-Control: no-store. Response phải có no-store và Age bằng 0 mới được coi là mẫu hợp lệ. Không dùng Network Information API.

EWMA có half-life 3 giây: alpha = 1 - 2^(-download_seconds / 3). Estimate mới = alpha * throughput + (1-alpha) * estimate cũ. Mẫu đầu tiên là giá trị khởi tạo. Mẫu tải lâu mang trọng số lớn hơn mẫu tải nhanh. Mạng loopback thường cho số đo rất cao; cần throttling để thấy ABR rõ.

Ngân sách an toàn = EWMA * 0,75. ABR tìm rendition có tổng bitrate nằm trong ngân sách. Buffer dưới 4 giây ưu tiên giảm ngay, không đợi cooldown. Băng thông không đủ có thể giảm nhiều mức. Tăng cần buffer trên 15 giây, ngân sách vượt bitrate mức kế tiếp ít nhất 15%, ba lần đánh giá trên các chu kỳ tải tốt và tối thiểu 8 giây từ lần chuyển trước. Mỗi lần chỉ tăng một mức. Khi mạng yếu hơn mức thấp nhất, giữ mức thấp nhất và cho trình duyệt buffering; request retry có giới hạn và backoff, hết retry hiện lỗi.

ABR được gọi trước lượt tải tiếp theo. Khi đang phát Auto ở mức trên thấp nhất, request video đã chạy hơn một giây và buffer dưới 4 giây, engine hủy request, giảm mức và tải lại đúng segment đó. Request bị hủy không vào EWMA. Nhánh khẩn cấp giữ buffer cũ, không seek và không tăng chỉ số segment. Ở chất lượng thấp nhất hoặc chế độ thủ công, request dùng timeout/retry giới hạn thông thường. Có thể thay strategy qua interface AbrStrategy.

## Tiến độ xem

SQL Server lưu một record mỗi user/video. POST progress/session tạo token ghi mới và sequence về 0. Tab mở phiên sau thay quyền ghi của tab trước. PUT chỉ cập nhật khi token khớp và sequence lớn hơn record đang lưu; điều kiện nằm trong câu UPDATE nên request đến trễ không ghi đè. Vị trí thấp hơn vẫn hợp lệ khi tua lùi, không dùng MAX(position).

Frontend lưu khoảng mỗi 5 giây trong lúc phát, khi pause/seek/ended và khi trang ẩn. Khi đổi trang có request cuối best-effort bằng Axios; không dựa vào request lúc đóng tab để bảo đảm dữ liệu. Không dùng localStorage làm nơi lưu tiến độ. Completed từ 95% trở lên sẽ mở lại ở 0. Player không ép autoplay; vị trí được chuẩn bị để người xem nhấn Play.

## Worker và phạm vi demo

Job claim bằng UPDLOCK/READPAST/ROWLOCK trong transaction. Mỗi worker chạy tối đa một job; nhiều tiến trình có thể claim job khác nhau. Heartbeat gia hạn lease. Job hết lease được claim lại, giới hạn ba lần. Mỗi lần xử lý dùng generation riêng. Token claim ngăn worker cũ công khai kết quả sau khi bị thay thế. API chỉ công khai generation ready.

Các generation lỗi và nguồn vẫn lưu để debug, chưa tự dọn theo lịch. Script init_db tạo schema mới hoặc bổ sung bảng chưa có; chưa hỗ trợ thay đổi cột như migration production. Không dùng kiến trúc microservice hoặc queue bên ngoài. Router dùng ORM trực tiếp ở thao tác CRUD đơn giản để sinh viên dễ theo dõi; logic media, worker và progress tách theo trách nhiệm.
