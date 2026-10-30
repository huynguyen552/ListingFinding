# LeadFinder

LeadFinder là ứng dụng tiếng Việt để thu thập và quản lý thông tin khách hàng tiềm năng cho quán ăn, nhà hàng. Giao diện quản lý chạy local bằng Docker Compose. Thu thập tự động theo lịch chạy bằng GitHub Actions, đọc danh sách từ `automation/targets.csv`, gửi workbook Excel qua email và ghi kết quả vào Google Sheets. Dữ liệu PostgreSQL cũ trên VPS chưa được chuyển sang máy local.

Ứng dụng đọc kết quả Google Maps bằng Chromium. Maps có thể thay đổi kết quả, giới hạn truy cập hoặc đóng kết nối tới một số máy chủ; số lượng và kết quả giữa các lượt chạy không được bảo đảm giống nhau. Xem [số đo hiệu năng và các giới hạn đã kiểm tra](docs/performance.md).

## Trạng thái hiện tại — 0.2.0

Chức năng chính: nhập từ khóa, khu vực và số lượng → chạy trình duyệt nền tìm Google Maps → đọc tên, SĐT, địa chỉ, website → tùy chọn đọc website/trang liên hệ để tìm MST và các kênh liên hệ công khai → lưu kết quả có nguồn → xuất Excel/CSV theo đợt.

Không cần API key cho luồng Google Maps trực tiếp. Có worker Celery, lịch đối soát, tạm dừng/tiếp tục/hủy, kết quả từng phần và lịch sử 30 đợt gần nhất. Trạng thái/từng địa điểm nằm trong PostgreSQL; một thời điểm chạy một đợt. Website có chặn hoặc Google yêu cầu xác minh thì ghi lỗi/dừng, không vượt CAPTCHA. Nếu worker báo `ERR_CONNECTION_CLOSED`, hãy dừng thử lại liên tục và kiểm tra log worker cùng kết nối tới Google. Số lượng là mục tiêu, không bảo đảm đạt đủ. Khu vực được đối chiếu với địa chỉ, không chỉ với tên quán.

MST lấy từ website là **ứng viên chưa xác minh**, không được coi là xác nhận pháp nhân. Email/Facebook/Zalo tìm được được lưu trong nguồn theo trường và sheet nguồn của Excel. Giao diện tập trung form thu thập và bảng kết quả; API CSV/quản lý cũ vẫn giữ để tương thích. Chưa có Google Search riêng, gộp/hoàn tác, lịch tiếp cận, xuất nền hoặc lịch sao lưu tự động.

Truy cập công khai không tự cấp quyền tái sử dụng dữ liệu; cần xem điều khoản của Google và từng website theo phạm vi vận hành. Cơ chế trình duyệt trực tiếp không phải giấy phép của nhà cung cấp. Chính sách nguồn được lưu trong bảng `sources` và được kiểm tra khi lưu/hiển thị/xuất.

## Khởi động nhanh trên Windows

Yêu cầu: Docker Desktop đang chạy ở Linux containers, Docker Compose, Python 3.13+ cho script quản lý. Đề xuất 8 GB RAM trở lên, SSD và ít nhất 5 GB trống cho image/cache.

Mở terminal tại thư mục dự án:

```powershell
python scripts/manage.py init
python scripts/manage.py start
```

Mở **http://localhost:5173** và tạo tài khoản đầu tiên. Tên đăng nhập ít nhất 3 ký tự; mật khẩu 12–128 ký tự. Không có tài khoản/mật khẩu mặc định. Lần build đầu cần Internet để tải image và thư viện.

Script tự sinh mật khẩu PostgreSQL vào `.env`, giữ nguyên file nếu đã tồn tại. Không sửa mật khẩu sau khi đã tạo volume nếu chưa đổi mật khẩu trong PostgreSQL tương ứng. Không đưa `.env`, bản sao lưu hoặc dữ liệu khách hàng lên Git.

Chỉ web bind `127.0.0.1:5173`; DB/Redis/API không mở cổng ra máy chủ. Bản này dùng HTTP local và cookie phiên HttpOnly/SameSite Strict, chỉ dành cho máy local. Không mở cổng ứng dụng ra Internet.

Database local dùng volume Docker riêng. Nó không tự đồng bộ với database LeadFinder còn lưu trong PostgreSQL dùng chung trên VPS; cần xuất/nhập dữ liệu riêng nếu muốn chuyển các lead cũ về máy.

## Thu thập tự động, email và Google Sheets

GitHub Actions chạy workflow `.github/workflows/nightly-crawl.yml` lúc **23:17 giờ Việt Nam** mỗi tối, hoặc chạy thủ công trong tab **Actions**. Trước mỗi lượt, workflow đọc tab `Targets` từ Google Sheet, tạo input tạm trong runner, khởi động database tạm, xử lý tuần tự các dòng đang bật rồi tạo file `.xlsx`. Email là kênh gửi tùy chọn; kết quả được ghi nối tiếp vào Google Sheets. File Excel được giữ trong GitHub Actions 7 ngày làm bản dự phòng. Các lượt này không tự thêm dữ liệu vào database local.

Để thay đổi input tự động mà không commit, mở Google Sheet và sửa tab `Targets`. Hàng đầu tiên cần có các cột:

| Cột | Ý nghĩa |
| --- | --- |
| `keyword` | Từ khóa tìm kiếm |
| `area` | Khu vực; nếu có dấu phẩy, đặt nội dung trong dấu ngoặc kép |
| `target` | Mục tiêu từ 1 đến 200 |
| `enrich_website` | `true` để đọc thêm website, `false` để bỏ qua |
| `enabled` | `true` để chạy dòng đó, `false` để tạm tắt |

`keyword`, `area`, `target` là bắt buộc; `enrich_website` và `enabled` mặc định là `true` nếu để trống. Các giá trị bật/tắt chấp nhận `true/false`, `yes/no` hoặc `1/0`. Mỗi lượt tối đa 25 dòng đang bật; `target` từ 1 đến 200. Có thể tạm dừng một mục tiêu bằng cách đặt `enabled` thành `false`. Tab phải tên chính xác `Targets`; nếu đang có tab trống `Trang tính1`, có thể đổi tên tab đó rồi nhập hàng tiêu đề. Nếu tab chưa được tạo, workflow tạm dùng `automation/targets.csv` và ghi cảnh báo; sau khi tạo tab, workflow sẽ dùng Google Sheet. File CSV vẫn dùng được cho các lượt chạy batch trực tiếp từ repo.

Để gửi email, thêm Actions Secrets: `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_TO`; `SMTP_PORT` mặc định là `587` và `MAIL_FROM` mặc định dùng tài khoản SMTP. `MAIL_TO` có thể chứa nhiều địa chỉ, ngăn cách bằng dấu phẩy.

Để đọc input và ghi kết quả Google Sheets, bật Google Sheets API trong Google Cloud, cấu hình Workload Identity Federation cho repo này và chia sẻ spreadsheet với email tài khoản dịch vụ quyền **Editor**. Thêm các Secrets `GOOGLE_SHEET_ID`, `GOOGLE_WORKLOAD_IDENTITY_PROVIDER` (tên đầy đủ của provider) và `GOOGLE_SERVICE_ACCOUNT` (email tài khoản dịch vụ). Workflow đọc tab `Targets`, đồng thời tự tạo các tab kết quả `Runs`, `Leads`, `Sources` và `Notifications`, sau đó nối thêm dòng của mỗi lượt chạy. Google Sheets là bắt buộc để chạy workflow; email là tùy chọn. Nên giới hạn provider chỉ tin cậy repo `huynguyen552/ListingFinding`. Xem [hướng dẫn thiết lập chi tiết](docs/github-actions-google-sheets.md), [Google Cloud WIF](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines) và [Google Sheets API append](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append).

Workflow cần cấu hình Google Sheets vì tab `Targets` là nguồn input và cũng là nơi lưu kết quả. Email có thể bỏ qua nếu chưa cấu hình; nếu email gặp lỗi, dữ liệu vẫn được ghi vào Sheets. Không đưa mật khẩu email, access token hoặc khóa tài khoản dịch vụ vào CSV hay commit. Chạy workflow thủ công lần đầu với một dòng nhỏ để xác nhận quyền truy cập, Google Maps và nơi nhận dữ liệu.

Runner của GitHub là máy cloud tạm thời; Google Maps có thể giới hạn hoặc đóng kết nối từ runner. Lịch workflow cũng có thể bắt đầu trễ khi GitHub quá tải. Google Sheets lưu dữ liệu qua các lần chạy; các địa điểm có thể lặp lại giữa những đợt thu thập. Muốn xem dữ liệu trong giao diện local thì cần nhập workbook riêng.

## Dùng thử

1. Đăng nhập. Màn hình chính là form **Thu thập dữ liệu**.
2. Nhập từ khóa, ví dụ `quán ăn`; khu vực, ví dụ `Đà Nẵng`; số lượng từ 1 đến 200. Nên chạy 2–5 quán để kiểm tra trước.
3. Bật/tắt đọc thêm website. Khi bật, mỗi quán đọc tối đa 3 trang cùng website và kiểm tra robots.txt, giới hạn thời gian/kích thước, chặn mạng nội bộ và ghim IP sau phân giải DNS.
4. Bấm **Bắt đầu thu thập**. Theo dõi tìm thấy/đã lưu/bỏ qua/lỗi. Kết quả xuất hiện ngay sau khi lưu từng địa điểm.
5. Có thể tạm dừng, tiếp tục hoặc hủy. Hủy vẫn giữ dữ liệu đã lưu. Đợt bị ngắt được đối soát sau khoảng 4 phút và đưa về trạng thái có thể tiếp tục.
6. Bấm **Xem nguồn** để xem thông tin từ Google Maps và website. Bấm Excel/CSV để xuất riêng đợt đang chọn. File có trạng thái MST; bản ứng viên chưa được xác minh được ghi rõ.
7. Chọn **Xem tất cả dữ liệu đã lưu** để xem dữ liệu qua các đợt, kể cả dữ liệu nhập trước đây.

Khu vực nên dùng tên đầy đủ xuất hiện trong địa chỉ. Nếu nhập nhiều cấp, ngăn bằng dấu phẩy, ví dụ `An Hải, Đà Nẵng`. Cơ chế đối chiếu bảo thủ có thể bỏ qua địa chỉ viết tắt; xem thông báo bỏ qua để kiểm tra.

Có thể nhập `Lê Trọng Tấn, phường Tây Thạnh, Hồ Chí Minh` hoặc `Lê Trọng Tấn, Hồ Chí Minh` mà không cần thêm chữ “đường”. Tên đứng đầu được nhận là đường khi khớp chính xác phần đường có bằng chứng số nhà/tiền tố trong địa chỉ và không khớp một thành phần hành chính. Điều kiện phường và thành phố vẫn phải khớp; tên có tiền tố hành chính không được dùng làm tên đường. Có thể dùng dấu chấm phẩy hoặc xuống dòng; các phần có nhãn rõ như `đường Lê Trọng Tấn phường Tây Thạnh TP.HCM` cũng được tách. Với tên không rõ cấp hoặc địa chỉ Google viết nhập nhằng, nên ghi rõ `đường/phường/quận` và ngăn bằng dấu phẩy.

Cảnh báo lỗi website có nhãn **Đã lưu · Cảnh báo website**: quán vẫn nằm trong bảng và file xuất. Lỗi đọc Maps có nhãn **Chưa đọc được**, có thể bấm Tiếp tục để thử lại, kể cả khi chưa lưu được quán nào. **Bỏ qua** dành cho địa chỉ chưa xác nhận khớp khu vực. Số đã lưu đếm địa điểm duy nhất, không cộng nhiều lần khi một quán có nhiều link ứng viên. Từ khóa dùng để tìm trên Google Maps; hiện chưa có bộ phân loại ngành nghề để loại tuyệt đối kết quả quảng cáo hoặc ngành liên quan.

Với `Lê Trọng Tấn, quận Tân Phú, Hồ Chí Minh`, tool dùng ranh giới quận Tân Phú cũ để đối chiếu tọa độ, kể cả khi địa chỉ chỉ ghi phường mới. Khi thiếu tọa độ, dùng ánh xạ các phường nằm hoàn toàn trong quận đã đối chiếu nguồn; không suy ra toàn bộ Bình Hưng Hòa thuộc Tân Phú. `Phường Tân Phú` và `Quận Tân Phú` là hai phạm vi khác nhau. Hiện dữ liệu ranh giới cục bộ chỉ hỗ trợ Quận 7 cũ, quận Tân Phú cũ và phường Tân Thuận, chưa bao phủ toàn quốc.

Đã bổ sung chuẩn hóa `TP.HCM`, `HCM`, `Hồ Chí Minh`, `Thành phố Hồ Chí Minh` và `Q.7/Quận 7/District 7`. Riêng Quận 7 cũ có ranh giới OpenStreetMap lưu cục bộ để kiểm tra tọa độ địa điểm khi địa chỉ chỉ còn tên phường mới. Không dùng tâm khung nhìn bản đồ làm tọa độ quán. Các khu vực khác chưa có ranh giới cục bộ vẫn dùng đối chiếu tên; không suy ra rằng mọi phường mới đã được ánh xạ toàn quốc.

Có thể nhập phạm vi theo đường, ví dụ `Đường Huỳnh Tấn Phát, Tân Thuận, Hồ Chí Minh`. Tên đường được đối chiếu riêng với phần đường của địa chỉ, bỏ qua khác biệt `Đường/Đ./Street/Road` và số nhà/hẻm; tên phường không được dùng thay cho tên đường. Điều kiện đường và phường đều phải thỏa mãn. Phường Tân Thuận có thêm ranh giới cục bộ để xử lý địa chỉ cũ chỉ ghi Quận 7. Nếu muốn tìm toàn bộ tuyến đường qua nhiều phường, nhập `Đường Huỳnh Tấn Phát, Hồ Chí Minh`.

Nếu đợt trước đã bỏ qua do khu vực, dùng **Kiểm tra lại khu vực** để xét lại các mục đó ngay trong đợt cũ. Kết quả đã lưu không bị xóa. Chi tiết đọc được được giữ trong `crawl_entries.raw_data` để những lần xét lại sau không cần đọc lại hồ sơ Google; địa chỉ bị bỏ qua cũng được ghi trong thông báo. Đợt kết thúc nhưng lưu 0 hồ sơ được hiển thị là **Chưa có kết quả phù hợp**.

Nguồn dữ liệu ranh giới và giấy phép: `backend/app/data/README.md` (© OpenStreetMap contributors, ODbL 1.0). Không gọi dịch vụ geocoding trong lúc thu thập.

Google có thể giới hạn số kết quả hoặc thay đổi cấu trúc trang; lúc đó hệ thống báo thiếu kết quả hoặc cần kiểm tra worker, không tự tạo dữ liệu. Lần cài đặt bản có crawler cần tải Chromium và các thư viện hệ thống, vì vậy build lâu hơn bản 0.1.

Nhập lại không ghi đè giá trị đang hiển thị. Những giá trị khác được giữ trong nguồn để đối chiếu. Bản này tự nhận diện bằng tên/địa chỉ đã chuẩn hóa hoặc URL khi thiếu địa chỉ; các trường hợp mơ hồ cần người dùng kiểm tra. Chưa suy ra tổng số chi nhánh và chưa xác minh qua nguồn thuế bên ngoài.

## Vận hành

```powershell
python scripts/manage.py status
python scripts/manage.py stop
python scripts/manage.py backup
python scripts/manage.py verify-backup backups/ten-file.dump
```

`stop` giữ nguyên volume. `verify-backup` phục hồi vào DB tạm, kiểm tra số hồ sơ và phiên bản migration, sau đó xóa DB tạm; không thay DB đang dùng. Bản đầu chưa tự lên lịch sao lưu. Không chạy `docker compose down -v` trừ khi chủ động muốn xóa dữ liệu.

Để cập nhật code: sao lưu trước, sau đó chạy lại `start`. Migration chạy trong dịch vụ riêng trước khi API khởi động. Lệnh xem nhật ký: `docker compose logs --tail 100 api migrate`.

## Phát triển

Backend: Python 3.13, FastAPI, SQLAlchemy 2, Alembic, Celery và Playwright Chromium. Frontend: React 19, TypeScript, Vite 7, Tailwind 4; nút giao diện theo mẫu shadcn với Radix Slot/CVA. PostgreSQL 17 và Redis 7.4 qua Compose. Python được khóa phiên bản trong `backend/requirements.txt`, JavaScript trong `frontend/package-lock.json`.

```powershell
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest -q
cd ../frontend
npm ci
npm run build
```

Kiểm thử mặc định dùng SQLite tạm, độc lập với DB thật. Để kiểm thử PostgreSQL, đặt `TEST_DATABASE_URL` tới DB **chỉ dành cho test, có tên kết thúc `_test`**. Tests sẽ xóa và tạo lại các bảng của DB đó, tuyệt đối không dùng DB nghiệp vụ.

Chạy frontend dev qua `npm run dev` và backend `uvicorn app.main:app --host 127.0.0.1 --port 8000` sau khi thiết lập `DATABASE_URL` và migration. Không cần dev server khi dùng Compose đầy đủ.

## Tài liệu

- Đặc tả gốc: `.doc/dacta.md` (thư mục cá nhân, bị Git bỏ qua).
- Tiến độ và phạm vi thực hiện: `docs/progress.md`.
- Quyết định kiến trúc: `docs/decisions.md`.

Các tài liệu kỹ thuật tham chiếu: [FastAPI](https://fastapi.tiangolo.com/tutorial/security/), [SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/quickstart.html), [Vite](https://vite.dev/guide/).
