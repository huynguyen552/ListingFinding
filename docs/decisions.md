# Quyết định triển khai

## Cập nhật 0.2 — Ưu tiên tool thu thập dữ liệu

Theo yêu cầu người dùng, màn hình chính chuyển thành form thu thập, không phải dashboard quản lý khách hàng. Connector Google Maps đọc trang công khai bằng Playwright, không cần API key; nhận cả danh sách và trường hợp Google mở trực tiếp hồ sơ nhưng URL vẫn là `/maps/search/`. Website được đọc bằng HTTP có ghim IP/DNS và kiểm tra robots. Không dùng stealth, proxy luân phiên hoặc vượt CAPTCHA. Cần tuân thủ điều khoản nguồn theo phạm vi sử dụng; browser connector không tự cấp quyền tái sử dụng dữ liệu.

Các ADR bên dưới mô tả nền tảng 0.1, một số giới hạn đã được mở rộng: nay có `crawl_jobs`, `crawl_entries`, `external_places`, khóa điều phối một đợt, worker Celery và scheduler. Công việc lưu trước khi gửi broker; scheduler phát lại job `queued`, nhận lại task không chạy trùng nếu job đã `running`. Job đang chạy bị ngắt được chuyển về `paused` sau heartbeat quá 4 phút; kết quả đã lưu giữ nguyên. Mỗi lần chạy có token để ngăn worker cũ ghi kết quả sau khi đã thu hồi quyền chạy. Đây chưa phải tổng quát hóa outbox/lease cho mọi loại tác vụ của đặc tả.

Kết quả từ Google có thể nằm ngoài khu vực dù tên chứa tên địa phương; chỉ nhận khi địa chỉ khớp chuỗi khu vực. Khớp bảo thủ theo từng phần ngăn bởi dấu phẩy; chưa có geocoding/ranh giới hành chính. Loại quán được đọc từ nút category của hồ sơ, không gán từ khóa tìm kiếm thành loại quán.

Xuất theo `crawl_job_id` để không trộn dữ liệu đợt khác. Form có thể xuất MST ứng viên với trạng thái xác minh rõ ràng; mặc định API xuất cũ vẫn bỏ MST chưa xác nhận. Các kênh liên hệ bổ sung có trong quan sát và sheet nguồn, chưa tách thành mô hình contact points.

## ADR-001 — Bắt đầu bằng dữ liệu người dùng cung cấp

Chưa có nhà cung cấp tìm kiếm được lựa chọn. Luồng thật ban đầu dùng CSV người dùng có quyền sử dụng, không phụ thuộc khóa trả phí và không tuyên bố đã có Google scraper. Nguồn CSV và chỉnh sửa thủ công được migration tạo sẵn. Bổ sung connector chỉ sau khi chốt quyền dùng và hạn mức.

## ADR-002 — Giao diện local qua cùng origin

Nginx phục vụ frontend build và proxy `/api` về FastAPI. Phiên đăng nhập lưu DB bằng hash token, trình duyệt nhận cookie HttpOnly và CSRF token. Không lưu token phiên trong localStorage. Chỉ bind loopback. Bản local chưa có HTTPS và không được cấu hình để đưa thẳng lên Internet.

## ADR-003 — Phạm vi dữ liệu 0.1

Bắt đầu với địa điểm, quan sát theo trường, provenance của giá trị hiện tại, import batch và audit. Một địa điểm hiện có một chuỗi liên hệ cho mỗi loại và trạng thái tiếp cận ngay trên địa điểm. Đây là mô hình trung gian, cần migration tách thương hiệu/pháp nhân/contact points/lead profiles trước giai đoạn mở rộng. Không lưu tên thương mại như bằng chứng tự động của chủ thể thuế.

## ADR-004 — Không ghi đè khi nhập lại

Khóa nhận diện tên+địa chỉ+tỉnh/thành chuẩn hóa (giữ dấu tiếng Việt), hoặc URL website khi thiếu cặp tên/địa chỉ. Điện thoại/MST không được dùng làm khóa chi nhánh. Import lưu quan sát mới và báo số giá trị khác nhưng giữ giá trị hiển thị. Một batch confirm có khóa hàng và kết quả lưu lại, gọi lặp không nhập lại. Các batch cạnh tranh trùng khóa trả 409 để thử lại, không tạo bản ghi trùng.

Giới hạn: chưa có xác suất đối chiếu/queue duyệt trùng, URL chung không đủ phân biệt chi nhánh chưa có địa chỉ. Ngưỡng nhận diện sẽ cần siết sau pilot, không gán đây là xác minh thực thể tuyệt đối.

## ADR-005 — Xuất đồng bộ có giới hạn ở 0.1

Xuất tối đa 10.000 dòng, xác thực, kiểm tra quyền nguồn theo trường, loại mặc định do_not_contact và MST chưa xác nhận, vô hiệu hóa công thức trong ô không tin cậy. XLSX có nguồn theo trường (có thể chứa MST ứng viên và được ghi rõ). Khi có worker bền vững, chuyển thành export job có hạn tải; CSV nguồn riêng và chọn cột để giai đoạn sau.

## ADR-006 — Sao lưu nhị phân

Script Python truyền trực tiếp stdout của pg_dump vào file nhị phân, tránh chuyển mã qua PowerShell. Phục hồi thử dùng DB tạm trên cùng PostgreSQL và xóa sau kiểm tra. Tự động hóa lịch/retention và phục hồi thay thế DB thật chưa triển khai.
