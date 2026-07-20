import React, {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import { useParams } from 'react-router-dom';
import {
  ArrowClockwise,
  ArrowUUpLeft,
  Check,
  CodeBlock,
  FilmStrip,
  Play,
  X,
} from '@phosphor-icons/react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Dialog } from '../components/ui/Dialog';
import type { DialogProps } from '../components/ui/Dialog';
import { api } from '../lib/api';
import type { AgentStep, AiRun, Project, RenderJob, Scene } from '../lib/api';
import {
  emptySceneWorkspace,
  appendStreamChunk,
  canApplyRestSnapshot,
  eventSceneId,
  filterCurrentRestScenes,
  getStepTextRaw,
  latestStep,
  mergeCurrentRestScenes,
  renderStatusFromEvent,
  reviewStagesFromOutput,
  sceneWorkspaceReducer,
  shouldAcceptRunEvent,
  shouldAcceptTerminalRender,
  stageLabel,
  websocketProjectUrl,
} from '../lib/sceneEditorState';
import type { ReviewStage, SceneRenderStatus } from '../lib/sceneEditorState';
import { isAuthDisabled, supabase } from '../lib/supabase';
import './SceneEditor.css';

const steps = [
  { name: 'Idea Sketch', label: 'Concise concept blueprint' },
  { name: 'Storyboarder', label: 'Project Storyboard' },
  { name: 'Manim Builder', label: 'Python Code + automatic review' },
];

type ProjectWorkspace = {
  runId: string | null;
  stepId: string | null;
  revision: number;
  status: AgentStep['status'] | 'missing';
  draft: string;
  dirty: boolean;
  stage: string;
  isGenerating: boolean;
  error: string | null;
};

type ProjectRenderState = {
  jobId: string | null;
  status: SceneRenderStatus;
  progress: number;
  persistedVideoRef: string | null;
  videoUrl: string | null;
  error: string | null;
};

const emptyProjectWorkspace: ProjectWorkspace = {
  runId: null,
  stepId: null,
  revision: 1,
  status: 'missing',
  draft: '',
  dirty: false,
  stage: 'Master: đang tải trạng thái dự án',
  isGenerating: false,
  error: null,
};

const emptyIdeaWorkspace: ProjectWorkspace = {
  ...emptyProjectWorkspace,
  stage: 'Idea sketch: đang tải trạng thái dự án',
};

const emptyProjectRender: ProjectRenderState = {
  jobId: null,
  status: 'idle',
  progress: 0,
  persistedVideoRef: null,
  videoUrl: null,
  error: null,
};

const renderLLMOutput = (text: string, selectedSceneIndex: number) => {
  if (!text) return null;
  const cleaned = text.replace(/<thought>[\s\S]*?<\/thought>/gi, '').trim();

  try {
    const parsed = JSON.parse(cleaned);
    if (
      parsed
      && typeof parsed === 'object'
      && typeof parsed.concept === 'string'
      && Array.isArray(parsed.key_points)
    ) {
      return (
        <div className="idea-blueprint">
          <h3>{parsed.concept}</h3>
          <p><strong>Audience:</strong> {parsed.audience}</p>
          <p><strong>Learning goal:</strong> {parsed.learning_goal}</p>
          <ul>{parsed.key_points.map((point: string, index: number) => <li key={index}>{point}</li>)}</ul>
          <p><strong>Visual metaphor:</strong> {parsed.visual_metaphor}</p>
          <p><strong>Scope:</strong> {parsed.scope_notes}</p>
        </div>
      );
    }
    const scenesList = parsed.scenes || (Array.isArray(parsed) ? parsed : null);
    if (Array.isArray(scenesList)) {
      const scene = scenesList[selectedSceneIndex] || scenesList[0];
      if (!scene) return null;
      return (
        <div className="storyboard-scene">
          <h3>Scene {scene.scene_order ?? selectedSceneIndex + 1}</h3>
          <p><strong>Narration:</strong> {scene.narration ?? ''}</p>
          <p><strong>Visual Action:</strong> {scene.visual_action ?? ''}</p>
        </div>
      );
    }
  } catch {
    // Plain text and Manim code are rendered line-by-line below.
  }

  return (
    <div>
      {cleaned.split('\n').map((line, index) => {
        if (line.startsWith('### ')) return <h3 key={index}>{line.slice(4)}</h3>;
        if (line.startsWith('**') && line.endsWith('**')) {
          return <strong key={index} className="output-strong">{line.replace(/\*\*/g, '')}</strong>;
        }
        if (line.startsWith('- ')) return <p key={index} className="output-list-item">• {line.slice(2)}</p>;
        if (line.trim() === '---') return <hr key={index} />;
        return <p key={index}>{line || '\u00a0'}</p>;
      })}
    </div>
  );
};

const newestRun = (runs: AiRun[]) => [...runs]
  .sort((left, right) => Date.parse(left.created_at) - Date.parse(right.created_at))
  .at(-1) || null;

const parsedStoryboardScenes = (draft: string): any[] => {
  if (!draft) return [];
  try {
    const parsed = JSON.parse(draft.replace(/<thought>[\s\S]*?<\/thought>/gi, '').trim());
    return parsed.scenes || (Array.isArray(parsed) ? parsed : []);
  } catch {
    return [];
  }
};

export const SceneEditor: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [ideaWorkspace, setIdeaWorkspace] = useState<ProjectWorkspace>(emptyIdeaWorkspace);
  const [projectWorkspace, setProjectWorkspace] = useState<ProjectWorkspace>(emptyProjectWorkspace);
  const [sceneWorkspaces, dispatchScene] = useReducer(sceneWorkspaceReducer, {});
  const [projectRender, setProjectRender] = useState<ProjectRenderState>(emptyProjectRender);
  const [selectedSceneId, setSelectedSceneIdState] = useState<string | null>(null);
  const [selectedStepView, setSelectedStepView] = useState(0);
  const [selectedStoryboardIndex, setSelectedStoryboardIndex] = useState(0);
  const [showRaw, setShowRaw] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [isStartingProject, setIsStartingProject] = useState(false);
  const [isStartingScene, setIsStartingScene] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'reconnecting' | 'offline'>('connecting');
  const [previewTarget, setPreviewTarget] = useState<'scene' | 'project'>('scene');
  const [dialog, setDialog] = useState<Omit<DialogProps, 'onConfirm' | 'onCancel'> & {
    isOpen: boolean;
    onConfirm?: (value?: string) => void;
  }>({ isOpen: false, title: '', message: '' });

  const selectedSceneIdRef = useRef<string | null>(null);
  const sceneRequestRef = useRef(0);
  const pipelineInFlightRef = useRef<Promise<void> | null>(null);
  const runSceneMapRef = useRef<Record<string, string>>({});
  const latestRunBySceneRef = useRef<Record<string, string>>({});
  const activeProjectRunIdRef = useRef<string | null>(null);
  const projectEventVersionRef = useRef(0);
  const sceneEventVersionRef = useRef<Record<string, number>>({});
  const topologyEventVersionRef = useRef(0);
  const streamQueueRef = useRef<Record<string, { delta: string; step?: AgentStep }>>({});
  const streamFrameRef = useRef<number | null>(null);
  const streamingStepsRef = useRef<Set<string>>(new Set());
  const wsRef = useRef<WebSocket | null>(null);
  const handleWsEventRef = useRef<(payload: any) => void>(() => undefined);
  const pollingJobsRef = useRef<Set<string>>(new Set());
  const renderPollWaitsRef = useRef<Record<string, { timer: number; resolve: () => void }>>({});
  const pollRenderJobRef = useRef<(jobId: string) => void>(() => undefined);
  const activeSceneRenderJobRef = useRef<Record<string, string>>({});
  const activeProjectRenderJobRef = useRef<string | null>(null);
  const resolvingJobsRef = useRef<Set<string>>(new Set());
  const resolvedJobsRef = useRef<Set<string>>(new Set());
  const objectUrlsRef = useRef<Set<string>>(new Set());
  const sceneVideoResolutionRef = useRef<Record<string, number>>({});
  const projectVideoResolutionRef = useRef(0);
  const resolvedSceneVideoAssetRef = useRef<Record<string, string>>({});
  const resolvedProjectVideoAssetRef = useRef<string | null>(null);
  const mountedRef = useRef(true);
  const hitlEnabledRef = useRef(true);

  const setSelectedSceneId = useCallback((sceneId: string | null) => {
    selectedSceneIdRef.current = sceneId;
    setSelectedSceneIdState(sceneId);
  }, []);

  const selectedWorkspace = selectedSceneId
    ? (sceneWorkspaces[selectedSceneId] || emptySceneWorkspace(selectedSceneId))
    : null;
  const storyboardScenes = useMemo(
    () => parsedStoryboardScenes(projectWorkspace.draft),
    [projectWorkspace.draft],
  );

  const rememberObjectUrl = useCallback((url: string | null) => {
    if (url?.startsWith('blob:')) objectUrlsRef.current.add(url);
    return url;
  }, []);

  const isCurrentRenderJob = useCallback((job: RenderJob) => (
    job.scene_id
      ? activeSceneRenderJobRef.current[job.scene_id] === job.id
      : activeProjectRenderJobRef.current === job.id
  ), []);

  const stopRenderPolling = useCallback((jobId: string) => {
    pollingJobsRef.current.delete(jobId);
    const waiting = renderPollWaitsRef.current[jobId];
    if (waiting) {
      window.clearTimeout(waiting.timer);
      delete renderPollWaitsRef.current[jobId];
      waiting.resolve();
    }
  }, []);

  const waitForRenderPoll = useCallback((jobId: string, delayMs: number) => new Promise<void>(resolve => {
    const timer = window.setTimeout(() => {
      delete renderPollWaitsRef.current[jobId];
      resolve();
    }, delayMs);
    renderPollWaitsRef.current[jobId] = { timer, resolve };
  }), []);

  const resolveSceneVideo = useCallback(async (
    pId: string,
    sceneId: string,
    assetUrl?: string | null,
  ) => {
    if (!assetUrl) return;
    if (resolvedSceneVideoAssetRef.current[sceneId] === assetUrl) return;
    const resolutionVersion = (sceneVideoResolutionRef.current[sceneId] || 0) + 1;
    sceneVideoResolutionRef.current[sceneId] = resolutionVersion;
    try {
      const url = rememberObjectUrl(await api.resolvePersistedVideoUrl(pId, assetUrl, sceneId));
      if (
        mountedRef.current
        && sceneVideoResolutionRef.current[sceneId] === resolutionVersion
      ) {
        resolvedSceneVideoAssetRef.current[sceneId] = assetUrl;
        dispatchScene({ type: 'video_resolved', sceneId, videoUrl: url });
        if (url && selectedSceneIdRef.current === sceneId) setPreviewTarget('scene');
      }
    } catch (error) {
      console.error('Unable to resolve persisted scene video:', error);
    }
  }, [rememberObjectUrl]);

  const resolveProjectVideo = useCallback(async (pId: string, assetUrl?: string | null) => {
    if (!assetUrl) return;
    if (resolvedProjectVideoAssetRef.current === assetUrl) return;
    const resolutionVersion = projectVideoResolutionRef.current + 1;
    projectVideoResolutionRef.current = resolutionVersion;
    try {
      const url = rememberObjectUrl(await api.resolvePersistedVideoUrl(pId, assetUrl));
      if (mountedRef.current && projectVideoResolutionRef.current === resolutionVersion) {
        resolvedProjectVideoAssetRef.current = assetUrl;
        setProjectRender(previous => ({ ...previous, persistedVideoRef: assetUrl, videoUrl: url }));
      }
    } catch (error) {
      console.error('Unable to resolve persisted project video:', error);
    }
  }, [rememberObjectUrl]);

  const hydrateSceneWorkspace = useCallback(async (
    pId: string,
    sceneId: string,
    knownRuns?: AiRun[],
  ) => {
    const requestId = ++sceneRequestRef.current;
    const observedEventVersion = sceneEventVersionRef.current[sceneId] || 0;
    dispatchScene({ type: 'mark_loading', sceneId });
    try {
      const runs = knownRuns || await api.getAiRuns(pId);
      for (const run of runs) {
        if (run.scene_id) runSceneMapRef.current[run.id] = run.scene_id;
      }
      const run = newestRun(runs.filter(candidate => candidate.scene_id === sceneId));
      if (
        requestId !== sceneRequestRef.current
        || selectedSceneIdRef.current !== sceneId
        || !canApplyRestSnapshot(
          observedEventVersion,
          sceneEventVersionRef.current[sceneId] || 0,
        )
      ) return;
      if (!run) {
        delete latestRunBySceneRef.current[sceneId];
        dispatchScene({
          type: 'hydrate',
          sceneId,
          runId: null,
          step: null,
          stage: 'Builder: chờ Master được duyệt',
        });
        return;
      }

      latestRunBySceneRef.current[sceneId] = run.id;

      const sceneSteps = await api.getAiRunSteps(pId, run.id);
      if (
        requestId !== sceneRequestRef.current
        || selectedSceneIdRef.current !== sceneId
        || !canApplyRestSnapshot(
          observedEventVersion,
          sceneEventVersionRef.current[sceneId] || 0,
        )
      ) return;
      const builder = latestStep(sceneSteps, 'builder');
      dispatchScene({
        type: 'hydrate',
        sceneId,
        runId: run.id,
        step: builder,
        stage: builder ? stageLabel(builder) : 'Builder: đang chờ worker',
      });
    } catch (error: any) {
      if (requestId !== sceneRequestRef.current) return;
      console.error('Failed to load scene run:', error);
      dispatchScene({
        type: 'load_failed',
        sceneId,
        error: error.message || 'không thể tải trạng thái',
      });
    }
  }, []);

  const loadPipeline = useCallback((pId: string, preferredSceneId?: string) => {
    if (pipelineInFlightRef.current) return pipelineInFlightRef.current;

    const task = (async () => {
      const observedTopologyVersion = topologyEventVersionRef.current;
      const observedProjectEventVersion = projectEventVersionRef.current;
      const observedSceneEventVersions = { ...sceneEventVersionRef.current };
      try {
        setLoadError(null);
        const settingsPromise = api.getSettings().catch(error => {
          console.error('Failed to load settings; keeping HITL enabled:', error);
          return null;
        });
        const [settings, loadedProject, existingRuns, loadedScenes, activeRenderJobs] = await Promise.all([
          settingsPromise,
          api.getProject(pId),
          api.getAiRuns(pId),
          api.getScenes(pId),
          api.getProjectRenderJobs(pId, true),
        ]);
        if (!mountedRef.current) return;
        if (!canApplyRestSnapshot(observedTopologyVersion, topologyEventVersionRef.current)) {
          return;
        }
        hitlEnabledRef.current = settings?.hitl_enabled ?? true;
        const projectRestSnapshotIsCurrent = canApplyRestSnapshot(
          observedProjectEventVersion,
          projectEventVersionRef.current,
        );
        if (projectRestSnapshotIsCurrent) setProject(loadedProject);

        let runs = existingRuns;
        let projectRun = newestRun(runs.filter(run => !run.scene_id));
        if (!projectRun) {
          const started = await api.generateScenes(
            pId,
            loadedProject.description || 'Generate an educational animation',
            hitlEnabledRef.current,
          );
          projectRun = started.run;
          runs = [...runs, started.run];
        }
        const projectSnapshotIsCurrent = canApplyRestSnapshot(
          observedProjectEventVersion,
          projectEventVersionRef.current,
        );
        if (projectSnapshotIsCurrent) activeProjectRunIdRef.current = projectRun.id;

        const projectSteps = await api.getAiRunSteps(pId, projectRun.id);
        if (!mountedRef.current) return;
        if (!canApplyRestSnapshot(observedTopologyVersion, topologyEventVersionRef.current)) {
          return;
        }
        const ideaSketcher = latestStep(projectSteps, 'idea_sketcher');
        const storyboarder = latestStep(projectSteps, 'storyboarder');
        if (
          projectSnapshotIsCurrent
          && canApplyRestSnapshot(observedProjectEventVersion, projectEventVersionRef.current)
        ) {
          setIdeaWorkspace(previous => ({
            ...previous,
            runId: projectRun?.id || null,
            stepId: ideaSketcher?.id || null,
            revision: ideaSketcher?.revision || 1,
            status: ideaSketcher?.status || (storyboarder ? 'approved' : 'missing'),
            draft: previous.dirty ? previous.draft : getStepTextRaw(ideaSketcher),
            stage: ideaSketcher
              ? stageLabel(ideaSketcher)
              : storyboarder
                ? 'Idea sketch: legacy run (not recorded separately)'
                : 'Idea sketch: đang chờ worker',
            isGenerating: ideaSketcher?.status === 'generating',
            error: ideaSketcher?.error || null,
          }));
          setProjectWorkspace(previous => ({
            ...previous,
            runId: projectRun?.id || null,
            stepId: storyboarder?.id || null,
            revision: storyboarder?.revision || 1,
            status: storyboarder?.status || 'missing',
            draft: previous.dirty ? previous.draft : getStepTextRaw(storyboarder),
            stage: storyboarder ? stageLabel(storyboarder) : 'Master: đang chờ worker',
            isGenerating: storyboarder?.status === 'generating',
            error: storyboarder?.error || null,
          }));
        }

        const orderedScenes = [...loadedScenes].sort((left, right) => left.scene_order - right.scene_order);
        setScenes(previous => mergeCurrentRestScenes(
          previous,
          orderedScenes,
          observedSceneEventVersions,
          sceneEventVersionRef.current,
        ));
        dispatchScene({
          type: 'seed_scenes',
          scenes: filterCurrentRestScenes(
            orderedScenes,
            observedSceneEventVersions,
            sceneEventVersionRef.current,
          ),
        });
        for (const run of runs) {
          if (run.scene_id) runSceneMapRef.current[run.id] = run.scene_id;
        }
        const scenesWithCurrentVideo = new Set<string>();
        for (const scene of orderedScenes) {
          const sceneSnapshotIsCurrent = canApplyRestSnapshot(
            observedSceneEventVersions[scene.id] || 0,
            sceneEventVersionRef.current[scene.id] || 0,
          );
          if (!sceneSnapshotIsCurrent) continue;
          const latestRun = newestRun(runs.filter(run => run.scene_id === scene.id));
          if (latestRun) {
            latestRunBySceneRef.current[scene.id] = latestRun.id;
            const reconciledStatus = latestRun.status === 'completed' && scene.manim_code
              ? 'completed'
              : latestRun.status === 'failed' || latestRun.status === 'cancelled'
                ? 'failed'
                : latestRun.status === 'queued' || latestRun.status === 'waiting_for_human'
                  ? 'generating'
                  : scene.generation_status;
            dispatchScene({
              type: 'generation_status',
              sceneId: scene.id,
              status: reconciledStatus,
            });
            if (reconciledStatus === 'completed' && scene.video_url) {
              scenesWithCurrentVideo.add(scene.id);
            }
          } else {
            delete latestRunBySceneRef.current[scene.id];
            if (scene.generation_status === 'completed' && scene.video_url) {
              scenesWithCurrentVideo.add(scene.id);
            }
          }
        }
        for (const scene of orderedScenes) {
          const sceneSnapshotIsCurrent = canApplyRestSnapshot(
            observedSceneEventVersions[scene.id] || 0,
            sceneEventVersionRef.current[scene.id] || 0,
          );
          if (!sceneSnapshotIsCurrent) continue;
          if (scene.video_url && scenesWithCurrentVideo.has(scene.id)) {
            void resolveSceneVideo(pId, scene.id, scene.video_url);
          } else if (!scenesWithCurrentVideo.has(scene.id)) {
            sceneVideoResolutionRef.current[scene.id] =
              (sceneVideoResolutionRef.current[scene.id] || 0) + 1;
            delete resolvedSceneVideoAssetRef.current[scene.id];
          }
        }
        const allSceneSnapshotsCurrent = orderedScenes.every(scene => canApplyRestSnapshot(
          observedSceneEventVersions[scene.id] || 0,
          sceneEventVersionRef.current[scene.id] || 0,
        ));
        if (projectSnapshotIsCurrent && allSceneSnapshotsCurrent) {
          if (
            loadedProject.video_url
            && orderedScenes.length > 0
            && scenesWithCurrentVideo.size === orderedScenes.length
          ) {
            void resolveProjectVideo(pId, loadedProject.video_url);
          } else {
            projectVideoResolutionRef.current += 1;
            resolvedProjectVideoAssetRef.current = null;
            setProjectRender(previous => ({
              ...previous,
              persistedVideoRef: null,
              videoUrl: null,
            }));
          }
        }

        const activeTargets = new Set<string>();
        for (const job of activeRenderJobs) {
          const targetKey = job.scene_id || 'project';
          if (activeTargets.has(targetKey)) continue;
          const targetSnapshotIsCurrent = job.scene_id
            ? canApplyRestSnapshot(
                observedSceneEventVersions[job.scene_id] || 0,
                sceneEventVersionRef.current[job.scene_id] || 0,
              )
            : canApplyRestSnapshot(
                observedProjectEventVersion,
                projectEventVersionRef.current,
              );
          if (!targetSnapshotIsCurrent) continue;
          activeTargets.add(targetKey);
          if (job.scene_id) {
            activeSceneRenderJobRef.current[job.scene_id] = job.id;
            dispatchScene({
              type: 'render',
              sceneId: job.scene_id,
              status: job.status,
              jobId: job.id,
              progress: job.progress,
              error: null,
              persistedVideoRef: job.asset_url ?? undefined,
            });
          } else {
            activeProjectRenderJobRef.current = job.id;
            setProjectRender(previous => ({
              ...previous,
              jobId: job.id,
              status: job.status,
              progress: job.progress,
              error: null,
            }));
          }
          pollRenderJobRef.current(job.id);
        }

        const currentSelection = preferredSceneId || selectedSceneIdRef.current;
        const nextScene = orderedScenes.find(scene => scene.id === currentSelection) || orderedScenes[0] || null;
        setSelectedSceneId(nextScene?.id || null);
        if (nextScene) {
          const sceneChangedDuringSnapshot = !canApplyRestSnapshot(
            observedSceneEventVersions[nextScene.id] || 0,
            sceneEventVersionRef.current[nextScene.id] || 0,
          );
          await hydrateSceneWorkspace(
            pId,
            nextScene.id,
            sceneChangedDuringSnapshot ? undefined : runs,
          );
        }
      } catch (error: any) {
        console.error('Failed to load pipeline:', error);
        if (mountedRef.current) setLoadError(error.message || 'Unable to load this project.');
      }
    })();

    pipelineInFlightRef.current = task;
    void task.finally(() => {
      if (pipelineInFlightRef.current === task) pipelineInFlightRef.current = null;
    });
    return task;
  }, [hydrateSceneWorkspace, resolveProjectVideo, resolveSceneVideo, setSelectedSceneId]);

  const reconcilePipeline = useCallback(async (pId: string, preferredSceneId?: string) => {
    const activeLoad = pipelineInFlightRef.current;
    if (activeLoad) await activeLoad;
    if (mountedRef.current) await loadPipeline(pId, preferredSceneId);
  }, [loadPipeline]);

  const enqueueStreamText = useCallback((key: string, delta: string, step?: AgentStep) => {
    const queued = streamQueueRef.current[key];
    streamQueueRef.current[key] = { delta: `${queued?.delta || ''}${delta}`, step: step || queued?.step };
    if (streamFrameRef.current !== null) return;
    streamFrameRef.current = window.requestAnimationFrame(() => {
      for (const [workspaceKey, value] of Object.entries(streamQueueRef.current)) {
        if (!value.delta) continue;
        if (workspaceKey === 'idea') {
          setIdeaWorkspace(previous => ({
            ...previous,
            draft: appendStreamChunk(previous.draft, value.delta),
            dirty: false,
            isGenerating: true,
          }));
        } else if (workspaceKey === 'project') {
          setProjectWorkspace(previous => ({
            ...previous,
            draft: appendStreamChunk(previous.draft, value.delta),
            dirty: false,
            isGenerating: true,
          }));
        } else {
          dispatchScene({
            type: 'stream_delta',
            sceneId: workspaceKey,
            delta: value.delta,
            step: value.step,
          });
        }
        streamQueueRef.current[workspaceKey] = { delta: '' };
      }
      streamFrameRef.current = null;
    });
  }, []);

  const stopStreaming = useCallback((key: string, stepId?: string) => {
    streamQueueRef.current[key] = { delta: '' };
    if (stepId) streamingStepsRef.current.delete(stepId);
  }, []);

  const finalizeRenderJob = useCallback(async (job: RenderJob) => {
    if (
      !isCurrentRenderJob(job)
      || resolvedJobsRef.current.has(job.id)
      || resolvingJobsRef.current.has(job.id)
    ) return;
    resolvingJobsRef.current.add(job.id);
    let videoUrl: string | null = null;
    let resolutionError: string | null = null;
    try {
      videoUrl = rememberObjectUrl(await api.getRenderVideoUrl(job.id));
    } catch (error: any) {
      console.error('Unable to load completed render:', error);
      resolutionError = error.message || 'Unable to load the completed render.';
    }

    try {
      if (!mountedRef.current || !isCurrentRenderJob(job)) return;
      resolvedJobsRef.current.add(job.id);
      stopRenderPolling(job.id);
      if (job.scene_id) {
        sceneEventVersionRef.current[job.scene_id] =
          (sceneEventVersionRef.current[job.scene_id] || 0) + 1;
        sceneVideoResolutionRef.current[job.scene_id] =
          (sceneVideoResolutionRef.current[job.scene_id] || 0) + 1;
        projectVideoResolutionRef.current += 1;
        if (job.asset_url && videoUrl) resolvedSceneVideoAssetRef.current[job.scene_id] = job.asset_url;
        resolvedProjectVideoAssetRef.current = null;
        dispatchScene({
          type: 'render',
          sceneId: job.scene_id,
          status: 'completed',
          jobId: job.id,
          progress: 100,
          persistedVideoRef: job.asset_url || null,
          error: resolutionError,
        });
        dispatchScene({ type: 'video_resolved', sceneId: job.scene_id, videoUrl });
        setScenes(previous => previous.map(scene => scene.id === job.scene_id
          ? { ...scene, video_url: job.asset_url || scene.video_url }
          : scene));
        setProject(previous => previous ? { ...previous, video_url: null } : previous);
        setProjectRender(previous => ({
          ...previous,
          status: 'idle',
          progress: 0,
          persistedVideoRef: null,
          videoUrl: null,
          error: null,
        }));
        delete activeSceneRenderJobRef.current[job.scene_id];
      } else {
        projectEventVersionRef.current += 1;
        projectVideoResolutionRef.current += 1;
        if (job.asset_url && videoUrl) resolvedProjectVideoAssetRef.current = job.asset_url;
        setProjectRender(previous => ({
          ...previous,
          jobId: job.id,
          status: 'completed',
          progress: 100,
          persistedVideoRef: job.asset_url || previous.persistedVideoRef,
          videoUrl,
          error: resolutionError,
        }));
        activeProjectRenderJobRef.current = null;
      }
    } finally {
      resolvingJobsRef.current.delete(job.id);
    }
  }, [isCurrentRenderJob, rememberObjectUrl, stopRenderPolling]);

  const pollRenderJob = useCallback(async (jobId: string) => {
    if (pollingJobsRef.current.has(jobId)) return;
    pollingJobsRef.current.add(jobId);
    let retryDelayMs = 1_500;
    try {
      while (mountedRef.current) {
        if (!pollingJobsRef.current.has(jobId) || resolvedJobsRef.current.has(jobId)) return;
        let job: RenderJob;
        try {
          job = await api.getRenderJob(jobId);
          retryDelayMs = 1_500;
        } catch (error) {
          console.error('Render polling request failed; retrying:', error);
          await waitForRenderPoll(jobId, retryDelayMs);
          retryDelayMs = Math.min(retryDelayMs * 2, 15_000);
          continue;
        }
        if (!isCurrentRenderJob(job)) return;
        if (job.scene_id) {
          dispatchScene({
            type: 'render',
            sceneId: job.scene_id,
            status: job.status,
            jobId: job.id,
            progress: job.progress,
            error: job.status === 'failed' || job.status === 'cancelled' ? job.logs || job.status : null,
            persistedVideoRef: job.asset_url ?? undefined,
          });
        } else {
          setProjectRender(previous => ({
            ...previous,
            jobId: job.id,
            status: job.status,
            progress: job.progress,
            error: job.status === 'failed' || job.status === 'cancelled' ? job.logs || job.status : null,
          }));
        }
        if (job.status === 'completed') {
          await finalizeRenderJob(job);
          return;
        }
        if (job.status === 'failed' || job.status === 'cancelled') {
          resolvedJobsRef.current.add(job.id);
          if (job.scene_id) delete activeSceneRenderJobRef.current[job.scene_id];
          else activeProjectRenderJobRef.current = null;
          return;
        }
        await waitForRenderPoll(jobId, 1_500);
      }
    } finally {
      stopRenderPolling(jobId);
    }
  }, [finalizeRenderJob, isCurrentRenderJob, stopRenderPolling, waitForRenderPoll]);
  pollRenderJobRef.current = jobId => {
    void pollRenderJob(jobId);
  };

  const handleRenderEvent = useCallback((type: string, data: any) => {
    const job = data?.job as RenderJob | undefined;
    const jobId = job?.id || data?.job_id;
    const sceneId = eventSceneId(data, null);
    const status = renderStatusFromEvent(type);
    if (!status || !jobId) return;

    if (status === 'queued') {
      if (sceneId) activeSceneRenderJobRef.current[sceneId] = jobId;
      else activeProjectRenderJobRef.current = jobId;
    } else if (status === 'rendering') {
      const activeJobId = sceneId
        ? activeSceneRenderJobRef.current[sceneId]
        : activeProjectRenderJobRef.current;
      if (activeJobId && activeJobId !== jobId) return;
      if (sceneId) activeSceneRenderJobRef.current[sceneId] = jobId;
      else activeProjectRenderJobRef.current = jobId;
    } else {
      const activeJobId = sceneId
        ? activeSceneRenderJobRef.current[sceneId]
        : activeProjectRenderJobRef.current;
      if (!shouldAcceptTerminalRender(activeJobId, jobId)) return;
    }

    if (sceneId) {
      sceneEventVersionRef.current[sceneId] = (sceneEventVersionRef.current[sceneId] || 0) + 1;
    } else {
      projectEventVersionRef.current += 1;
    }

    if (status === 'completed') {
      if (job) void finalizeRenderJob(job);
      else if (projectId) void reconcilePipeline(projectId, selectedSceneIdRef.current || undefined);
      return;
    }

    const terminalError = status === 'failed' || status === 'cancelled'
      ? job?.logs || status
      : null;
    if (sceneId) {
      dispatchScene({
        type: 'render',
        sceneId,
        status,
        jobId,
        progress: job?.progress,
        error: terminalError,
        persistedVideoRef: job?.asset_url ?? undefined,
      });
    } else {
      setProjectRender(previous => ({
        ...previous,
        jobId: jobId || previous.jobId,
        status,
        progress: job?.progress ?? previous.progress,
        error: terminalError,
        persistedVideoRef: job?.asset_url || previous.persistedVideoRef,
      }));
    }
    if (status === 'failed' || status === 'cancelled') {
      resolvedJobsRef.current.add(jobId);
      stopRenderPolling(jobId);
      if (sceneId) delete activeSceneRenderJobRef.current[sceneId];
      else activeProjectRenderJobRef.current = null;
    }
  }, [finalizeRenderJob, projectId, reconcilePipeline, stopRenderPolling]);

  const handleWsEvent = useCallback((payload: any) => {
    const type = payload?.type;
    const data = payload?.data;
    if (typeof type !== 'string' || !data) return;

    if (type.startsWith('render.')) {
      handleRenderEvent(type, data);
      return;
    }

    if (type === 'hitl.run.rolled_back') {
      topologyEventVersionRef.current += 1;
      projectEventVersionRef.current += 1;
      if (projectId) void reconcilePipeline(projectId, selectedSceneIdRef.current || undefined);
      return;
    }

    const step = data.step as AgentStep | undefined;
    if (!step) return;
    const eventStatus = type.replace('hitl.step.', '');
    const isIdea = step.kind === 'idea_sketcher';
    const isStoryboard = step.kind === 'storyboarder';
    const isProjectStep = isIdea || isStoryboard;
    const sceneId = isProjectStep
      ? null
      : eventSceneId(data, step) || runSceneMapRef.current[step.run_id] || null;
    if (sceneId) runSceneMapRef.current[step.run_id] = sceneId;
    const announcesNewRun = data?.run?.id === step.run_id;
    if (isProjectStep) {
      if (!shouldAcceptRunEvent(activeProjectRunIdRef.current, step.run_id, type, announcesNewRun)) return;
      if (type === 'hitl.step.queued' && announcesNewRun) activeProjectRunIdRef.current = step.run_id;
      projectEventVersionRef.current += 1;
    } else if (sceneId) {
      const activeRunId = latestRunBySceneRef.current[sceneId];
      if (!shouldAcceptRunEvent(activeRunId, step.run_id, type, announcesNewRun)) return;
      if (!activeRunId || (type === 'hitl.step.queued' && announcesNewRun)) {
        latestRunBySceneRef.current[sceneId] = step.run_id;
      }
      sceneEventVersionRef.current[sceneId] = (sceneEventVersionRef.current[sceneId] || 0) + 1;
      const startsNewBuilderVersion = (type === 'hitl.step.queued' && announcesNewRun)
        || ((type === 'hitl.step.generating' || type === 'hitl.step.started')
          && !streamingStepsRef.current.has(step.id));
      if (startsNewBuilderVersion) {
        const staleSceneRenderJob = activeSceneRenderJobRef.current[sceneId];
        if (staleSceneRenderJob) stopRenderPolling(staleSceneRenderJob);
        delete activeSceneRenderJobRef.current[sceneId];
        const staleProjectRenderJob = activeProjectRenderJobRef.current;
        if (staleProjectRenderJob) stopRenderPolling(staleProjectRenderJob);
        activeProjectRenderJobRef.current = null;
        sceneVideoResolutionRef.current[sceneId] =
          (sceneVideoResolutionRef.current[sceneId] || 0) + 1;
        projectVideoResolutionRef.current += 1;
        delete resolvedSceneVideoAssetRef.current[sceneId];
        resolvedProjectVideoAssetRef.current = null;
        setScenes(previous => previous.map(item => item.id === sceneId
          ? { ...item, video_url: null, generation_status: 'generating' }
          : item));
        setProject(previous => previous ? { ...previous, video_url: null } : previous);
        setProjectRender(emptyProjectRender);
      }
    }
    const workspaceKey = isIdea ? 'idea' : isStoryboard ? 'project' : sceneId;
    if (!workspaceKey) return;

    if (type === 'hitl.step.generating' || type === 'hitl.step.started') {
      if (!streamingStepsRef.current.has(step.id)) {
        streamingStepsRef.current.add(step.id);
        if (isProjectStep) {
          const setWorkspace = isIdea ? setIdeaWorkspace : setProjectWorkspace;
          setWorkspace(previous => ({
            ...previous,
            runId: step.run_id,
            stepId: step.id,
            revision: step.revision,
            status: 'generating',
            draft: '',
            dirty: false,
            stage: stageLabel(step, 'generating'),
            isGenerating: true,
            error: null,
          }));
        } else if (sceneId) {
          dispatchScene({ type: 'stream_started', sceneId, step, stage: stageLabel(step, 'generating') });
        }
      }
      if (typeof data.content_delta === 'string' && data.content_delta) {
        enqueueStreamText(workspaceKey, data.content_delta, step);
      }
      if (isProjectStep || sceneId === selectedSceneIdRef.current) {
        setSelectedStepView(isIdea ? 0 : isStoryboard ? 1 : 2);
      }
      return;
    }

    if (type === 'hitl.step.review' && sceneId && data.review) {
      const review = data.review as ReviewStage;
      dispatchScene({
        type: 'append_review',
        sceneId,
        review,
        stage: stageLabel(step, undefined, review),
        step,
      });
      return;
    }

    const draft = getStepTextRaw(step);
    const reviews = reviewStagesFromOutput(step.draft_output || step.final_output);
    if (isProjectStep) {
      stopStreaming(isIdea ? 'idea' : 'project', step.id);
      const setWorkspace = isIdea ? setIdeaWorkspace : setProjectWorkspace;
      setWorkspace(previous => ({
        ...previous,
        runId: step.run_id,
        stepId: step.id,
        revision: step.revision,
        status: step.status,
        draft: previous.dirty && type === 'hitl.step.edited' ? previous.draft : (draft || previous.draft),
        dirty: previous.dirty && type === 'hitl.step.edited',
        stage: stageLabel(step, eventStatus),
        isGenerating: step.status === 'generating',
        error: step.error || null,
      }));
    } else if (sceneId) {
      stopStreaming(sceneId, step.id);
      dispatchScene({
        type: 'step_snapshot',
        sceneId,
        step,
        stage: stageLabel(step, eventStatus),
        draft: draft || undefined,
        reviews,
        preserveDirty: type === 'hitl.step.edited',
      });
    }

    if (type === 'hitl.step.rejected' && data.retry) {
      const retry = data.retry as AgentStep;
      const retrySceneId = eventSceneId(data, retry) || sceneId;
      if (retrySceneId) {
        runSceneMapRef.current[retry.run_id] = retrySceneId;
        dispatchScene({
          type: 'step_snapshot',
          sceneId: retrySceneId,
          step: retry,
          stage: stageLabel(retry, 'queued'),
          preserveDirty: false,
        });
      } else {
        const setWorkspace = retry.kind === 'idea_sketcher'
          ? setIdeaWorkspace
          : setProjectWorkspace;
        setWorkspace(previous => ({
          ...previous,
          runId: retry.run_id,
          stepId: retry.id,
          revision: retry.revision,
          status: retry.status,
          dirty: false,
          stage: stageLabel(retry, 'queued'),
        }));
      }
    }

    if ((type === 'hitl.step.approved' || type === 'hitl.step.auto_approved') && isProjectStep) {
      if (isStoryboard) topologyEventVersionRef.current += 1;
      if (projectId) void reconcilePipeline(projectId, selectedSceneIdRef.current || undefined);
    }
    if ((type === 'hitl.step.approved' || type === 'hitl.step.auto_approved') && sceneId) {
      const staleSceneRenderJob = activeSceneRenderJobRef.current[sceneId];
      if (staleSceneRenderJob) stopRenderPolling(staleSceneRenderJob);
      delete activeSceneRenderJobRef.current[sceneId];
      const staleProjectRenderJob = activeProjectRenderJobRef.current;
      if (staleProjectRenderJob) stopRenderPolling(staleProjectRenderJob);
      activeProjectRenderJobRef.current = null;
      sceneVideoResolutionRef.current[sceneId] =
        (sceneVideoResolutionRef.current[sceneId] || 0) + 1;
      projectVideoResolutionRef.current += 1;
      delete resolvedSceneVideoAssetRef.current[sceneId];
      resolvedProjectVideoAssetRef.current = null;
      dispatchScene({
        type: 'render',
        sceneId,
        status: 'idle',
        jobId: null,
        progress: 0,
        persistedVideoRef: null,
        error: null,
      });
      dispatchScene({ type: 'video_resolved', sceneId, videoUrl: null });
      setScenes(previous => previous.map(scene => scene.id === sceneId
        ? { ...scene, video_url: null }
        : scene));
      setProject(previous => previous ? { ...previous, video_url: null } : previous);
      setProjectRender(previous => ({
        ...previous,
        status: 'idle',
        progress: 0,
        persistedVideoRef: null,
        videoUrl: null,
        error: null,
      }));
    }
    if (isProjectStep || sceneId === selectedSceneIdRef.current) {
      const ideaAdvanced = isIdea
        && (type === 'hitl.step.approved' || type === 'hitl.step.auto_approved');
      setSelectedStepView(ideaAdvanced ? 1 : isIdea ? 0 : isStoryboard ? 1 : 2);
    }
  }, [enqueueStreamText, handleRenderEvent, projectId, reconcilePipeline, stopRenderPolling, stopStreaming]);

  handleWsEventRef.current = handleWsEvent;

  useEffect(() => {
    const objectUrls = objectUrlsRef.current;
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      for (const url of objectUrls) URL.revokeObjectURL(url);
      objectUrls.clear();
    };
  }, []);

  useEffect(() => {
    if (!projectId) return;
    void loadPipeline(projectId);
  }, [loadPipeline, projectId]);

  useEffect(() => {
    if (!projectId) return;
    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let heartbeatTimer: number | null = null;
    let reconnectAttempt = 0;
    let lastSocketActivity = Date.now();

    const clearHeartbeat = () => {
      if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    };

    const connect = async () => {
      if (disposed) return;
      // Defer one microtask so React development StrictMode can dispose its
      // probe effect before any socket is opened.
      await Promise.resolve();
      if (disposed) return;
      setConnectionState(reconnectAttempt ? 'reconnecting' : 'connecting');
      let token: string | null = null;
      if (!isAuthDisabled) {
        try {
          const { data } = await supabase.auth.getSession();
          token = data.session?.access_token || null;
        } catch (error) {
          console.error('Unable to read WebSocket session:', error);
        }
      }
      if (disposed) return;

      socket = new WebSocket(websocketProjectUrl(import.meta.env.VITE_WS_BASE_URL, projectId, token));
      wsRef.current = socket;
      socket.onopen = () => {
        if (disposed) {
          socket?.close(1000, 'Scene editor unmounted');
          return;
        }
        reconnectAttempt = 0;
        lastSocketActivity = Date.now();
        setConnectionState('connected');
        heartbeatTimer = window.setInterval(() => {
          if (socket?.readyState !== WebSocket.OPEN) return;
          if (Date.now() - lastSocketActivity > 60_000) {
            socket.close(4000, 'Heartbeat timed out');
            return;
          }
          socket.send('ping');
        }, 25_000);
        void reconcilePipeline(projectId, selectedSceneIdRef.current || undefined);
      };
      socket.onmessage = event => {
        if (disposed) return;
        lastSocketActivity = Date.now();
        if (event.data === 'pong') return;
        try {
          handleWsEventRef.current(JSON.parse(event.data));
        } catch (error) {
          console.error('WebSocket payload could not be parsed:', error);
        }
      };
      socket.onerror = () => {
        if (!disposed) console.warn('WebSocket transport error; close handler will reconnect');
      };
      socket.onclose = event => {
        clearHeartbeat();
        if (disposed) return;
        setConnectionState(navigator.onLine ? 'reconnecting' : 'offline');
        reconnectAttempt += 1;
        const delay = Math.min(15_000, 750 * (2 ** Math.min(reconnectAttempt, 4)));
        console.warn(`WebSocket closed (${event.code}); retrying in ${delay}ms`);
        reconnectTimer = window.setTimeout(() => void connect(), delay);
      };
    };

    void connect();
    return () => {
      disposed = true;
      clearHeartbeat();
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close(1000, 'Scene editor unmounted');
      if (wsRef.current === socket) wsRef.current = null;
    };
  }, [projectId, reconcilePipeline]);

  useEffect(() => {
    const pollingJobs = pollingJobsRef.current;
    const pollingWaits = renderPollWaitsRef.current;
    return () => {
      if (streamFrameRef.current !== null) window.cancelAnimationFrame(streamFrameRef.current);
      pollingJobs.clear();
      for (const waiting of Object.values(pollingWaits)) {
        window.clearTimeout(waiting.timer);
        waiting.resolve();
      }
      for (const jobId of Object.keys(pollingWaits)) delete pollingWaits[jobId];
    };
  }, []);

  useEffect(() => {
    if (!projectId || connectionState === 'connected') return;
    const timer = window.setInterval(() => {
      if (!mountedRef.current || !navigator.onLine) return;
      void reconcilePipeline(projectId, selectedSceneIdRef.current || undefined);
    }, 5_000);
    return () => window.clearInterval(timer);
  }, [connectionState, projectId, reconcilePipeline]);

  const hasActiveGeneration = ideaWorkspace.isGenerating
    || ideaWorkspace.status === 'queued'
    || projectWorkspace.isGenerating
    || projectWorkspace.status === 'queued'
    || Object.values(sceneWorkspaces).some(workspace => (
      workspace.isGenerating || workspace.stepStatus === 'queued'
    ));

  useEffect(() => {
    if (!projectId || !hasActiveGeneration) return;
    // WebSocket heartbeats only prove the API connection is open. Refresh the
    // durable state while a generation is active so a worker timeout or crash
    // is surfaced even when no terminal WebSocket event can be emitted.
    const timer = window.setInterval(() => {
      if (mountedRef.current && navigator.onLine) {
        void reconcilePipeline(projectId, selectedSceneIdRef.current || undefined);
      }
    }, 15_000);
    return () => window.clearInterval(timer);
  }, [hasActiveGeneration, projectId, reconcilePipeline]);

  useEffect(() => {
    if (previewTarget === 'scene' && !selectedWorkspace?.videoUrl && projectRender.videoUrl) {
      setPreviewTarget('project');
    }
  }, [previewTarget, projectRender.videoUrl, selectedWorkspace?.videoUrl]);

  const closeDialog = () => setDialog(previous => ({ ...previous, isOpen: false }));

  const handleSceneChange = (sceneId: string) => {
    if (!projectId || sceneId === selectedSceneIdRef.current) return;
    setSelectedSceneId(sceneId);
    setSelectedStepView(2);
    setPreviewTarget('scene');
    void hydrateSceneWorkspace(projectId, sceneId);
  };

  const ideaComplete = ideaWorkspace.status === 'approved' || projectWorkspace.status !== 'missing';
  const currentStep = projectWorkspace.status === 'approved'
    ? (selectedWorkspace?.stepStatus === 'approved' ? 3 : 2)
    : ideaComplete
      ? 1
      : 0;
  const viewedWorkspace = selectedStepView === 0
    ? ideaWorkspace
    : selectedStepView === 1
      ? projectWorkspace
      : selectedWorkspace;
  const activeDraftText = viewedWorkspace?.draft || '';
  const viewedStatus = selectedStepView === 0
    ? ideaWorkspace.status
    : selectedStepView === 1
      ? projectWorkspace.status
      : selectedWorkspace?.stepStatus || 'missing';
  const viewedStage = selectedStepView === 0
    ? ideaWorkspace.stage
    : selectedStepView === 1
      ? projectWorkspace.stage
      : selectedWorkspace?.stage || 'Builder: chưa có scene';
  const viewedGenerating = selectedStepView === 0
    ? ideaWorkspace.isGenerating
    : selectedStepView === 1
      ? projectWorkspace.isGenerating
      : selectedWorkspace?.isGenerating || false;
  const isActionable = viewedStatus === 'pending_review'
    && Boolean(selectedStepView === 1
      ? projectWorkspace.runId && projectWorkspace.stepId
      : selectedStepView === 2 && selectedWorkspace?.runId && selectedWorkspace.stepId);
  const isDirty = selectedStepView === 1
    ? projectWorkspace.dirty
    : selectedStepView === 2
      ? selectedWorkspace?.dirty || false
      : false;

  const handleRawChange = (draft: string) => {
    if (!isActionable) return;
    if (selectedStepView === 1) {
      setProjectWorkspace(previous => ({ ...previous, draft, dirty: true }));
    } else if (selectedSceneId) {
      dispatchScene({ type: 'edit', sceneId: selectedSceneId, draft });
    }
  };

  const handleApprove = async () => {
    if (!projectId || !isActionable) return;
    const workspace = selectedStepView === 1 ? projectWorkspace : selectedWorkspace;
    if (!workspace?.runId || !workspace.stepId) return;
    setIsMutating(true);
    try {
      let revision = workspace.revision;
      if (workspace.dirty) {
        let draftOutput: Record<string, unknown>;
        if (selectedStepView === 1) {
          let parsed: any;
          try {
            parsed = JSON.parse(workspace.draft);
          } catch {
            throw new Error('Storyboard JSON is invalid. Fix it before approving.');
          }
          const sceneList = Array.isArray(parsed) ? parsed : parsed?.scenes;
          if (!Array.isArray(sceneList) || sceneList.length === 0) {
            throw new Error('Storyboard must contain a non-empty scenes array.');
          }
          draftOutput = { scenes: sceneList };
        } else {
          draftOutput = { manim_code: workspace.draft };
        }
        const edited = await api.editStep(projectId, workspace.runId, workspace.stepId, revision, draftOutput);
        revision = edited.revision;
        if (selectedStepView === 1) {
          setProjectWorkspace(previous => ({ ...previous, revision, dirty: false }));
        } else if (selectedSceneId) {
          dispatchScene({
            type: 'step_snapshot',
            sceneId: selectedSceneId,
            step: edited,
            stage: stageLabel(edited, 'edited'),
            draft: workspace.draft,
            preserveDirty: false,
          });
        }
      }
      const transition = await api.approveStep(projectId, workspace.runId, workspace.stepId, revision);
      if (transition?.step) {
        handleWsEvent({
          type: 'hitl.step.approved',
          data: { step: transition.step, scene_id: transition.step.scene_id || null },
        });
      }
    } catch (error: any) {
      console.error(error);
      setDialog({
        isOpen: true,
        title: 'Unable to approve',
        message: error.message || 'Failed to approve step.',
        onConfirm: closeDialog,
      });
    } finally {
      setIsMutating(false);
    }
  };

  const handleReject = () => {
    if (!projectId || !isActionable) return;
    const workspace = selectedStepView === 1 ? projectWorkspace : selectedWorkspace;
    if (!workspace?.runId || !workspace.stepId) return;
    setDialog({
      isOpen: true,
      title: 'Reject Draft',
      message: 'Provide feedback for the AI Agent to regenerate this stage.',
      inputPlaceholder: 'Feedback...',
      onConfirm: async feedback => {
        if (!feedback?.trim()) return;
        setIsMutating(true);
        try {
          const transition = await api.rejectStep(
            projectId,
            workspace.runId as string,
            workspace.stepId as string,
            workspace.revision,
            feedback.trim(),
          );
          if (transition?.step) {
            handleWsEvent({
              type: 'hitl.step.rejected',
              data: {
                step: transition.step,
                retry: transition.next_step,
                scene_id: transition.step.scene_id || null,
              },
            });
          }
          closeDialog();
        } catch (error: any) {
          console.error(error);
          setDialog({
            isOpen: true,
            title: 'Unable to reject',
            message: error.message || 'Failed to reject step.',
            onConfirm: closeDialog,
          });
        } finally {
          setIsMutating(false);
        }
      },
    });
  };

  const handleRollbackClick = () => {
    if (!projectId) return;
    const workspace = selectedStepView === 1 ? projectWorkspace : selectedWorkspace;
    if (!workspace?.runId || !workspace.stepId) return;
    setDialog({
      isOpen: true,
      title: 'Reopen approved draft?',
      message: selectedStepView === 1
        ? 'This cancels unfinished Builder runs and removes the scenes and videos derived from this Master approval.'
        : 'This clears the approved scene code, scene video, and full-project video before reopening the Builder draft.',
      onConfirm: async () => {
        setIsMutating(true);
        try {
          await api.rollbackRun(projectId, workspace.runId as string, workspace.stepId as string);
          closeDialog();
          await reconcilePipeline(projectId, selectedSceneIdRef.current || undefined);
        } catch (error: any) {
          setDialog({
            isOpen: true,
            title: 'Unable to rollback',
            message: error.message || 'Failed to rollback.',
            onConfirm: closeDialog,
          });
        } finally {
          setIsMutating(false);
        }
      },
    });
  };

  const handleStartSceneRun = () => {
    if (!projectId || !selectedSceneId || projectWorkspace.status !== 'approved') return;
    const scene = scenes.find(item => item.id === selectedSceneId);
    setDialog({
      isOpen: true,
      title: selectedWorkspace?.stepStatus === 'failed' ? 'Retry Builder' : 'Regenerate Scene',
      message: 'Start a new Builder run for this scene? Unsaved code in the current tab remains locally available until the new run starts.',
      onConfirm: async () => {
        setIsStartingScene(true);
        try {
          const started = await api.startSceneRun(
            projectId,
            selectedSceneId,
            scene?.storyboard_text || undefined,
            hitlEnabledRef.current,
          );
          sceneEventVersionRef.current[selectedSceneId] =
            (sceneEventVersionRef.current[selectedSceneId] || 0) + 1;
          const staleSceneRenderJob = activeSceneRenderJobRef.current[selectedSceneId];
          if (staleSceneRenderJob) stopRenderPolling(staleSceneRenderJob);
          delete activeSceneRenderJobRef.current[selectedSceneId];
          const staleProjectRenderJob = activeProjectRenderJobRef.current;
          if (staleProjectRenderJob) stopRenderPolling(staleProjectRenderJob);
          activeProjectRenderJobRef.current = null;
          sceneVideoResolutionRef.current[selectedSceneId] =
            (sceneVideoResolutionRef.current[selectedSceneId] || 0) + 1;
          projectVideoResolutionRef.current += 1;
          delete resolvedSceneVideoAssetRef.current[selectedSceneId];
          resolvedProjectVideoAssetRef.current = null;
          setScenes(previous => previous.map(item => item.id === selectedSceneId
            ? { ...item, video_url: null, generation_status: 'generating' }
            : item));
          setProject(previous => previous ? { ...previous, video_url: null } : previous);
          setProjectRender(emptyProjectRender);
          runSceneMapRef.current[started.run.id] = selectedSceneId;
          latestRunBySceneRef.current[selectedSceneId] = started.run.id;
          dispatchScene({
            type: 'step_snapshot',
            sceneId: selectedSceneId,
            step: started.first_step,
            stage: stageLabel(started.first_step, 'queued'),
            preserveDirty: true,
          });
          closeDialog();
        } catch (error: any) {
          setDialog({
            isOpen: true,
            title: 'Unable to start Builder',
            message: error.message || 'Failed to start a new scene run.',
            onConfirm: closeDialog,
          });
        } finally {
          setIsStartingScene(false);
        }
      },
    });
  };

  const handleStartProjectRun = async () => {
    if (!projectId || !project) return;
    setIsStartingProject(true);
    try {
      const started = await api.generateScenes(
        projectId,
        project.description || 'Generate an educational animation',
        hitlEnabledRef.current,
      );
      projectEventVersionRef.current += 1;
      activeProjectRunIdRef.current = started.run.id;
      setSelectedStepView(0);
      setIdeaWorkspace({
        runId: started.run.id,
        stepId: started.first_step.id,
        revision: started.first_step.revision,
        status: 'queued',
        draft: '',
        dirty: false,
        stage: stageLabel(started.first_step, 'queued'),
        isGenerating: false,
        error: null,
      });
      setProjectWorkspace(emptyProjectWorkspace);
    } catch (error: any) {
      setDialog({
        isOpen: true,
        title: 'Unable to retry generation pipeline',
        message: error.message || 'Failed to start a new idea and storyboard run.',
        onConfirm: closeDialog,
      });
    } finally {
      setIsStartingProject(false);
    }
  };

  const handleSceneRender = async () => {
    if (!projectId || !selectedSceneId || !selectedWorkspace?.codeReady) return;
    setPreviewTarget('scene');
    dispatchScene({ type: 'render', sceneId: selectedSceneId, status: 'queued', error: null });
    try {
      const operationVersion = `${selectedWorkspace.stepId || 'persisted'}:${selectedWorkspace.revision}`;
      const { job_id: jobId } = await api.enqueueSceneRender(
        projectId,
        selectedSceneId,
        operationVersion,
      );
      sceneEventVersionRef.current[selectedSceneId] =
        (sceneEventVersionRef.current[selectedSceneId] || 0) + 1;
      activeSceneRenderJobRef.current[selectedSceneId] = jobId;
      dispatchScene({ type: 'render', sceneId: selectedSceneId, status: 'queued', jobId, progress: 0 });
      void pollRenderJob(jobId);
    } catch (error: any) {
      dispatchScene({ type: 'render', sceneId: selectedSceneId, status: 'failed', error: error.message });
      setDialog({ isOpen: true, title: 'Render failed', message: error.message, onConfirm: closeDialog });
    }
  };

  const handleProjectRender = async () => {
    if (!projectId) return;
    setPreviewTarget('project');
    setProjectRender(previous => ({ ...previous, status: 'queued', error: null }));
    try {
      const operationVersion = scenes
        .map(scene => {
          const workspace = sceneWorkspaces[scene.id];
          return `${scene.id}:${workspace?.stepId || 'persisted'}:${workspace?.revision || 0}:${scene.manim_code || ''}`;
        })
        .join('|');
      const { job_id: jobId } = await api.enqueueProjectRender(projectId, operationVersion);
      projectEventVersionRef.current += 1;
      activeProjectRenderJobRef.current = jobId;
      setProjectRender(previous => ({ ...previous, jobId, status: 'queued', progress: 0 }));
      void pollRenderJob(jobId);
    } catch (error: any) {
      setProjectRender(previous => ({ ...previous, status: 'failed', error: error.message }));
      setDialog({ isOpen: true, title: 'Render failed', message: error.message, onConfirm: closeDialog });
    }
  };

  const selectedSceneRendering = selectedWorkspace?.renderStatus === 'queued'
    || selectedWorkspace?.renderStatus === 'rendering';
  const projectRendering = projectRender.status === 'queued' || projectRender.status === 'rendering';
  const hasProjectSources = scenes.some(scene => {
    const workspace = sceneWorkspaces[scene.id];
    const generationStatus = workspace?.generationStatus || scene.generation_status;
    return generationStatus === 'completed' && Boolean(workspace?.codeReady || scene.manim_code);
  });
  const previewUrl = previewTarget === 'project' ? projectRender.videoUrl : selectedWorkspace?.videoUrl;
  const previewRendering = previewTarget === 'project' ? projectRendering : selectedSceneRendering;
  const visibleRenderError = previewTarget === 'project'
    ? projectRender.error
    : selectedWorkspace?.renderError || null;

  const statusBadge = (() => {
    if (viewedGenerating) return { color: 'blue' as const, label: 'Generating…' };
    if (viewedStatus === 'approved') return { color: 'green' as const, label: 'Approved' };
    if (viewedStatus === 'failed') return { color: 'red' as const, label: 'Failed' };
    if (viewedStatus === 'pending_review') return { color: 'yellow' as const, label: 'Pending review' };
    return { color: 'gray' as const, label: viewedStatus === 'missing' ? 'Not started' : viewedStatus };
  })();

  return (
    <div className="editor-page animate-fade-in">
      <header className="editor-header">
        <div>
          <div className="editor-title-line">
            <h1 className="editorial-heading editor-title">{project?.title || 'Loading…'}</h1>
            <Badge color={connectionState === 'connected' ? 'green' : connectionState === 'offline' ? 'red' : 'yellow'}>
              Live {connectionState}
            </Badge>
          </div>
          <p className="editor-subtitle">{project?.description || 'Visualizing…'}</p>
        </div>
        <div className="editor-actions">
          {(ideaWorkspace.status === 'failed' || projectWorkspace.status === 'failed') && (
            <Button variant="secondary" onClick={() => void handleStartProjectRun()} disabled={isStartingProject}>
              <ArrowClockwise size={18} />
              <span>{isStartingProject ? 'Retrying pipeline…' : 'Retry Idea + Storyboard'}</span>
            </Button>
          )}
          <Button
            variant="primary"
            onClick={() => void handleSceneRender()}
            disabled={!selectedSceneId || !selectedWorkspace?.codeReady || selectedSceneRendering}
            title={!selectedWorkspace?.codeReady ? 'Approve Builder code before rendering this scene' : undefined}
          >
            <Play size={18} weight="fill" />
            <span>{selectedSceneRendering ? 'Rendering…' : 'Render Scene'}</span>
          </Button>
          <Button
            variant="primary"
            onClick={() => void handleProjectRender()}
            disabled={!hasProjectSources || projectRendering}
            title={!hasProjectSources ? 'Generate at least one Manim scene before rendering the final project' : 'Re-renders all scene sources and skips invalid scenes'}
          >
            <FilmStrip size={18} weight="fill" />
            <span>{projectRendering ? 'Rendering final video…' : 'Render Full Project'}</span>
          </Button>
        </div>
      </header>

      {loadError && (
        <div className="editor-error" role="alert">
          <span>{loadError}</span>
          <Button size="sm" variant="secondary" onClick={() => projectId && void loadPipeline(projectId, selectedSceneIdRef.current || undefined)}>
            Retry
          </Button>
        </div>
      )}

      {visibleRenderError && (
        <div className="editor-error" role="alert">
          <span>Render error: {visibleRenderError}</span>
        </div>
      )}

      <div className="stepper" aria-label="Generation stages">
        {steps.map((step, index) => {
          const completed = index < currentStep;
          const active = index === Math.min(currentStep, 2);
          const disabled = (index === 1 && !ideaComplete)
            || (index === 2 && projectWorkspace.status !== 'approved' && scenes.length === 0);
          return (
            <button
              type="button"
              key={step.name}
              className={`step-item ${completed ? 'step-completed' : active ? 'step-active' : 'step-pending'} ${index === selectedStepView ? 'step-viewed' : ''}`}
              onClick={() => setSelectedStepView(index)}
              disabled={disabled}
              aria-current={index === selectedStepView ? 'step' : undefined}
            >
              <span className="step-circle">{index + 1}</span>
              <span className="step-label">{step.name}</span>
              {index < steps.length - 1 && <span className="step-line" />}
            </button>
          );
        })}
      </div>

      {selectedStepView === 1 && storyboardScenes.length > 0 && (
        <div className="scene-tabs" role="tablist" aria-label="Storyboard scenes">
          {storyboardScenes.map((scene, index) => (
            <button
              type="button"
              role="tab"
              aria-selected={index === selectedStoryboardIndex}
              className={`scene-tab ${index === selectedStoryboardIndex ? 'scene-tab-selected' : ''}`}
              key={`${scene.scene_order ?? index}-${index}`}
              onClick={() => setSelectedStoryboardIndex(index)}
            >
              Scene {scene.scene_order ?? index + 1}
            </button>
          ))}
        </div>
      )}

      {selectedStepView === 2 && scenes.length > 0 && (
        <div className="scene-tabs" role="tablist" aria-label="Builder scenes">
          {scenes.map((scene, index) => {
            const workspace = sceneWorkspaces[scene.id] || emptySceneWorkspace(scene.id);
            const sceneState = workspace.dirty ? 'dirty' : workspace.generationStatus;
            return (
              <button
                type="button"
                role="tab"
                aria-selected={scene.id === selectedSceneId}
                className={`scene-tab ${scene.id === selectedSceneId ? 'scene-tab-selected' : ''}`}
                key={scene.id}
                onClick={() => handleSceneChange(scene.id)}
              >
                Scene {index + 1}
                <span
                  className={`scene-tab-state scene-tab-state-${sceneState}`}
                  title={`Scene state: ${sceneState}`}
                  aria-label={`Scene state: ${sceneState}`}
                />
              </button>
            );
          })}
        </div>
      )}

      <div className="editor-content" data-with-preview={Boolean(previewUrl || previewRendering)}>
        <div className="editor-main-col">
          <Card padding="lg" className="output-card">
            <div className="output-header">
              <div className="output-statuses">
                <Badge color={statusBadge.color}>{statusBadge.label}</Badge>
                {isDirty && <Badge color="yellow">Unsaved locally</Badge>}
              </div>
              <div className="output-header-actions">
                <Button variant="ghost" size="sm" onClick={() => setShowRaw(previous => !previous)} disabled={!activeDraftText}>
                  <CodeBlock size={16} /> {showRaw ? 'Hide raw' : isActionable ? 'Edit raw' : 'View raw'}
                </Button>
                {selectedStepView === 2 && selectedSceneId && projectWorkspace.status === 'approved' && (
                  <Button variant="ghost" size="sm" onClick={handleStartSceneRun} disabled={isStartingScene || selectedSceneRendering}>
                    <ArrowClockwise size={16} />
                    {selectedWorkspace?.stepStatus === 'failed' ? 'Retry Builder' : 'Regenerate Scene'}
                  </Button>
                )}
                {selectedStepView !== 0 && viewedStatus === 'approved' && (
                  <Button variant="ghost" size="sm" onClick={handleRollbackClick} disabled={isMutating}>
                    <ArrowUUpLeft size={16} /> Reopen review
                  </Button>
                )}
              </div>
            </div>

            <div className="output-body">
              {showRaw ? (
                <textarea
                  className="raw-editor"
                  value={activeDraftText}
                  readOnly={!isActionable}
                  aria-label={`${steps[selectedStepView].name} raw output`}
                  onChange={event => handleRawChange(event.target.value)}
                />
              ) : (
                <div className={`elegant-renderer ${selectedStepView === 2 ? 'code-output' : ''}`}>
                  {renderLLMOutput(activeDraftText, selectedStoryboardIndex) || (
                    <p>{viewedGenerating ? '' : viewedStage}</p>
                  )}
                  {viewedGenerating && <span className="blinking-cursor" aria-label="Generating" />}
                </div>
              )}

              {selectedStepView === 2 && selectedWorkspace?.reviewStages.length ? (
                <section className="review-stage-panel" aria-live="polite">
                  <h3>Builder auto-review</h3>
                  {selectedWorkspace.reviewStages.map((review, index) => (
                    <article className="review-stage" key={`${review.phase}-${review.model}-${review.attempt}-${index}`}>
                      <strong>{review.message}</strong>
                      <span>{review.reviewer} · attempt {review.attempt} · {review.model}</span>
                      <div className="review-debug-meta">
                        {review.outcome && <span>Outcome: {review.outcome}</span>}
                        {Boolean(review.repair_history_count) && (
                          <span>Prior repairs: {review.repair_history_count}</span>
                        )}
                        {review.escalated && <span>Escalated</span>}
                        {review.same_error && <span>Same error persisted</span>}
                        {review.strategy_guard_triggered && <span>Duplicate strategy blocked</span>}
                      </div>
                      {review.strategy_fingerprint && (
                        <code className="strategy-fingerprint">Strategy: {review.strategy_fingerprint}</code>
                      )}
                      {review.original_code && review.replacement_code && (
                        <div className="review-patch">
                          <del>{review.original_code}</del>
                          <ins>{review.replacement_code}</ins>
                          {review.explanation && <small>{review.explanation}</small>}
                        </div>
                      )}
                      {review.runtime_api_context && (
                        <details className="runtime-api-context">
                          <summary>
                            Runtime Manim {review.runtime_api_context.manim_version || 'unknown'} API · {review.runtime_api_context.target_symbol || 'unknown symbol'}
                          </summary>
                          {review.runtime_api_context.source_line && (
                            <code>Source: {review.runtime_api_context.source_line}</code>
                          )}
                          <p>
                            Runtime symbol {review.runtime_api_context.exact_api?.exists ? 'exists' : 'does not exist'}.
                          </p>
                          {review.runtime_api_context.exact_api?.signature && (
                            <code>{review.runtime_api_context.target_symbol}{review.runtime_api_context.exact_api.signature}</code>
                          )}
                          {review.runtime_api_context.exact_api?.summary && (
                            <p>{review.runtime_api_context.exact_api.summary}</p>
                          )}
                          {review.runtime_api_context.exact_api?.example && (
                            <pre>{review.runtime_api_context.exact_api.example}</pre>
                          )}
                          {review.runtime_api_context.alternatives?.map(alternative => (
                            <div className="runtime-api-alternative" key={alternative.symbol}>
                              <strong>Alternative: {alternative.symbol}</strong>
                              {alternative.reason && <p>{alternative.reason}</p>}
                              {alternative.signature && <code>{alternative.signature}</code>}
                              {alternative.example && <pre>{alternative.example}</pre>}
                            </div>
                          ))}
                        </details>
                      )}
                    </article>
                  ))}
                </section>
              ) : null}

              {selectedStepView === 2 && selectedWorkspace?.conflictDraft && (
                <details className="runtime-api-context local-draft-conflict">
                  <summary>Local draft preserved from a previous Builder run</summary>
                  <p>
                    This draft belongs to run {selectedWorkspace.conflictRunId || 'unknown'} and was not attached to the current step.
                  </p>
                  <pre>{selectedWorkspace.conflictDraft}</pre>
                </details>
              )}
            </div>

            {isActionable && (
              <div className="action-bar">
                <Button variant="ghost" className="reject-btn" onClick={handleReject} disabled={isMutating || viewedGenerating}>
                  <X size={18} weight="bold" /> Reject
                </Button>
                <Button variant="primary" className="approve-btn" onClick={() => void handleApprove()} disabled={isMutating || viewedGenerating || !activeDraftText}>
                  <Check size={18} weight="bold" /> {isMutating ? 'Saving…' : 'Approve'}
                </Button>
              </div>
            )}
          </Card>
        </div>

        {(previewUrl || previewRendering) && (
          <div className="editor-side-col">
            <Card padding="none" className="preview-card">
              {previewRendering ? (
                <div className="preview-placeholder">
                  <div className="spinner" />
                  <span>{previewTarget === 'project' ? 'Rendering final project from scene sources…' : 'Rendering scene…'}</span>
                </div>
              ) : (
                <video src={previewUrl || undefined} controls preload="metadata" />
              )}
            </Card>
            <div className="preview-switcher">
              {selectedWorkspace?.videoUrl && (
                <Button size="sm" variant={previewTarget === 'scene' ? 'primary' : 'secondary'} onClick={() => setPreviewTarget('scene')}>
                  Scene video
                </Button>
              )}
              {projectRender.videoUrl && (
                <Button size="sm" variant={previewTarget === 'project' ? 'primary' : 'secondary'} onClick={() => setPreviewTarget('project')}>
                  Full project
                </Button>
              )}
            </div>
          </div>
        )}
      </div>

      <Dialog
        {...dialog}
        onConfirm={dialog.onConfirm || closeDialog}
        onCancel={closeDialog}
      />
    </div>
  );
};
