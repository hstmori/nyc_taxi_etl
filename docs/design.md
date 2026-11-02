# Thiết kế và giới hạn

## Luồng ETL

Extract: đọc file local (có downloader riêng), tính checksum streaming. Transform: chuẩn hóa tên cột, xác nhận schema, kiểm tra lookup, tạo reject_reason và quality_flags, tính duration_minutes. Load: thay thế partition trong transaction, lưu manifest, tạo SQL views và CSV.

Staging là bảng tạm của DuckDB, không copy dữ liệu gốc vào repo. Raw là các file người dùng đã tải. DQ được tính trên raw, marts trên accepted. Do đó DQ và dashboard có mẫu số khác nhau.

## Tính đúng và tính ổn định

- Hai khóa zone được kiểm tra trên bảng lookup có LocationID duy nhất, tránh fan-out khi join.
- Source partition theo tên file; ngày đón được kiểm tra riêng. Không giả định tên file đảm bảo mọi ngày đều hợp lệ.
- Vi phạm nhiều rule vẫn chỉ là một dòng quarantine; các check có thể chồng lấp, không được cộng tổng check để suy ra số reject.
- Hash lookup thay đổi sẽ invalidation cache của tháng được chạy. Khi đổi SQL/policy cần tăng POLICY_VERSION và chạy lại toàn bộ.
- Tiền dùng DOUBLE theo nguồn. Khi cần chuẩn kế toán, cần thiết kế rounding và DECIMAL, đối soát theo business rule. Chưa cam kết độ chính xác kế toán đến từng cent.
- Không suy diễn các null của nhiều cột là cùng một nhóm dòng nếu chưa kiểm tra đồng xuất hiện.
- Bảng dim_zone giữ null gốc: không tự suy đoán tên vùng. Power BI có thể hiển thị nhãn Unknown mà không đổi mã gốc.

## Giới hạn vận hành

Một writer tại một thời điểm; không hỗ trợ chạy nhiều process ETL đồng thời trên cùng database. Transaction theo tháng, không theo toàn bộ quý. CSV exports chỉ được cập nhật sau khi các tháng hoàn tất; nếu run thất bại, kiểm tra log và chạy lại trước khi refresh báo cáo. Export từng CSV chưa phải atomic bundle; không đọc exports trong khi ETL đang chạy.

Downloader chưa có retry/backoff/checksum nguồn chính thức; có timeout và file tạm, kiểm tra magic bytes Parquet. Với local đã tải, pipeline vẫn ghi checksum để truy xuất. CLI là batch chạy chủ động, không phải scheduler.

## Lộ trình mở rộng

1. PostgreSQL: staging + transaction thay partition; index theo pickup date và location.
2. Scheduler: gọi CLI theo lịch, retry có giới hạn, gửi cảnh báo nếu exit code khác 0.
3. DQ: kiểm tra sâu currency components theo vendor, cập nhật/refund, timestamp timezone, drift kiểu dữ liệu.
4. Dashboard: so sánh accepted/all và tập không bị gắn cờ; phân tích độ nhạy trước khi diễn giải outlier.
