# Triển khai production

## Profile được hỗ trợ

Production ban đầu là một Hugging Face Docker Space chạy root `Dockerfile`. Space phục vụ React/FastAPI trên cổng `7860`, Redis chỉ bind loopback, và Supervisor quản lý Backend cùng hai Celery worker độc lập. Supabase cung cấp Auth, Postgres và private Storage.

Chọn Space `Protected` nếu người dùng cần truy cập ứng dụng nhưng source phải kín; chọn `Private` nếu cả ứng dụng chỉ dành cho thành viên được cấp quyền. Với production, dùng hardware always-on và gắn persistent storage tại `/data`: queue, lock và render-job coordination nằm trong Redis AOF nên disk ephemeral chỉ phù hợp demo/staging và có thể mất công việc đang chờ sau restart. Video hoàn tất vẫn phải được upload vào Supabase Storage.

Profile này chỉ dành cho single-tenant/trusted-input. Xem [Security](../SECURITY.md) trước khi mở quyền truy cập.

## 1. Chuẩn bị Supabase

1. Tạo project production và bật các Auth provider cần dùng.
2. Thêm URL của Space/custom domain vào Auth Site URL và Redirect URLs.
3. Lấy Project URL, publishable key `sb_publishable_*`, secret key `sb_secret_*`, project ref và database password.
4. Chạy validator local:

   ```bash
   bash backend/supabase/validate_migrations.sh
   ```

5. Với database mới, để workflow CD chạy `supabase db push`. Với database đã tồn tại, đối chiếu `supabase migration list` và làm baseline có kiểm chứng trước lần deploy đầu.
6. Sau migration, hai truy vấn post-deploy trong [Database](DATABASE.md) phải trả về 0 hàng; chạy Supabase Security và Performance Advisors.

Migration tạo bucket `videos` private, chỉ nhận MP4 và giới hạn 1 GiB. Giới hạn toàn cục của gói Supabase vẫn có thể thấp hơn.

## 2. Tạo Hugging Face Space

Tạo Docker Space rồi cấu hình các build Variables:

| Variable | Giá trị |
| --- | --- |
| `VITE_AUTH_MODE` | `jwt` |
| `VITE_SUPABASE_URL` | Supabase Project URL |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | `sb_publishable_*` |
| `VITE_API_BASE_URL` | Để trống để dùng `/v1` cùng origin |
| `VITE_WS_BASE_URL` | Để trống để dùng `/v1` cùng origin |

Các giá trị `VITE_*` được nhúng lúc build và luôn có thể đọc trong browser; tuyệt đối không đặt secret key ở đây.

Cấu hình runtime Secrets:

| Secret | Ghi chú |
| --- | --- |
| `SUPABASE_SECRET_KEY` | `sb_secret_*`, chỉ Backend dùng; legacy alias là `SUPABASE_SERVICE_ROLE_KEY` |
| `INTERNAL_SERVICE_TOKEN` | Chuỗi ngẫu nhiên ít nhất 32 byte, dùng chung nội bộ trong container |
| `GOOGLE_API_KEY` | Một key hoặc danh sách phân cách bằng dấu phẩy; cũng hỗ trợ `_1`, `_2`, ... |
| `SENTRY_DSN` | Tùy chọn |
| `SUPABASE_JWT_SECRET` | Chỉ cho JWT HS256 legacy; bỏ khi đã chuyển sang JWKS |

Cấu hình runtime Variables:

| Variable | Giá trị production |
| --- | --- |
| `APP_ENV` | `production` |
| `AUTH_MODE` | `jwt` |
| `SUPABASE_URL` | Supabase Project URL |
| `SUPABASE_STORAGE_BUCKET` | `videos` |
| `SUPABASE_SIGNED_URL_SECONDS` | `3600`; URL video là bearer URL, không đặt quá 86400 giây. |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` |
| `SUPABASE_JWT_ISSUER` | Tùy chọn; mặc định `<SUPABASE_URL>/auth/v1` |
| `SUPABASE_JWT_JWKS_URL` | Tùy chọn; tự suy ra từ issuer |
| `CORS_ORIGINS` | Để trống cho same-origin hoặc đặt origin chính xác; không dùng `*` |
| `REDIS_URL` / `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` |
| `BACKEND_INTERNAL_URL` | `http://127.0.0.1:7860/internal` |
| `ARTIFACTS_DIR` | `/artifacts` |
| `LOG_LEVEL` | `INFO` |

Root image đã đặt các default nội bộ phù hợp. Không trỏ Redis sang host ngoài trong profile này: Hugging Face chỉ cho outbound qua một số cổng HTTP và current runtime phụ thuộc Redis loopback.

## 3. Cấu hình GitHub

Tạo Environment `production`, bật required reviewers và chỉ cho nhánh `main` deploy.

Environment variables:

- `HF_SPACE_ID`: `namespace/space-name`.
- `SUPABASE_PROJECT_REF`: project ref production.
- `HF_SPACE_URL`: tùy chọn, `https://<slug>.hf.space`; chỉ dùng khi endpoint truy cập được từ GitHub runner.

Environment secrets:

- `HF_TOKEN`: fine-grained write chỉ trên Space đích.
- `SUPABASE_ACCESS_TOKEN`: token dùng bởi Supabase CLI.
- `SUPABASE_DB_PASSWORD`: password của đúng production project.

Không đưa Google/Supabase runtime secret vào GitHub Environment vì workflow không cần đọc chúng; đặt trực tiếp trong Space Settings.

Bảo vệ `main` bằng các job Backend, AI Core, Frontend, migration replay, dependency audit và production image. Workflow deploy dùng đúng SHA đã qua CI, dry-run/push migration, sync Space, rồi kiểm tra trạng thái build/runtime.

## 4. Xác minh sau deploy

```bash
curl --fail https://<space>.hf.space/health
curl --fail https://<space>.hf.space/ready
```

- `/health` chỉ chứng minh FastAPI còn sống.
- `/ready` chỉ trả 200 khi Redis và Supabase sẵn sàng.
- Mở `/`, đăng nhập, tạo một project test, chạy một Builder, render một scene và reload trang để xác nhận video được lấy lại từ private Storage.
- Kiểm tra log có đủ bốn process: `redis`, `backend`, `ai-worker`, `render-worker`.

## Rollback

Ứng dụng rollback bằng cách redeploy một commit đã qua CI và còn tương thích schema. Database migration là forward-only: tạo migration bù đã kiểm thử, không sửa migration đã áp dụng và không chạy `db reset --linked`. Nếu migration thành công nhưng Space build lỗi, dữ liệu không tự rollback; sửa/revert ứng dụng rồi chạy lại CD.
