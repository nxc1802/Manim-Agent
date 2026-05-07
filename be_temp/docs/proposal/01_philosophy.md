# Triết lý & Tầm nhìn Hệ thống (No-DSL Version)

Dự án AI Manim Agent hướng tới việc tối ưu hóa tốc độ và khả năng linh hoạt bằng cách cho phép AI sinh mã nguồn Python trực tiếp, thay vì sử dụng các lớp trung gian phức tạp.

---

## 1. Thách thức: Duy trì tính chính xác trong mã nguồn

Việc để AI viết code trực tiếp (Generative) thường đi kèm với rủi ro về lỗi cú pháp và cấu trúc hỗn loạn. Tuy nhiên, thay vì xây dựng một ngôn ngữ DSL (Domain Specific Language) mới tốn thời gian, chúng tôi áp dụng chiến lược **"Rào chắn Thư viện" (Primitive Helper Functions)**.

---

## 2. Ba Nguyên tắc Nền tảng Mới

### 2.1 Functional Code Generation (Sinh mã theo chức năng)

Thay vì các lớp DSL, AI sẽ sinh mã Python thuần túy nhưng được chia nhỏ thành các hàm (function-based).

- **Tại sao?** Giúp mã nguồn dễ đọc, dễ debug và dễ can thiệp bởi con người. Tránh tình trạng một file code dài hàng ngàn dòng không cấu trúc.

### 2.2 Decomposition over Monolith (Chia nhỏ quy trình)

Quy trình sản xuất video nảy sinh từ sự phối hợp giữa các chuyên gia:

- **Creative (Director):** Kịch bản và hình ảnh.
- **Audio (Voice Agent):** Thuyết minh và cảm xúc.
- **Technical (Builder Agent):** Hiện thực hóa bằng mã Manim.

### 2.3 Audio-Visual Synchronization (Đồng bộ là tiên quyết)

Trong video kỹ thuật, hình ảnh minh họa chỉ có giá trị khi nó xuất hiện đúng lúc với lời giải thích. Chúng tôi ưu tiên việc lấy **thời gian của giọng nói** làm trục tọa độ chính để điều phối hoạt ảnh.

---

## 3. Tầm nhìn: "AI Đề xuất, Con người Quyết định"

Hệ thống hoạt động như một cộng sự (Copilot) cho các nhà sáng tạo nội dung giáo dục. AI xử lý các tác vụ lặp đi lặp lại như render, căn chỉnh tọa độ và đồng bộ âm thanh, trong khi con người tập trung vào giá trị cốt lõi của nội dung.

---

*Trở về tập chỉ mục:* [00_index.md](./00_index.md)