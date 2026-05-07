# Lộ trình phát triển (9 giai đoạn: 8 xây tính năng + 1 gate E2E LLM)

Lộ trình bám **pipeline nội dung + pipeline render** (xem [05_pipeline.md](./05_pipeline.md)). Mỗi phase có **mục tiêu**, **deliverables**, **hạng mục công việc**, **tiêu chí nghiệp vụ** và — **bắt buộc** — mục **Kiểm thử (chuẩn chỉ)**. **Không coi phase là hoàn thành** nếu bộ test được giao cho phase đó chưa xanh trên CI (hoặc quy ước tương đương trên nhánh release).

> **Nguyên tắc kiểm thử:** Mỗi phase đóng bằng **cổng chất lượng (quality gate)** — unit đủ cho logic; integration cho biên (API, DB, Docker); **LLM thật chỉ bắt buộc ở Phase 9** (tránh chi phí và flake trên mọi PR). Các phase 4–8 trong CI mặc định dùng **fake LLM / fixture đã ghi** (VCR) hoặc mock adapter; hành vi schema và pipeline vẫn được kiểm chứng chuẩn chỉ.

---

## Tổng quan 9 phase


| Phase | Tên ngắn                           | Trọng tâm                                              |
| ----- | ---------------------------------- | ------------------------------------------------------ |
| 1     | Nền tảng kỹ thuật                  | Repo, API, cấu hình, contract dữ liệu                  |
| 2     | Primitives & catalog               | Thư viện đồ họa an toàn cho AI                         |
| 3     | Worker & Docker render             | Job queue, Manim chỉ trong container                   |
| 4     | Nội dung: Director → HITL          | Storyboard, Planner (LLM mock trong CI)                |
| 5     | Builder & scene hoàn chỉnh         | Sinh mã function-based + render preview                |
| 6     | Cloud & Auth & Storage             | Supabase, RLS, Storage                                 |
| 7     | Voice & timestamp                  | TTS + timestamps (mock TTS trong CI)                   |
| 8     | Sync, drift, Visual QA, webhook    | Đóng pipeline sản phẩm                                 |
| **9** | **Gate phát hành: E2E + LLM thực** | **Một luồng đầy đủ qua API LLM thật; kiểm tra output** |


---

## Phase 1 — Nền tảng kỹ thuật & API xương sống

**Mục tiêu:** Dịch vụ backend triển khai lặp lại; schema dùng chung (chưa Manim).

**Deliverables**

- FastAPI: health/readiness, Pydantic Settings, logging + correlation id.
- `shared/schemas`: `Project`, `Scene`, `RenderJob` (khớp [09_supabase_schema.md](./09_supabase_schema.md)).
- `backend/core`: CORS (nếu cần), error handler thống nhất.
- Makefile/README dev; `tests/` đã có `unit/`, `integration/`, `e2e/`.

**Hạng mục công việc**

- `requirements.txt` / lockfile; endpoint stub `GET /v1/projects`.
- CI: **lint + typecheck + `pytest tests/unit`** trên mọi PR.

### Kiểm thử (chuẩn chỉ — bắt buộc)

- **Unit:** `GET /health` & `GET /ready` (nếu có) → 200; ít nhất một test lỗi có dạng JSON ổn định (422/404).
- **Unit:** Round-trip / validation cho schema Pydantic quan trọng (`Project`, `Scene` tối thiểu).
- **Tiêu chí xanh:** `pytest tests/unit` không skip bắt buộc; coverage tối thiểu cho module `backend/core` và schemas (ngưỡng do team chọn, ghi vào `pyproject`).

**Tiêu chí xong phase**

- Clone → cài → chạy API → health OK trong vài phút; **CI xanh** với đủ gate unit đã nêu.

---

## Phase 2 — Thư viện Primitives & catalog

**Mục tiêu:** Primitives + catalog cho Builder; giảm mã Manim “tự do”.

**Deliverables**

- 15–20 hàm trong `primitives/`; registry; `GET /v1/primitives/catalog` (read-only).
- Scene mẫu thủ công (không AI), có thể render dev.

**Hạng mục công việc**

- Theme/font; hướng dẫn COPY primitives vào image worker (phase 3).

### Kiểm thử (chuẩn chỉ — bắt buộc)

- **Unit — parametrized:** mọi hàm **public** trong catalog: gọi với tham số tối thiểu, không exception (subset tối thiểu không được nhỏ hơn 80% hàm public trừ khi có `@pytest.mark.skip` có lý do ghi trong code).
- **Unit / contract:** Response `catalog` khớp JSON Schema (hoặc Pydantic) đã commit; thay đổi catalog phải **cập nhật test + schema** cùng PR.
- **Tuỳ chọn:** snapshot hash nội dung catalog để phát hiện drift vô ý.

**Tiêu chí xong phase**

- Catalog embed được vào prompt; **toàn bộ gate unit phase 2 xanh**; ít nhất một scene demo render (local hoặc chờ phase 3 nếu chỉ worker).

---

## Phase 3 — Worker, Docker & pipeline render

**Mục tiêu:** Manim chỉ trong worker + Docker; API chỉ enqueue.

**Deliverables**

- Dockerfile (ManimCE + FFmpeg + font, pin version); consumer job; materialize → `docker run` → upload → cập nhật job.
- `POST /v1/projects/{id}/render` thật (enqueue).

**Hạng mục công việc**

- Timeout, disk quota, preview vs full profile.

### Kiểm thử (chuẩn chỉ — bắt buộc)

- **Unit:** Máy trạng thái job (`queued` → `rendering` → `completed`/`failed`) với store giả (in-memory) hoặc DB test.
- **Integration (`@pytest.mark.integration`):** một scene `.py` **cố định trong repo** → worker/container → file video tồn tại, kích thước > 0, duration trong ngưỡng; nhánh `failed` (ví dụ syntax Manim sai) có log.
- **CI:** PR có thể **không** chạy integration Docker (tùy tài nguyên); nhưng **nhánh `main` / trước merge release** phải chạy integration này (hoặc nightly bắt buộc xanh trước khi tag). Ghi rõ trong `CONTRIBUTING`.

**Tiêu chí xong phase**

- Scene cố định render được qua worker; **gate integration đã định nghĩa xanh trên pipeline bắt buộc của team**.

---

## Phase 4 — Director, Planner, HITL storyboard

**Mục tiêu:** Vòng C1–C4a; chưa bắt buộc TTS/sync.

**Deliverables**

- Director + lưu scene; API HITL duyệt storyboard; Planner → `planner_output` JSON.
- JSON Schema / Pydantic cho `planner_output`; prompt versioning.

### Kiểm thử (chuẩn chỉ — bắt buộc)

- **Unit:** Validate `planner_output` với ví dụ golden (file JSON trong `tests/fixtures/`) — valid/invalid cases.
- **Integration:** Gọi pipeline Director→Planner với `**FakeLLMClient`** (trả JSON cố định): assert DB đúng trạng thái, `planner_output` parse được.
- **Integration:** Luồng HITL: từ `draft` → `approved` (hoặc flag tương đương) chỉ qua endpoint cho phép.

**Tiêu chí xong phase**

- Luồng tạo project → storyboard → approve → `planner_output` hợp lệ; **không có LLM thật trong gate bắt buộc của PR** (dùng fake/fixture).

---

## Phase 5 — Builder & scene hoàn chỉnh

**Mục tiêu:** C7: Builder → `manim_code` → DB → enqueue preview render.

**Deliverables**

- Builder + function-based output; `manim_code_version`; API trigger generate + render preview.

**Hạng mục công việc**

- Sandbox import whitelist; giới hạn kích thước mã.

### Kiểm thử (chuẩn chỉ — bắt buộc)

- **Unit:** `ast.parse` trên output Builder (fixture từ fake LLM); deny-list import (không `os.system`, không `subprocess` nếu policy cấm).
- **Integration:** `planner_output` fixture → Builder (fake LLM) → mã lưu DB → enqueue → worker render (có thể tái dùng test phase 3) → file video tồn tại.
- **Regression:** Mỗi bug sinh mã sai → thêm một fixture + assert lỗi đó không tái diễn.

**Tiêu chí xong phase**

- Preview video từ planner fixture; **full gate phase 5 xanh** (unit + integration đã chọn).

---

## Phase 6 — Supabase: Auth, DB, Storage, RLS

**Mục tiêu:** Production-like; JWT Bearer.

**Deliverables**

- Migration đầy đủ [09](./09_supabase_schema.md); Storage paths; middleware auth.

**Hạng mục công việc**

- Service role worker hoặc RPC an toàn; backup/retention.

### Kiểm thử (chuẩn chỉ — bắt buộc)

- **Integration (Supabase test project hoặc local Postgres + policy tương đương):** User A **không** đọc/ghi project của User B (RLS) — tối thiểu 2 JWT test.
- **Integration:** Upload metadata `assets` / signed URL theo policy (nếu dùng).
- **Unit:** Parse JWT mock → `user_id` đúng cho dependency API.

**Tiêu chí xong phase**

- RLS và auth được chứng minh bằng test tự động; không chỉ kiểm tay.

---

## Phase 7 — Voice, TTS, timestamp

**Mục tiêu:** C4b: audio + `timestamps` JSONB.

**Deliverables**

- Voice Agent; TTS provider; alignment fallback; API voice.

**Hạng mục công việc**

- Versioning audio; loudness (tuỳ chọn).

### Kiểm thử (chuẩn chỉ — bắt buộc)

- **Unit:** Normalization / merge schema `timestamps` (shape, sorted time, không overlap âm).
- **Integration với `MockTTS`:** trả file wav/mp3 giả + JSON timestamp cố định → lưu DB đúng cột.
- **Staging (tuỳ chọn, không chặn PR):** một test manual hoặc scheduled job gọi TTS thật với key staging.

**Tiêu chí xong phase**

- Pipeline voice ổn định trên mock; schema đủ cho phase 8.

---

## Phase 8 — Sync, drift, Visual QA, webhook

**Mục tiêu:** C5–C9 + Q1–Q3 đóng sản phẩm MVP+ .

**Deliverables**

- `sync_segments`; Builder merge; `sync_report`; overlap cơ bản; vòng **Code Reviewer + Visual Reviewer** (mỗi round cả hai); webhook.

### Kiểm thử (chuẩn chỉ — bắt buộc)

- **Unit:** Sync Engine — input timestamps + script → segment output khớp golden; edge: segment rỗng, một từ.
- **Unit:** Drift calculation (nếu có pure function) với số liệu giả.
- **Integration:** Webhook nhận POST (dùng test server / respx) khi job `completed` (mock job completion).
- **Integration:** Visual QA trả JSON schema cố định (mock vision API).

**Tiêu chí xong phase**

- Video có thoại trên môi trường staging hoặc fixture end-to-end nội bộ (vẫn có thể mock vision/TTS); **gate phase 8 xanh**.

---

## Phase 9 — Gate phát hành: E2E với **API LLM thực**

**Mục tiêu:** Trước khi gắn **tag release** (hoặc bàn giao milestone khách hàng), chạy **một hoặc vài kịch bản E2E** đi qua toàn bộ pipeline có **gọi LLM provider thật** (LiteLLM/OpenRouter/… tuỳ cấu hình), **không** dùng fake response body — để phát hiện thay đổi model, rate limit, format JSON lệch, suy giảm chất lượng prompt.

**Deliverables**

- `tests/e2e/test_pipeline_real_llm.py` (hoặc tương đương), đánh dấu `@pytest.mark.e2e`.
- Tài liệu: `OPENROUTER_API_KEY`, **ngân sách token** và prompt cố định ngắn (một brief đã chọn trước).
- **Skip có kiểm soát:** nếu thiếu `OPENROUTER_API_KEY` → `pytest.skip` (local / fork PR); trên repo chính nên cấu hình secret để job CI chạy thật.

### Kiểm thử (chuẩn chỉ — bắt buộc cho release)

- **E2E LLM:** Luồng tối thiểu: tạo project → Director (LLM thật) → (có thể auto-approve storyboard trong test hoặc gọi API set trạng thái) → Planner (LLM thật nếu tách) → Voice **có thể** vẫn mock TTS để giảm chi phí **hoặc** TTS thật nếu policy cho phép — **ít nhất một bước LLM text reasoning phải là thật** (Director + Planner hoặc gộp).
- **Assert output (không chỉ “200 OK”):**
  - `storyboard_text` / `planner_output` không rỗng và pass schema.
  - `manim_code` sinh ra parse được `ast.parse`, pass deny-import.
  - Render job hoàn thành → **file video** tồn tại, `duration > 0`, kích thước tối thiểu.
  - (Nếu đã bật sync) `sync_segments` hoặc `sync_report` tồn tại và pass schema tối thiểu.
- **Ổn định:** Chạy **ít nhất 3 lần** trên staging trước release; ghi nhận flakiness; ngưỡng timeout rõ.

**Tiêu chí xong phase / release**

- **Phase 9 xanh** trên môi trường có secret; artifact (log + hash prompt version) lưu cho audit.

---

## Chiến lược kiểm thử (`tests/`) — tóm tắt vận hành


| Thư mục / marker                      | Khi chạy                              | Nội dung                                              |
| ------------------------------------- | ------------------------------------- | ----------------------------------------------------- |
| `tests/unit/`                         | Mọi PR, local trước push              | Nhanh, không mạng ngoài, không Docker (trừ pure lib). |
| `tests/integration/`                  | PR hoặc `main` (tuỳ Docker/Supabase)  | API, DB, worker, webhook mock.                        |
| `tests/e2e/` + `@pytest.mark.e2e` | **Trước tag release**; có thể nightly; CI `main`/PR | **LLM thật** khi có secret; không có key thì skip. |



| Sự kiện                    | Lệnh / hành vi                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------ |
| PR hàng ngày               | `pytest tests/unit` (+ integration nhẹ không tốn kém).                               |
| Merge `main` / pre-release | + integration Docker/Supabase theo quy ước repo.                                     |
| **Release tag**            | `pytest tests/e2e -m e2e` với `OPENROUTER_API_KEY` (job CI trên `main` hoặc chạy tay) **nên xanh** trước khi tag. |


**Build Docker** không thay thế pytest. **LLM thật** không chạy trên mọi commit để tránh chi phí và flake; tập trung vào **Phase 9** và nhánh release.

---

## Phụ lục: phụ thuộc chéo & rủi ro

- Phase 3 phụ thuộc Phase 2 (primitives trong image).
- Phase 5 song song một phần Phase 4 khi schema `planner_output` ổn.
- Phase 7–8: versioning audio/code (`manim_code_version`) để test E2E lặp lại có ý nghĩa.
- **Phase 9:** rủi ro chi phí API và độ lệch model — dùng prompt ngắn, model cố định, và có thể **chốt phiên bản model** trong config release.

---

## Sau Phase 9 (mở rộng, không chặn gate tối thiểu)

- Plugin primitives; pool worker; preview UI; multi-tenant nâng cao.

---

*Trở về tập chỉ mục:* [00_index.md](./00_index.md)