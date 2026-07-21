import { describe, expect, it } from 'vitest';
import type { AgentStep, Scene } from './api';
import {
  appendStreamChunk,
  canApplyRestSnapshot,
  eventSceneId,
  filterCurrentRestScenes,
  mergeCurrentRestScenes,
  latestStep,
  renderStatusFromEvent,
  reviewStagesFromOutput,
  sceneWorkspaceReducer,
  shouldAcceptRunEvent,
  shouldAcceptTerminalRender,
  websocketProjectUrl,
  websocketAuthProtocols,
} from './sceneEditorState';

const scene = (id: string): Scene => ({
  id,
  project_id: 'project-1',
  scene_order: id === 'scene-a' ? 1 : 2,
  generation_status: 'pending',
});

const builderStep = (overrides: Partial<AgentStep> = {}): AgentStep => ({
  id: 'step-1',
  run_id: 'run-1',
  project_id: 'project-1',
  scene_id: 'scene-a',
  sequence: 1,
  kind: 'builder',
  status: 'pending_review',
  input: {},
  draft_output: { manim_code: 'server code' },
  revision: 1,
  ...overrides,
});

describe('scene editor workspace state', () => {
  it('keeps dirty drafts isolated when a late scene load or WebSocket snapshot arrives', () => {
    let state = sceneWorkspaceReducer({}, { type: 'seed_scenes', scenes: [scene('scene-a'), scene('scene-b')] });
    state = sceneWorkspaceReducer(state, {
      type: 'hydrate',
      sceneId: 'scene-a',
      runId: 'run-1',
      step: builderStep(),
      stage: 'Builder A loaded',
    });
    state = sceneWorkspaceReducer(state, { type: 'edit', sceneId: 'scene-a', draft: 'unsaved scene A' });
    state = sceneWorkspaceReducer(state, {
      type: 'hydrate',
      sceneId: 'scene-b',
      runId: 'run-b',
      step: builderStep({ id: 'step-b', run_id: 'run-b', scene_id: 'scene-b' }),
      stage: 'Builder B loaded',
    });
    state = sceneWorkspaceReducer(state, {
      type: 'step_snapshot',
      sceneId: 'scene-a',
      step: builderStep({ revision: 2, draft_output: { manim_code: 'late server code' } }),
      stage: 'Late snapshot',
      draft: 'late server code',
    });

    expect(state['scene-a'].draft).toBe('unsaved scene A');
    expect(state['scene-a'].dirty).toBe(true);
    expect(state['scene-b'].draft).toBe('server code');
  });

  it('preserves a dirty draft as a conflict instead of rebinding it to a newer run', () => {
    let state = sceneWorkspaceReducer({}, { type: 'seed_scenes', scenes: [scene('scene-a')] });
    state = sceneWorkspaceReducer(state, {
      type: 'hydrate',
      sceneId: 'scene-a',
      runId: 'run-old',
      step: builderStep({ run_id: 'run-old', id: 'step-old' }),
      stage: 'Old Builder loaded',
    });
    state = sceneWorkspaceReducer(state, { type: 'edit', sceneId: 'scene-a', draft: 'local old-run code' });
    state = sceneWorkspaceReducer(state, {
      type: 'hydrate',
      sceneId: 'scene-a',
      runId: 'run-new',
      step: builderStep({
        run_id: 'run-new',
        id: 'step-new',
        draft_output: { manim_code: 'new server code' },
      }),
      stage: 'New Builder loaded',
    });

    expect(state['scene-a'].runId).toBe('run-new');
    expect(state['scene-a'].draft).toBe('new server code');
    expect(state['scene-a'].dirty).toBe(false);
    expect(state['scene-a'].conflictDraft).toBe('local old-run code');
    expect(state['scene-a'].conflictRunId).toBe('run-old');
  });

  it('filters stale REST scene snapshots after a newer WebSocket event', () => {
    const scenes = [
      { ...scene('scene-a'), generation_status: 'completed' as const, video_url: 'file:///old-a.mp4' },
      { ...scene('scene-b'), generation_status: 'completed' as const, video_url: 'file:///current-b.mp4' },
    ];

    expect(canApplyRestSnapshot(2, 3)).toBe(false);
    expect(filterCurrentRestScenes(scenes, { 'scene-a': 2, 'scene-b': 4 }, { 'scene-a': 3, 'scene-b': 4 }))
      .toEqual([scenes[1]]);
  });

  it('preserves a newer live scene while merging an older REST list', () => {
    const current = [
      { ...scene('scene-a'), generation_status: 'generating' as const, video_url: null },
      scene('scene-b'),
    ];
    const rest = [
      { ...scene('scene-a'), generation_status: 'completed' as const, video_url: 'file:///stale.mp4' },
      { ...scene('scene-b'), generation_status: 'completed' as const },
    ];

    const merged = mergeCurrentRestScenes(
      current,
      rest,
      { 'scene-a': 2, 'scene-b': 4 },
      { 'scene-a': 3, 'scene-b': 4 },
    );

    expect(merged[0]).toBe(current[0]);
    expect(merged[1]).toBe(rest[1]);
  });

  it('keeps render progress and video state separate per scene', () => {
    let state = sceneWorkspaceReducer({}, { type: 'seed_scenes', scenes: [scene('scene-a'), scene('scene-b')] });
    state = sceneWorkspaceReducer(state, {
      type: 'render',
      sceneId: 'scene-a',
      status: 'rendering',
      jobId: 'job-a',
      progress: 45,
    });
    state = sceneWorkspaceReducer(state, { type: 'video_resolved', sceneId: 'scene-b', videoUrl: 'https://video-b' });

    expect(state['scene-a'].renderStatus).toBe('rendering');
    expect(state['scene-a'].renderProgress).toBe(45);
    expect(state['scene-b'].renderStatus).toBe('idle');
    expect(state['scene-b'].videoUrl).toBe('https://video-b');
  });

  it('disables rendering while a newer Builder revision is not approved', () => {
    let state = sceneWorkspaceReducer({}, {
      type: 'seed_scenes',
      scenes: [{ ...scene('scene-a'), manim_code: 'old approved code' }],
    });
    expect(state['scene-a'].codeReady).toBe(true);

    state = sceneWorkspaceReducer(state, {
      type: 'stream_started',
      sceneId: 'scene-a',
      step: builderStep({ status: 'generating', id: 'new-step' }),
      stage: 'Generating replacement',
    });
    expect(state['scene-a'].codeReady).toBe(false);

    state = sceneWorkspaceReducer(state, {
      type: 'step_snapshot',
      sceneId: 'scene-a',
      step: builderStep({ status: 'approved', id: 'new-step' }),
      stage: 'Approved replacement',
    });
    expect(state['scene-a'].codeReady).toBe(true);
  });

  it('accepts authoritative video invalidation instead of retaining a stale asset', () => {
    let state = sceneWorkspaceReducer({}, {
      type: 'seed_scenes',
      scenes: [{ ...scene('scene-a'), video_url: 'file:///artifacts/old.mp4' }],
    });
    state = sceneWorkspaceReducer(state, {
      type: 'render',
      sceneId: 'scene-a',
      status: 'idle',
      persistedVideoRef: null,
    });

    expect(state['scene-a'].persistedVideoRef).toBeNull();
  });

  it('invalidates local video state as soon as a newer Builder starts', () => {
    let state = sceneWorkspaceReducer({}, {
      type: 'seed_scenes',
      scenes: [{
        ...scene('scene-a'),
        generation_status: 'completed',
        manim_code: 'old code',
        video_url: 'file:///artifacts/old.mp4',
      }],
    });
    state = sceneWorkspaceReducer(state, { type: 'video_resolved', sceneId: 'scene-a', videoUrl: 'blob:old' });
    state = sceneWorkspaceReducer(state, {
      type: 'stream_started',
      sceneId: 'scene-a',
      step: builderStep({ id: 'step-new', run_id: 'run-new', status: 'generating' }),
      stage: 'Generating replacement',
    });

    expect(state['scene-a'].persistedVideoRef).toBeNull();
    expect(state['scene-a'].videoUrl).toBeNull();
    expect(state['scene-a'].codeReady).toBe(false);
  });

  it('appends complete provider chunks for visible master streaming', () => {
    expect(appendStreamChunk('Master ', 'đang tạo')).toBe('Master đang tạo');
  });

  it('selects the latest retry step instead of the rejected first step', () => {
    const steps = [
      builderStep({ id: 'old', sequence: 1, status: 'rejected' }),
      builderStep({ id: 'retry', sequence: 2, status: 'generating' }),
    ];
    expect(latestStep(steps, 'builder')?.id).toBe('retry');
  });

  it('maps backend render events to frontend render states', () => {
    expect(renderStatusFromEvent('render.queued')).toBe('queued');
    expect(renderStatusFromEvent('render.started')).toBe('rendering');
    expect(renderStatusFromEvent('render.completed')).toBe('completed');
    expect(renderStatusFromEvent('render.failed')).toBe('failed');
  });

  it('uses step scene IDs and keeps bearer tokens out of WebSocket URLs', () => {
    expect(eventSceneId({}, builderStep())).toBe('scene-a');
    expect(websocketProjectUrl(
      undefined,
      'project-1',
      { protocol: 'https:', host: 'manim.example.hf.space' },
    )).toBe('wss://manim.example.hf.space/v1/ws/projects/project-1');
    expect(websocketProjectUrl('http://localhost:8000/v1/', 'project-1'))
      .toBe('ws://localhost:8000/v1/ws/projects/project-1');
    expect(websocketProjectUrl('https://api.example/v1', 'project-1'))
      .toBe('wss://api.example/v1/ws/projects/project-1');
    expect(websocketAuthProtocols('jwt.token')).toEqual(['manim.jwt', 'jwt.token']);
    expect(websocketAuthProtocols(null)).toBeUndefined();
  });

  it('rejects late events from an older run but accepts an explicitly announced new run', () => {
    expect(shouldAcceptRunEvent('run-new', 'run-old', 'hitl.step.pending_review', false)).toBe(false);
    expect(shouldAcceptRunEvent('run-old', 'run-new', 'hitl.step.queued', true)).toBe(true);
  });

  it('accepts terminal render state only for the active job', () => {
    expect(shouldAcceptTerminalRender('job-new', 'job-old')).toBe(false);
    expect(shouldAcceptTerminalRender('job-new', 'job-new')).toBe(true);
    expect(shouldAcceptTerminalRender(null, 'job-new')).toBe(false);
  });

  it('retains runtime API context and strategy-guard diagnostics from repair history', () => {
    const [review] = reviewStagesFromOutput({
      auto_review: {
        code: {
          iterations: [{
            iteration: 2,
            model: 'gemini-test',
            error_summary: 'Unknown API',
            outcome: 'duplicate_strategy',
            strategy_guard_triggered: true,
            strategy_guard_reason: 'Strategy already attempted',
            repair_history_count: 1,
            runtime_api_context: {
              manim_version: '0.19.0',
              target_symbol: 'OldFunction',
              exact_api: { exists: false },
              alternatives: [{ symbol: 'NewFunction', exists: true }],
            },
          }],
        },
      },
    });

    expect(review.phase).toBe('strategy_guard');
    expect(review.repair_history_count).toBe(1);
    expect(review.runtime_api_context?.manim_version).toBe('0.19.0');
    expect(review.runtime_api_context?.alternatives?.[0].symbol).toBe('NewFunction');
  });
});
