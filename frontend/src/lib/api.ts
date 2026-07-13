const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/v1';

export interface Project {
  id: string;
  title: string;
  description?: string;
  status?: string;
  created_at?: string;
}

export interface UserSettings {
  theme: string;
  language: string;
  hitl_enabled: boolean;
  ai_agent_persona: string;
  template_selection: string;
}

export const applyTheme = (theme: string) => {
  if (theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
};

export const api = {
  async getSettings(): Promise<UserSettings> {
    const res = await fetch(`${API_BASE_URL}/users/me/settings`);
    if (!res.ok) throw new Error('Failed to fetch settings');
    return await res.json();
  },

  async updateSettings(settings: Partial<UserSettings>): Promise<UserSettings> {
    const { theme, language, hitl_enabled, ai_agent_persona, template_selection } = settings;
    const updateBody: Record<string, any> = {};
    if (theme !== undefined) updateBody.theme = theme;
    if (language !== undefined) updateBody.language = language;
    if (hitl_enabled !== undefined) updateBody.hitl_enabled = hitl_enabled;
    if (ai_agent_persona !== undefined) updateBody.ai_agent_persona = ai_agent_persona;
    if (template_selection !== undefined) updateBody.template_selection = template_selection;

    const res = await fetch(`${API_BASE_URL}/users/me/settings`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updateBody),
    });
    if (!res.ok) throw new Error('Failed to update settings');
    return await res.json();
  },

  async getProjects(): Promise<Project[]> {
    const res = await fetch(`${API_BASE_URL}/projects?page=1&limit=20`);
    if (!res.ok) throw new Error('Failed to fetch projects');
    const data = await res.json();
    return data.items || data;
  },

  async createProject(title: string, description: string): Promise<Project> {
    const res = await fetch(`${API_BASE_URL}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description }),
    });
    if (!res.ok) throw new Error('Failed to create project');
    return await res.json();
  },

  async getProject(projectId: string): Promise<Project> {
    const res = await fetch(`${API_BASE_URL}/projects/${projectId}`);
    if (!res.ok) throw new Error('Failed to fetch project');
    return await res.json();
  },

  async getScenes(projectId: string): Promise<any[]> {
    const res = await fetch(`${API_BASE_URL}/projects/${projectId}/scenes`);
    if (!res.ok) throw new Error('Failed to fetch scenes');
    const data = await res.json();
    return data.items || data;
  },

  async createScene(projectId: string, sceneOrder: number): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/projects/${projectId}/scenes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene_order: sceneOrder }),
    });
    if (!res.ok) throw new Error('Failed to create scene');
    return await res.json();
  },

  async getAiRuns(projectId: string): Promise<any[]> {
    const res = await fetch(`${API_BASE_URL}/projects/${projectId}/ai-runs`);
    if (!res.ok) throw new Error('Failed to fetch AI runs');
    return await res.json();
  },

  async startAiRun(projectId: string, sceneId: string, briefOverride?: string): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/projects/${projectId}/ai-runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene_id: sceneId, brief_override: briefOverride, hitl_enabled: true }),
    });
    if (!res.ok) throw new Error('Failed to start AI run');
    return await res.json();
  },

  async getAiRunSteps(projectId: string, runId: string): Promise<any[]> {
    const res = await fetch(`${API_BASE_URL}/projects/${projectId}/ai-runs/${runId}/steps`);
    if (!res.ok) throw new Error('Failed to fetch steps');
    return await res.json();
  },

  async approveStep(projectId: string, runId: string, stepId: string, revision: number): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/projects/${projectId}/ai-runs/${runId}/steps/${stepId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_revision: revision }),
    });
    if (!res.ok) throw new Error('Failed to approve step');
    return await res.json();
  },

  async editStep(projectId: string, runId: string, stepId: string, revision: number, draftOutput: any): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/projects/${projectId}/ai-runs/${runId}/steps/${stepId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_revision: revision, draft_output: draftOutput }),
    });
    if (!res.ok) throw new Error('Failed to edit step');
    return await res.json();
  },

  async rejectStep(projectId: string, runId: string, stepId: string, revision: number, feedback: string): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/projects/${projectId}/ai-runs/${runId}/steps/${stepId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_revision: revision, feedback }),
    });
    if (!res.ok) throw new Error('Failed to reject step');
    return await res.json();
  },

  async rollbackRun(projectId: string, runId: string, targetStepId: string): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/projects/${projectId}/ai-runs/${runId}/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_step_id: targetStepId }),
    });
    if (!res.ok) throw new Error('Failed to rollback run');
    return await res.json();
  }
};

