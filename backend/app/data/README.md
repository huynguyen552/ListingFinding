# Ranh giới dùng để đối chiếu khu vực

`hcm-tan-phu-district.geojson` là ranh giới quận Tân Phú cũ, OpenStreetMap relation 6846128, tải thủ công ngày 29/10/2026 qua Nominatim lookup (boundary/historic). Nguồn: https://www.openstreetmap.org/relation/6846128. Giữ geometry và metadata nguồn, cùng attribution/giấy phép ODbL 1.0 bên dưới. Chỉ kích hoạt cho truy vấn ghi rõ `Quận Tân Phú/Q. Tân Phú/District Tan Phu` cùng Hồ Chí Minh; không coi `Phường Tân Phú` là quận. Không gọi Nominatim trong luồng thu thập.

Khi không có tọa độ, chỉ suy ra quận Tân Phú cũ từ các phường hiện tại nằm hoàn toàn trong quận: Tây Thạnh, Tân Sơn Nhì, Phú Thọ Hòa, Tân Phú, Phú Thạnh, đối chiếu khoản 62–66 của Nghị quyết 1685 bên dưới. Bình Hưng Hòa có phần nhận từ Sơn Kỳ (khoản 41), nên không suy ra cả phường thuộc quận Tân Phú. Nếu có tọa độ quán, kiểm tra polygon được ưu tiên; các điều kiện đường/phường hẹp hơn vẫn phải thỏa mãn.

`hcm-tan-thuan.geojson` là ranh giới phường Tân Thuận hiện tại, OpenStreetMap relation 2766956, tải ngày 29/10/2026. Nguồn: https://www.openstreetmap.org/relation/2766956. Cùng attribution và giấy phép ODbL 1.0 bên dưới. Dùng khi truy vấn chỉ rõ Tân Thuận và Hồ Chí Minh, bao gồm truy vấn hẹp hơn theo tên đường. Tên đường vẫn phải được đối chiếu riêng; điểm nằm trong phường không tự có nghĩa là nằm trên đường được yêu cầu.

`hcm-district-7.geojson` là phần trích ranh giới Quận 7 cũ từ OpenStreetMap relation 2764875, tải ngày 29/10/2026. Nominatim phân loại đối tượng là boundary/historic. File giữ nguyên geometry và metadata nguồn; không gọi Nominatim khi người dùng chạy thu thập.

- Nguồn: https://www.openstreetmap.org/relation/2764875
- Attribution: © OpenStreetMap contributors
- Giấy phép dữ liệu: Open Database License 1.0 — https://opendatacommons.org/licenses/odbl/1-0/
- Bản quyền/đóng góp: https://www.openstreetmap.org/copyright

Đối chiếu địa chỉ mới của khu vực Quận 7 dựa thêm vào bốn phường Tân Thuận, Phú Thuận, Tân Mỹ, Tân Hưng theo các khoản 18–21, Điều 1, Nghị quyết 1685/NQ-UBTVQH15, nguồn Chính phủ:
https://xaydungchinhsach.chinhphu.vn/toan-van-nghi-quyet-so-1685-nq-ubtvqh15-sap-xep-cac-dvhc-cap-xa-cua-thanh-pho-ho-chi-minh-nam-2025-119250616211341304.htm

Ranh giới là dữ liệu tham khảo từ cộng đồng, không phải bản xác nhận địa giới pháp lý. Chỉ dùng tọa độ địa điểm `!3d...!4d...` trong link Maps, không dùng tâm khung nhìn `/@lat,lon`. Với yêu cầu hẹp hơn như một phường trong Quận 7, vẫn phải khớp thêm phường yêu cầu. Các khu vực khác hiện dùng đối chiếu tên/viết tắt; chưa có ranh giới toàn quốc.
