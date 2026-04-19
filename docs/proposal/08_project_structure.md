# Cấu trúc Dự án & Tổ chức Mã nguồn

Tài liệu này đặc tả cách tổ chức thư mục và quy chuẩn viết mã. **Manim chỉ được khởi chạy trong worker**, trong môi trường **Docker** (image cố định phiên bản); backend API không embed Manim runtime.

---

## 1. Cấu trúc Thư mục Tổng thể (Project Tree)

Cây dưới đây khớp skeleton repo (file `.gitkeep` giữ thư mục rỗng trong Git). Các file `main.py`, `tasks.py`, v.v. sẽ được thêm khi triển khai code.

```text
Manim_Agent/
├── backend/                # FastAPI (không chạy Manim)
│   ├── api/
│   ├── core/
│   ├── db/
│   └── main.py             # (sẽ thêm) entrypoint API
├── worker/                 # Consumer job render — Manim/FFmpeg **trong Docker**
│   ├── environment/        # Dockerfile, requirements image render
│   ├── tasks.py            # (sẽ thêm) dequeue / gọi docker run
│   └── renderer.py         # (sẽ thêm) chuẩn bị volume, log, upload
├── ai_engine/
│   ├── agents/
│   ├── config/
│   │   └── agent_models.example.yaml  # model/temperature theo agent; copy → agent_models.yaml
│   ├── prompts/
│   └── llm_client.py       # (sẽ thêm) LiteLLM wrapper — đọc config ở trên
├── primitives/             # Helper Manim — mount/copy vào image worker khi build
├── shared/
│   └── schemas/            # Pydantic / contract dùng chung API ↔ worker
├── output/                 # Artefact cục bộ khi dev (không commit video lớn)
├── tests/                  # Pytest: unit → integration → e2e (gate cuối: LLM thật)
│   ├── unit/
│   ├── integration/
│   └── e2e/                # Full pipeline + LLM API thực (chỉ chạy khi có secret / CI release)
├── docs/
│   ├── proposal.md
│   └── proposal/
└── requirements.txt        # (sẽ thêm) dependency backend/ai; image Docker tách file riêng
```

---

## 2. Phân vai runtime


| Vị trí       | Manim             | Docker                                    |
| ------------ | ----------------- | ----------------------------------------- |
| `backend/`   | Không             | Không (chỉ orchestration)                 |
| `worker/`    | Có (CLI / Python) | Có — container là môi trường render chuẩn |
| `ai_engine/` | Không             | Không                                     |


---

## 3. Tổ chức Mã nguồn Manim (Function-based)

Để tránh file sinh ra quá dài, áp dụng **Part-based Scene** (ví dụ minh họa — sẽ nằm trong artefact scene do Builder sinh):

```python
from primitives import *

class TechnicalScene(Scene):
    def construct(self):
        self.setup_environment()
        self.step_1_introduction()
        self.step_2_explanation()
        self.step_3_conclusion()

    def setup_environment(self):
        pass

    def step_1_introduction(self):
        title = get_text_panel("Tìm kiếm nhị phân")
        self.play(Write(title))
        self.wait(2.5)

    def step_2_explanation(self):
        pass
```

- Mỗi `step_n` ánh xạ tới nhóm segment trên timeline (xem `05_pipeline.md`).
- Worker mount thư mục job (code + asset), chạy image, ghi `output/`.

---

## 4. Cấu trúc Lưu trữ (Cloud Storage)

- `**audio/`:** `{project_id}/{scene_id}.mp3`, `{project_id}/{scene_id}_timestamps.json`
- `**videos/`:** `{project_id}/previews/`, `{project_id}/final/`
- `**assets/`:** logo, ảnh người dùng

---

*Trở về tập chỉ mục:* [00_index.md](./00_index.md)