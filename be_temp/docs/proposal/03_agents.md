# Đặc tả Hệ thống Đa Đại lý (Multi-Agent System)

Kiến trúc hệ thống dựa trên sự phối hợp của các đại lý chuyên biệt, được thiết kế để tối ưu hóa quy trình từ kịch bản đến video hoàn thiện.

---

## 1. Danh sách các Đại lý AI

### 1.1 Director Agent (Creative & Scripting)

- **Nhiệm vụ:** Tạo storyboard văn bản và kịch bản thuyết minh thô.
- **Mục tiêu:** Mạch truyện logic, phù hợp giáo dục kỹ thuật.

### 1.2 Voice Agent (Audio & Emotional Layer)

- **Nhiệm vụ:** 
  - Tinh chỉnh kịch bản thuyết minh (ngắt nghỉ, nhấn mạnh).
  - Giọng đọc (Voice ID), tham số cảm xúc (stability, clarity).
  - Gọi TTS, thu **timestamps** (ưu tiên word-level từ nhà cung cấp; fallback alignment).
- **Output:** URL hoặc path file âm thanh + cấu trúc timestamps (lưu DB/Storage).

### 1.3 Planner Agent (Logic Mapping)

- **Nhiệm vụ:** Từ storyboard đã duyệt, xác định primitives / cảnh / bước hình ảnh cần cho Builder.
- **Output:** Kế hoạch có cấu trúc (JSON) — contract rõ ràng cho Builder.

### 1.4 Sync Engine (không phải “LLM agent” nhưng là bước bắt buộc)

- **Nhiệm vụ:** Gộp script thoại + timestamps thành **timeline segments** (beat / cụm từ / câu), tính khoảng trống, gợi ý anchor cho từng `step_n` của scene.
- **Mục tiêu:** Chuẩn hóa đầu vào thời gian để Builder không tự đoán mơ hồ từ raw JSON TTS.

### 1.5 Builder Agent (Writer — Code Generation)

- **Nhiệm vụ:** Sinh mã Manim Python **chỉ khi** đã có `Planner output` + `Sync timeline` + (tuỳ chọn) bản thoại cuối.
- **Nguyên tắc:** Function-based; `self.wait` / `run_time` bám segment, không magic number tách rời timeline.

### 1.6 Code Reviewer Agent (Review 1 — nguồn)

- **Nhiệm vụ:** Đọc **mã nguồn** Manim (và có thể diff so với vòng trước); báo cáo có cấu trúc: lỗi logic Manim, API ManimCE dùng sai, vi phạm quy ước function-based, mùi mã dễ gây crash render, gợi ý sửa có nhắm mục tiêu.
- **Output:** JSON (ví dụ `issues[]` với `severity`, `location`, `suggestion`) — **không** thay thế các kiểm tra tĩnh bắt buộc (`ast.parse`, deny-import); kết hợp **AND** với tĩnh trong tiêu chí `code_review_passed`.

### 1.7 Visual Reviewer Agent (Review 2 — hình)

- **Nhiệm vụ:** Đọc **frame hoặc video preview** đã render; phát hiện overlap, chữ tràn, khoảng trắng, cân bố cục, v.v. (vision model).
- **Output:** JSON `issues[]` tương thích pipeline với Code Reviewer để orchestrator dừng sớm thống nhất.

---

## 2. Quy trình Phối hợp (Interaction Flow)

1. Người dùng duyệt **storyboard** từ Director (HITL 1).
2. Song song: **Planner** (đồ họa) và **Voice** (audio + timestamps).
3. **Sync Engine** làm giàu timeline từ đầu ra Voice (và text đã khóa).
4. **Builder** nhận merge từ bước 2–3, sinh mã, lưu DB; có thể vào **vòng Builder ↔ hai Reviewer** (mục 4) trước khi coi mã “đủ chất lượng render hàng loạt”.
5. **Worker + Docker** render preview/final; artefact phục vụ Visual Reviewer.
6. Sau vòng review tự động (nếu có): **HITL cuối** với người; revision có thể quay lại Builder hoặc chỉnh audio/plan.

---

## 3. Cấu hình tên model theo từng agent

**Trạng thái repo:** file mẫu `[ai_engine/config/agent_models.example.yaml](../../ai_engine/config/agent_models.example.yaml)` khai báo riêng `code_reviewer` và `visual_reviewer`. `llm_client` đọc `agent_models.yaml` (bản copy) và có thể override bằng env.

- **Chuỗi model:** LiteLLM (`provider/model`).
- **Code Reviewer:** thường model text mạnh, nhiệt độ thấp.
- **Visual Reviewer:** model **có vision**; có thể khác model Builder.
- **Sync Engine:** model nhỏ, nhiệt độ thấp.

---

## 4. Vòng lặp Builder ↔ hai Reviewer (code + visual) & dừng sớm

**Writer** = Builder. **Mỗi vòng lặp (round)** luôn gồm **đủ hai bước review** trước khi quyết định dừng sớm hay vào round tiếp theo:

1. **Builder** sinh hoặc sửa mã (round 1 từ đầu; round sau nhận góp ý có cấu trúc từ hai reviewer).
2. **Review 1 — Code:** kiểm tra tĩnh (bắt buộc) + **Code Reviewer Agent** (LLM) trên source.
3. **Render preview** nếu cần cho bước 4 (có thể bỏ qua preview chỉ khi policy cho phép “chỉ code” một vòng — mặc định nên có preview trước visual khi mã đã qua gate tĩnh).
4. **Review 2 — Visual:** **Visual Reviewer Agent** trên frame/video.

Giới hạn vòng: `**max_rounds`** trong YAML, **mặc định 3** (xem `builder_review_loop.max_rounds` trong file mẫu).

### 4.1 Dừng sớm (early stop)

Sau khi **cả hai** review trong **cùng một round** đã có kết quả, orchestrator đánh giá `**early_stop.require_all`** (logic **AND**):

- `**code_review_passed`:** tất cả tiêu chí bật trong `pass_criteria.code_review_passed` (ví dụ: không còn issue blocking từ agent code review, `ast.parse` ok, deny-import ok). Mức “blocking” so với `blocking_severity_min` (mặc định từ `warning` trở lên là chặn).
- `**visual_review_passed`:** tương tự theo `pass_criteria.visual_review_passed` trên output Visual Reviewer.

Chỉ khi **cả hai** nhánh đều `passed` → **thoát vòng lặp ngay** (dù chưa dùng hết `max_rounds`). Nếu **một trong hai** chưa pass và **số round vẫn nhỏ hơn `max_rounds`** → Builder vào round tiếp với feedback hợp nhất từ hai báo cáo. Nếu **đạt `max_rounds`** mà vẫn chưa đủ điều kiện dừng sớm → `on_max_rounds_exceeded` (HITL hoặc fail), cấu hình trong YAML.

### 4.2 Tuỳ chọn

- `**stop_when_only_info_severity`:** nếu `true`, có thể nới tiêu chí “blocking” (rủi ro cao hơn; cân nhắc kỹ).
- **Tiết kiệm:** round đầu có thể chạy đủ tĩnh + code reviewer trước; chỉ enqueue preview khi tĩnh đã sạch — nhưng **một khi vào visual review**, round đó vẫn tính là đã thực hiện đủ hai review theo policy (tránh “visual không chạy nhưng vẫn coi là pass”).

---

*Trở về tập chỉ mục:* [00_index.md](./00_index.md)