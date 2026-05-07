export type ProjectStatus = 'draft' | 'processing' | 'completed' | 'archived';

export interface Project {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  source_language: string;
  target_scenes: number | null;
  config: Record<string, any>;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export type StoryboardStatus = 'missing' | 'pending_review' | 'approved';
export type PlanStatus = 'missing' | 'pending_review' | 'approved';
export type VoiceScriptStatus = 'missing' | 'pending_review' | 'approved';
export type ReviewLoopStatus = 'idle' | 'running' | 'completed' | 'hitl_pending' | 'failed';

export interface Scene {
  id: string;
  project_id: string;
  scene_order: number;
  
  // Content
  storyboard_text: string | null;
  voice_script: string | null;
  planner_output: any | null;
  sync_segments: any | null;
  manim_code: string | null;
  manim_code_version: number;

  // Audio
  audio_url: string | null;
  timestamps: any | null;
  duration_seconds: number | null;

  // Status fields
  storyboard_status: StoryboardStatus;
  plan_status: PlanStatus;
  voice_script_status: VoiceScriptStatus;
  review_loop_status: ReviewLoopStatus;

  created_at: string;
  updated_at: string;
}

export type JobStatus = 'queued' | 'rendering' | 'completed' | 'failed' | 'cancelled';
export type JobType = 'full' | 'preview' | 'scene';

export interface Job {
  id: string;
  project_id: string;
  scene_id?: string;
  job_type: JobType;
  render_quality: string;
  status: JobStatus;
  progress: number;
  logs: string | null;
  asset_url: string | null;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  metadata: Record<string, any>;
}

export type VoiceJobStatus = 'queued' | 'synthesizing' | 'completed' | 'failed';

export interface VoiceJob {
  id: string;
  project_id: string;
  scene_id: string;
  status: VoiceJobStatus;
  progress: number;
  asset_url: string | null;
  voice_engine: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export interface PipelineEvent {
  ts: string;
  component: string;
  phase: string;
  message: string;
  scene_id: string;
  payload?: any;
}
