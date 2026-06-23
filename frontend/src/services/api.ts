import axios from 'axios';
import { supabase } from './supabase';
import type { 
  Project, 
  Scene, 
  Job, 
  VoiceJob, 
  PaginatedResponse,
  DashboardStats,
  ArtifactEntityType,
  ArtifactVersion,
} from '../types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor for Auth (Supabase JWT)
api.interceptors.request.use(async (config) => {
  let token: string | undefined;
  
  // 1. Check Supabase session
  const { data: { session } } = await supabase.auth.getSession();
  token = session?.access_token;
  
  // 2. Fallback to Guest mode dummy token if needed for dev
  if (!token && localStorage.getItem('manim_guest_user')) {
    token = 'guest-dev-token'; // Backend should accept this or skip auth if AUTH_MODE=off
  }
  
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const projectService = {
  getAll: (page = 1, limit = 20) => 
    api.get<PaginatedResponse<Project>>('/projects', { params: { page, limit } }),
    
  getById: (id: string) => 
    api.get<Project>(`/projects/${id}`),
    
  create: (data: Partial<Project>) => 
    api.post<Project>('/projects', data),
    
  update: (id: string, data: Partial<Project>) => 
    api.patch<Project>(`/projects/${id}`, data),
    
  delete: (id: string) => 
    api.delete(`/projects/${id}`),
    
  getScenes: (projectId: string) => 
    api.get<PaginatedResponse<Scene>>(`/projects/${projectId}/scenes`),
    
  createScene: (projectId: string, data: { scene_order: number }) => 
    api.post<Scene>(`/projects/${projectId}/scenes`, data),
    
  batchCreateScenes: (projectId: string, scenes: Partial<Scene>[]) => 
    api.post<Scene[]>(`/projects/${projectId}/scenes/batch`, scenes),
    
  approveAllStoryboards: (projectId: string) => 
    api.post<Scene[]>(`/projects/${projectId}/approve-storyboard`),
    
  getPipelineRuns: (projectId: string) => 
    api.get(`/projects/${projectId}/pipeline-runs`),

  runWorkflow: (projectId: string, data?: { mode?: 'auto' | 'hitl', extra_rounds?: number }) =>
    api.post<{ project_id: string, task_id: string, scene_count: number }>(
      `/projects/${projectId}/workflow`,
      data,
    ),
    
  render: (projectId: string, data: { render_type: string, quality: string, scene_id?: string }) => 
    api.post<{ job_id: string, status: string }>(`/projects/${projectId}/render`, data),
    
  getStats: () => 
    api.get<DashboardStats>('/projects/stats'),
};

export const sceneService = {
  getById: (id: string) => 
    api.get<Scene>(`/scenes/${id}`),
    
  update: (id: string, data: Partial<Scene>) => 
    api.patch<Scene>(`/scenes/${id}`, data),
    
  delete: (id: string) => 
    api.delete(`/scenes/${id}`),
    
  generateStoryboard: (id: string, brief_override?: string) => 
    api.post<Scene>(`/scenes/${id}/generate-storyboard`, { brief_override }),
    
  approveStoryboard: (id: string) => 
    api.post<Scene>(`/scenes/${id}/approve-storyboard`),
    
  plan: (id: string) => 
    api.post<Scene>(`/scenes/${id}/plan`),
    
  approvePlan: (id: string) => 
    api.post<Scene>(`/scenes/${id}/approve-plan`),
    
  approveVoiceScript: (id: string) => 
    api.post<Scene>(`/scenes/${id}/approve-voice-script`),
    
  generateVoice: (id: string, data?: { voice_script_override?: string, language?: string }) => 
    api.post<{ voice_job_id: string, status: string, poll_path: string }>(`/scenes/${id}/voice`, data),
    
  syncTimeline: (id: string) => 
    api.post<Scene>(`/scenes/${id}/sync-timeline`),
    
  generateCode: (id: string, data?: { enqueue_preview?: boolean }) => 
    api.post<{ scene: Scene, preview_job_id: string | null }>(`/scenes/${id}/generate-code`, data),
    
  runReviewLoop: (id: string, data: { mode: 'auto' | 'hitl', preview_poll_timeout_seconds?: number }) => 
    api.post<{ scene_id: string, job_id: string, review_loop_status: string }>(`/scenes/${id}/builder-review-loop`, data),
    
  hitlAck: (id: string, data: { action: 'continue' | 'revert' | 'stop', extra_rounds?: number }) => 
    api.post<{ scene: Scene, message: string }>(`/scenes/${id}/hitl-ack-builder-review`, data),

  getVersions: (id: string, entityType?: ArtifactEntityType) =>
    api.get<ArtifactVersion[]>(`/scenes/${id}/versions`, { params: { entity_type: entityType } }),

  rollback: (id: string, data: { entity_type: ArtifactEntityType, target_version: number }) =>
    api.post<ArtifactVersion>(`/scenes/${id}/rollback`, data),

  patchDsl: (id: string, data: { dsl_code: string }) =>
    api.patch<{ scene: Scene, preview_job_id: string }>(`/scenes/${id}/dsl`, data),
};

export const jobService = {
  getRenderJob: (id: string) => 
    api.get<Job>(`/jobs/${id}`),
    
  getSignedVideoUrl: (id: string) => 
    api.get<{ signed_url: string, expires_in_seconds: number }>(`/jobs/${id}/signed-video-url`),
    
  getVoiceJob: (id: string) => 
    api.get<VoiceJob>(`/voice-jobs/${id}`),
};

export const primitiveService = {
  getCatalog: () => api.get('/primitives/catalog'),
};

export default api;
