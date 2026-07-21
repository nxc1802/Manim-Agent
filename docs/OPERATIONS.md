# Vận hành production

## Health và quan sát

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `GET /health` | Liveness của Backend/SPA process |
| `GET /ready` | Redis/Supabase truy cập được và có consumer cho cả queue `ai`, `render` |
| Hugging Face runtime stage | Image build/start có thành công |
| Supabase Advisors | RLS, index và database security/performance drift |

Mọi API request nhận `X-Request-ID`; Backend giữ hoặc sinh ID và trả lại trong error envelope. Khi điều tra, tìm ID đó trong log Backend rồi đối chiếu `job_id`, `run_id`, `step_id`, `project_id`. Không log bearer token, Google key, Supabase secret hoặc nội dung header WebSocket subprotocol.

Sentry là tùy chọn qua `SENTRY_DSN`. Log vẫn đi stdout/stderr để Hugging Face thu thập.

## Process và queue

Supervisor chạy Redis, Backend, AI worker và render worker. Hai worker đều concurrency/prefetch bằng 1; task dùng late acknowledgement, hard/soft timeout và worker-child recycling. Render có giới hạn CPU, address space và file descriptor ở subprocess.

Redis dùng AOF `appendfsync everysec` tại `/data/redis`. Production cần persistent storage và hardware always-on để giữ queue/lock/render-job coordination qua restart; không có persistent `/data` chỉ là profile demo/staging. Persistent storage vẫn không thay thế Postgres/Storage: project, scene, HITL state và video URL nằm trong Supabase.

Nếu task bị kẹt:

1. Kiểm tra `/ready` và log Redis/worker.
2. Xác định trạng thái job/run trong UI và log bằng ID.
3. Restart Space chỉ sau khi đã chấp nhận task đang chạy có thể thất bại/requeue.
4. Retry từ UI; không sửa trực tiếp Redis production trừ khi có runbook sự cố đã review.

## Backup và retention

- Bật backup/PITR phù hợp với gói Supabase; thử restore sang project riêng định kỳ.
- Migration DDL/data lớn phải có checkpoint trước khi deploy.
- Bucket `videos` private là nơi lưu artifact bền vững. Xóa row project không tự đảm bảo xóa object; cần quy trình lifecycle/garbage collection riêng.
- Disk Hugging Face ngoài persistent `/data` là ephemeral. `/artifacts` chỉ là vùng staging;
  render worker tự xóa file cục bộ sau khi Backend xác nhận object `supabase://` đã được lưu bền vững.
  Nếu cleanup lỗi, cảnh báo được ghi log nhưng job đã hoàn tất không bị chạy lại.

## Rotation secret

- `INTERNAL_SERVICE_TOKEN`: thay trong Space rồi restart toàn container; Backend và worker đọc cùng một secret.
- `GOOGLE_API_KEY`: thêm key mới vào pool, kiểm tra readiness/luồng test rồi bỏ key cũ.
- `SUPABASE_SECRET_KEY`: tạo key mới, đổi Space Secret, xác minh `/ready`, sau đó revoke key cũ.
- JWT signing key: dùng asymmetric signing keys/JWKS để Supabase cho phép rotation không downtime. HS256 secret chỉ là đường tương thích legacy.
- `HF_TOKEN` và Supabase deployment token/password: rotate trong GitHub Environment; chúng không thuộc runtime image.

## Sự cố thường gặp

| Hiện tượng | Kiểm tra đầu tiên |
| --- | --- |
| `/health` lỗi | Space build/runtime log, port `7860`, Supervisor |
| `/ready` 503 | Redis, Supabase URL/key/grants/migration, hoặc thiếu AI/render worker |
| Login được nhưng API 401 | JWT issuer/audience, JWKS reachability, Auth redirect URL |
| WebSocket reconnect liên tục | Proxy hỗ trợ subprotocol, access token còn hạn, Redis Pub/Sub |
| Render fail/timeout | Manim stderr, worker memory/CPU, TeX/FFmpeg, hard limits |
| Render xong nhưng reload mất video | Supabase Storage upload/signing và bucket `videos` |
| CD dừng trước sync Space | Migration history hoặc post-deploy schema gate |

Khi database có constraint `NOT VALID` hoặc duplicate step sequence, dừng promotion và làm data-repair migration theo [Database](DATABASE.md); không xóa dữ liệu âm thầm.
