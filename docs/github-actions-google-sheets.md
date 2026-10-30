# Cấu hình GitHub Actions ghi Google Sheets

Workflow xác thực qua Workload Identity Federation, không cần tải khóa dài hạn của service account về máy. Sau khi tạo xong, chỉ repo `huynguyen552/ListingFinding` được phép dùng service account ghi vào spreadsheet được chia sẻ.

## 1. Bật Google Sheets API

Trong Google Cloud Console, chọn hoặc tạo project, mở **APIs & Services → Library**, tìm **Google Sheets API** và bấm **Enable**. Việc cấu hình Workload Identity Federation có thể yêu cầu project đã bật billing; kiểm tra project và điều khoản billing trước khi tiếp tục.

Mở **Cloud Shell** của project đó và đặt project ID:

```bash
PROJECT_ID="your-google-cloud-project-id"
gcloud config set project "$PROJECT_ID"
gcloud services enable sheets.googleapis.com iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com
```

## 2. Tạo service account và GitHub identity provider

Chạy lần lượt trong Cloud Shell:

```bash
gcloud iam service-accounts create leadfinder-sheet-writer \
  --display-name="LeadFinder Google Sheets writer"

gcloud iam workload-identity-pools create leadfinder-github \
  --location="global" \
  --display-name="LeadFinder GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc leadfinder \
  --location="global" \
  --workload-identity-pool="leadfinder-github" \
  --issuer-uri="https://token.actions.githubusercontent.com/" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository == 'huynguyen552/ListingFinding'"
```

Cho phép danh tính từ đúng repo impersonate service account:

```bash
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
POOL_NAME="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/leadfinder-github"
SERVICE_ACCOUNT="leadfinder-sheet-writer@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL_NAME}/attribute.repository/huynguyen552/ListingFinding"

echo "$SERVICE_ACCOUNT"

gcloud iam workload-identity-pools providers describe leadfinder \
  --location="global" \
  --workload-identity-pool="leadfinder-github" \
  --format="value(name)"
```

Lệnh cuối trả về tên đầy đủ dạng `projects/.../locations/global/workloadIdentityPools/leadfinder-github/providers/leadfinder`. Lưu giá trị đó để thêm vào GitHub Secrets.

## 3. Chia sẻ spreadsheet với service account

Tạo hoặc mở Google Sheet, bấm **Share**, thêm email trong biến `SERVICE_ACCOUNT` và cấp quyền **Editor**. Lấy spreadsheet ID từ URL phần nằm giữa `/d/` và `/edit`.

Tạo tab tên chính xác `Targets` để nhập danh sách cần thu thập. Hàng đầu tiên dùng các cột:

```text
keyword | area | target | enrich_website | enabled
```

`keyword`, `area` và `target` là bắt buộc. `enrich_website` và `enabled` mặc định là `true` nếu để trống. Mỗi workflow chạy tối đa 25 dòng đang bật; `target` nhận giá trị từ 1 đến 200. Nếu spreadsheet đã có tab trống `Trang tính1`, có thể đổi tên tab đó thành `Targets`.

## 4. Thêm GitHub Actions Secrets

Trong repo, mở **Settings → Secrets and variables → Actions → New repository secret** và tạo:

| Name | Giá trị |
| --- | --- |
| `GOOGLE_SHEET_ID` | ID lấy từ URL của spreadsheet |
| `GOOGLE_WORKLOAD_IDENTITY_PROVIDER` | Tên đầy đủ trả về ở bước 2 |
| `GOOGLE_SERVICE_ACCOUNT` | Email service account, dạng `leadfinder-sheet-writer@PROJECT_ID.iam.gserviceaccount.com` |

Email là kênh gửi tùy chọn. Để nhận workbook qua email, cấu hình thêm `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD` và `MAIL_TO` theo README. Workflow đọc input từ tab `Targets`, ghi kết quả vào Sheets và giữ file Excel làm artifact 7 ngày.

Sau khi cấu hình, chạy workflow **LeadFinder nightly collection** thủ công với một dòng nhỏ đang bật ở tab `Targets`. Google Sheet sẽ được tạo các tab `Runs`, `Leads`, `Sources`, `Notifications`; mỗi lượt chạy được nối thêm cùng mã lần chạy và thời gian thu thập. Các lần chỉnh sửa input sau đó chỉ cần sửa tab `Targets`, không cần commit CSV.

Tham khảo: [Google Cloud Workload Identity Federation cho pipeline](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines), [Google Sheets API append](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append), [Google auth action](https://github.com/google-github-actions/auth).
