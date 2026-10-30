# Tiến độ LeadFinder Local

## Rà soát toàn luồng sau các lỗi khu vực

Đã bổ sung ma trận hồi quy cho kiểu nhập đường/thành phố, nhãn hành chính/viết tắt/dấu phân tách, tên đường/phường gần giống, tên quận trùng phường và họ Dương trong tên đường. Sửa nhánh tất cả mục lỗi để tiếp tục được, bộ đếm hồ sơ duy nhất, thông báo website vẫn giữ dữ liệu Maps, URL liên hệ sai định dạng, MST bị cắt ngắn, kiểm tra robots sau chuyển hướng, tiếp tục cuộn qua ứng viên đã lưu và kiểm tra token khi ghi lỗi/bỏ qua. Tách tiền tố đường trước khi bỏ dấu và tránh lấy tiêu đề quảng cáo làm tên quán.

Chi tiết trường hợp đã kiểm tra, kết quả và phần chưa hỗ trợ ở `docs/qa-audit-2026-10-29.md`. Có 100 ca backend qua trên SQLite và PostgreSQL riêng biệt, đã kiểm tra DOM và giao diện với Chromium thật. Bản sửa đã cập nhật lên local; readiness và Alembic check qua, DB test đã được dọn. Dữ liệu phường/quận đổi tên toàn quốc, lọc ngành nghề chặt, Google Search riêng và xác minh MST vẫn chưa triển khai đầy đủ; không coi các phần đó là đã hoàn tất.

## Đối chiếu quận Tân Phú cũ với địa chỉ phường hiện tại

Case `lê trọng tấn, quận tân phú, hồ chí minh` tìm 18 ứng viên nhưng lưu 0 vì địa chỉ chỉ ghi Tây Thạnh/Tân Sơn Nhì. Đã giữ riêng cấp quận trong chuẩn hóa (`Quận/Q./District Tan Phu`), phân biệt phường Tân Phú; thêm ranh giới quận cũ OSM relation 6846128 lưu cục bộ. Khi có tọa độ, kiểm tra ranh giới trước, giữ điều kiện đường/phường hẹp hơn. Khi thiếu tọa độ, dùng bảng ánh xạ các phường nằm hoàn toàn trong quận theo Nghị quyết 1685 khoản 62–66; không gán toàn bộ phường Bình Hưng Hòa vào quận Tân Phú.

56 kiểm thử qua trên SQLite và PostgreSQL tạm riêng biệt; Ruff check/format, TypeScript/Vite build, readiness và Alembic check qua. Kiểm thử thêm tên quận/alias, phân biệt phường với quận, đường khác, điểm ngoài quận, điều kiện phường hẹp và phường giao ranh quận. Đã cập nhật stack local, chạy lại cùng đợt `c7297403-d9cf-47f4-9697-5bcae57e8fab` từ 18 chi tiết đã cache: **completed, lưu 12/50 địa điểm, bỏ qua 6, không có mục lỗi**. Không đạt mục tiêu 50 vì đã hết ứng viên phù hợp trong đợt. Không xóa dữ liệu cũ; DB test đã được dọn sau kiểm tra.

## Sửa tên đường không có tiền tố

Case `lê trọng tấn, phường tây thạnh, hồ chí minh`: 30 ứng viên bị bỏ qua vì tên đường đứng đầu bị xem là điều kiện hành chính. Nay đối chiếu tên đường đứng đầu với phần đường có bằng chứng số nhà/tiền tố trong địa chỉ, đồng thời giữ nguyên điều kiện phường/thành phố. Không áp dụng suy luận này cho thành phần ghi rõ tiền tố hành chính. Dùng chung cho bộ lọc văn bản và bộ lọc có tọa độ, không thêm ngoại lệ riêng cho Lê Trọng Tấn.

49 kiểm thử qua trên SQLite và PostgreSQL tạm riêng biệt; Ruff check/format qua. Trong 30 chi tiết đã cache, 12 địa chỉ khớp đường và phường; 18 địa chỉ không thỏa mãn đầy đủ. Đã cập nhật stack local và chạy lại cùng đợt từ cache: **completed, lưu 12/20 địa điểm, bỏ qua 18, không có mục lỗi**. Không đạt mục tiêu 20 vì đã hết ứng viên phù hợp trong đợt này. Readiness và Alembic check qua; DB test đã được xóa sau kiểm tra.

## Sửa đối chiếu tên đường và phường

Case: truy vấn `đường huỳnh tấn phát, tân thuận, hồ chí minh` có 60 ứng viên, bản cũ chỉ lưu 1 vì bắt địa chỉ phải có nguyên chữ “đường”. Bộ lọc mới tách tên đường và điều kiện hành chính, nhận dạng số nhà/hẻm, `Đường/Đ./Street/Road`, địa chỉ tách số nhà bằng dấu phẩy và đường đánh số. Không dùng số nhà làm số đường, không dùng tên phường trùng tên đường làm chứng cứ khớp đường.

Thêm ranh giới phường Tân Thuận hiện tại (OpenStreetMap relation 2766956, dữ liệu cục bộ ODbL) để đối chiếu các địa chỉ trên đường này vẫn ghi Quận 7 thay vì tên phường. Tọa độ trong phường không thay thế việc kiểm tra tên đường. Nguồn được ghi ở `backend/app/data/README.md`, không gọi geocoding khi thu thập.

Đối chiếu lại 60 dữ liệu đã cache: 29 mục thỏa mãn bộ lọc mới; 11 mục chưa khớp tên đường, 20 mục nằm ngoài phường Tân Thuận. Đây là số dự kiến theo dữ liệu đã đọc và ranh giới tham khảo, không phải số đã lưu hoàn tất của đợt. Thông báo bỏ qua nay phân biệt không khớp đường, ngoài phường và chưa xác nhận điều kiện hành chính.

Đã chạy lại 59 mục bỏ qua trong cùng đợt, giữ 1 mục đã lưu. Kết quả thực tế: **completed, 20/20 địa điểm đã lưu**, 24 mục đã xét bị bỏ qua, 16 ứng viên còn lại không cần xử lý sau khi đạt mục tiêu. 42 kiểm thử qua trên PostgreSQL riêng cho test; kiểm tra Ruff, TypeScript/Vite build và Alembic check đều qua. Không tạo đợt mới, không xóa dữ liệu cũ, không bỏ điều kiện phường để tăng số lượng.

## Sửa lỗi loại toàn bộ kết quả theo khu vực

Case thực tế: tìm quán ăn tại `quận 7, thành phố hồ chí minh`, có 119 ứng viên nhưng bị loại hết bởi so khớp chuỗi nguyên văn. Địa chỉ Google trả về chỉ còn dạng `Tân Hưng, Hồ Chí Minh` hoặc `Phú Thuận, Hồ Chí Minh`, thiếu tên quận và tiền tố Thành phố.

Đã sửa: chuẩn hóa tên/viết tắt, so từ đầy đủ để không nhầm Quận 7 với Quận 70; thêm ranh giới Quận 7 cũ lưu cục bộ từ OpenStreetMap để đối chiếu tọa độ quán; fallback theo bốn phường mới đã đối chiếu nguồn Chính phủ khi không có tọa độ. Không lấy tâm viewport làm tọa độ địa điểm và vẫn giữ điều kiện phường nếu người dùng yêu cầu phạm vi hẹp hơn Quận 7.

29 kiểm thử qua trên SQLite và PostgreSQL riêng cho test; có ba ví dụ địa chỉ thật bị loại, điểm ngoài ranh giới dù địa chỉ chứa Quận 7, alias, ranh số, polygon có lỗ, phạm vi hẹp và chạy lại mục bỏ qua mà không làm mất kết quả đã lưu. TypeScript/Vite build và Ruff qua. Migration thêm cache JSON nullable cho chi tiết đã đọc, không sửa/xóa dữ liệu cũ.

Đối chiếu 119 tọa độ đã tìm thấy: 117 nằm trong ranh giới tham khảo Quận 7 cũ, 2 nằm ngoài. Đã đưa các mục bị bỏ qua của đợt Quận 7 trở lại hàng đợi trong cùng đợt, mục tiêu 100. Checkpoint sau khi chạy lại đã lưu thành công 13 địa điểm và còn tiếp tục; không coi checkpoint là kết quả hoàn tất 100 hồ sơ. Giao diện có nút Kiểm tra lại khu vực và không hiển thị 0 kết quả như một lần thu thập thành công.

## Cập nhật bản 0.2 — Chức năng thu thập đã chạy

Ngày 29/10/2026: thay giao diện dashboard bằng form từ khóa/khu vực/số lượng, nút thu thập, tiến độ và bảng kết quả. Google Maps đọc trực tiếp qua trình duyệt nền, không cần API key. Có chọn đọc thêm website, lưu nguồn, tạm dừng/tiếp tục/hủy và xuất riêng từng đợt. Thư viện Chromium được đóng gói trong Docker; worker và scheduler khởi động cùng app.

Đã kiểm tra thực tế trên stack QA tách biệt:

- Tìm đúng tên `Mộc quán Seafood`, khu vực Đà Nẵng, mục tiêu 1: Google trả hồ sơ trực tiếp; lưu được 1/1 địa điểm thật, gồm tên, địa chỉ, SĐT và website.
- Tìm `quán ăn`, khu vực Đà Nẵng, mục tiêu 2: tìm thấy 7 ứng viên, lưu 2/2 địa điểm thật, bỏ qua 1 địa chỉ chưa khớp khu vực, không có lỗi đọc địa điểm. Các ứng viên còn lại không cần xử lý sau khi đạt mục tiêu.
- Hai địa điểm được lưu trong lượt rộng: Mộc quán Seafood Đà Nẵng và Thìa Gỗ Đà Nẵng. Đây là dữ liệu trang công khai đọc được lúc thử, không phải hồ sơ mẫu cài sẵn.
- Đọc thêm trang chủ/giới thiệu/liên hệ của Mộc; có quan sát SĐT, Facebook, Zalo và link nguồn từng trang. Lượt thử này không tìm được MST công khai, nên để trống. Trích MST có nhãn được kiểm tra riêng bằng fixture, không tuyên bố đã xác minh MST ngoài thực tế.
- Excel tải từ giao diện có đúng 2 dòng, 3 sheet, trạng thái MST và bằng chứng nguồn. Đã mở lại bằng openpyxl để đối chiếu.
- 19 kiểm thử qua trên SQLite và 19 kiểm thử qua trên PostgreSQL QA: kiểm soát trạng thái, idempotency, lưu quan sát/không ghi đè, thu hồi token, đối soát heartbeat, URL/IP riêng, trích xuất MST có nhãn và nhánh Google giữ URL search khi mở hồ sơ.
- TypeScript/Vite build qua, Ruff qua, Alembic check không thấy lệch schema. Ảnh giao diện được xem để kiểm tra form/bảng; dữ liệu test không đưa vào DB local chính.

Giới hạn còn lại: cấu trúc Google có thể thay đổi/chặn, không bảo đảm đủ số lượng hoặc mọi trường; khớp khu vực hiện là chuỗi địa chỉ, MST chỉ là ứng viên; chưa có Google Search riêng, gộp/hoàn tác, AI hay export job nền. Chưa chạy pilot 100–200 hồ sơ hoặc đo tải 10.000 hồ sơ. Các bảng tiến độ dưới đây là lịch sử nền tảng 0.1, không thay thế cập nhật 0.2 này.

Ngày triển khai: 29/10/2026. Bản 0.1 tập trung nền tảng và luồng CSV.

| Giai đoạn đặc tả | Trạng thái | Phạm vi |
|---|---|---|
| 0 — Nguồn/đầu vào | Một phần | CSV có xác nhận quyền, file mẫu; chưa chọn API tìm kiếm hay bộ mẫu khách hàng thật |
| 1 — Khung local | Đã kiểm tra bản đầu | Compose, migration, tài khoản, phiên cookie/CSRF, UI/API, healthcheck |
| 2 — Dữ liệu/import | Một phần | Địa điểm, quan sát, import xem trước, giữ dữ liệu khi nhập lại, sửa có audit; chưa tách thương hiệu/pháp nhân/contact points |
| 3 — Điều phối | Chưa triển khai | Redis đã chuẩn bị; chưa có chiến dịch/worker nghiệp vụ/outbox |
| 4 — Đọc website | Chưa triển khai | Không có tác vụ tự truy cập website |
| 5 — Tìm kiếm | Chưa triển khai | Cần quyết định nguồn và hạn mức |
| 6 — Duyệt/ghép | Một phần nhỏ | Xác nhận MST thủ công và xem quan sát; chưa có tra cứu thuế/gộp/hoàn tác |
| 7 — Khách hàng/xuất | Một phần | Trạng thái, ghi chú, XLSX/CSV; chưa có lịch liên hệ và export job nền |
| 8 — Vận hành | Một phần | Script sao lưu/phục hồi thử, bộ kiểm thử; chưa pilot dữ liệu thật, chưa lịch backup |

## Kiểm tra

Kết quả kiểm tra ngày 29/10/2026:

- 8 kiểm thử nghiệp vụ qua trên SQLite tạm và 8 kiểm thử tương ứng qua trên PostgreSQL 17 riêng cho QA. Có kiểm tra phiên/CSRF, nhập lại, chi nhánh cùng hotline, tên khác dấu, địa chỉ giống ở khác tỉnh/thành, mâu thuẫn và sửa phiên bản cũ, MST thay đổi cần xác nhận lại, quyền xuất/hiển thị và ô công thức.
- Frontend TypeScript và Vite build thành công; kiểm tra Ruff backend qua.
- Compose chạy thành công với PostgreSQL/Redis/API khỏe, migration hoàn tất; `alembic check` không phát hiện chênh lệch mô hình và schema.
- Playwright đã chạy trên stack QA riêng: tạo tài khoản → xem trạng thái trống → xem trước CSV tiếng Việt → xác nhận nhập 2 hồ sơ minh họa → mở nguồn → sửa trạng thái thành quan tâm → tải Excel thành công.
- Đã chụp và xem ảnh giao diện 1440×1000; phát hiện và sửa lỗi biểu thức kiểm tra tên đăng nhập phía trình duyệt.
- `pg_dump` và phục hồi thử sang DB tạm thành công: đủ 2 địa điểm minh họa và phiên bản migration `0002_seed_sources`.
- Dữ liệu kiểm thử tách biệt với bản local chính; bản chính để người dùng tự tạo tài khoản đầu tiên.

Giới hạn: chưa pilot dữ liệu khách hàng thật, chưa kiểm tra đầy đủ ma trận AC-01..AC-20, chưa đo hiệu năng 10.000 hồ sơ hoặc hoàn thiện các giai đoạn sau. TestClient hiện báo một cảnh báo tương thích về httpx; các kiểm thử vẫn qua, cần rà soát khi nâng bộ phụ thuộc. Không dùng dữ liệu minh họa để báo cáo như khách hàng thật hoặc nguồn tìm kiếm đã tích hợp.

## Thứ tự công việc tiếp theo

1. Hoàn thiện mô hình thương hiệu/pháp nhân, nhiều liên hệ và giá trị được chọn.
2. Xây chiến dịch, work items, outbox, lease và phục hồi hàng đợi.
3. Xây bộ đọc website có chặn SSRF/rate limit/robots và bằng chứng.
4. Chọn nguồn tìm kiếm thực, thêm connector, kiểm soát quyền và ngân sách.
5. Hàng chờ duyệt trùng/MST, gộp và hoàn tác, quản lý lịch tiếp cận.
6. Xuất nền, lịch sao lưu/retention, pilot và nghiệm thu đầy đủ.
