# PROJECT PROPOSAL: AI MANIM AGENT (Executive Summary)
## Cinematic Technical Video Generation Ecosystem

**Trọng tâm:** Thiết kế Hệ thống AI & Backend (Direct Code Generation & Sync Focus)

---

## 1. Tóm tắt Điều hành (Executive Summary)

Dự án này hướng tới việc xây dựng một **Hệ sinh thái AI Agent** tự động hóa quy trình sản xuất video kỹ thuật đỉnh cao. Thay vì sử dụng các lớp ngôn ngữ trung gian (DSL) phức tạp, hệ thống tập trung vào việc **sinh mã nguồn Python trực tiếp** và **đồng bộ hóa hoạt ảnh với âm thanh** một cách tuyệt đối.

### Các thành phần cốt lõi:
1.  **Direct Code Gen (No-DSL):** AI sinh trực tiếp mã Manim Python, tối ưu hóa tốc độ và khả năng tùy biến.
2.  **Function-based Project Structure:** Quy chuẩn hóa mã nguồn thành các hàm nhỏ để dễ quản lý và bảo trì.
3.  **Voice & Sync Engine:** Sử dụng dữ liệu Word-level Timestamps để khớp chính xác từng giây thoại với từng hiệu ứng hình ảnh.
4.  **Primitive Helper Library:** Một thư viện các hàm Python chuẩn giúp AI tạo lập đồ họa chuyên nghiệp và đồng nhất.

---

## 2. Truy cập Tài liệu Chi tiết

Để tìm hiểu sâu hơn về kiến trúc mới (không DSL) và cơ chế đồng bộ âm thanh, vui lòng tham khảo các phần sau:

*   📑 **[Chỉ mục Tổng (Index)](file:///Volumes/WorkSpace/Project/Manim_Agent/docs/proposal/00_index.md)** - Cổng vào toàn bộ tài liệu.
*   🧠 **[Triết lý & Tầm nhìn mới](file:///Volumes/WorkSpace/Project/Manim_Agent/docs/proposal/01_philosophy.md)** - Loại bỏ DSL, tập trung vào Functional Code.
*   🏗️ **[Kiến trúc & Hạ tầng Sync](file:///Volumes/WorkSpace/Project/Manim_Agent/docs/proposal/02_architecture.md)** - Luồng tích hợp Voice Agent và Sync Engine.
*   🤖 **[Đặc tả AI Agents](file:///Volumes/WorkSpace/Project/Manim_Agent/docs/proposal/03_agents.md)** - Chi tiết về Voice Agent và Builder Agent.
*   🎨 **[Thư viện Primitive Helpers](file:///Volumes/WorkSpace/Project/Manim_Agent/docs/proposal/04_primitives.md)** - Các hàm tiện ích Python thay thế cho DSL.
*   🎬 **[Pipeline Sync & Audio](file:///Volumes/WorkSpace/Project/Manim_Agent/docs/proposal/05_pipeline.md)** - Quy trình đồng bộ hóa Timeline chi tiết.
*   📡 **[Đặc tả API Backend](file:///Volumes/WorkSpace/Project/Manim_Agent/docs/proposal/06_api_specification.md)** - Các Endpoints cho Audio và Module Code.
*   🛤️ **[Lộ trình Phát triển mới](file:///Volumes/WorkSpace/Project/Manim_Agent/docs/proposal/07_roadmap.md)** - Ưu tiên Voice Sync và Cinematic Polish.
*   📂 **[Cấu trúc Dự án & Mã nguồn](file:///Volumes/WorkSpace/Project/Manim_Agent/docs/proposal/08_project_structure.md)** - Sơ đồ thư mục và quy chuẩn viết mã function-based.
*   🗄️ **[Đặc tả Cơ sở dữ liệu Supabase](file:///Volumes/WorkSpace/Project/Manim_Agent/docs/proposal/09_supabase_schema.md)** - Thiết kế Schema và mã SQL Migration.

---

> **"Chúng ta tối ưu hóa tốc độ bằng cách loại bỏ các rào cản trung gian, đưa con người vào tâm điểm của quy trình kiểm soát chất lượng hình ảnh và âm thanh."**
