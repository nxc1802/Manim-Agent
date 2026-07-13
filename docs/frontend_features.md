# Tài liệu Chức năng Frontend (Manim Agent Studio)

Tài liệu này cung cấp cái nhìn tổng quan về các chức năng hiện có trên giao diện người dùng (Frontend) của ứng dụng Manim Agent. Thay vì đi sâu vào cấu trúc mã nguồn, tài liệu này tập trung vào trải nghiệm và các luồng thao tác của người dùng.

## 1. Xác thực người dùng (Authentication)
- **Đăng nhập / Đăng ký**: Giao diện kết nối trực tiếp với Supabase Auth. Người dùng bắt buộc phải đăng nhập để có thể truy cập vào không gian làm việc (Studio).
- **Quản lý phiên (Session)**: Tự động lưu trữ và phục hồi phiên đăng nhập. Nút đăng xuất (Logout) được đặt trên thanh điều hướng (Top Nav).

## 2. Thanh điều hướng toàn cục (Top Navigation)
- Thay thế hoàn toàn thanh trượt bên (Sidebar) cũ bằng một thanh điều hướng trên cùng (TopNav) mang phong cách Glassmorphism chuyên nghiệp, tối đa hóa không gian màn hình.
- Chứa Logo dự án, liên kết truy cập nhanh về trang chủ Studio, nút Cài đặt (Settings), và thông tin/nút Đăng xuất.

## 3. Không gian làm việc chính (Studio Page)
Trang tổng hợp toàn bộ các thông tin quan trọng nhất của người dùng, bao gồm:
- **Bảng tóm tắt (Quick Stats)**: Hiển thị nhanh số lượng dự án, tổng số token AI đã tiêu thụ, tổng thời gian render video và số lượng công việc (Jobs) đang chạy.
- **Quản lý dự án (Project Browser)**:
  - Danh sách các dự án hiển thị dưới dạng thẻ (Cards).
  - Thanh tìm kiếm thông minh giúp lọc dự án nhanh chóng.
  - Chức năng **Tạo Dự Án Mới (New Project)** thông qua một Popup Modal, yêu cầu người dùng cung cấp Tên dự án và Kịch bản ban đầu (Storyboard).
  - Click vào một dự án bất kỳ sẽ chuyển trực tiếp tới Scene Editor của dự án đó.
- **Hàng đợi công việc (Active Jobs)**: Hiển thị trạng thái của các tiến trình chạy ngầm như Render Video hoặc Tạo Voice.

## 4. Trình chỉnh sửa Kịch bản & Video (Scene Editor)
Đây là trung tâm tương tác giữa người dùng và trí tuệ nhân tạo (AI) thông qua cơ chế **Human-in-the-Loop (HITL)**. Các chức năng cốt lõi:

- **Thanh Tiến độ (Stepper UI)**: 
  - Mô tả trực quan 6 giai đoạn tạo video của AI: `Director` -> `Planner` -> `Scene Designer` -> `Manim Builder` -> `Code Reviewer` -> `Visual Reviewer`.
  - Giúp người dùng biết chính xác AI đang ở bước nào (Đang xử lý, Chờ duyệt, hoặc Đã hoàn thành).
- **Chế độ xem mượt mà & Đẹp mắt (Elegant Renderer)**:
  - Các kết quả trả về của AI ở giai đoạn lên ý tưởng (như Kịch bản, Kế hoạch, Thiết kế bối cảnh) sẽ được hệ thống phân tích và hiển thị thành các đoạn văn, danh sách có cấu trúc đẹp mắt thay vì hiển thị dữ liệu JSON khô khan.
- **Biên tập mã nguồn (Raw Data Editor)**: 
  - Tích hợp trình soạn thảo chuyên nghiệp (Monaco Editor).
  - Người dùng có thể nhấn nút Toggle ("Edit Raw JSON") để tự tay chỉnh sửa sâu vào các dữ liệu JSON hoặc can thiệp trực tiếp vào mã code Python (`manim_code`) sinh ra bởi AI.
- **Tương tác Real-time (Streaming)**: Khi AI đang suy nghĩ và sinh kết quả (Generating), văn bản sẽ được "gõ" trực tiếp lên màn hình theo thời gian thực (typewriter effect) mang lại cảm giác phản hồi tức thì.
- **Duyệt & Phản hồi (Approve / Reject)**: 
  - Tại mỗi bước, người dùng có quyền **Lưu chỉnh sửa (Save)**, **Chấp thuận (Approve)** để AI đi tiếp, hoặc **Từ chối (Reject)** kèm theo lý do/phản hồi để AI làm lại bước đó.
- **Khôi phục trạng thái (Rollback)**: 
  - Bằng cách click vào một giai đoạn đã hoàn thành trên thanh Stepper, người dùng có thể xem lại nội dung cũ và nhấn nút **"Revert to this Stage"** để quay ngược thời gian, bắt AI làm lại từ giai đoạn đó (hủy bỏ toàn bộ các bước sau nó).
- **Video Preview**: Một khu vực dành riêng để xem trước đoạn video sau khi đã render thành công dựa trên code Manim.

## 5. Trang Cài đặt (Settings Page)
Nơi tinh chỉnh các cấu hình cá nhân và studio:
- **Cấu hình Studio (Studio Defaults)**:
  - Bật/Tắt tính năng Human-in-the-Loop (HITL). Nếu tắt, AI sẽ tự động chạy một mạch từ kịch bản ra video cuối cùng.
  - Lựa chọn "Nhân vật AI" (AI Agent Persona) như: Giáo viên chuyên nghiệp, Người kể chuyện sáng tạo,... để điều chỉnh tông giọng sinh nội dung.
  - Chọn giao diện Template cho video (ví dụ: Cinematic, Educational).
- **Cấu hình chung (General)**: Quản lý giao diện Sáng/Tối và Ngôn ngữ hiển thị.
