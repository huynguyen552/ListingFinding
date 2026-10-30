# Giảm bộ nhớ của bộ thu thập

## Thay đổi

- Trình duyệt chỉ khởi động khi phải đọc Maps. Nếu đợt đã tìm xong và các hồ sơ cần xử lý có cache chi tiết, việc đối chiếu khu vực không mở Chromium.
- Khi Google mở thẳng một hồ sơ sau truy vấn, lưu ngay tên, địa chỉ, SĐT, website và loại quán đã đọc. Không điều hướng lại cùng hồ sơ lần thứ hai.
- Sau bước tìm kiếm và sau mỗi lần đọc hồ sơ, đóng Chromium và Playwright driver. Không giữ trình duyệt trong lúc lưu PostgreSQL hoặc đọc thêm website bằng HTTP.
- Mỗi hồ sơ chưa có cache được đọc bằng một phiên trình duyệt mới; không giữ trang Maps trước đó trong bộ nhớ. Tắt back/forward cache trong các phiên đọc này.
- Vẫn đọc từng hồ sơ tuần tự, giữ kiểm tra khu vực, nguồn, tạm dừng/hủy và phục hồi tác vụ.

Việc khởi động lại trình duyệt có thể tăng chi phí khởi động khi đọc nhiều hồ sơ. Không dùng các chế độ Chromium không an toàn hoặc giả lập kết quả để giảm số đo RAM.

## Đo trước và sau trên máy local

Môi trường: cùng máy, cùng image nền và database PostgreSQL test riêng, cùng giới hạn app 1 CPU và 1 GiB RAM. Bộ lấy mẫu đọc working set của cgroup mỗi 100 ms (memory.current trừ inactive_file), tương tự cách báo bộ nhớ làm việc của container. Số đo tính toàn bộ container app; **không cộng PostgreSQL hoặc Docker daemon**.

| Lượt thử | Trước tối ưu | Sau tối ưu |
|---|---:|---:|
| Tìm `Mộc quán Seafood`, Đà Nẵng, mục tiêu 1, không đọc thêm website | 615.5 MiB cao nhất quan sát | 451.6 MiB cao nhất quan sát |
| Kết quả | Lưu 1 địa điểm | Lưu 1 địa điểm |
| Thời gian lượt thử | 16.8 giây | 12.7 giây |

Trong lượt này, RAM cao nhất quan sát giảm **26.6%**. Đã so trực tiếp dữ liệu nguồn trước/sau: tên, địa chỉ, SĐT, website và loại quán đều có giá trị và khớp nhau. Không dùng các trường đã có sẵn trong hồ sơ gộp để che việc nguồn mới thiếu thông tin.

Thử thêm bản mới với truy vấn rộng `quán ăn`, Đà Nẵng, mục tiêu 2: tìm 6 ứng viên, lưu 2 địa điểm, dừng khi đạt mục tiêu; mức cao nhất quan sát **375.0 MiB**, thời gian 16.4 giây. Đây chỉ là lượt xác nhận bản mới ở đường đi nhiều kết quả, không có số đo đối chứng trước tối ưu cho truy vấn rộng này.

Các phép đo trên là từng lượt nhỏ trên local, không phải bảo đảm mọi truy vấn, mọi địa điểm hoặc mọi VPS đều dùng cùng lượng RAM. Chromium và nội dung Google vẫn quyết định phần lớn mức đỉnh; PostgreSQL và các dịch vụ khác trên VPS cần được tính riêng.

## Kiểm tra

- 115 kiểm thử backend qua trên SQLite.
- Image bản mới kiểm tra trên PostgreSQL riêng: 114 qua, 1 ca kiểm tra đường dẫn source runtime bỏ qua trong image; startup runtime được kiểm tra riêng bằng container thật.
- Thêm hồi quy cho cache không khởi động trình duyệt, dữ liệu hồ sơ trực tiếp được giữ đủ, đóng browser/driver sau từng hồ sơ và khi lỗi, đóng Chromium trước khi đọc website.
- Ruff check/format và Docker build qua. Hai lượt thu thập thực của bản mới đều đạt mục tiêu.

Các tối ưu này được kiểm tra ở local. Giữ nguyên quyết định dừng cào trên Render Free; không tự chạy lại hoặc nâng gói Render trong bước tối ưu này.
