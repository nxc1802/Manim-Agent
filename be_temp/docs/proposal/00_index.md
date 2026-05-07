# Hệ sinh thái AI Manim Agent: Bộ Tài liệu Đề xuất
## (Cinematic Technical Video Generation Ecosystem)

Chào mừng bạn đến với bộ tài liệu chi tiết về dự án **AI Manim Agent**. Tài liệu này được chia nhỏ thành các phần chuyên biệt để cung cấp cái nhìn sâu sắc nhất về cấu trúc, vận hành và lộ trình của hệ thống.

---

## 📑 Danh mục Tài liệu

### 1. [Triết lý & Tầm nhìn](./01_philosophy.md)
*   Insight cốt lõi về việc kiểm soát sự hỗn loạn trong sản xuất video AI.
*   Ba nguyên tắc: sinh mã theo chức năng, phân rã quy trình, ưu tiên đồng bộ âm–hình.

### 2. [Kiến trúc & Hạ tầng](./02_architecture.md)
*   Sơ đồ kiến trúc tổng thể (Mermaid).
*   Phân tách **API (FastAPI)** và **Worker render (Manim trong Docker)**.

### 3. [Đặc tả Hệ thống Đa Đại lý (Agents)](./03_agents.md)
*   Chi tiết vai trò của Director, Voice, Planner, Builder, **Code Reviewer**, **Visual Reviewer**, vòng lặp review & dừng sớm.
*   Các điểm Human-in-the-loop (HITL).

### 4. [Hệ thống Primitives](./04_primitives.md)
*   Danh mục thành phần đồ họa căn bản (Visual, Motion).
*   Quy tắc đăng ký và catalog cho Builder.

### 5. [Pipeline sản xuất & đồng bộ âm–hình](./05_pipeline.md)
*   Pipeline nội dung (C1–C9), pipeline render worker (R1–R8), QA (Q1–Q3).
*   Sync Engine như một giai đoạn; phụ lục rủi ro sync thực tế.

### 6. [Đặc tả API Backend](./06_api_specification.md)
*   Endpoints quản lý Job, Storyboard và Render (enqueue tới worker).

### 7. [Lộ trình Phát triển (Roadmap)](./07_roadmap.md)
*   **9 phase:** 8 phase xây tính năng — **mỗi phase có gate kiểm thử chuẩn chỉ**; phase **9** là gate phát hành: **E2E với API LLM thực**, kiểm tra output (video, schema, v.v.).

### 8. [Cấu trúc Dự án & Mã nguồn](./08_project_structure.md)
*   Cây thư mục và quy chuẩn function-based; worker là nơi duy nhất chạy Manim trong container.

### 9. [Đặc tả Cơ sở dữ liệu (Supabase)](./09_supabase_schema.md)
*   Schema PostgreSQL đầy đủ: index, trigger `updated_at`, RLS cho mọi bảng nghiệp vụ.

---

*Tóm tắt điều hành:* [docs/proposal.md](../proposal.md)
