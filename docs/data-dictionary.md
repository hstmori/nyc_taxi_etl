# Data dictionary

Tập cột đầu vào của bộ local Q1/2025; schema đích chuẩn hóa thành chữ thường. Mô tả theo các nhóm trường của TLC; khi diễn giải mã danh mục phải đối chiếu phiên bản data dictionary chính thức của nguồn.

| Cột nguồn | Kiểu đích | Ý nghĩa / cách xử lý |
|---|---|---|
| VendorID | INTEGER | Mã đơn vị cung cấp bản ghi; dimension, không phải mã xe |
| tpep_pickup_datetime | TIMESTAMP | Thời điểm đón; dùng xác định ngày/giờ và kiểm tra tháng |
| tpep_dropoff_datetime | TIMESTAMP | Thời điểm trả; dùng tính thời lượng |
| passenger_count | DOUBLE nullable | Số khách; giữ null, không suy đoán là 0 |
| trip_distance | DOUBLE | Khoảng cách theo miles; gắn cờ 0, <0, >200 |
| RatecodeID | DOUBLE nullable | Mã loại giá cước; giữ null |
| store_and_fwd_flag | VARCHAR nullable | Cờ lưu và chuyển bản ghi; giữ giá trị nguồn |
| PULocationID | INTEGER | Mã khu vực đón, nối dim_zone.location_id |
| DOLocationID | INTEGER | Mã khu vực trả, nối dim_zone.location_id bằng vai trò riêng |
| payment_type | BIGINT | Mã phương thức/trạng thái thanh toán; chưa ánh xạ nhãn |
| fare_amount | DOUBLE | Cước ghi nhận, USD |
| extra | DOUBLE | Khoản phụ thu ghi nhận, USD |
| mta_tax | DOUBLE | Thuế MTA ghi nhận, USD |
| tip_amount | DOUBLE | Tiền tip được ghi nhận, USD; không mặc định bao phủ mọi tip tiền mặt |
| tolls_amount | DOUBLE | Phí cầu đường ghi nhận, USD |
| improvement_surcharge | DOUBLE | Phụ phí cải thiện ghi nhận, USD |
| total_amount | DOUBLE | Tổng tiền ghi nhận, USD; giữ số âm và outlier, không gọi là lợi nhuận |
| congestion_surcharge | DOUBLE nullable | Phụ phí ùn tắc ghi nhận, USD; null không tương đương 0 |
| Airport_fee | DOUBLE nullable | Phí sân bay ghi nhận, USD; null không tương đương 0 |
| cbd_congestion_fee | DOUBLE | Phí ùn tắc CBD ghi nhận, USD; giữ giá trị nguồn |

Timestamp được giữ như nguồn (không có timezone trong schema file local). Chưa chuẩn hóa UTC hoặc xử lý DST; duration dựa trên hai timestamp nguồn nên cần cân nhắc khi dùng làm SLA.

## Trường bổ sung

| Trường | Ý nghĩa |
|---|---|
| source_month | Tháng trong tên file, YYYY-MM |
| source_row_number | Vị trí dòng vật lý, bắt đầu từ 0 trong file |
| duration_minutes | Chênh lệch timestamp đến giây chia 60 |
| quality_flags | Các cờ cần xem xét, phân cách bằng dấu pipe |
| reject_reason | Các lý do cách ly; chỉ có trong quarantine |

dim_zone có `location_id`, `borough`, `zone`, `service_zone`. Null ở các trường mô tả được giữ nguyên. Bảng tra không có duplicate LocationID trong bộ local đã kiểm tra.
