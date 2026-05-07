import { useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import PipelineVisualizer from '../components/PipelineVisualizer';
import type { Stage } from '../components/PipelineVisualizer';
import CodePreview from '../components/CodePreview';
import { ArrowLeft, Check, AlertTriangle, Activity, Loader2, Play, Music, Layout, Wand2 } from 'lucide-react';
import { sceneService } from '../services/api';
import { useSceneWebSocket } from '../hooks/useSceneWebSocket';
import { useSceneStore } from '../store/useSceneStore';
import styles from './SceneEditor.module.css';

const SceneEditor = () => {
  const { sceneId } = useParams<{ sceneId: string }>();
  const navigate = useNavigate();
  const { currentScene: scene, loading, fetchScene, updateSceneState, generateStoryboard, approveStoryboard, planBeats, approvePlan } = useSceneStore();

  const { events, isConnected, lastEvent } = useSceneWebSocket(sceneId);

  useEffect(() => {
    if (sceneId) {
      fetchScene(sceneId);
    }
  }, [sceneId, fetchScene]);

  // Sync scene state if WS event indicates completion
  useEffect(() => {
    if (lastEvent?.phase?.endsWith('_ok') || lastEvent?.phase === 'completed' || lastEvent?.phase === 'job_completed') {
      if (sceneId) fetchScene(sceneId);
    }
  }, [lastEvent, sceneId, fetchScene]);

  const handleAction = async (name: string, fn: () => Promise<any>) => {
    try {
      await fn();
      if (sceneId) fetchScene(sceneId);
    } catch (err) {
      console.error(`Action ${name} failed`, err);
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
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                   {scene.review_loop_status === 'idle' && (
                      <button 
                        onClick={() => handleAction('builder', () => sceneService.runReviewLoop(scene.id, { mode: 'hitl' }))}
                        className="btn-primary"
                        style={{ padding: '12px 32px', fontSize: '1rem' }}
                      >
                        Start Builder Agent
                      </button>
                    )}
                </div>
                {scene.manim_code && <CodePreview code={scene.manim_code} />}
              </div>
            )}
          </div>

          {/* Sidebar Area (Events & Logs) */}
          <div className={styles.sidebarColumn}>
            <div className={`glass ${styles.activityFeed}`}>
              <h4 style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Activity size={18} color="var(--accent-primary)" />
                Agent Activity
              </h4>
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
