import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import PipelineVisualizer from '../components/PipelineVisualizer';
import type { Stage } from '../components/PipelineVisualizer';
import CodePreview from '../components/CodePreview';
import { ArrowLeft, Check, AlertTriangle, Activity, Loader2, Play, Music, Layout, Wand2 } from 'lucide-react';
import { sceneService, jobService } from '../services/api';
import { useSceneWebSocket } from '../hooks/useSceneWebSocket';
import { useJobPolling } from '../hooks/useJobPolling';
import type { Scene, VoiceJob } from '../types/api';

const SceneEditor = () => {
  const { sceneId } = useParams<{ sceneId: string }>();
  const navigate = useNavigate();
  const [scene, setScene] = useState<Scene | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const { events, isConnected, lastEvent } = useSceneWebSocket(sceneId);

  const fetchScene = useCallback(async () => {
    if (!sceneId) return;
    try {
      const res = await sceneService.getById(sceneId);
      setScene(res.data);
    } catch (err) {
      console.error('Failed to fetch scene', err);
    } finally {
      setLoading(false);
    }
  }, [sceneId]);

  useEffect(() => {
    fetchScene();
  }, [fetchScene]);

  // Sync scene state if WS event indicates completion
  useEffect(() => {
    if (lastEvent?.phase?.endsWith('_ok') || lastEvent?.phase === 'completed' || lastEvent?.phase === 'job_completed') {
      fetchScene();
    }
  }, [lastEvent, fetchScene]);

  // Voice Job Polling
  const { startPolling: _pollVoice } = useJobPolling<VoiceJob>({
    fetchFn: () => jobService.getVoiceJob(scene?.id || ''), // This will be set when action starts
    isCompleted: (job) => job.status === 'completed',
    isFailed: (job) => job.status === 'failed',
    onSuccess: () => fetchScene(),
  });

  const handleAction = async (name: string, fn: () => Promise<any>) => {
    setActionLoading(name);
    try {
      await fn();
      await fetchScene();
    } catch (err) {
      console.error(`Action ${name} failed`, err);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading || !scene) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', color: 'white' }}>
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
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      
      <main style={{ marginLeft: '300px', padding: '40px 60px', width: '100%' }}>
        <header style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '32px' }}>
          <div className="glass" style={{ padding: '10px', borderRadius: '12px', cursor: 'pointer' }} onClick={() => navigate(-1)}>
            <ArrowLeft size={20} />
          </div>
          <div>
            <h1 style={{ fontSize: '1.8rem' }}>Scene Editor</h1>
            <p style={{ color: 'var(--text-secondary)' }}>Scene #{scene.scene_order + 1} • {scene.id.split('-')[0]}</p>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: '12px', alignItems: 'center' }}>
            <div style={{ 
              width: '8px', height: '8px', borderRadius: '50%', 
              background: isConnected ? 'var(--accent-success)' : '#ef4444' 
            }} />
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              {isConnected ? 'Live Connected' : 'Disconnected'}
            </span>
          </div>
        </header>

        <section style={{ marginBottom: '40px' }}>
          <PipelineVisualizer stages={stages} />
        </section>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 400px', gap: '32px' }}>
          {/* Main Content Area */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
            
            {/* 1. Storyboard Section */}
            <div className="glass-card" style={{ padding: '32px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <Layout size={20} color="var(--accent-primary)" />
                  <h3 style={{ fontSize: '1.25rem' }}>Storyboard & Script</h3>
                </div>
                
                <div style={{ display: 'flex', gap: '12px' }}>
                  {scene.storyboard_status === 'missing' && (
                    <button 
                      onClick={() => handleAction('storyboard', () => sceneService.generateStoryboard(scene.id))}
                      className="btn-primary"
                      disabled={!!actionLoading}
                    >
                      {actionLoading === 'storyboard' ? <Loader2 size={18} className="spin" /> : <Wand2 size={18} />}
                      Generate Storyboard
                    </button>
                  )}
                  {scene.storyboard_status === 'pending_review' && (
                    <button 
                      onClick={() => handleAction('approve-storyboard', () => sceneService.approveStoryboard(scene.id))}
                      className="btn-primary"
                      style={{ background: 'var(--accent-success)' }}
                    >
                      <Check size={18} />
                      Approve Storyboard
                    </button>
                  )}
                </div>
              </div>
              <div style={{ background: 'rgba(0,0,0,0.2)', padding: '20px', borderRadius: '12px', border: '1px solid var(--surface-border)' }}>
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
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <Play size={20} color="var(--accent-primary)" />
                    <h3 style={{ fontSize: '1.25rem' }}>Execution Plan</h3>
                  </div>
                  <div style={{ display: 'flex', gap: '12px' }}>
                    {scene.plan_status === 'missing' && (
                      <button 
                        onClick={() => handleAction('plan', () => sceneService.plan(scene.id))}
                        className="btn-primary"
                      >
                        {actionLoading === 'plan' ? <Loader2 size={18} className="spin" /> : <Wand2 size={18} />}
                        Design Beats
                      </button>
                    )}
                    {scene.plan_status === 'pending_review' && (
                      <button 
                        onClick={() => handleAction('approve-plan', () => sceneService.approvePlan(scene.id))}
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
                  <pre style={{ fontSize: '0.9rem', color: '#94a3b8', background: '#0f172a', padding: '16px', borderRadius: '8px', overflow: 'auto' }}>
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
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <Music size={20} color="var(--accent-primary)" />
                    <h3 style={{ fontSize: '1.25rem' }}>Voice & Audio</h3>
                  </div>
                  <div style={{ display: 'flex', gap: '12px' }}>
                    {!scene.audio_url && (
                      <button 
                        onClick={() => handleAction('voice', async () => {
                          const res = await sceneService.generateVoice(scene.id);
                          // Polling logic would go here, or we wait for WS
                          return res;
                        })}
                        className="btn-primary"
                      >
                        {actionLoading === 'voice' ? <Loader2 size={18} className="spin" /> : <Music size={18} />}
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
                        {actionLoading === 'sync' ? <Loader2 size={18} className="spin" /> : <Activity size={18} />}
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
              <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                   {scene.review_loop_status === 'idle' && (
                      <button 
                        onClick={() => handleAction('builder', () => sceneService.runReviewLoop(scene.id, { mode: 'hitl' }))}
                        className="btn-primary"
                        style={{ padding: '12px 32px', fontSize: '1rem' }}
                      >
                        {actionLoading === 'builder' ? <Loader2 size={18} className="spin" /> : <Loader2 size={18} />}
                        Start Builder Agent
                      </button>
                    )}
                </div>
                {scene.manim_code && <CodePreview code={scene.manim_code} />}
              </div>
            )}
          </div>

          {/* Sidebar Area (Events & Logs) */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div className="glass" style={{ padding: '24px', height: '500px', display: 'flex', flexDirection: 'column' }}>
              <h4 style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Activity size={18} color="var(--accent-primary)" />
                Agent Activity
              </h4>
              <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {events.length === 0 ? (
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Waiting for agent events...</p>
                ) : (
                  events.map((ev, i) => (
                    <div key={i} style={{ fontSize: '0.8rem', display: 'flex', gap: '10px', borderLeft: '2px solid var(--surface-border)', paddingLeft: '12px' }}>
                      <span style={{ color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                        {new Date(ev.ts).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                      <div>
                        <div style={{ fontWeight: 600, color: 'var(--accent-primary)', fontSize: '0.7rem', textTransform: 'uppercase' }}>{ev.phase}</div>
                        <div style={{ color: 'white' }}>{ev.message}</div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* HITL Control Panel */}
            {scene.review_loop_status === 'hitl_pending' && (
              <div className="glass" style={{ padding: '24px', border: '1px solid #ef4444', background: 'rgba(239, 68, 68, 0.05)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#ef4444', marginBottom: '12px' }}>
                  <AlertTriangle size={20} />
                  <span style={{ fontWeight: 600 }}>Human-In-The-Loop</span>
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
