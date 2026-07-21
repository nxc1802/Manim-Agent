---
title: Manim Agent
emoji: 🎬
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Manim Agent

Manim Agent biến một ý tưởng giáo dục thành storyboard, mã Manim có vòng review, video từng cảnh và video hoàn chỉnh. Frontend React trên Vercel cung cấp HITL; FastAPI trên Hugging Face quản lý quyền truy cập và trạng thái; Celery chạy AI/review/render; Supabase lưu dữ liệu và video bền vững.

## Kiến trúc triển khai

Bản phát hành production dùng **Vercel cho frontend** và **một Hugging Face
Docker Space cho API/AI/render runtime**:

```mermaid
flowchart LR
  U["Browser"] --> WEB["React SPA\nVercel"]
  WEB -->|"HTTPS + WebSocket"| API["FastAPI :7860\nHugging Face"]
  API --> DB["Supabase\nAuth + Postgres + Storage"]
  API --> R[("Redis AOF")]
  R --> AI["Celery AI worker\nconcurrency 1"]
  R --> Render["Celery render worker\nconcurrency 1"]
  AI -->|"internal callback"| API
  Render -->|"internal callback + artifact"| API
```

Monorepo vẫn giữ ranh giới rõ:

| Thư mục | Trách nhiệm |
| --- | --- |
| `frontend/` | React/Vite trên Vercel, Supabase Auth, REST và WebSocket tới HF |
| `backend/` | FastAPI, authorization, Supabase, HITL, cache và điều phối queue |
| `ai_core/` | LLM, review loop, TTS, Manim và Celery workers |
| `shared/` | Pydantic contracts dùng chung, không chứa persistence/runtime |
| `deploy/huggingface/` | Supervisor, Redis và entrypoint cho Space |

Space phải dùng visibility **Protected** để browser trên Vercel gọi được API
trong khi source vẫn kín. Đây là profile **single-tenant, trusted-input**: mã
Python Manim sinh tự động không chạy trong sandbox bảo mật hoàn chỉnh. Không
dùng profile này làm dịch vụ thực thi code công khai cho nhiều tenant. Lộ trình
tách ba dịch vụ được mô tả trong [kiến trúc](docs/ARCHITECTURE.md).

## Chạy local

Yêu cầu: Docker + Docker Compose, Node.js 22 nếu chạy frontend dev, Python 3.12 nếu chạy service trực tiếp, một Supabase project và Google API key cho luồng AI thật.

```bash
cp backend/.env.example backend/.env
cp ai_core/.env.example ai_core/.env
cp frontend/.env.example frontend/.env
```

Điền cấu hình cần thiết, sau đó:

```bash
bash backend/supabase/validate_migrations.sh
docker compose up --build
```

Ở terminal khác:

```bash
cd frontend
npm ci
npm run dev
```

- Frontend: `http://localhost:5173`
- Backend OpenAPI: `http://localhost:8000/docs`
- Backend liveness/readiness: `/health`, `/ready`
- AI Core chỉ được expose trong mạng Compose tại cổng `8001`

`AUTH_MODE=off` và `VITE_AUTH_MODE=off` chỉ dành cho local. Production bắt buộc JWT.

## Kiểm tra trước khi phát hành

```bash
make check       # lint + 3 test suites + frontend build + migration replay
make audit       # Python locks + npm vulnerability audit
make image       # build image API/AI/render dùng cho Hugging Face
```

Dependency Python production/dev được khóa bằng hash trong `requirements*.lock`; frontend dùng `package-lock.json`. `backend/supabase/migrations/*.sql` là nguồn schema duy nhất có thể deploy; `init_schema.sql` chỉ là marker tương thích và không được chạy.

## Deploy

1. Tạo Supabase production project, Hugging Face Docker Space `Protected`, và Vercel project có root directory `frontend`.
2. Cấu hình Space/Vercel Variables và Secrets theo [hướng dẫn deployment](docs/DEPLOYMENT.md).
3. Tạo GitHub Environment `production`, thêm các biến target và deployment credentials.
4. Bảo vệ nhánh `main` bằng required check ổn định `CI Gate`.
5. Tắt Vercel Git auto-deploy để tránh deploy kép; GitHub Actions sẽ build prebuilt output và promote production.
6. Merge/push vào `main`. CD chỉ chạy target có artifact production thay đổi: migration → Supabase, frontend → Vercel, Backend/AI/shared/runtime → Hugging Face.

Các tên key hiện hành được ưu tiên:

- Browser build: `VITE_SUPABASE_PUBLISHABLE_KEY` (`sb_publishable_*`).
- Backend runtime: `SUPABASE_SECRET_KEY` (`sb_secret_*`).
- Legacy `anon`/`service_role` vẫn được chấp nhận trong giai đoạn chuyển đổi.
- JWT ES256/RS256 được xác minh qua Supabase JWKS; chỉ cấu hình `SUPABASE_JWT_SECRET` khi còn dùng HS256 legacy.

Không commit `.env`, service key hoặc Google key. File `frontend/.env` cũ đã được loại khỏi tracking; production build cũng không đọc file `.env` của developer.

## Tài liệu

- [Mục lục tài liệu](docs/README.md)
- [Kiến trúc và state machine](docs/ARCHITECTURE.md)
- [Deployment Vercel + Hugging Face + Supabase](docs/DEPLOYMENT.md)
- [CI/CD](docs/CI_CD.md)
- [Database và migration](docs/DATABASE.md)
- [Vận hành và khôi phục](docs/OPERATIONS.md)
- [Security model](SECURITY.md)
- [Frontend API contract](docs/FRONTEND_API.md)
