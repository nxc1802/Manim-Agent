import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import PipelineVisualizer from '../components/PipelineVisualizer';
import type { Stage } from '../components/PipelineVisualizer';
import CodePreview from '../components/CodePreview';
import { 
  ArrowLeft, 
  Check, 
  AlertTriangle, 
  Activity, 
  Loader2, 
  Play, 
  Music, 
  Layout, 
  Wand2, 
  History, 
  Save, 
  Edit2, 
  RotateCcw, 
  FileText, 
  Code 
} from 'lucide-react';
import { sceneService } from '../services/api';
import { useSceneWebSocket } from '../hooks/useSceneWebSocket';
import { useSceneStore } from '../store/useSceneStore';
import styles from './SceneEditor.module.css';

const formatDslToPython = (dsl: any): string => {
  if (!dsl) return '';
  const title = dsl.title || 'Untitled Scene';
  const theme = dsl.global_theme ? 
    `ThemeConfig(primary_color=${JSON.stringify(dsl.global_theme.primary_color || 'BLUE')})` : 
    `ThemeConfig(primary_color='BLUE')`;
    
  const beatsStr = (dsl.beats || []).map((beat: any) => {
    const visualElementsStr = (beat.visual_elements || []).map((vel: any) => {
      const positionStr = vel.position ? 
        `Position(x=${vel.position.x ?? 0.0}, y=${vel.position.y ?? 0.0})` : 'Position(x=0.0, y=0.0)';
      return `                VisualElement(
                    id=${JSON.stringify(vel.id)},
                    type=${JSON.stringify(vel.type)},
                    params=${JSON.stringify(vel.params || {})},
                    position=${positionStr}
                )`;
    }).join(',\n');

    const animationsStr = (beat.animations || []).map((anim: any) => {
      return `                AnimationStep(
                    target_ids=${JSON.stringify(anim.target_ids || [])},
                    animation_type=${JSON.stringify(anim.animation_type)},
                    run_time=${anim.run_time ?? 1.0}
                )`;
    }).join(',\n');

    return `        SceneDSLBeat(
            id=${JSON.stringify(beat.id)},
            label=${JSON.stringify(beat.label)},
            duration_seconds=${beat.duration_seconds ?? 1.0},
            narration=${JSON.stringify(beat.narration || '')},
            visual_elements=[\n${visualElementsStr}\n            ],
            animations=[\n${animationsStr}\n            ]
        )`;
  }).join(',\n');

  return `from shared.schemas.scene_dsl import SceneDSLBeat, VisualElement, AnimationStep, Position, ThemeConfig

class GeneratedSceneDSL:
    title = ${JSON.stringify(title)}
    global_theme = ${theme}
    beats = [
${beatsStr}
    ]
`;
};

const defaultDslTemplate = `from shared.schemas.scene_dsl import SceneDSLBeat, VisualElement, AnimationStep, Position, ThemeConfig

class GeneratedSceneDSL:
    title = "My Scene DSL"
    global_theme = ThemeConfig(primary_color="BLUE")
    beats = [
        SceneDSLBeat(
            id="beat_1",
            label="Intro Beat",
            duration_seconds=2.0,
            narration="Welcome to this video scene.",
            visual_elements=[
                VisualElement(
                    id="title_text",
                    type="get_text_panel",
                    params={"text": "Introduction", "color": "BLUE"},
                    position=Position(x=0.0, y=0.0)
                )
            ],
            animations=[
                AnimationStep(
                    target_ids=["title_text"],
                    animation_type="cinematic_fade_in",
                    run_time=1.0
                )
            ]
        )
    ]
`;

const SceneEditor = () => {
  const { sceneId } = useParams<{ sceneId: string }>();
  const navigate = useNavigate();
  const { currentScene: scene, loading, fetchScene, updateSceneState, generateStoryboard, approveStoryboard, planBeats, approvePlan } = useSceneStore();

  const { events, isConnected, lastEvent } = useSceneWebSocket(sceneId);

  // Custom UI State
  const [sidebarTab, setSidebarTab] = useState<'activity' | 'history'>('activity');
  const [versions, setVersions] = useState<any[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<any | null>(null);
  const [activeView, setActiveView] = useState<'code' | 'dsl'>('code');
  const [dslCode, setDslCode] = useState<string>('');
  const [dslError, setDslError] = useState<string | null>(null);
  const [isDslSaving, setIsDslSaving] = useState<boolean>(false);

  const loadVersions = useCallback(async () => {
    if (!sceneId) return;
    try {
      const res = await sceneService.getVersions(sceneId);
      setVersions(res.data);
    } catch (err) {
      console.error('Failed to load versions', err);
    }
  }, [sceneId]);

  useEffect(() => {
    if (sceneId) {
      fetchScene(sceneId);
      loadVersions();
    }
  }, [sceneId, fetchScene, loadVersions]);

  useEffect(() => {
    if (scene) {
      if (scene.scene_dsl) {
        setDslCode(formatDslToPython(scene.scene_dsl));
      } else {
        setDslCode(defaultDslTemplate);
      }
    }
  }, [scene]);

  // Sync scene state and versions if WS event indicates completion
  useEffect(() => {
    if (lastEvent?.phase?.endsWith('_ok') || lastEvent?.phase === 'completed' || lastEvent?.phase === 'job_completed') {
      if (sceneId) {
        fetchScene(sceneId);
        loadVersions();
      }
    }
  }, [lastEvent, sceneId, fetchScene, loadVersions]);

  const handleAction = async (name: string, fn: () => Promise<any>) => {
    try {
      await fn();
      if (sceneId) {
        fetchScene(sceneId);
        loadVersions();
      }
    } catch (err) {
      console.error(`Action ${name} failed`, err);
    }
  };

  const handleRollback = async (entityType: string, versionNum: number) => {
    if (!sceneId) return;
    if (!window.confirm(`Are you sure you want to rollback ${entityType} to version ${versionNum}?`)) {
      return;
    }
    try {
      await sceneService.rollback(sceneId, {
        entity_type: entityType,
        target_version: versionNum,
      });
      setSelectedVersion(null);
      fetchScene(sceneId);
      loadVersions();
    } catch (err: any) {
      alert(`Rollback failed: ${err.response?.data?.detail || err.message || err}`);
    }
  };

  const handleSaveDsl = async () => {
    if (!sceneId) return;
    setIsDslSaving(true);
    setDslError(null);
    try {
      const res = await sceneService.patchDsl(sceneId, { dsl_code: dslCode });
      updateSceneState(res.data.scene);
      loadVersions();
      setActiveView('code');
    } catch (err: any) {
      const errMsg = err.response?.data?.detail || err.message || err;
      setDslError(errMsg);
    } finally {
      setIsDslSaving(false);
    }
  };

  if (loading || !scene) {
    return (
      <div className={styles.loaderContainer} style={{ minHeight: '100vh', color: 'white' }}>
        <Loader2 className="spin" />
      </div>
    );
  }

  const stages: Stage[] = [
    { 
      id: 'director', 
      label: 'Director', 
      status: scene.storyboard_status === 'approved' ? 'completed' : 
              scene.storyboard_status === 'pending_review' ? 'running' : 'pending' 
    },
    { 
      id: 'planner', 
      label: 'Planner', 
      status: scene.plan_status === 'approved' ? 'completed' : 
              scene.plan_status === 'pending_review' ? 'running' : 'pending' 
    },
    { 
      id: 'audio', 
      label: 'Audio & Sync', 
      status: (scene.voice_script_status === 'approved' && scene.sync_segments) ? 'completed' : 
              (scene.voice_script_status === 'pending_review' || scene.audio_url) ? 'running' : 'pending' 
    },
    { 
      id: 'builder', 
      label: 'Builder', 
      status: scene.review_loop_status === 'completed' ? 'completed' : 
              scene.review_loop_status === 'running' ? 'running' : 'pending' 
    },
  ];

  return (
    <div className={styles.container}>
      <Sidebar />
      
      <main className={styles.main}>
        <header className={styles.header}>
          <div className={`glass ${styles.backButton}`} onClick={() => navigate(-1)}>
            <ArrowLeft size={20} />
          </div>
          <div>
            <h1 className={styles.title}>Scene Editor</h1>
            <p className={styles.subtitle}>Scene #{scene.scene_order + 1} • {scene.id.split('-')[0]}</p>
          </div>
          <div className={styles.statusIndicator}>
            <div className={`${styles.statusDot} ${isConnected ? styles.dotConnected : styles.dotDisconnected}`} />
            <span className={styles.statusText}>
              {isConnected ? 'Live Connected' : 'Disconnected'}
            </span>
          </div>
        </header>

        <section className={styles.visualizerSection}>
          <PipelineVisualizer stages={stages} />
        </section>

        <div className={styles.editorGrid}>
          {/* Main Content Area */}
          <div className={styles.contentColumn}>
            
            {/* 1. Storyboard Section */}
            <div className="glass-card" style={{ padding: '32px' }}>
              <div className={styles.cardHeader}>
                <div className={styles.cardTitleWrapper}>
                  <Layout size={20} color="var(--accent-primary)" />
                  <h3 className={styles.cardTitle}>Storyboard & Script</h3>
                </div>
                
                <div style={{ display: 'flex', gap: '12px' }}>
                  {scene.storyboard_status === 'missing' && (
                    <button 
                      onClick={() => handleAction('storyboard', () => generateStoryboard(scene.id))}
                      className="btn-primary"
                    >
                      <Wand2 size={18} />
                      Generate Storyboard
                    </button>
                  )}
                  {scene.storyboard_status === 'pending_review' && (
                    <button 
                      onClick={() => handleAction('approve-storyboard', () => approveStoryboard(scene.id))}
                      className="btn-primary"
                      style={{ background: 'var(--accent-success)' }}
                    >
                      <Check size={18} />
                      Approve Storyboard
                    </button>
                  )}
                </div>
              </div>
              <div className={styles.contentBox}>
                {scene.storyboard_text ? (
                  <p style={{ color: '#cbd5e1', lineHeight: '1.8', whiteSpace: 'pre-wrap' }}>{scene.storyboard_text}</p>
                ) : (
                  <p style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>No storyboard content generated yet.</p>
                )}
              </div>
            </div>

            {/* 2. Planner Section (Visible if storyboard approved) */}
            {scene.storyboard_status === 'approved' && (
              <div className="glass-card" style={{ padding: '32px' }}>
                <div className={styles.cardHeader}>
                  <div className={styles.cardTitleWrapper}>
                    <Play size={20} color="var(--accent-primary)" />
                    <h3 className={styles.cardTitle}>Execution Plan</h3>
                  </div>
                  <div style={{ display: 'flex', gap: '12px' }}>
                    {scene.plan_status === 'missing' && (
                      <button 
                        onClick={() => handleAction('plan', () => planBeats(scene.id))}
                        className="btn-primary"
                      >
                        <Wand2 size={18} />
                        Design Beats
                      </button>
                    )}
                    {scene.plan_status === 'pending_review' && (
                      <button 
                        onClick={() => handleAction('approve-plan', () => approvePlan(scene.id))}
                        className="btn-primary"
                        style={{ background: 'var(--accent-success)' }}
                      >
                        <Check size={18} />
                        Approve Plan
                      </button>
                    )}
                  </div>
                </div>
                {scene.planner_output ? (
                  <pre className={styles.pre}>
                    {JSON.stringify(scene.planner_output, null, 2)}
                  </pre>
                ) : (
                  <p style={{ color: 'var(--text-secondary)' }}>Waiting for Director approval...</p>
                )}
              </div>
            )}

            {/* 3. Audio Section (Visible if plan approved) */}
            {scene.plan_status === 'approved' && (
              <div className="glass-card" style={{ padding: '32px' }}>
                <div className={styles.cardHeader}>
                  <div className={styles.cardTitleWrapper}>
                    <Music size={20} color="var(--accent-primary)" />
                    <h3 className={styles.cardTitle}>Voice & Audio</h3>
                  </div>
                  <div style={{ display: 'flex', gap: '12px' }}>
                    {!scene.audio_url && (
                      <button 
                        onClick={() => handleAction('voice', async () => {
                          const res = await sceneService.generateVoice(scene.id);
                          return res;
                        })}
                        className="btn-primary"
                      >
                        <Music size={18} />
                        Synthesize Voice
                      </button>
                    )}
                    {scene.audio_url && scene.voice_script_status === 'pending_review' && (
                      <button 
                        onClick={() => handleAction('approve-voice', () => sceneService.approveVoiceScript(scene.id))}
                        className="btn-primary"
                        style={{ background: 'var(--accent-success)' }}
                      >
                        <Check size={18} />
                        Approve Voice
                      </button>
                    )}
                    {scene.voice_script_status === 'approved' && !scene.sync_segments && (
                      <button 
                        onClick={() => handleAction('sync', () => sceneService.syncTimeline(scene.id))}
                        className="btn-primary"
                      >
                        <Activity size={18} />
                        Sync Timeline
                      </button>
                    )}
                  </div>
                </div>
                {scene.audio_url && (
                  <audio controls src={scene.audio_url} style={{ width: '100%', marginTop: '12px' }} />
                )}
                {scene.sync_segments && (
                  <div style={{ marginTop: '20px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    ✅ Timeline synced with {Object.keys(scene.sync_segments).length} segments.
                  </div>
                )}
              </div>
            )}

            {/* 4. Builder Section (Visible if sync ok) */}
            {scene.sync_segments && (
              <div className={styles.contentColumn}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => { setActiveView('code'); setSelectedVersion(null); }}
                      className={`${styles.tabButton} ${activeView === 'code' ? styles.tabButtonActive : ''}`}
                      style={{ background: activeView === 'code' ? 'rgba(255,255,255,0.1)' : 'transparent', border: '1px solid var(--surface-border)' }}
                    >
                      <Code size={14} style={{ marginRight: '6px', display: 'inline' }} />
                      Compiled Code
                    </button>
                    <button
                      onClick={() => { setActiveView('dsl'); setSelectedVersion(null); }}
                      className={`${styles.tabButton} ${activeView === 'dsl' ? styles.tabButtonActive : ''}`}
                      style={{ background: activeView === 'dsl' ? 'rgba(255,255,255,0.1)' : 'transparent', border: '1px solid var(--surface-border)' }}
                    >
                      <Edit2 size={14} style={{ marginRight: '6px', display: 'inline' }} />
                      Scene DSL (Editable)
                    </button>
                  </div>
                  <div>
                    {scene.review_loop_status === 'idle' && activeView === 'code' && (
                      <button 
                        onClick={() => handleAction('builder', () => sceneService.runReviewLoop(scene.id, { mode: 'hitl' }))}
                        className="btn-primary"
                        style={{ padding: '10px 24px' }}
                      >
                        Start Builder Agent
                      </button>
                    )}
                  </div>
                </div>

                {activeView === 'code' && (
                  <>
                    {selectedVersion && (
                      <div className="glass-card" style={{ padding: '16px', background: 'rgba(59,130,246,0.1)', border: '1px solid #3b82f6', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <div>
                          <span style={{ fontWeight: 'bold', color: '#60a5fa' }}>Historical Preview: </span>
                          <span>v{selectedVersion.version} ({selectedVersion.entity_type})</span>
                          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginLeft: '12px' }}>Created by {selectedVersion.created_by}</span>
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <button
                            onClick={() => handleRollback(selectedVersion.entity_type, selectedVersion.version)}
                            className="btn-primary"
                            style={{ background: 'var(--accent-success)', padding: '6px 12px', fontSize: '0.85rem' }}
                          >
                            <RotateCcw size={14} style={{ marginRight: '4px' }} />
                            Restore This Version
                          </button>
                          <button
                            onClick={() => setSelectedVersion(null)}
                            className="btn-secondary"
                            style={{ padding: '6px 12px', fontSize: '0.85rem' }}
                          >
                            Close
                          </button>
                        </div>
                      </div>
                    )}
                    
                    {selectedVersion ? (
                      <CodePreview code={typeof selectedVersion.content === 'string' ? selectedVersion.content : JSON.stringify(selectedVersion.content, null, 2)} />
                    ) : (
                      scene.manim_code && <CodePreview code={scene.manim_code} />
                    )}
                  </>
                )}

                {activeView === 'dsl' && (
                  <div className="glass-card" style={{ padding: '32px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                      <h4 style={{ margin: 0 }}>Edit Python Class DSL</h4>
                      <button
                        onClick={handleSaveDsl}
                        disabled={isDslSaving}
                        className="btn-primary"
                        style={{ background: 'var(--accent-success)' }}
                      >
                        {isDslSaving ? <Loader2 size={16} className="spin" /> : <Save size={16} style={{ marginRight: '8px' }} />}
                        Save & Recompile
                      </button>
                    </div>
                    <textarea
                      value={dslCode}
                      onChange={(e) => setDslCode(e.target.value)}
                      className={styles.dslTextarea}
                      placeholder="Write your Python DSL Class here..."
                    />
                    {dslError && (
                      <div className={styles.errorMessage}>
                        <AlertTriangle size={18} style={{ flexShrink: 0 }} />
                        <div>
                          <strong>Compilation Error:</strong>
                          <pre style={{ whiteSpace: 'pre-wrap', marginTop: '6px', fontSize: '0.8rem', fontFamily: 'monospace' }}>{dslError}</pre>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Sidebar Area (Events & Logs + Versions) */}
          <div className={styles.sidebarColumn}>
            <div className={`glass ${styles.activityFeed}`} style={{ height: '600px' }}>
              <div className={styles.tabsContainer}>
                <button
                  onClick={() => setSidebarTab('activity')}
                  className={`${styles.tabButton} ${sidebarTab === 'activity' ? styles.tabButtonActive : ''}`}
                >
                  <Activity size={14} style={{ marginRight: '6px', display: 'inline' }} />
                  Activity Logs
                </button>
                <button
                  onClick={() => setSidebarTab('history')}
                  className={`${styles.tabButton} ${sidebarTab === 'history' ? styles.tabButtonActive : ''}`}
                >
                  <History size={14} style={{ marginRight: '6px', display: 'inline' }} />
                  Version History
                </button>
              </div>

              {sidebarTab === 'activity' && (
                <div className={styles.activityList}>
                  {events.length === 0 ? (
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Waiting for agent events...</p>
                  ) : (
                    events.map((ev, i) => (
                      <div key={i} className={styles.activityItem}>
                        <span className={styles.activityTime}>
                          {new Date(ev.ts).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                        <div>
                          <div className={styles.activityPhase}>{ev.phase}</div>
                          <div className={styles.activityMessage}>{ev.message}</div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {sidebarTab === 'history' && (
                <div className={styles.activityList}>
                  {versions.length === 0 ? (
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>No version history recorded yet.</p>
                  ) : (
                    versions.map((ver, i) => (
                      <div key={i} className={styles.versionItem}>
                        <div className={styles.versionDetails}>
                          <div className={styles.versionHeader}>
                            <span style={{ fontWeight: 'bold', fontSize: '0.9rem' }}>v{ver.version}</span>
                            <span className={`${styles.versionBadge} ${styles['badge_' + ver.entity_type]}`}>
                              {ver.entity_type}
                            </span>
                          </div>
                          <div className={styles.versionMeta}>
                            by {ver.created_by}
                          </div>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                            {new Date(ver.created_at).toLocaleString()}
                          </div>
                        </div>
                        <div className={styles.versionActions}>
                          <button
                            title="Preview Version"
                            onClick={() => {
                              setSelectedVersion(ver);
                              setActiveView('code');
                            }}
                            className={styles.actionButton}
                          >
                            <FileText size={16} />
                          </button>
                          <button
                            title="Rollback to this version"
                            onClick={() => handleRollback(ver.entity_type, ver.version)}
                            className={styles.actionButton}
                            style={{ color: 'var(--accent-primary)' }}
                          >
                            <RotateCcw size={16} />
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

            {/* HITL Control Panel */}
            {scene.review_loop_status === 'hitl_pending' && (
              <div className={`glass ${styles.hitlPanel}`}>
                <div className={styles.hitlHeader}>
                  <AlertTriangle size={20} />
                  <span>Human-In-The-Loop</span>
                </div>
                <p style={{ fontSize: '0.9rem', marginBottom: '16px', color: 'var(--text-secondary)' }}>
                  AI is struggling to pass visual review. It needs your guidance or more rounds.
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <button 
                    onClick={() => handleAction('hitl-continue', () => sceneService.hitlAck(scene.id, { action: 'continue', extra_rounds: 3 }))}
                    className="btn-primary" 
                    style={{ background: 'var(--accent-primary)', width: '100%' }}
                  >
                    Give 3 more rounds
                  </button>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button 
                      onClick={() => handleAction('hitl-revert', () => sceneService.hitlAck(scene.id, { action: 'revert' }))}
                      className="btn-primary" 
                      style={{ background: 'transparent', border: '1px solid var(--surface-border)', flex: 1 }}
                    >
                      Revert
                    </button>
                    <button 
                      onClick={() => handleAction('hitl-stop', () => sceneService.hitlAck(scene.id, { action: 'stop' }))}
                      className="btn-primary" 
                      style={{ background: '#ef4444', flex: 1 }}
                    >
                      Stop
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default SceneEditor;

