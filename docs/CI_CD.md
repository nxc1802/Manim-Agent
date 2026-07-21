# CI/CD và triển khai production

Dự án được phát hành dưới dạng **một Hugging Face Docker Space**. Space nhận toàn bộ monorepo, build `Dockerfile` ở thư mục gốc, phục vụ frontend và Backend trên một cổng công khai, đồng thời chạy Redis, AI worker và render worker dưới Supervisor trong cùng container. Supabase là nguồn dữ liệu và artifact bền vững; Redis AOF được lưu dưới `/data/redis` khi Space có persistent storage.

## Luồng phát hành

Workflow `CI` chạy trên mọi pull request vào `main`, mọi push lên `main`, và khi kích hoạt thủ công:

1. Backend: cài dependency khóa phiên bản, `ruff check`, chạy `pytest` trên Python 3.12.
2. AI Core: cài thư viện hệ thống của Manim, dependency khóa phiên bản, `ruff check`, chạy `pytest` trên Python 3.12.
3. Frontend: `npm ci`, lint, test và production build trên Node.js 22.
4. Database: bắt buộc chạy `bash backend/supabase/validate_migrations.sh`; script replay toàn bộ migration trên PostgreSQL tạm thời. Thiếu validator hoặc replay lỗi đều làm CI thất bại.
5. Supply chain: Trivy quét secret đã commit, `pip-audit` kiểm tra các lock file Python, `npm audit` kiểm tra frontend.
6. Image: kiểm tra metadata Docker Space (`sdk: docker`, `app_port: 7860`), build `Dockerfile` gốc với cấu hình frontend JWT giả an toàn, quét CVE `HIGH`/`CRITICAL` có bản vá bằng Trivy, xác nhận entrypoint production từ chối `AUTH_MODE=off`, rồi khởi động đầy đủ profile production bằng placeholder không có quyền truy cập thật. Smoke test đợi `GET /health`, xác nhận bốn process Supervisor, kiểm tra secret đã bị loại khỏi từng process và render một cảnh MathTex 480p thật bằng Manim/TeX/FFmpeg.

Workflow `Deploy production` chỉ chạy khi chính workflow `CI` thành công cho một sự kiện `push` lên `main` từ repository này. Job còn phải vượt qua approval của GitHub Environment `production`. Nó checkout đúng commit SHA đã được CI kiểm tra và từ chối tiếp tục nếu commit đó không còn là HEAD của `main`, tránh một CI cũ hoàn tất muộn rồi ghi đè bản mới. Trước khi migrate, CD xác minh Space đã có đủ Variables/Secrets production; sau đó chạy migration Supabase, đồng bộ monorepo và đợi đúng Hugging Face commit vừa upload đạt `RUNNING`. Cuối cùng, workflow lấy canonical `*.hf.space` URL từ Hub API và bắt buộc `GET /ready` trả JSON có `status: ready`.

`workflow_run` ở đây là ranh giới privilege có chủ đích để secret deploy không bao giờ đi vào job pull request. Các scanner như Zizmor sẽ cảnh báo heuristic `dangerous-triggers` cho mọi `workflow_run`; không được bỏ các gate `success` + `push` + `main` + same-repository, checkout exact SHA, stale-HEAD checks hay Environment approval khi xử lý cảnh báo này.

Runtime poll dùng deadline tuyệt đối 30 phút; readiness poll đích có xác thực dùng tối đa 5 phút. Job deploy có timeout 90 phút để còn đủ thời gian cho checkout, preflight, migration và upload, thay vì cộng các lần `curl` retry ngoài thời lượng dự kiến.

Không có secret production nào được cấp cho pull request hoặc job CI. Workflow deploy dùng quyền GitHub tối thiểu `contents: read`; credential checkout không được giữ lại.

## Cấu hình GitHub

Tạo Environment tên `production` và nên cấu hình:

- Required reviewers cho mọi deployment.
- Deployment branch chỉ cho phép `main`.
- Branch protection của `main` yêu cầu toàn bộ job trong workflow `CI` thành công trước khi merge.
- Không cho phép bỏ qua required checks hoặc force-push lên `main`.

Khai báo các Environment variables sau:

| Tên | Bắt buộc | Ý nghĩa |
| --- | --- | --- |
| `HF_SPACE_ID` | Có | Hugging Face repo theo dạng `namespace/space-name`. |
| `SUPABASE_PROJECT_REF` | Có | Project ref của Supabase production. |

Khai báo các Environment secrets sau:

| Tên | Bắt buộc | Phạm vi tối thiểu |
| --- | --- | --- |
| `HF_TOKEN` | Có | Hugging Face fine-grained token có quyền write **chỉ** trên Space đích. |
| `SUPABASE_ACCESS_TOKEN` | Có | Personal access token dùng bởi Supabase CLI và Management API; fine-grained token phải có quyền database migration write và database read. |
| `SUPABASE_DB_PASSWORD` | Có | Mật khẩu database của đúng project production. |

Không dùng service-role key, Google API key hoặc Redis password làm GitHub deployment secret: workflow không cần và không nên nhìn thấy các giá trị runtime đó.

## Tạo Hugging Face Space

1. Tạo Space trước với SDK `Docker` và cùng ID đã đặt trong `HF_SPACE_ID`. CD cố ý preflight cấu hình trước migration nên không hỗ trợ deploy lần đầu vào một Space chưa tồn tại.
2. Chọn visibility `Private` hoặc `Protected` theo nhu cầu. Workflow vẫn truyền `private: true` cho action sync như lớp phòng vệ, nhưng không thay đổi visibility của Space đã tồn tại; cần kiểm tra thiết lập này khi provisioning.
3. Đảm bảo metadata đầu `README.md` ở root khai báo `sdk: docker` và `app_port: 7860`, khớp với root `Dockerfile`.
4. CD luôn xác minh build/runtime private qua Hugging Face API bằng `HF_TOKEN`, lấy canonical URL do Hub trả về và gửi Bearer token khi gọi `GET /ready`; không cần khai báo URL thủ công, kể cả với Space private.
5. Dùng hardware always-on và persistent storage gắn tại `/data` cho production. Disk mặc định là ephemeral và chỉ phù hợp demo/staging vì Redis chứa queue/lock/render-job coordination; video hoàn tất luôn phải được đưa vào Supabase Storage.

Hugging Face rebuild Space sau mỗi lần đồng bộ. Workflow dùng `huggingface/hub-sync` chính thức tại commit của `v0.2.1`, khóa `hf` CLI `1.24.0`, và root Dockerfile khóa Node/Python base image bằng manifest digest để lần rebuild không đổi nền tảng sau khi CI đã test. Trước khi sync, workflow checkout lại đúng SHA đã qua CI vào một thư mục sạch; file tạm do Supabase CLI tạo không thể lọt vào Space. Action mirror source, xóa file remote không còn trong GitHub, và loại `.git/`, `.github/`. CD đọc revision SHA từ Hub sau khi sync và chỉ chấp nhận `RUNNING` khi runtime báo đúng SHA đó. Nếu đúng revision đang `SLEEPING`, workflow chỉ gọi health endpoint để đánh thức rồi tiếp tục đợi; `BUILD_ERROR`, `CONFIG_ERROR`, `RUNTIME_ERROR`, `NO_APP_FILE`, `STOPPED` hoặc `PAUSED` làm deployment thất bại.

## Runtime variables và secrets trên Hugging Face

Các giá trị này được cấu hình trong **Settings của Space**, độc lập với GitHub Environment.

### Secrets

| Tên | Thành phần dùng |
| --- | --- |
| `INTERNAL_SERVICE_TOKEN` | Backend và worker; cùng một chuỗi ngẫu nhiên ít nhất 32 ký tự, không dùng giá trị mặc định. |
| `GOOGLE_API_KEY` | AI Core; có thể chứa danh sách key theo contract hiện tại. |
| `SUPABASE_SECRET_KEY` | `sb_secret_*`, chỉ Backend; legacy alias là `SUPABASE_SERVICE_ROLE_KEY`. Tuyệt đối không đặt vào biến `VITE_*`. |
| `SUPABASE_JWT_SECRET` | Chỉ cần trong thời gian còn xác thực legacy HS256. Khi Backend dùng JWKS ES256/RS256 thì loại bỏ secret này. |
| `SENTRY_DSN` | Tùy chọn cho quan sát lỗi Backend. |

### Variables

| Tên | Giá trị production gợi ý |
| --- | --- |
| `APP_ENV` | `production` |
| `AUTH_MODE` | `jwt` |
| `PORT` | `7860` |
| `LOG_LEVEL` | `INFO` |
| `CORS_ORIGINS` | Origin chính xác của Space hoặc custom domain, không dùng `*`. |
| `SUPABASE_URL` | URL project production. |
| `SUPABASE_STORAGE_BUCKET` | `videos` |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` |
| `REDIS_PREFIX` | Prefix riêng cho môi trường, ví dụ `manim:prod`. |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` cho profile một Space. |
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` cho profile một Space. |
| `BACKEND_INTERNAL_URL` | `http://127.0.0.1:7860/internal`. |
| `ARTIFACTS_DIR` | Thư mục tạm worker có quyền ghi; artifact phải được upload trước khi job hoàn tất. |
| `DEFAULT_CHAT_MODEL` | Model mặc định của runtime; hiện là bản GA `gemini-3.5-flash`. |
| `VITE_API_BASE_URL` | Để trống; frontend tự dùng `/v1` cùng origin. |
| `VITE_WS_BASE_URL` | Để trống; frontend tự dùng WebSocket `/v1` cùng origin. |
| `VITE_AUTH_MODE` | `jwt` |
| `VITE_SUPABASE_URL` | URL Supabase public dùng lúc frontend build. |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Publishable key public của Supabase, không phải service-role key. Frontend vẫn đọc `VITE_SUPABASE_ANON_KEY` như fallback legacy, nhưng image production dùng tên hiện hành này. |

Docker Spaces truyền Variables vào cả build args và môi trường runtime. Root `Dockerfile` khai báo `ARG` cho các biến `VITE_*` cần lúc `npm run build`. Secrets chỉ được inject vào môi trường runtime trong profile này; workflow không chuyển chúng thành build arg và không ghi chúng vào image layer.

Preflight CD bắt buộc các Variables `APP_ENV=production`, `AUTH_MODE=jwt`, `SUPABASE_URL`, `VITE_AUTH_MODE=jwt`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`; hai URL phải trùng canonical URL được suy ra từ `SUPABASE_PROJECT_REF`. Nó cũng kiểm tra sự hiện diện — không đọc giá trị — của `INTERNAL_SERVICE_TOKEN`, một Supabase secret key và ít nhất một Google provider key. Độ dài token nội bộ và giá trị secret được entrypoint kiểm tra khi container khởi động. Các giá trị runtime vẫn được quản lý trong Hugging Face Space Settings, không sao chép sang GitHub deployment secrets.

Không trỏ `REDIS_URL` ra dịch vụ ngoài đối với profile một Space hiện tại: container đã chạy Redis chỉ bind loopback. Production phải gắn persistent storage của Space vào `/data` để giữ AOF qua restart; nếu không, coi deployment là demo/staging không bền vững. Supabase vẫn là nơi lưu project, trạng thái HITL và video; Redis không được coi là nguồn dữ liệu nghiệp vụ dài hạn.

## Migration production lần đầu

Trước lần deploy đầu tiên, chạy validator local:

```bash
bash backend/supabase/validate_migrations.sh
```

Workflow deploy chạy `supabase db push --dry-run` rồi mới `supabase db push --include-all`. Ngay sau đó, nó gọi endpoint read-only của Supabase Management API và chỉ cho phép promote ứng dụng khi số public constraint chưa validate và số nhóm `(run_id, sequence)` trùng đều bằng `0`. Nếu database production từng được tạo thủ công bằng `init_schema.sql`, cần đối chiếu `supabase migration list` và baseline lịch sử bằng `supabase migration repair` một lần, có kiểm chứng. Không sửa lịch sử migration production một cách tự động và không bỏ qua lỗi đồng bộ.

Migration là forward-only. Nếu migration hoặc integrity gate thất bại, workflow dừng trước khi source mới được đưa lên Hugging Face. Gate có thể thất bại sau khi DDL đã được áp dụng nếu production chứa legacy data bẩn; khi đó cần một migration sửa dữ liệu được review rồi chạy lại, không bỏ qua gate. Nếu source deploy lỗi sau khi migration đã thành công, revert commit ứng dụng hoặc chạy lại workflow với một commit tương thích; không tự động rollback database bằng SQL ngược chưa được kiểm thử.

## Xử lý lỗi CI thường gặp

- `pip-audit` hoặc Trivy thất bại: nâng dependency trực tiếp, tái sinh lock file và chạy lại test; không thêm ignore CVE chỉ để làm xanh pipeline.
- Frontend pass local nhưng fail GitHub: luôn tái hiện bằng `npm ci && npm test`, không dùng `node_modules` cũ; giữ Node major giống workflow.
- Migration replay fail: xem migration đầu tiên báo lỗi trên PostgreSQL sạch, sửa migration mới thay vì sửa file đã áp dụng ở production.
- Space không đạt `RUNNING`: kiểm tra runtime stage và build/run log của đúng revision SHA; `CONFIG_ERROR` thường là metadata hoặc Variable thiếu, còn `RUNTIME_ERROR` thường là entrypoint/Secret production.
- `/ready` trả `503`: kiểm tra kết nối Redis, URL/key Supabase và quyền truy cập bảng; `/health` chỉ là liveness nên không thay thế readiness production.
- `supabase db push` báo lịch sử lệch: dừng deployment, dùng `supabase migration list` để xác định baseline; chỉ dùng `migration repair` sau khi xác minh schema thực tế.

## Tài liệu nền tảng

- [Hugging Face: Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker)
- [Hugging Face: đồng bộ Space bằng GitHub Actions](https://huggingface.co/docs/hub/spaces-github-actions)
- [Supabase: database migrations](https://supabase.com/docs/guides/deployment/database-migrations)
- [Supabase: CLI `db push`](https://supabase.com/docs/reference/cli/supabase-db-push)
