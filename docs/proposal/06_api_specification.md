# Đặc tả API Backend (Production Ready)

Tài liệu này đặc tả các điểm cuối (Endpoints) của hệ thống Manim Agent, bao gồm cả cơ chế xác thực và quản lý tài sản trên Cloud.

**Quan trọng:** API **không** render Manim trực tiếp. `POST .../render` chỉ tạo bản ghi `render_jobs` và đẩy vào hàng đợi; **worker** (Docker + Manim) thực thi render và cập nhật `status` / `asset_url`.

---

## 1. Xác thực (Authentication)

Dự án tích hợp **Supabase Auth**. Mọi yêu cầu (ngoại trừ các endpoint công khai) đều yêu cầu Header xác thực:

- `Authorization: Bearer <SUPABASE_ACCESS_TOKEN>`

---

## 2. Quản lý Dự án (Projects)

### `GET /v1/projects`

Lấy danh sách tất cả dự án của người dùng hiện tại.

### `POST /v1/projects`

Khởi tạo một dự án mới.

- **Body:**
  ```json
  {
    "title": "Cơ chế tìm kiếm nhị phân",
    "description": "Giải thích trực quan về thuật toán Binary Search",
    "source_language": "vi"
  }
  ```

---

## 3. Phân cảnh & Thuyết minh (Scenes & Voice)

### `POST /v1/projects/{id}/scenes`

Thêm một phân cảnh mới vào dự án.

### `POST /v1/scenes/{scene_id}/voice`

Tạo audio thuyết minh và trích xuất dữ liệu timestamp.

- **Response:**
  ```json
  {
    "audio_url": "https://<supabase-storage>/bucket/audio/scene_01.mp3",
    "duration": 12.5,
    "timestamps": [
      {"word": "Binary", "start": 0.5, "end": 0.8},
      {"word": "Search", "start": 0.9, "end": 1.4}
    ]
  }
  ```

---

## 4. Quản lý Mã nguồn & Render (Code & Jobs)

### `POST /v1/projects/{id}/render`

Kích hoạt tiến trình render cho dự án.

- **Body:**
  ```json
  {
    "render_type": "preview|full",
    "quality": "720p|1080p|4k",
    "webhook_url": "https://your-app.com/api/webhooks/render" // Optional
  }
  ```
- **Response:** `202 Accepted` kèm theo `job_id`.

### `GET /v1/jobs/{job_id}`

Truy vấn trạng thái render hiện tại.

- **Response Fields:** `status` (queued, rendering, completed, failed), `progress` (0-100), `logs`, `asset_url`.

---

## 5. Webhooks (Optional/Phase sau)

Khi tiến trình render hoàn tất, hệ thống sẽ gửi một yêu cầu `POST` đến `webhook_url` đã đăng ký.

- **Payload:**
  ```json
  {
    "job_id": "uuid-123",
    "status": "completed",
    "asset_url": "https://<cloud-storage>/videos/final_video.mp4",
    "metadata": {
      "duration": 45.0,
      "token_usage": 1500
    }
  }
  ```

---

*Trở về tập chỉ mục:* [00_index.md](./00_index.md)