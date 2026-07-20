import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getSession } = vi.hoisted(() => ({ getSession: vi.fn() }));

vi.mock('./supabase', () => ({
  isAuthDisabled: false,
  supabase: { auth: { getSession } },
}));

import { ApiError, api } from './api';

describe('API authentication and render contract', () => {
  beforeEach(() => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'real-session-token' } } });
    vi.stubGlobal('fetch', vi.fn());
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => 'blob:authenticated-video'),
    });
  });

  it('queues a scene render with auth and the scene render contract', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ job_id: 'job-1' }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ job_id: 'job-1' }), { status: 200 }));

    await expect(api.enqueueSceneRender('project-1', 'scene-1', 'step-1:2'))
      .resolves.toEqual({ job_id: 'job-1' });
    await api.enqueueSceneRender('project-1', 'scene-1', 'step-1:2');
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    const headers = new Headers(init?.headers);
    const retryHeaders = new Headers(vi.mocked(fetch).mock.calls[1][1]?.headers);
    expect(url).toContain('/projects/project-1/render');
    expect(headers.get('Authorization')).toBe('Bearer real-session-token');
    expect(headers.get('X-Idempotency-Key')).toMatch(/^render:[0-9a-f]{16}$/);
    expect(retryHeaders.get('X-Idempotency-Key')).toBe(headers.get('X-Idempotency-Key'));
    expect(JSON.parse(String(init?.body))).toEqual({
      scene_id: 'scene-1',
      render_type: 'full',
      quality: '720p',
    });
  });

  it('queues a full project render without a scene ID', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ job_id: 'job-full' }), { status: 202 }));

    await api.enqueueProjectRender('project-1');
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({ render_type: 'full_project', quality: '720p' });
  });

  it('sends the saved language through the project source-language contract', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({
      id: 'project-1',
      title: 'English project',
    }), { status: 201 }));

    await api.createProject('English project', 'Explain limits', 'en');
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      title: 'English project',
      description: 'Explain limits',
      source_language: 'en',
    });
  });

  it('persists every supported setting rather than silently dropping options', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({}), { status: 200 }));

    await api.updateSettings({
      theme: 'light',
      language: 'vi',
      hitl_enabled: false,
      ai_agent_persona: 'Technical Explainer',
      template_selection: 'Worked example',
      code_review_enabled: true,
      visual_review_enabled: false,
      max_review_attempts: 2,
      video_quality: '1080p',
      fps: 60,
      llm_model: 'gemini-3.5-flash',
      llm_temperature: 0.3,
      llm_max_tokens: 8192,
      llm_agent_configs: {
        idea_sketcher: { model: 'gemini-3-flash-preview', reasoning_effort: 'low', max_tokens: 4096 },
        builder: { model: 'gemini-3.5-flash', temperature: 0.1, max_tokens: 8192, reasoning_effort: 'high' },
        code_reviewer: {
          review_tiers: [
            { model: 'gemma-4-31b-it', max_attempts: 1, reasoning_effort: 'none' },
            { model: 'gemini-3-flash-preview', max_attempts: 2, reasoning_effort: 'medium' },
          ],
        },
      },
      tts_enabled: true,
      tts_voice: 'vi-VN-Standard-A',
      tts_speaking_rate: 1.25,
      tts_pitch: 2,
    });

    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      theme: 'light',
      language: 'vi',
      hitl_enabled: false,
      ai_agent_persona: 'Technical Explainer',
      template_selection: 'Worked example',
      code_review_enabled: true,
      visual_review_enabled: false,
      max_review_attempts: 2,
      video_quality: '1080p',
      fps: 60,
      llm_model: 'gemini-3.5-flash',
      llm_temperature: 0.3,
      llm_max_tokens: 8192,
      llm_agent_configs: {
        idea_sketcher: { model: 'gemini-3-flash-preview', reasoning_effort: 'low', max_tokens: 4096 },
        builder: { model: 'gemini-3.5-flash', temperature: 0.1, max_tokens: 8192, reasoning_effort: 'high' },
        code_reviewer: {
          review_tiers: [
            { model: 'gemma-4-31b-it', max_attempts: 1, reasoning_effort: 'none' },
            { model: 'gemini-3-flash-preview', max_attempts: 2, reasoning_effort: 'medium' },
          ],
        },
      },
      tts_enabled: true,
      tts_voice: 'vi-VN-Standard-A',
      tts_speaking_rate: 1.25,
      tts_pitch: 2,
    });
  });

  it('uses the signed video endpoint when storage is configured', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ signed_url: 'https://cdn.example/video.mp4' }), { status: 200 }));
    await expect(api.getRenderVideoUrl('job-1')).resolves.toBe('https://cdn.example/video.mp4');
  });

  it('fetches a local video as an authenticated blob when signing is unavailable', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: { message: 'Storage unavailable' } }), { status: 503 }))
      .mockResolvedValueOnce(new Response(new Blob(['video']), { status: 200, headers: { 'Content-Type': 'video/mp4' } }));

    await expect(api.getRenderVideoUrl('job-1')).resolves.toBe('blob:authenticated-video');
    const [, localInit] = vi.mocked(fetch).mock.calls[1];
    expect(new Headers(localInit?.headers).get('Authorization')).toBe('Bearer real-session-token');
    expect(URL.createObjectURL).toHaveBeenCalledOnce();
  });

  it('resolves persisted storage references through Backend rather than browser storage access', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ signed_url: 'https://backend.example/signed.mp4' }), { status: 200 }));

    await expect(api.resolvePersistedVideoUrl('project-1', 'supabase://videos/project/renders/video.mp4', 'scene-1'))
      .resolves.toBe('https://backend.example/signed.mp4');
    expect(String(vi.mocked(fetch).mock.calls[0][0]))
      .toContain('/projects/project-1/rendered-video-url?scene_id=scene-1');
  });

  it('loads active project render jobs for reload reconciliation', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));
    await expect(api.getProjectRenderJobs('project-1', true)).resolves.toEqual([]);
    expect(String(vi.mocked(fetch).mock.calls[0][0]))
      .toContain('/projects/project-1/render-jobs?active=true');
  });

  it('parses the Backend error envelope and retains its request ID', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({
      error: {
        code: 'http_error',
        message: 'Step was updated elsewhere',
        request_id: 'request-409',
      },
    }), { status: 409 }));

    const error = await api.approveStep('project-1', 'run-1', 'step-1', 1).catch(value => value);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toContain('Step was updated elsewhere');
    expect(error.requestId).toBe('request-409');
    expect(error.status).toBe(409);
  });

  it('requests the full supported project page', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    await api.getProjects();
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain('limit=100');
  });
});
