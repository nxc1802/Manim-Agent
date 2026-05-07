Dưới đây là đề xuất giải pháp kỹ thuật để chuyển đổi sang cơ chế "Conversational Review Loop" (Vòng lặp Review dạng hội thoại):

1. Đề xuất kiến trúc: Vòng lặp hội thoại đa vai trò
Thay vì gửi các chuỗi văn bản rời rạc, chúng ta sẽ xây dựng một Message Thread (Luồng tin nhắn) xuyên suốt các vòng lặp.

Assistant Role (Bot): Dùng để lưu trữ các đoạn mã (Python code) mà Builder đã sinh ra. Điều này giúp LLM hiểu rằng: "Đây là những gì tôi đã viết trước đó".
User Role: Dùng để gửi Feedback từ Reviewer. Điều này giúp LLM hiểu rằng: "Đây là những gì người dùng (Reviewer) muốn tôi sửa đổi".
2. Cơ chế Append Feedback & History
Tôi đề xuất cấu trúc messages như sau trong mỗi vòng lặp:

Vòng 1:

System: Hướng dẫn Builder & Primitives Catalog.
User: "Hãy lập trình cho kế hoạch này: [Plan JSON]"
Assistant (Builder): [Code Version 1]
Vòng 2:

System: (Giữ nguyên)
User: "Hãy lập trình cho kế hoạch này: [Plan JSON]"
Assistant: [Code Version 1]
User: "Phản hồi từ Reviewer: [Feedback vòng 1]. Hãy sửa lại code trên."
Assistant (Builder): [Code Version 2]
3. Nâng cấp cho Reviewer (Context-Aware Review)
Reviewer cũng cần biết lịch sử để không lặp lại các feedback vô ích:

Audit Log: Reviewer sẽ nhận được thông tin: "Vòng trước tôi đã góp ý X, Builder đã sửa thành Y. Bây giờ hãy đánh giá xem Y đã tốt chưa".
4. Kế hoạch thực hiện cụ thể:
Bước 1: Nâng cấp LLMClient & LiteLLMClient
Thêm phương thức complete_chat chấp nhận danh sách messages thay vì chỉ system và user.
Bước 2: Refactor builder_review_loop.py
Khởi tạo một biến chat_history = [].
Mỗi vòng lặp, chúng ta append Code của Builder (Assistant role) và Feedback của Reviewer (User role) vào chat_history.
Truyền chat_history này vào hàm run_builder.
Bước 3: Cập nhật Prompt cho Builder
Thay đổi Builder system prompt để nó hiểu rằng nó đang làm việc trong một quá trình lặp (Iterative process) và cần phải kế thừa từ code cũ.