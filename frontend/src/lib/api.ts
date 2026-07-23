import { isAuthDisabled, supabase } from './supabase';

export const apiBaseUrl = (configured?: string) =>
  ((configured || '').trim() || '/v1').replace(/\/+$/, '');

const API_BASE_URL = apiBaseUrl(import.meta.env.VITE_API_BASE_URL);

const newRequestId = () => globalThis.crypto?.randomUUID?.() || `fe-${Date.now()}-${Math.random()}`;

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('X-Request-ID', headers.get('X-Request-ID') || newRequestId());

  if (!isAuthDisabled) {
    const { data } = await supabase.auth.getSession();
    if (data.session?.access_token) {
      headers.set('Authorization', `Bearer ${data.session.access_token}`);
    }
  }

  return fetch(`${API_BASE_URL}${path}`, { ...init, headers });
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly requestId?: string;
  readonly details?: unknown;

  constructor(
    message: string,
    options: { status: number; code?: string; requestId?: string; details?: unknown },
  ) {
    super(options.requestId ? `${message} (request ${options.requestId})` : message);
    this.name = 'ApiError';
    this.status = options.status;
    this.code = options.code;
    this.requestId = options.requestId;
    this.details = options.details;
  }
}

async function responseError(response: Response, fallback: string): Promise<ApiError> {
  let body: any = null;
  try {
    body = await response.json();
  } catch {
    // Non-JSON errors still retain the response request ID below.
  }

  const envelope = body?.error && typeof body.error === 'object' ? body.error : null;
  const detail = typeof body?.detail === 'string'
    ? body.detail
    : typeof body?.message === 'string'
      ? body.message
      : typeof envelope?.message === 'string'
        ? envelope.message
        : fallback;
  const requestId = typeof envelope?.request_id === 'string'
    ? envelope.request_id
    : response.headers.get('X-Request-ID') || undefined;

  return new ApiError(detail, {
    status: response.status,
    code: typeof envelope?.code === 'string' ? envelope.code : undefined,
    requestId,
    details: body?.details,
  });
}

export interface Project {
  id: string;
  title: string;
  description?: string | null;
  status?: string;
  video_url?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface Scene {
  id: string;
  project_id: string;
  scene_order: number;
  storyboard_text?: string | null;
  voice_script?: string | null;
  manim_code?: string | null;
  video_url?: string | null;
  generation_status: 'pending' | 'generating' | 'completed' | 'failed';
}

export type GenerationModel =
  | 'gemini-3-flash-preview'
  | 'gemini-3.5-flash'
  | 'gemini-3.5-flash-lite'
  | 'gemini-3.6-flash'
  | 'gemma-4-31b-it'
  | 'gemma-4-26b-it'
  | 'gemma-4-31b-it-thinking'
  | 'gemma-4-26b-it-thinking';

export interface UserSettings {
  theme: 'dark' | 'light';
  language: 'vi' | 'en';
  hitl_enabled: boolean;
  ai_agent_persona: 'Professional Educator' | 'Creative Storyteller' | 'Technical Explainer';
  template_selection: 'Educational' | 'Conceptual walkthrough' | 'Worked example';
  visual_review_enabled: boolean;
  code_review_enabled: boolean;
  max_review_attempts: number;
  video_quality: '480p' | '720p' | '1080p' | '4k';
  fps: 15 | 30 | 60;
  llm_model: GenerationModel | null;
  llm_temperature: number | null;
  llm_max_tokens: number | null;
  llm_agent_configs: Partial<Record<GenerationAgent, AgentLlmConfig>>;
  tts_enabled: boolean;
  tts_voice: 'auto' | 'vi-VN-female' | 'vi-VN-male' | 'en-US-female' | 'en-US-male' | 'vi-VN-Standard-A' | 'vi-VN-Standard-B' | 'en-US-Standard-C' | 'en-US-Standard-D';
  tts_speaking_rate: number;
  tts_pitch: number;
}

export type GenerationAgent = 'idea_sketcher' | 'storyboarder' | 'builder' | 'code_reviewer' | 'visual_reviewer';
export type ReasoningEffort = 'none' | 'minimal' | 'low' | 'medium' | 'high';

export interface AgentLlmConfig {
  model?: GenerationModel | null;
  temperature?: number | null;
  max_tokens?: number | null;
  reasoning_effort?: ReasoningEffort | null;
  review_tiers?: ReviewTierConfig[] | null;
}

export interface ReviewTierConfig {
  model: GenerationModel;
  max_attempts: number;
  reasoning_effort?: ReasoningEffort;
}

export interface DashboardStats {
  total_projects: number;
  active_jobs: number;
  total_render_time_hours: number;
}

export interface AiRun {
  id: string;
  project_id: string;
  scene_id?: string | null;
  status: 'queued' | 'waiting_for_human' | 'completed' | 'failed' | 'cancelled';
  hitl_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export type AgentStepStatus =
  | 'queued'
  | 'generating'
  | 'pending_review'
  | 'approved'
  | 'rejected'
  | 'failed';

export interface AgentStep {
  id: string;
  run_id: string;
  project_id: string;
  scene_id?: string | null;
  sequence: number;
  kind:
    | 'director'
    | 'planner'
    | 'scene_designer'
    | 'idea_sketcher'
    | 'storyboarder'
    | 'builder'
    | 'code_reviewer'
    | 'visual_reviewer';
  status: AgentStepStatus;
  input: Record<string, unknown>;
  draft_output?: Record<string, any> | null;
  final_output?: Record<string, any> | null;
  revision: number;
  error?: string | null;
}

export interface RenderJob {
  id: string;
  project_id: string;
  scene_id?: string | null;
  job_type: 'preview' | 'full' | 'full_project';
  status: 'queued' | 'rendering' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  logs?: string | null;
  asset_url?: string | null;
}

export interface RenderEnqueueResponse {
  job_id: string;
  status?: 'queued';
}

export const applyTheme = (theme: string) => {
  if (theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
};

const stableOperationHash = (value: string) => {
  let first = 0x811c9dc5;
  let second = 0x9e3779b9;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    first = Math.imul(first ^ code, 0x01000193);
    second = Math.imul(second ^ code, 0x85ebca6b);
  }
  return `${(first >>> 0).toString(16).padStart(8, '0')}${(second >>> 0).toString(16).padStart(8, '0')}`;
};

const renderIdempotencyKey = (scope: string) => `render:${stableOperationHash(scope)}`;

export const api = {
  async getSettings(): Promise<UserSettings> {
    const res = await request('/users/me/settings');
    if (!res.ok) throw await responseError(res, 'Failed to fetch settings');
    return res.json();
  },

  async updateSettings(settings: Partial<UserSettings>): Promise<UserSettings> {
    const {
      theme,
      language,
      hitl_enabled,
      ai_agent_persona,
      template_selection,
      visual_review_enabled,
      code_review_enabled,
      max_review_attempts,
      video_quality,
      fps,
      llm_model,
      llm_temperature,
      llm_max_tokens,
      llm_agent_configs,
      tts_enabled,
      tts_voice,
      tts_speaking_rate,
      tts_pitch,
    } = settings;
    const updateBody: Record<string, unknown> = {};
    if (theme !== undefined) updateBody.theme = theme;
    if (language !== undefined) updateBody.language = language;
    if (hitl_enabled !== undefined) updateBody.hitl_enabled = hitl_enabled;
    if (ai_agent_persona !== undefined) updateBody.ai_agent_persona = ai_agent_persona;
    if (template_selection !== undefined) updateBody.template_selection = template_selection;
    if (visual_review_enabled !== undefined) updateBody.visual_review_enabled = visual_review_enabled;
    if (code_review_enabled !== undefined) updateBody.code_review_enabled = code_review_enabled;
    if (max_review_attempts !== undefined) updateBody.max_review_attempts = max_review_attempts;
    if (video_quality !== undefined) updateBody.video_quality = video_quality;
    if (fps !== undefined) updateBody.fps = fps;
    if (llm_model !== undefined) updateBody.llm_model = llm_model;
    if (llm_temperature !== undefined) updateBody.llm_temperature = llm_temperature;
    if (llm_max_tokens !== undefined) updateBody.llm_max_tokens = llm_max_tokens;
    if (llm_agent_configs !== undefined) updateBody.llm_agent_configs = llm_agent_configs;
    if (tts_enabled !== undefined) updateBody.tts_enabled = tts_enabled;
    if (tts_voice !== undefined) updateBody.tts_voice = tts_voice;
    if (tts_speaking_rate !== undefined) updateBody.tts_speaking_rate = tts_speaking_rate;
    if (tts_pitch !== undefined) updateBody.tts_pitch = tts_pitch;

    const res = await request('/users/me/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updateBody),
    });
    if (!res.ok) throw await responseError(res, 'Failed to update settings');
    return res.json();
  },

  async getProjects(): Promise<Project[]> {
    const res = await request('/projects?page=1&limit=100');
    if (!res.ok) throw await responseError(res, 'Failed to fetch projects');
    const data = await res.json();
    return data.items || data;
  },

  async getDashboardStats(): Promise<DashboardStats> {
    const res = await request('/projects/stats');
    if (!res.ok) throw await responseError(res, 'Failed to fetch dashboard stats');
    return res.json();
  },

  async createProject(title: string, description: string, sourceLanguage = 'vi'): Promise<Project> {
    const res = await request('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description, source_language: sourceLanguage }),
    });
    if (!res.ok) throw await responseError(res, 'Failed to create project');
    return res.json();
  },

  async getProject(projectId: string): Promise<Project> {
    const res = await request(`/projects/${projectId}`);
    if (!res.ok) throw await responseError(res, 'Failed to fetch project');
    return res.json();
  },

  async getScenes(projectId: string): Promise<Scene[]> {
    const res = await request(`/projects/${projectId}/scenes?page=1&limit=100`);
    if (!res.ok) throw await responseError(res, 'Failed to fetch scenes');
    const data = await res.json();
    return data.items || data;
  },

  async getAiRuns(projectId: string): Promise<AiRun[]> {
    const res = await request(`/projects/${projectId}/ai-runs`);
    if (!res.ok) throw await responseError(res, 'Failed to fetch AI runs');
    return res.json();
  },

  async deleteProject(projectId: string): Promise<void> {
    const res = await request(`/projects/${projectId}`, { method: 'DELETE' });
    if (!res.ok) throw await responseError(res, 'Failed to delete project');
  },

  async generateScenes(projectId: string, prompt: string, hitlEnabled = true): Promise<{ run: AiRun; first_step: AgentStep }> {
    const res = await request(`/projects/${projectId}/generate-scenes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, hitl_enabled: hitlEnabled }),
    });
    if (!res.ok) throw await responseError(res, 'Failed to generate scenes');
    return res.json();
  },

  async startSceneRun(
    projectId: string,
    sceneId: string,
    briefOverride?: string,
    hitlEnabled = true,
  ): Promise<{ run: AiRun; first_step: AgentStep }> {
    const res = await request(`/projects/${projectId}/ai-runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene_id: sceneId, brief_override: briefOverride, hitl_enabled: hitlEnabled }),
    });
    if (!res.ok) throw await responseError(res, 'Failed to start AI run');
    return res.json();
  },

  async getAiRunSteps(projectId: string, runId: string): Promise<AgentStep[]> {
    const res = await request(`/projects/${projectId}/ai-runs/${runId}/steps`);
    if (!res.ok) throw await responseError(res, 'Failed to fetch steps');
    return res.json();
  },

  async approveStep(projectId: string, runId: string, stepId: string, revision: number): Promise<any> {
    const res = await request(`/projects/${projectId}/ai-runs/${runId}/steps/${stepId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_revision: revision }),
    });
    if (!res.ok) throw await responseError(res, 'Failed to approve step');
    return res.json();
  },

  async editStep(
    projectId: string,
    runId: string,
    stepId: string,
    revision: number,
    draftOutput: Record<string, unknown>,
  ): Promise<AgentStep> {
    const res = await request(`/projects/${projectId}/ai-runs/${runId}/steps/${stepId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_revision: revision, draft_output: draftOutput }),
    });
    if (!res.ok) throw await responseError(res, 'Failed to edit step');
    return res.json();
  },

  async rejectStep(
    projectId: string,
    runId: string,
    stepId: string,
    revision: number,
    feedback: string,
  ): Promise<any> {
    const res = await request(`/projects/${projectId}/ai-runs/${runId}/steps/${stepId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_revision: revision, feedback }),
    });
    if (!res.ok) throw await responseError(res, 'Failed to reject step');
    return res.json();
  },

  async rollbackRun(projectId: string, runId: string, targetStepId: string): Promise<any> {
    const res = await request(`/projects/${projectId}/ai-runs/${runId}/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_step_id: targetStepId }),
    });
    if (!res.ok) throw await responseError(res, 'Failed to rollback run');
    return res.json();
  },

  async enqueueSceneRender(
    projectId: string,
    sceneId: string,
    operationVersion = 'current',
    quality: UserSettings['video_quality'] = '720p',
  ): Promise<RenderEnqueueResponse> {
    const res = await request(`/projects/${projectId}/render`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Idempotency-Key': renderIdempotencyKey(`${projectId}:scene:${sceneId}:${operationVersion}`),
      },
      body: JSON.stringify({ scene_id: sceneId, render_type: 'full', quality }),
    });
    if (!res.ok) throw await responseError(res, 'Failed to queue scene render');
    return res.json();
  },

  async enqueueProjectRender(
    projectId: string,
    operationVersion = 'current',
    quality: UserSettings['video_quality'] = '720p',
  ): Promise<RenderEnqueueResponse> {
    const res = await request(`/projects/${projectId}/render`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Idempotency-Key': renderIdempotencyKey(`${projectId}:full-project:${operationVersion}`),
      },
      body: JSON.stringify({ render_type: 'full_project', quality }),
    });
    if (!res.ok) throw await responseError(res, 'Failed to queue full project render');
    return res.json();
  },

  async getRenderJob(jobId: string): Promise<RenderJob> {
    const res = await request(`/jobs/${jobId}`);
    if (!res.ok) throw await responseError(res, 'Failed to load render job');
    return res.json();
  },

  async getProjectRenderJobs(projectId: string, active = false): Promise<RenderJob[]> {
    const query = active ? '?active=true' : '';
    const res = await request(`/projects/${projectId}/render-jobs${query}`);
    if (!res.ok) throw await responseError(res, 'Failed to load project render jobs');
    return res.json();
  },

  async getRenderVideoUrl(jobId: string): Promise<string> {
    const signed = await request(`/jobs/${jobId}/signed-video-url`);
    if (signed.ok) return (await signed.json()).signed_url;

    // A <video src> navigation cannot attach the Supabase Bearer token. Fetch
    // local Compose artifacts through the authenticated API and expose a
    // browser-local object URL instead.
    const local = await request(`/jobs/${jobId}/video`);
    if (!local.ok) throw await responseError(local, 'Failed to load rendered video');
    return URL.createObjectURL(await local.blob());
  },

  async resolvePersistedVideoUrl(
    projectId: string,
    assetUrl?: string | null,
    sceneId?: string | null,
  ): Promise<string | null> {
    if (!assetUrl) return null;
    if (/^(https?:|blob:)/i.test(assetUrl)) return assetUrl;

    const query = sceneId ? `?scene_id=${encodeURIComponent(sceneId)}` : '';
    if (assetUrl.startsWith('supabase://')) {
      const signed = await request(`/projects/${projectId}/rendered-video-url${query}`);
      if (!signed.ok) throw await responseError(signed, 'Failed to sign persisted video');
      return (await signed.json()).signed_url;
    }

    if (assetUrl.startsWith('file://')) {
      const local = await request(`/projects/${projectId}/rendered-video${query}`);
      if (!local.ok) throw await responseError(local, 'Failed to load persisted video');
      return URL.createObjectURL(await local.blob());
    }

    throw new ApiError('Unsupported persisted video reference', { status: 409 });
  },
};
