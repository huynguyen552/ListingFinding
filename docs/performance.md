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

## Xác nhận bản thực sự chạy trên Render

Khi người dùng báo Render vẫn bị ngắt, đã kiểm tra và xác nhận dịch vụ vẫn chạy commit `8b241e7`; commit tối ưu `e46cb94` bị bỏ qua auto-deploy vì có nhãn `[skip render]` theo quyết định dừng cào ở bước trước.

Ngày 30/10/2026, sau yêu cầu kiểm tra tiếp, đã manual deploy `e46cb94` trên cùng gói Free, giữ nguyên PostgreSQL và tài khoản. Tiếp tục đợt `quán ăn / tân phú` từ 3/5: lưu thêm 2 hồ sơ, hoàn thành **5/5**, giữ nguyên ba kết quả cũ; không quan sát thấy ngắt trong lượt tiếp tục này. Readiness trả HTTP 200 sau khi chạy.

Đây là xác nhận một đợt tiếp tục nhỏ đã hoàn tất trên Render Free, không phải bảo đảm mọi đợt mới hoặc mục tiêu 100 địa điểm đều vừa 512 MB.

## Lỗi chờ danh sách Maps sau khi tối ưu RAM

Đợt `coffee / phường Tây Thạnh, Hồ Chí Minh` mục tiêu 100 sau đó tìm được 13 ứng viên nhưng thất bại hai lần lúc 11:03 và 11:04 ngày 30/10/2026. Application logs ghi `Locator.evaluate: Timeout 5000ms exceeded`, chờ `get_by_role("feed")` tại bước cuộn danh sách. Đây là lỗi timeout đã xác nhận; không có căn cứ quy hai lần lỗi này cho OOM.

- Đổi sang locator DOM `[role="feed"]` để không phụ thuộc feed đang được công bố trong accessibility tree khi Maps cập nhật trang; cho thao tác cuộn tối đa 30 giây.
- Nếu vẫn timeout, kiểm tra chặn/xác minh và trạng thái tạm dừng/hủy trước, đóng trình duyệt tìm kiếm, rồi đọc những ứng viên đã lưu. Không đánh dấu tìm kiếm hoàn tất.
- Nếu chưa đạt mục tiêu sau phần ứng viên đó, báo tạm dừng với lý do danh sách phản hồi chậm và cho tiếp tục. Không báo đã hết kết quả.
- 118 kiểm thử backend qua trên SQLite; 10 ca hồi quy cache/browser/discovery qua trên PostgreSQL riêng trong image mới. Bao gồm timeout sau khi lưu ứng viên, giữ điện thoại, đạt mục tiêu, chưa đạt mục tiêu và Google yêu cầu xác minh.

### Xác nhận sau deploy bản sửa timeout

Render auto-deploy commit `5fef11b` thành công lúc 11:12 ngày 30/10/2026, giữ nguyên gói Free. Tiếp tục chính đợt coffee đã thất bại: xử lý đủ 13 ứng viên, lưu **4 quán** khớp Tây Thạnh, bỏ qua **9 quán** khác khu vực, không có hồ sơ lỗi. Tác vụ kết thúc `completed` lúc khoảng 11:18, không bị ngắt trong lượt này; readiness trả HTTP 200. Không đạt mục tiêu 100 do không có thêm kết quả đọc được phù hợp trong lượt tìm kiếm này. Không đổi mục tiêu hoặc nới bộ lọc để tăng số lượng.

Render Free không cung cấp biểu đồ bộ nhớ ứng dụng, nên không có số đo RAM đỉnh thực tế trên cloud. Kết quả này xác nhận đợt trên đã hoàn tất sau sửa lỗi, không bảo đảm mọi truy vấn đều vừa 512 MB.

## Kết quả khác nhau giữa local và VPS

Nguyên nhân trong worker là bộ tìm kiếm cũ coi bốn lần cuộn liên tiếp không có địa điểm mới (khoảng 8 giây) là đã hết kết quả, dù không kiểm tra thông báo hết danh sách của Google Maps. Maps có thể dừng tải lâu hơn rồi mới thêm địa điểm, nên local và VPS có thể lưu số lượng khác nhau.

Worker hiện kiểm tra riêng thông báo hết danh sách, đợi tối đa 45 giây khi danh sách không tiến triển, thử cuộn lại để kích hoạt tải lười và giới hạn tổng thời gian tìm kiếm ở 180 giây. Nếu không xác nhận được đã hết danh sách, thông tin này được lưu vào audit và trạng thái đợt; tác vụ sẽ giữ kết quả đã có và tạm dừng khi chưa đạt mục tiêu. Không có migration database.

Đã quan sát trực tiếp giao diện Maps cho truy vấn `quán ăn tại đường Lê Trọng Tấn, quận Tân Phú, thành phố Hồ Chí Minh Việt Nam`: số liên kết tăng 7 → 14 → 20, đứng ở 20 qua hai nhịp cuộn, sau đó tăng lên 23 và hiển thị thông báo hết danh sách. Giao diện đồng thời báo đang ở chế độ bị hạn chế. Vì Google có thể trả snapshot khác theo thời điểm, máy chủ và trạng thái giới hạn, sửa lỗi này tránh dừng sớm nhưng không bảo đảm hai lượt tìm kiếm riêng biệt có dữ liệu hoàn toàn giống nhau.
