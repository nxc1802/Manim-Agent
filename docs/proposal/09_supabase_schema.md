# Đặc tả Cơ sở dữ liệu (Supabase Schema)

Thiết kế PostgreSQL (Supabase): bảng nghiệp vụ, **index**, **trigger `updated_at`**, **RLS đầy đủ** cho các bảng chứa dữ liệu người dùng.

---

## 1. Sơ đồ Quan hệ (khái niệm)

- **User** (`auth.users`) `1:N` **Project**
- **Project** `1:N` **Scene**
- **Project** `1:N` **RenderJob**
- **Project** `1:N` **Asset**
- **Scene** có thể `1:N` **RenderJob** (render theo từng scene — tuỳ chọn qua `scene_id`)

---

## 2. Mã SQL Migration (đầy đủ)

Chạy trong **Supabase SQL Editor** hoặc qua migration CLI. Thứ tự: extension → bảng → index → trigger → RLS.

```sql
-- (Tuỳ chọn) pgcrypto cho UUID — Supabase thường đã bật gen_random_uuid()
-- CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- 1. Projects
-- ---------------------------------------------------------------------------
CREATE TABLE public.projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT,
  source_language TEXT DEFAULT 'vi',
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'processing', 'completed', 'archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_user_id ON public.projects (user_id);
CREATE INDEX idx_projects_status ON public.projects (status);
CREATE INDEX idx_projects_updated_at ON public.projects (updated_at DESC);

-- ---------------------------------------------------------------------------
-- 2. Scenes
-- ---------------------------------------------------------------------------
CREATE TABLE public.scenes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_order INTEGER NOT NULL,
  storyboard_text TEXT,
  voice_script TEXT,
  planner_output JSONB,
  sync_segments JSONB,
  manim_code TEXT,
  manim_code_version INTEGER NOT NULL DEFAULT 1,
  audio_url TEXT,
  timestamps JSONB,
  duration_seconds NUMERIC(10, 3),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, scene_order)
);

CREATE INDEX idx_scenes_project_id ON public.scenes (project_id);
CREATE INDEX idx_scenes_project_order ON public.scenes (project_id, scene_order);

-- ---------------------------------------------------------------------------
-- 3. Render jobs (worker cập nhật trạng thái)
-- ---------------------------------------------------------------------------
CREATE TABLE public.render_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID REFERENCES public.scenes (id) ON DELETE SET NULL,
  job_type TEXT NOT NULL CHECK (job_type IN ('preview', 'full')),
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'rendering', 'completed', 'failed', 'cancelled')),
  progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
  logs TEXT,
  asset_url TEXT,
  error_code TEXT,
  webhook_url TEXT,
  docker_image_tag TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

CREATE INDEX idx_render_jobs_project ON public.render_jobs (project_id);
CREATE INDEX idx_render_jobs_status ON public.render_jobs (status);
CREATE INDEX idx_render_jobs_created ON public.render_jobs (created_at DESC);
CREATE INDEX idx_render_jobs_scene ON public.render_jobs (scene_id);

-- ---------------------------------------------------------------------------
-- 4. Assets (file trong Storage — metadata DB)
-- ---------------------------------------------------------------------------
CREATE TABLE public.assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID REFERENCES public.scenes (id) ON DELETE SET NULL,
  file_name TEXT NOT NULL,
  file_type TEXT NOT NULL CHECK (file_type IN ('audio', 'image', 'video', 'subtitle', 'other')),
  bucket_path TEXT NOT NULL,
  meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_assets_project ON public.assets (project_id);
CREATE INDEX idx_assets_scene ON public.assets (scene_id);
CREATE INDEX idx_assets_type ON public.assets (file_type);

-- ---------------------------------------------------------------------------
-- 5. Trigger: cập nhật updated_at
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_projects_updated_at
  BEFORE UPDATE ON public.projects
  FOR EACH ROW EXECUTE PROCEDURE public.set_updated_at();

CREATE TRIGGER trg_scenes_updated_at
  BEFORE UPDATE ON public.scenes
  FOR EACH ROW EXECUTE PROCEDURE public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 6. Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scenes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.render_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assets ENABLE ROW LEVEL SECURITY;

-- Projects: chủ sở hữu
CREATE POLICY projects_owner_all
  ON public.projects
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Scenes: thuộc project của user
CREATE POLICY scenes_by_project_owner
  ON public.scenes
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = scenes.project_id AND p.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = scenes.project_id AND p.user_id = auth.uid()
    )
  );

-- Render jobs: cùng quyền với project
CREATE POLICY render_jobs_by_project_owner
  ON public.render_jobs
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = render_jobs.project_id AND p.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = render_jobs.project_id AND p.user_id = auth.uid()
    )
  );

-- Assets: cùng quyền với project
CREATE POLICY assets_by_project_owner
  ON public.assets
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = assets.project_id AND p.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = assets.project_id AND p.user_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- 7. (Tuỳ chọn) Service role / worker
-- ---------------------------------------------------------------------------
-- Worker thường dùng Supabase **service role** (bypass RLS) hoặc RPC bảo vệ.
-- Nếu worker chạy với JWT của user, giữ RLS như trên là đủ.
```

### Ghi chú triển khai

- Trigger dùng `EXECUTE PROCEDURE` (tương thích PostgreSQL / Supabase hiện tại). Nếu dùng bản Postgres hỗ trợ cú pháp mới hơn, có thể đổi sang `EXECUTE FUNCTION` theo tài liệu cụ thể phiên bản.
- `**sync_segments` / `planner_output`:** lưu artefact trung gian để Builder idempotent và debug sync.
- `**manim_code_version`:** tăng khi audio/timeline thay đổi để worker biết cache cũ vô hiệu.

---

*Trở về tập chỉ mục:* [00_index.md](./00_index.md)