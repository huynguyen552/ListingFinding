# Triển khai toàn bộ LeadFinder trên Render

Repository: https://github.com/niconguyen2209/LeadFinder

## Kiến trúc

`render.yaml` tạo một Web Service Docker và một Render PostgreSQL, cùng vùng Singapore. Trong Web Service có giao diện đã build, FastAPI và một tiến trình thu thập duy nhất lấy việc từ PostgreSQL (`QUEUE_MODE=database`). Không chạy Redis/Celery/beat riêng ở bản Render để giảm RAM. Không cần VPS hay máy công ty chạy bộ cào. Chỉ chạy một instance web.

Hồ sơ, nguồn, phiên đăng nhập, hàng đợi, đợt thu thập và checkpoint lưu trong PostgreSQL. Khi Render khởi động lại, các đợt queued được điều phối lại. Đợt đang chạy bị gián đoạn sẽ được đối soát sau khoảng bốn phút, chuyển về tạm dừng để bấm Tiếp tục. Không dùng SQLite trên ổ đĩa tạm của Render. Compose local vẫn giữ Celery/Redis như trước.

## Tạo dịch vụ

1. Vào Render → New → Blueprint, chọn repository này và nhánh `main`.
2. Giữ đường dẫn `render.yaml`. Blueprint chọn Free cho web và PostgreSQL, không tự chọn gói trả phí.
3. Nhập `INITIAL_ADMIN_USERNAME`: 3–100 ký tự chữ không dấu, số, dấu chấm, gạch dưới/gạch ngang.
4. Nhập `INITIAL_ADMIN_PASSWORD`: 12–128 ký tự, dùng mật khẩu riêng. Hai giá trị chỉ nhập trong Render, không đưa vào GitHub.
5. Deploy. Lần đầu cần thời gian để tải Chromium và build giao diện. Startup tự chạy migrations, tạo quản trị viên trước khi mở cổng HTTP, rồi chạy các tiến trình.
6. Mở URL `.onrender.com` được Render cấp và đăng nhập bằng tài khoản trên. Nếu database đã có người dùng, việc deploy lại không đổi mật khẩu hoặc tạo lại tài khoản.

Database cloud mới ban đầu trống; lịch sử và hồ sơ local không nằm trong repository. Không đưa `.env`, `.doc`, bản sao lưu, database hoặc dữ liệu trình duyệt lên GitHub.

Render tự cung cấp `RENDER_EXTERNAL_HOSTNAME`, `RENDER_EXTERNAL_URL` và `PORT`; app dùng đúng hostname/origin/port này. Cookie phiên có Secure/HttpOnly. Nếu dùng tên miền riêng, bổ sung `ALLOWED_HOSTS=tenmien.example` và `ALLOWED_ORIGINS=https://tenmien.example` trong Render.

## UptimeRobot hoặc cron-job.org

Sau khi web hoạt động, cấu hình monitor HTTP(s) của UptimeRobot gọi:

```text
https://TEN-DICH-VU.onrender.com/api/v1/health/live
```

Chọn chu kỳ 5 phút ở UptimeRobot Free, hoặc đặt 10 phút ở cron-job.org. Kết quả bình thường là HTTP 200 với `status: ok`. Không gửi cookie, mật khẩu hoặc thông tin quản trị vào monitor. Đường dẫn Render health check của Blueprint dùng `/api/v1/health/ready` để kiểm tra thêm database.

Request định kỳ giúp tránh ngủ vì thiếu truy cập; không tăng RAM/CPU, không ngăn mọi lần restart, không bảo đảm tác vụ cào luôn hoàn tất. Free web hiện có 512 MB RAM và 0.1 CPU; cần thử lượt nhỏ trước và theo dõi bộ nhớ. Nếu OOM/timeout khi mở Maps, tăng compute plan của web thay vì tăng tần suất ping.

## Lưu dữ liệu và giới hạn Free

Render PostgreSQL Free hết hạn sau 30 ngày theo tài liệu hiện tại. Xuất dữ liệu/sao lưu hoặc nâng gói trước khi hết hạn; ping không gia hạn PostgreSQL. Free web còn chịu hạn mức giờ hoạt động và băng thông. Không đặt mật khẩu hay sao lưu trong filesystem tạm của web.

Tài liệu nguồn: [Render Free](https://render.com/docs/free), [Docker](https://render.com/docs/docker), [Blueprint](https://render.com/docs/blueprint-spec), [UptimeRobot Free](https://help.uptimerobot.com/en/articles/11604710-who-should-use-uptimerobot-s-free-plan).

## Các file triển khai

- `Dockerfile`: build React, đóng gói Python/Chromium và runtime tiết kiệm bộ nhớ.
- `deploy/render_runtime.py`: migrations, bootstrap quản trị viên, giám sát và dừng các tiến trình.
- `render.yaml`: định nghĩa Web Service và PostgreSQL, tham chiếu DB nội bộ.
- `.dockerignore`, `.gitignore`: loại secrets, tài liệu riêng, môi trường local, bản sao lưu và build artifacts.

Docker Compose local vẫn dùng cấu hình riêng ở `compose.yaml`.

## Kiểm tra bản triển khai ngày 30/10/2026

- 108 kiểm thử qua trên SQLite. Docker image gộp chạy trên PostgreSQL test riêng: 107 qua, 1 ca chỉ kiểm tra đường dẫn source của runtime được bỏ qua trong image; runtime thực được kiểm tra bằng khởi động container.
- Dockerfile gốc build thành công; `render.yaml` hợp lệ theo JSON Schema chính thức của Render.
- Container thử giới hạn 512 MiB RAM và 0.1 CPU khởi động, chạy migration, bootstrap quản trị viên, trả readiness và đăng nhập thành công.
- Lượt thực tế tìm `Mộc quán Seafood`, Đà Nẵng, mục tiêu 1, không đọc thêm website: completed, lưu 1 địa điểm thật. Dữ liệu thử ở DB riêng, không đưa vào database local chính hoặc repo.
- Bộ nhớ quan sát khi chờ khoảng 256 MiB; một lần quan sát khi đang đọc Maps khoảng 509 MiB, container không bị OOM trong lượt này. Đây không phải bảo đảm mọi lượt đều vừa 512 MiB; nên theo dõi và nâng compute nếu thường xuyên hết bộ nhớ.

Bản gộp Redis/Celery đầu tiên khởi động được nhưng lượt cào thực tế trên Render vượt 512 MB và bị restart. Vì vậy bản Render được đổi sang hàng đợi PostgreSQL và một tiến trình collector nhẹ, đồng thời chạy bootstrap ở tiến trình tạm để không giữ thư viện nặng trong supervisor. Các số đo 256/509 MiB phía trên thuộc bản trước khi tối ưu, không dùng để khẳng định mức dùng của bản mới.

## Kết quả cuối trên Render Free

- Website: https://leadfinder-7bgc.onrender.com — đã deploy thành công, đăng nhập và readiness PostgreSQL hoạt động.
- UptimeRobot Free đã có monitor HTTP(s) gọi `/api/v1/health/live` mỗi 5 phút, đã quan sát trạng thái Up.
- Bản collector PostgreSQL mới giảm RAM chờ trong môi trường thử xuống khoảng 123 MiB; 110 kiểm thử SQLite qua, 109 kiểm thử PostgreSQL qua và 1 ca kiểm tra đường dẫn source được bỏ qua trong image.
- Dù vậy, **lượt đọc chi tiết Google Maps thực tế trên Render vẫn vượt 512 MB**, Render ghi sự kiện OOM và tự khởi động lại. Không coi phép thử thành công ở máy local là bằng chứng bộ cào chạy được ổn định trên Render Free.
- Người dùng chọn giữ Free và dừng cào. Lượt cào thử cloud đã được hủy; không nâng compute hoặc phát sinh phí. Website, database và monitor tiếp tục tồn tại. Chưa khẳng định chức năng cào ổn định với gói Free.
- Trang Compute lúc kiểm tra niêm yết 1 CPU / 2 GB RAM ở mức 25 USD/tháng riêng phần web; đây là lựa chọn trả phí chưa được áp dụng. PostgreSQL Free vẫn có giới hạn hết hạn 30 ngày như trên.
