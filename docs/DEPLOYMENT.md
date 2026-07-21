# Triển khai production

## Profile được hỗ trợ

- Vercel phục vụ React/Vite SPA.
- Một Hugging Face Docker Space `Protected` chạy FastAPI, Redis, AI worker và
  render worker.
- Supabase cung cấp Auth, Postgres và private Storage.

Space là profile single-tenant/trusted-input; mã Manim sinh tự động chưa chạy
trong sandbox cô lập hoàn chỉnh. Dùng hardware always-on và persistent storage
gắn tại `/data` để Redis AOF không mất queue/lock khi restart.

## 1. Supabase

1. Tạo project production và bật Auth provider.
2. Thêm origin Vercel vào Auth Site URL và Redirect URLs.
3. Lấy Project URL, publishable key, secret key, project ref và database
   password.
4. Chạy local:

   ```bash
   bash backend/supabase/validate_migrations.sh
   ```

5. Để GitHub Actions áp dụng full ordered migration chain. Sau deploy, cả tám
   counter trong `backend/supabase/postmigration_gate.sql` phải bằng 0.

Migration tạo private bucket `videos`, chỉ nhận MP4 và giới hạn object 1 GiB.

## 2. Hugging Face

Tạo trước một Docker Space với visibility **Protected**, port `7860`, always-on
hardware và persistent `/data`. Private Space không dùng được với browser
Vercel vì không được đưa `HF_TOKEN` cho client.

Runtime Variables:

| Variable | Giá trị production |
| --- | --- |
| `APP_ENV` | `production` |
| `AUTH_MODE` | `jwt` |
| `SUPABASE_URL` | Supabase Project URL |
| `CORS_ORIGINS` | Origin Vercel chính xác, không `*` |
| `SUPABASE_STORAGE_BUCKET` | `videos` |
| `SUPABASE_SIGNED_URL_SECONDS` | `3600` |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` |
| `REDIS_URL` / `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` |
| `BACKEND_INTERNAL_URL` | `http://127.0.0.1:7860/internal` |
| `ARTIFACTS_DIR` | `/artifacts` |

Runtime Secrets:

| Secret | Ghi chú |
| --- | --- |
| `SUPABASE_SECRET_KEY` | Backend only; legacy alias `SUPABASE_SERVICE_ROLE_KEY` |
| `INTERNAL_SERVICE_TOKEN` | Chuỗi ngẫu nhiên ít nhất 32 ký tự, dùng nội bộ |
| `GOOGLE_API_KEY` / numbered pool | AI/render provider keys |
| `SUPABASE_JWT_SECRET` | Chỉ cho HS256 legacy; bỏ khi dùng JWKS |
| `SENTRY_DSN` | Tùy chọn |

Không đặt biến `VITE_*` trên Space. Frontend không còn nằm trong HF image.

## 3. Vercel

Tạo Vercel project và đặt Root Directory là `frontend`. Tắt Git auto-deploy vì
GitHub Actions là deployment authority; nếu để cả hai, mỗi commit frontend sẽ
tạo hai deployment.

Production Environment Variables:

| Variable | Giá trị |
| --- | --- |
| `VITE_AUTH_MODE` | `jwt` |
| `VITE_API_BASE_URL` | `https://<space>.hf.space/v1` |
| `VITE_WS_BASE_URL` | `https://<space>.hf.space/v1` |
| `VITE_SUPABASE_URL` | Supabase Project URL |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Public publishable key |

`frontend/vercel.json` cấu hình Vite build output và rewrite deep-link SPA. Build
production không đọc `frontend/.env` của developer.

## 4. GitHub

Tạo Environment `production`, bật required reviewers và chỉ cho `main` deploy.

Environment Variables:

- `HF_SPACE_ID=namespace/space-name`
- `HF_SPACE_ORIGIN=https://<canonical-space-host>.hf.space`
- `SUPABASE_PROJECT_REF=<20-character-ref>`
- `VERCEL_PRODUCTION_ORIGIN=https://<canonical-domain>`

Environment Secrets:

- `HF_TOKEN`: fine-grained write chỉ trên Space.
- `SUPABASE_ACCESS_TOKEN` và `SUPABASE_DB_PASSWORD`.
- `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`.

Bảo vệ `main` bằng required check `CI Gate`. Workflow tự chọn target theo
production dependency graph; docs-only không deploy, frontend-only chỉ Vercel,
runtime-only chỉ HF, migration-only chỉ Supabase.

## Xác minh sau deploy

```bash
curl --fail https://<space>.hf.space/health
curl --fail https://<space>.hf.space/ready
curl --fail https://<vercel-production-origin>/
```

- Space `/health` là liveness; `/ready` chỉ trả 200 khi Redis/Supabase sẵn sàng
  và worker đang consume đủ queue `ai`, `render`. Docker healthcheck còn yêu cầu
  `redis`, `backend`, `ai-worker`, `render-worker` đều `RUNNING`.
- Vercel root và deep-link như `/settings` phải trả SPA.
- Đăng nhập, tạo project, chạy HITL, render scene và reload để xác nhận video
  được lấy lại từ private Storage.
- HF log phải có `redis`, `backend`, `ai-worker`, `render-worker` ở trạng thái
  `RUNNING`.

## Rollback

Revert bằng commit mới trên `main` đã qua CI. GitHub Deployments baseline ngăn
CI cũ ghi đè revision mới. Migration là forward-only: tạo migration bù, không
sửa migration đã apply và không chạy `db reset --linked` trên production.
