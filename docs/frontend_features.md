# Chức năng Frontend hiện tại

Frontend là một React/Vite client mỏng. Mọi dữ liệu dự án, HITL, render job và URL video riêng tư đều đi qua Backend; trình duyệt chỉ dùng Supabase cho phiên đăng nhập khi chạy `VITE_AUTH_MODE=jwt`.

## Xác thực và chế độ phát triển

- JWT mode phục hồi Supabase session, gắn Bearer token cho REST và WebSocket, và tự chuyển về Login khi hết phiên.
- `VITE_AUTH_MODE=off` cho phép chạy FE độc lập với Backend development `AUTH_MODE=off`; cấu hình Supabase giả không làm ứng dụng crash.
- Route Dashboard, Scene Editor và Settings được lazy-load để giữ bundle khởi động nhỏ.

## Dashboard

- Liệt kê, tạo và xóa các project thuộc user hiện tại.
- Hiển thị tổng project, số render job đang chạy và tổng thời gian render do Backend tổng hợp.
- Mọi lỗi hiển thị message cùng request ID do Backend trả về để tra log.

## Scene Editor

Pipeline người dùng nhìn thấy có ba bước:

1. **Idea Sketch** tạo bản phác thảo ý tưởng ngắn, được lưu thành step riêng và tự chuyển tiếp.
2. **Storyboarder** dùng bản phác thảo để tạo danh sách scene ở cấp project.
3. **Builder** tạo Manim code cho từng scene và chạy Code/Visual auto-review nội bộ.

Sau khi Storyboard được duyệt, Backend tạo scene và dispatch các Builder song song. Mỗi tab scene giữ workspace riêng gồm run/step/revision, draft chưa lưu, reviewer history, generation status, render job/progress và video preview. Chuyển tab không dùng chung một ô state nên không mất draft và không hiển thị code/video của scene khác.

Draft chưa lưu luôn gắn với đúng `run_id`/`step_id`. Nếu một Builder mới thay thế owner trong lúc người dùng đang sửa, FE giữ nguyên nội dung cũ trong vùng conflict có thể sao chép thay vì đưa nhầm nó vào step mới.

Người dùng có thể:

- xem output đã trình bày hoặc mở raw editor;
- chỉnh draft đang `pending_review`, sau đó Approve (tự lưu đúng revision) hoặc Reject kèm feedback;
- rollback một step đã duyệt về review; Master rollback hủy child run/scene phát sinh, Builder rollback xóa code/video đã duyệt trước khi mở lại draft;
- retry/regenerate riêng một Builder;
- render scene đã có code được duyệt;
- ghép full project khi mọi scene đã có video;
- chuyển preview giữa scene video và full-project video.

Các patch của reviewer được hiển thị dưới dạng before/after. Runtime API context, repair-memory reset và Strategy Guard xuất hiện trong luồng review event/audit thay vì trở thành button hay endpoint công khai mới.

## Real-time và phục hồi

- Project WebSocket có heartbeat, bounded exponential reconnect và REST reconciliation sau mỗi lần mở lại.
- Event được route bằng `scene_id`; render event không bị bỏ chỉ vì không chứa `step`.
- Streaming delta được gom theo animation frame và tách theo project/scene.
- Video local được tải qua authenticated API thành Blob URL; private Supabase object được Backend ký.
- REST vẫn là source of truth nếu Pub/Sub/WebSocket bỏ lỡ event; khi reload/reconnect FE lấy cả active render jobs để nối lại polling.
- Snapshot REST chậm được merge theo event version của từng scene/project, không được ghi đè state WebSocket mới hơn. Poll render tiếp tục với bounded backoff khi socket mất lâu dài và chỉ terminal event của job đang active mới được nhận.

## Settings

Settings lưu theme, language, HITL mode, agent persona và template. Language được gửi thành `source_language` khi tạo project; HITL/persona/template được đọc trước khi bắt đầu run mới; theme được áp dụng ngay khi app khởi động.
