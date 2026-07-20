import type { AgentStep, AgentStepStatus, Scene } from './api';

export type RuntimeApiReference = {
  symbol?: string;
  exists?: boolean;
  signature?: string | null;
  summary?: string | null;
  example?: string | null;
  example_source?: string | null;
  reason?: string | null;
};

export type RuntimeApiContext = {
  manim_version?: string;
  target_symbol?: string;
  target_discovery?: string;
  source_line?: string | null;
  exact_api?: RuntimeApiReference;
  alternatives?: RuntimeApiReference[];
};

export type ReviewStage = {
  phase: string;
  reviewer: string;
  attempt: number;
  model: string;
  message: string;
  original_code?: string;
  replacement_code?: string;
  explanation?: string;
  error_summary?: string | null;
  outcome?: string | null;
  escalated?: boolean;
  same_error?: boolean;
  strategy_fingerprint?: string | null;
  strategy_guard_triggered?: boolean;
  strategy_guard_reason?: string | null;
  repair_history_count?: number;
  runtime_api_context?: RuntimeApiContext | null;
};

export type SceneRenderStatus = 'idle' | 'queued' | 'rendering' | 'completed' | 'failed' | 'cancelled';

export interface SceneWorkspace {
  sceneId: string;
  runId: string | null;
  stepId: string | null;
  revision: number;
  stepStatus: AgentStepStatus | 'missing';
  draft: string;
  dirty: boolean;
  dirtyRunId: string | null;
  dirtyStepId: string | null;
  conflictDraft: string | null;
  conflictRunId: string | null;
  conflictStepId: string | null;
  reviewStages: ReviewStage[];
  stage: string;
  isGenerating: boolean;
  generationStatus: Scene['generation_status'];
  codeReady: boolean;
  persistedVideoRef: string | null;
  videoUrl: string | null;
  renderJobId: string | null;
  renderStatus: SceneRenderStatus;
  renderProgress: number;
  error: string | null;
  renderError: string | null;
  isLoading: boolean;
}

export type SceneWorkspaceState = Record<string, SceneWorkspace>;

type HydrateSceneAction = {
  type: 'hydrate';
  sceneId: string;
  runId: string | null;
  step: AgentStep | null;
  stage: string;
};

export type SceneWorkspaceAction =
  | { type: 'seed_scenes'; scenes: Scene[] }
  | { type: 'mark_loading'; sceneId: string }
  | { type: 'load_failed'; sceneId: string; error: string }
  | HydrateSceneAction
  | { type: 'edit'; sceneId: string; draft: string }
  | { type: 'stream_started'; sceneId: string; step: AgentStep; stage: string }
  | { type: 'stream_delta'; sceneId: string; delta: string; step?: AgentStep }
  | {
      type: 'step_snapshot';
      sceneId: string;
      step: AgentStep;
      stage: string;
      draft?: string;
      reviews?: ReviewStage[];
      preserveDirty?: boolean;
    }
  | { type: 'append_review'; sceneId: string; review: ReviewStage; stage: string; step?: AgentStep }
  | {
      type: 'render';
      sceneId: string;
      status: SceneRenderStatus;
      jobId?: string | null;
      progress?: number;
      error?: string | null;
      persistedVideoRef?: string | null;
    }
  | { type: 'video_resolved'; sceneId: string; videoUrl: string | null }
  | { type: 'generation_status'; sceneId: string; status: Scene['generation_status'] };

export const emptySceneWorkspace = (sceneId: string): SceneWorkspace => ({
  sceneId,
  runId: null,
  stepId: null,
  revision: 1,
  stepStatus: 'missing',
  draft: '',
  dirty: false,
  dirtyRunId: null,
  dirtyStepId: null,
  conflictDraft: null,
  conflictRunId: null,
  conflictStepId: null,
  reviewStages: [],
  stage: 'Builder: đang chờ Master được duyệt',
  isGenerating: false,
  generationStatus: 'pending',
  codeReady: false,
  persistedVideoRef: null,
  videoUrl: null,
  renderJobId: null,
  renderStatus: 'idle',
  renderProgress: 0,
  error: null,
  renderError: null,
  isLoading: false,
});

const workspaceFor = (state: SceneWorkspaceState, sceneId: string) =>
  state[sceneId] || emptySceneWorkspace(sceneId);

export function sceneWorkspaceReducer(
  state: SceneWorkspaceState,
  action: SceneWorkspaceAction,
): SceneWorkspaceState {
  if (action.type === 'seed_scenes') {
    const next = { ...state };
    for (const scene of action.scenes) {
      const current = workspaceFor(next, scene.id);
      next[scene.id] = {
        ...current,
        generationStatus: scene.generation_status,
        codeReady: current.runId ? current.codeReady : Boolean(scene.manim_code),
        persistedVideoRef: scene.video_url ?? null,
        videoUrl: scene.video_url ? current.videoUrl : null,
      };
    }
    return next;
  }

  const current = workspaceFor(state, action.sceneId);
  let updated: SceneWorkspace;

  switch (action.type) {
    case 'mark_loading':
      updated = { ...current, isLoading: true, codeReady: false, error: null };
      break;
    case 'load_failed':
      updated = {
        ...current,
        isLoading: false,
        stage: `Builder: ${action.error}`,
        error: action.error,
      };
      break;
    case 'hydrate': {
      const serverDraft = action.step ? getStepTextRaw(action.step) : '';
      const incomingRunId = action.runId;
      const incomingStepId = action.step?.id || null;
      const sameDirtyBinding = current.dirty
        && current.dirtyRunId === incomingRunId
        && current.dirtyStepId === incomingStepId;
      const displacedDirtyDraft = current.dirty && !sameDirtyBinding;
      const invalidatesRenderedArtifact = Boolean(action.runId)
        && action.step?.status !== 'approved'
        && action.step?.status !== 'failed';
      updated = {
        ...current,
        runId: incomingRunId,
        stepId: incomingStepId,
        revision: action.step?.revision || 1,
        stepStatus: action.step?.status || 'missing',
        draft: sameDirtyBinding ? current.draft : serverDraft,
        dirty: sameDirtyBinding,
        dirtyRunId: sameDirtyBinding ? current.dirtyRunId : null,
        dirtyStepId: sameDirtyBinding ? current.dirtyStepId : null,
        conflictDraft: displacedDirtyDraft ? current.draft : current.conflictDraft,
        conflictRunId: displacedDirtyDraft ? current.dirtyRunId : current.conflictRunId,
        conflictStepId: displacedDirtyDraft ? current.dirtyStepId : current.conflictStepId,
        reviewStages: action.step
          ? reviewStagesFromOutput(action.step.draft_output || action.step.final_output)
          : current.reviewStages,
        stage: action.stage,
        isGenerating: action.step?.status === 'generating',
        generationStatus: stepGenerationStatus(action.step, current.generationStatus),
        codeReady: action.step ? action.step.status === 'approved' : current.codeReady,
        persistedVideoRef: invalidatesRenderedArtifact ? null : current.persistedVideoRef,
        videoUrl: invalidatesRenderedArtifact ? null : current.videoUrl,
        renderJobId: invalidatesRenderedArtifact ? null : current.renderJobId,
        renderStatus: invalidatesRenderedArtifact ? 'idle' : current.renderStatus,
        renderProgress: invalidatesRenderedArtifact ? 0 : current.renderProgress,
        renderError: invalidatesRenderedArtifact ? null : current.renderError,
        error: action.step?.error || null,
        isLoading: false,
      };
      break;
    }
    case 'edit':
      updated = {
        ...current,
        draft: action.draft,
        dirty: true,
        dirtyRunId: current.runId,
        dirtyStepId: current.stepId,
      };
      break;
    case 'stream_started': {
      const displacedDirtyDraft = current.dirty;
      updated = {
        ...current,
        runId: action.step.run_id,
        stepId: action.step.id,
        revision: action.step.revision,
        stepStatus: 'generating',
        draft: '',
        dirty: false,
        dirtyRunId: null,
        dirtyStepId: null,
        conflictDraft: displacedDirtyDraft ? current.draft : current.conflictDraft,
        conflictRunId: displacedDirtyDraft ? current.dirtyRunId : current.conflictRunId,
        conflictStepId: displacedDirtyDraft ? current.dirtyStepId : current.conflictStepId,
        reviewStages: [],
        stage: action.stage,
        isGenerating: true,
        generationStatus: 'generating',
        codeReady: false,
        persistedVideoRef: null,
        videoUrl: null,
        renderJobId: null,
        renderStatus: 'idle',
        renderProgress: 0,
        renderError: null,
        error: null,
        isLoading: false,
      };
      break;
    }
    case 'stream_delta': {
      const incomingRunId = action.step?.run_id || current.runId;
      const incomingStepId = action.step?.id || current.stepId;
      const changedStep = incomingRunId !== current.runId || incomingStepId !== current.stepId;
      const displacedDirtyDraft = current.dirty && changedStep;
      updated = {
        ...current,
        runId: incomingRunId,
        stepId: incomingStepId,
        revision: action.step?.revision || current.revision,
        draft: appendStreamChunk(changedStep ? '' : current.draft, action.delta),
        dirty: false,
        dirtyRunId: null,
        dirtyStepId: null,
        conflictDraft: displacedDirtyDraft ? current.draft : current.conflictDraft,
        conflictRunId: displacedDirtyDraft ? current.dirtyRunId : current.conflictRunId,
        conflictStepId: displacedDirtyDraft ? current.dirtyStepId : current.conflictStepId,
        isGenerating: true,
        generationStatus: 'generating',
        codeReady: false,
        isLoading: false,
      };
      break;
    }
    case 'step_snapshot': {
      const sameDirtyBinding = current.dirty
        && current.dirtyRunId === action.step.run_id
        && current.dirtyStepId === action.step.id;
      const preserveDraft = (action.preserveDirty ?? true) && sameDirtyBinding;
      const displacedDirtyDraft = current.dirty && (!sameDirtyBinding || !(action.preserveDirty ?? true));
      const changedStep = current.runId !== action.step.run_id || current.stepId !== action.step.id;
      const snapshotDraft = action.draft
        ?? (changedStep ? getStepTextRaw(action.step) : current.draft);
      const invalidatesRenderedArtifact = action.step.status === 'queued'
        || action.step.status === 'generating'
        || action.step.status === 'pending_review'
        || action.step.status === 'rejected';
      updated = {
        ...current,
        runId: action.step.run_id,
        stepId: action.step.id,
        revision: action.step.revision,
        stepStatus: action.step.status,
        draft: preserveDraft ? current.draft : snapshotDraft,
        dirty: preserveDraft,
        dirtyRunId: preserveDraft ? current.dirtyRunId : null,
        dirtyStepId: preserveDraft ? current.dirtyStepId : null,
        conflictDraft: displacedDirtyDraft ? current.draft : current.conflictDraft,
        conflictRunId: displacedDirtyDraft ? current.dirtyRunId : current.conflictRunId,
        conflictStepId: displacedDirtyDraft ? current.dirtyStepId : current.conflictStepId,
        reviewStages: action.reviews ?? current.reviewStages,
        stage: action.stage,
        isGenerating: action.step.status === 'generating',
        generationStatus: stepGenerationStatus(action.step, current.generationStatus),
        codeReady: action.step.status === 'approved',
        persistedVideoRef: invalidatesRenderedArtifact ? null : current.persistedVideoRef,
        videoUrl: invalidatesRenderedArtifact ? null : current.videoUrl,
        renderJobId: invalidatesRenderedArtifact ? null : current.renderJobId,
        renderStatus: invalidatesRenderedArtifact ? 'idle' : current.renderStatus,
        renderProgress: invalidatesRenderedArtifact ? 0 : current.renderProgress,
        renderError: invalidatesRenderedArtifact ? null : current.renderError,
        error: action.step.error || null,
        isLoading: false,
      };
      break;
    }
    case 'append_review': {
      const invalidatesRenderedArtifact = action.step?.status === 'generating';
      updated = {
        ...current,
        runId: action.step?.run_id || current.runId,
        stepId: action.step?.id || current.stepId,
        revision: action.step?.revision || current.revision,
        stepStatus: action.step?.status || current.stepStatus,
        reviewStages: [...current.reviewStages, action.review],
        stage: action.stage,
        isGenerating: action.step?.status === 'generating' || current.isGenerating,
        generationStatus: action.step ? stepGenerationStatus(action.step, current.generationStatus) : current.generationStatus,
        codeReady: action.step ? action.step.status === 'approved' : current.codeReady,
        persistedVideoRef: invalidatesRenderedArtifact ? null : current.persistedVideoRef,
        videoUrl: invalidatesRenderedArtifact ? null : current.videoUrl,
        renderJobId: invalidatesRenderedArtifact ? null : current.renderJobId,
        renderStatus: invalidatesRenderedArtifact ? 'idle' : current.renderStatus,
        renderProgress: invalidatesRenderedArtifact ? 0 : current.renderProgress,
        renderError: invalidatesRenderedArtifact ? null : current.renderError,
        isLoading: false,
      };
      break;
    }
    case 'render':
      updated = {
        ...current,
        renderStatus: action.status,
        renderJobId: action.jobId === undefined ? current.renderJobId : action.jobId,
        renderProgress: action.progress ?? current.renderProgress,
        renderError: action.error === undefined ? current.renderError : action.error,
        persistedVideoRef: action.persistedVideoRef === undefined
          ? current.persistedVideoRef
          : action.persistedVideoRef,
      };
      break;
    case 'video_resolved':
      updated = { ...current, videoUrl: action.videoUrl };
      break;
    case 'generation_status':
      updated = action.status === 'generating'
        ? {
            ...current,
            generationStatus: action.status,
            codeReady: false,
            persistedVideoRef: null,
            videoUrl: null,
            renderJobId: null,
            renderStatus: 'idle',
            renderProgress: 0,
            renderError: null,
          }
        : { ...current, generationStatus: action.status };
      break;
  }

  return { ...state, [action.sceneId]: updated };
}

const stepGenerationStatus = (
  step: AgentStep | null,
  fallback: Scene['generation_status'],
): Scene['generation_status'] => {
  if (!step) return fallback;
  if (step.status === 'failed') return 'failed';
  if (step.status === 'generating' || step.status === 'queued' || step.status === 'rejected') {
    return 'generating';
  }
  if (step.status === 'pending_review' || step.status === 'approved') return 'completed';
  return fallback;
};

export const reviewStagesFromOutput = (output: any): ReviewStage[] => {
  const reviews = output?.auto_review;
  if (!reviews || typeof reviews !== 'object') return [];
  return ['code', 'visual'].flatMap(reviewer => (reviews[reviewer]?.iterations || []).map((iteration: any) => ({
    phase: iteration.strategy_guard_triggered
      ? 'strategy_guard'
      : iteration.fix_applied
        ? 'patch_applied'
        : (iteration.outcome || (iteration.escalated ? 'escalated' : 'completed')),
    reviewer,
    attempt: iteration.iteration,
    model: iteration.model,
    message: iteration.strategy_guard_reason
      || iteration.fix_applied
      || iteration.error_summary
      || 'Reviewer completed without changes',
    original_code: iteration.original_code,
    replacement_code: iteration.replacement_code,
    explanation: iteration.fix_applied,
    error_summary: iteration.error_summary,
    outcome: iteration.outcome,
    escalated: iteration.escalated,
    same_error: iteration.same_error,
    strategy_fingerprint: iteration.strategy_fingerprint,
    strategy_guard_triggered: iteration.strategy_guard_triggered,
    strategy_guard_reason: iteration.strategy_guard_reason,
    repair_history_count: iteration.repair_history_count,
    runtime_api_context: iteration.runtime_api_context,
  })));
};

export const getStepTextRaw = (step?: AgentStep | null): string => {
  if (!step) return '';
  const output = step.final_output || step.draft_output;
  if (!output) return '';
  if (typeof output === 'string') return output;
  if (output.scenes) return JSON.stringify(output.scenes, null, 2);
  if (output.manim_code) return String(output.manim_code);
  if (output.text) return String(output.text);
  if (output.passed !== undefined) {
    return `Passed: ${output.passed}\n\nCode:\n${output.manim_code || ''}\n\nAttempts: ${output.total_attempts}\n${output.final_error ? `Error: ${output.final_error}` : ''}`;
  }
  return JSON.stringify(output, null, 2);
};

export const latestStep = (steps: AgentStep[], kind: AgentStep['kind']): AgentStep | null =>
  steps
    .filter(step => step.kind === kind)
    .sort((left, right) => left.sequence - right.sequence)
    .at(-1) || null;

export const stageLabel = (step?: AgentStep | null, eventStatus?: string, review?: ReviewStage) => {
  const name = step?.kind === 'idea_sketcher'
    ? 'Idea sketch'
    : step?.kind === 'storyboarder'
      ? 'Storyboard'
      : 'Builder';
  if (review?.message) return `${name}: ${review.message}`;
  const state = eventStatus || step?.status || 'working';
  const labels: Record<string, string> = {
    queued: 'đang chờ worker',
    started: 'đang khởi động',
    generating: 'đang tạo nội dung',
    pending_review: 'đang chờ bạn duyệt',
    edited: 'đã lưu bản chỉnh sửa',
    approved: 'đã được duyệt',
    auto_approved: 'đã tự duyệt',
    completed: 'đã hoàn thành',
    failed: step?.error || 'đã thất bại',
    rejected: 'đang tạo lại theo phản hồi',
  };
  return `${name}: ${labels[state] || state}`;
};

export const eventSceneId = (data: any, step?: AgentStep | null): string | null => {
  const value = data?.scene_id || step?.scene_id || data?.run?.scene_id || data?.job?.scene_id;
  return typeof value === 'string' && value ? value : null;
};

export const websocketBaseUrl = (configured?: string) => {
  const base = (configured || 'ws://localhost:8000/v1').replace(/\/$/, '');
  if (base.startsWith('https://')) return `wss://${base.slice('https://'.length)}`;
  if (base.startsWith('http://')) return `ws://${base.slice('http://'.length)}`;
  return base;
};

export const websocketProjectUrl = (configured: string | undefined, projectId: string, token?: string | null) => {
  const authQuery = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${websocketBaseUrl(configured)}/ws/projects/${projectId}${authQuery}`;
};

export const appendStreamChunk = (current: string, delta: string) => `${current}${delta}`;

export const renderStatusFromEvent = (eventType: string): SceneRenderStatus | null => {
  const statuses: Record<string, SceneRenderStatus> = {
    'render.queued': 'queued',
    'render.started': 'rendering',
    'render.completed': 'completed',
    'render.failed': 'failed',
    'render.cancelled': 'cancelled',
  };
  return statuses[eventType] || null;
};

export const shouldAcceptRunEvent = (
  activeRunId: string | null | undefined,
  incomingRunId: string,
  eventType: string,
  announcesNewRun: boolean,
) => !activeRunId
  || activeRunId === incomingRunId
  || (eventType === 'hitl.step.queued' && announcesNewRun);

/** A REST response may only mutate live pipeline state if no newer event arrived. */
export const canApplyRestSnapshot = (observedEventVersion: number, currentEventVersion: number) =>
  observedEventVersion === currentEventVersion;

export const filterCurrentRestScenes = (
  scenes: Scene[],
  observedEventVersions: Record<string, number>,
  currentEventVersions: Record<string, number>,
) => scenes.filter(scene => canApplyRestSnapshot(
  observedEventVersions[scene.id] || 0,
  currentEventVersions[scene.id] || 0,
));

/** Merge a REST scene list without replacing fields changed by newer live events. */
export const mergeCurrentRestScenes = (
  currentScenes: Scene[],
  restScenes: Scene[],
  observedEventVersions: Record<string, number>,
  currentEventVersions: Record<string, number>,
) => {
  const currentById = new Map(currentScenes.map(scene => [scene.id, scene]));
  return restScenes.map(scene => canApplyRestSnapshot(
    observedEventVersions[scene.id] || 0,
    currentEventVersions[scene.id] || 0,
  ) ? scene : (currentById.get(scene.id) || scene));
};

/** Terminal render events are authoritative only for the job currently tracked by the target. */
export const shouldAcceptTerminalRender = (
  activeJobId: string | null | undefined,
  incomingJobId: string | null | undefined,
) => Boolean(activeJobId && incomingJobId && activeJobId === incomingJobId);
