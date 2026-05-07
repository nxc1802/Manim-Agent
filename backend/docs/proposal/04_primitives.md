# Hệ thống Primitives (Python Helper Library)

Hệ thống Primitives được thiết kế dưới dạng một thư viện các hàm tiện ích (Utility Functions) viết bằng Python, đóng vai trò là lớp trừu tượng đồ họa cho AI Builder.

---

## 1. Cấu trúc Primitives

Thay vì để AI tự viết mã Manim thô từ đầu (vốn dễ sai sót), chúng tôi cung cấp các bộ hàm chuẩn đã được kiểm thử:

### 1.1 Visual Helpers
*   `def get_text_panel(text, color, font_size)`
*   `def get_array_block(values, highlight_index)`
*   `def get_code_box(code_string, language)`
*   👉 **Lợi ích:** Đảm bảo kiểu dáng (spacing, font, alignment) luôn đồng nhất và đẹp mắt.

### 1.2 Animation Helpers
*   `def cinematic_fade_in(mobject, duration)`
*   `def smooth_transform(mobject_from, mobject_to)`
*   `def focus_highlight(mobject)`

---

## 2. Cách AI sử dụng Primitives

Trong quá trình sinh mã, Builder Agent sẽ gọi các hàm này thay vì viết logic khởi tạo đối tượng Manim từ đầu.

**Ví dụ mã nguồn AI sinh ra:**
```python
def create_intro_scene(self):
    # Sử dụng Primitives thay vì code raw
    title = get_text_panel("Tìm kiếm nhị phân", color=BLUE)
    self.play(cinematic_fade_in(title))
    self.wait(1.5)
```

---

## 3. Quản lý Thư viện (Function Registry)

Chúng tôi cung cấp cho AI một danh mục (Catalog) các hàm có sẵn kèm theo:
*   **Mô tả chức năng:** Hàm này dùng để làm gì.
*   **Tham số:** Các biến đầu vào cần thiết.
*   **Ví dụ sử dụng:** Để AI bắt chước cú pháp gọi hàm chuẩn.

Việc chuyển từ DSL sang Library giúp hệ thống chạy nhanh hơn đáng kể vì không tốn thời gian cho bước "Dịch" (Compilation) và cho phép AI tận dụng tối đa khả năng viết code Python vốn có của nó.

---

*Trở về tập chỉ mục:* [00_index.md](./00_index.md)
