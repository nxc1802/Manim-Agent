export type ProjectStatus = 'draft' | 'processing' | 'completed' | 'archived';
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface Project {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  source_language: string;
  target_scenes: number | null;
  config: Record<string, JsonValue>;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface DashboardStats {
  total_projects: number;
  active_jobs: number;
  total_tokens_used: number;
  total_render_time_hours: number;
}

export type StoryboardStatus = 'missing' | 'pending_review' | 'approved';
export type PlanStatus = 'missing' | 'pending_review' | 'approved';
export type VoiceScriptStatus = 'missing' | 'pending_review' | 'approved';
export type ReviewLoopStatus = 'idle' | 'running' | 'completed' | 'hitl_pending' | 'failed';

export interface DslPosition {
  x: number;
  y: number;
  z: number;
  relative_to: string | null;
  target_id: string | null;
  buff: number;
}

export interface DslTheme {
  primary_color: string;
  secondary_color: string;
  background_color: string;
  font: string | null;
}

export interface DslCameraState {
  position: [number, number, number] | null;
  zoom: number | null;
}

export interface DslTransition {
  transition_type: string;
  duration: number;
}

export interface DslVisualElement {
  id: string;
  type: string;
  params: Record<string, JsonValue>;
  position: DslPosition | null;
}

export interface DslAnimationStep {
  target_ids: string[];
  animation_type: string;
  params: Record<string, JsonValue>;
  run_time: number | null;
  simultaneous: boolean;
}

export interface SceneDslBeat {
  id: string;
  label: string;
  duration_seconds: number;
  narration: string | null;
  visual_elements: DslVisualElement[];
  animations: DslAnimationStep[];
  camera: DslCameraState | null;
  transition_out: DslTransition | null;
}

export interface SceneDsl {
  version: string;
  title: string;
  beats: SceneDslBeat[];
  global_theme: DslTheme | null;
  metadata: Record<string, JsonValue>;
}

export interface Scene {
  id: string;
  project_id: string;
  scene_order: number;
  
  // Content
  storyboard_text: string | null;
  voice_script: string | null;
  planner_output: JsonValue;
  sync_segments: JsonValue;
  manim_code: string | null;
  manim_code_version: number;
  scene_dsl: SceneDsl | null;
  scene_dsl_version: number;

  // Audio
  audio_url: string | null;
  timestamps: JsonValue;
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
  metadata: Record<string, JsonValue>;
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
  id: string;
  ts?: string;
  component: string;
  phase: string;
  message: string;
  scene_id: string;
  project_id: string;
  details: Record<string, JsonValue>;
  trace_id?: string;
  created_at: string;
}

export type ArtifactEntityType = 'storyboard' | 'plan' | 'dsl' | 'code';

export interface ArtifactVersion {
  id: string;
  entity_type: ArtifactEntityType;
  entity_id: string;
  version: number;
  content_hash: string;
  content: JsonValue;
  parent_version: number | null;
  created_by: string;
  created_at: string;
}
