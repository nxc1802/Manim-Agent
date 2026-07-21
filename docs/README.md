# Tài liệu Manim Agent

| Tài liệu | Khi nào cần đọc |
| --- | --- |
| [Architecture](ARCHITECTURE.md) | Thay đổi boundary, HITL pipeline, queue, cache hoặc artifact flow |
| [Deployment](DEPLOYMENT.md) | Tạo Supabase/Hugging Face/GitHub production từ đầu |
| [CI/CD](CI_CD.md) | Cấu hình required checks, Environment approval và xử lý workflow lỗi |
| [Database](DATABASE.md) | Viết/replay/push migration, RLS, grants, Storage và data repair |
| [Operations](OPERATIONS.md) | Healthcheck, log, backup, rollback, worker/Redis incident |
| [Frontend API](FRONTEND_API.md) | Thay đổi REST/WebSocket contract mà frontend sử dụng |
| [Settings](SETTINGS_SPECIFICATION.md) | Thay đổi user settings, model/review/TTS/render options |
| [Frontend features](frontend_features.md) | Hành vi HITL, state scene và reconciliation thời gian thực |
| [Security](../SECURITY.md) | Trust boundary, secret ownership và hạn chế của code execution |

Nguồn schema deploy duy nhất nằm tại `backend/supabase/migrations/`. Hướng dẫn ngắn dành riêng cho database ở [backend/supabase/README.md](../backend/supabase/README.md).

