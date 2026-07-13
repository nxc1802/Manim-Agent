import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Play, Check, X, ArrowUUpLeft, CodeBlock } from '@phosphor-icons/react';
import { Dialog } from '../components/ui/Dialog';
import type { DialogProps } from '../components/ui/Dialog';
import { api } from '../lib/api';
import type { Project } from '../lib/api';
import './SceneEditor.css';

const steps = [
  { name: 'Director', label: 'Brief Outline' },
  { name: 'Planner', label: 'Scene Outline' },
  { name: 'Scene Designer', label: 'Visual Design' },
  { name: 'Manim Builder', label: 'Python Code' },
  { name: 'Code Reviewer', label: 'Self-Correction' },
  { name: 'Visual Reviewer', label: 'Visual Review' }
];

const kindToIndex: Record<string, number> = {
  director: 0,
  planner: 1,
  scene_designer: 2,
  builder: 3,
  code_reviewer: 4,
  visual_reviewer: 5
};

const getStepText = (step: any): string => {
  if (!step) return '';
  const output = step.draft_output || step.final_output;
  if (!output) return '';
  if (typeof output === 'string') return output;
  if (output.storyboard) return output.storyboard;
  if (output.manim_code) return output.manim_code;
  if (output.text) return output.text;
  if (output.passed !== undefined) {
    return `Passed: ${output.passed}\n\nCode:\n${output.manim_code || ''}\n\nAttempts: ${output.total_attempts}\n${output.final_error ? `Error: ${output.final_error}` : ''}`;
  }
  return JSON.stringify(output, null, 2);
};

export const SceneEditor: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  
  // Pipeline State
  const [activeRun, setActiveRun] = useState<any>(null);
  const [currentStep, setCurrentStep] = useState(0); // 0-5
  const [selectedStepView, setSelectedStepView] = useState(0); // 0-5
  const [draftContent, setDraftContent] = useState<string[]>(Array(6).fill(''));
  const [revisions, setRevisions] = useState<number[]>(Array(6).fill(1));
  const [stepIds, setStepIds] = useState<string[]>(Array(6).fill(''));

  const [isGenerating, setIsGenerating] = useState(false);
  const [isRendering, setIsRendering] = useState(false);
  const [videoRendered, setVideoRendered] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  // Dialog State
  const [dialog, setDialog] = useState<Omit<DialogProps, 'onConfirm' | 'onCancel'> & {
    isOpen: boolean;
    onConfirm?: (val?: string) => void;
  }>({ isOpen: false, title: '', message: '' });

  const loadPipeline = async (pId: string) => {
    try {
      const proj = await api.getProject(pId);
      setProject(proj);

      // 1. Fetch scenes
      let scenes = await api.getScenes(pId);
      if (scenes.length === 0) {
        // Create default scene
        const newScene = await api.createScene(pId, 0);
        scenes = [newScene];
      }

      const activeScene = scenes[0];

      // 2. Fetch AI Runs
      let runs = await api.getAiRuns(pId);
      let run: any = null;
      
      if (runs.length === 0) {
        // Start first AI Run
        const startRes = await api.startAiRun(pId, activeScene.id, proj.description);
        run = startRes.run;
      } else {
        run = runs[runs.length - 1]; // Get latest run
      }

      setActiveRun(run);

      // 3. Fetch steps
      const stepsList = await api.getAiRunSteps(pId, run.id);
      
      const newDrafts = Array(6).fill('');
      const newRevs = Array(6).fill(1);
      const newIds = Array(6).fill('');
      let maxActiveIdx = 0;

      stepsList.forEach((s: any) => {
        const idx = kindToIndex[s.kind];
        if (idx !== undefined) {
          newDrafts[idx] = getStepText(s);
          newRevs[idx] = s.revision;
          newIds[idx] = s.id;
          
          if (s.status === 'generating') {
            setIsGenerating(true);
            maxActiveIdx = Math.max(maxActiveIdx, idx);
          } else if (s.status === 'pending_review') {
            maxActiveIdx = Math.max(maxActiveIdx, idx);
          } else if (s.status === 'approved') {
            maxActiveIdx = Math.max(maxActiveIdx, idx + 1);
          }
        }
      });

      // Clamp maxActiveIdx to 0-5
      const activeIdx = Math.min(Math.max(maxActiveIdx, 0), 5);
      
      setDraftContent(newDrafts);
      setRevisions(newRevs);
      setStepIds(newIds);
      setCurrentStep(activeIdx);
      setSelectedStepView(activeIdx);

    } catch (e) {
      console.error('Failed to load pipeline:', e);
    }
  };

  useEffect(() => {
    if (!projectId) return;

    loadPipeline(projectId);

    // Setup WebSocket
    const wsUrl = (import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000/v1').replace('http', 'ws');
    const ws = new WebSocket(`${wsUrl}/ws/projects/${projectId}`);
    
    ws.onopen = () => console.log('WS Connected');
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleWsEvent(payload);
      } catch (e) {
        console.error('WS Parse Error:', e);
      }
    };
    ws.onclose = () => console.log('WS Disconnected');
    wsRef.current = ws;

    return () => {
      wsRef.current?.close();
    };
  }, [projectId]);

  const handleWsEvent = (payload: any) => {
    const { type, data } = payload;
    if (!data || !data.step) return;

    const step = data.step;
    const stepIdx = kindToIndex[step.kind];
    if (stepIdx === undefined) return;

    // Update step ID and revision locally
    setStepIds(prev => {
      const copy = [...prev];
      copy[stepIdx] = step.id;
      return copy;
    });
    setRevisions(prev => {
      const copy = [...prev];
      copy[stepIdx] = step.revision;
      return copy;
    });

    switch (type) {
      case 'hitl.step.started':
        setCurrentStep(stepIdx);
        setSelectedStepView(stepIdx);
        setIsGenerating(true);
        setDraftContent(prev => {
          const copy = [...prev];
          copy[stepIdx] = '';
          return copy;
        });
        break;

      case 'hitl.step.generating':
        setIsGenerating(true);
        // Only append delta if available
        if (payload.content_delta) {
          setDraftContent(prev => {
            const copy = [...prev];
            copy[stepIdx] = (copy[stepIdx] || '') + payload.content_delta;
            return copy;
          });
        }
        break;

      case 'hitl.step.pending_review':
        setIsGenerating(false);
        setCurrentStep(stepIdx);
        setSelectedStepView(stepIdx);
        if (step.draft_output) {
          setDraftContent(prev => {
            const copy = [...prev];
            copy[stepIdx] = getStepText(step);
            return copy;
          });
        }
        break;

      case 'hitl.step.completed':
      case 'hitl.step.approved':
        setIsGenerating(false);
        if (step.final_output) {
          setDraftContent(prev => {
            const copy = [...prev];
            copy[stepIdx] = getStepText(step);
            return copy;
          });
        }
        // Advance currentStep
        if (stepIdx < 5) {
          setCurrentStep(stepIdx + 1);
          setSelectedStepView(stepIdx + 1);
        }
        break;

      case 'hitl.step.rejected':
        setIsGenerating(false);
        // Step went back to previous or queued
        break;

      case 'hitl.run.rolled_back':
        setIsGenerating(false);
        // Reload whole pipeline on rollback to get accurate state
        if (projectId) {
          loadPipeline(projectId);
        }
        break;
    }
  };

  const closeDialog = () => setDialog(prev => ({ ...prev, isOpen: false }));

  const handleApprove = async () => {
    if (!projectId || !activeRun) return;
    const stepId = stepIds[currentStep];
    const revision = revisions[currentStep];

    if (!stepId) return;

    try {
      // If user modified raw text, call editStep first
      if (showRaw) {
        let editPayload: any = {};
        if (currentStep === 0) editPayload = { storyboard: draftContent[currentStep] };
        else if (currentStep === 3) editPayload = { manim_code: draftContent[currentStep] };
        else editPayload = { text: draftContent[currentStep] };

        await api.editStep(projectId, activeRun.id, stepId, revision, editPayload);
      }

      await api.approveStep(projectId, activeRun.id, stepId, revision);
      
      // Dialog for end of pipeline
      if (currentStep === steps.length - 1) {
        setDialog({
          isOpen: true,
          title: 'Success',
          message: 'Pipeline completed successfully!',
          onConfirm: closeDialog
        });
      }
    } catch (e: any) {
      console.error(e);
      setDialog({
        isOpen: true,
        title: 'Error',
        message: e.message || 'Failed to approve step.',
        onConfirm: closeDialog
      });
    }
  };

  const handleReject = () => {
    if (!projectId || !activeRun) return;
    const stepId = stepIds[currentStep];
    const revision = revisions[currentStep];

    if (!stepId) return;

    setDialog({
      isOpen: true,
      title: 'Reject Draft',
      message: 'Provide feedback for the AI Agent to regenerate this stage.',
      inputPlaceholder: 'Feedback...',
      onConfirm: async (feedback) => {
        if (!feedback) return;
        try {
          await api.rejectStep(projectId, activeRun.id, stepId, revision, feedback);
          closeDialog();
        } catch (e: any) {
          console.error(e);
          setDialog({
            isOpen: true,
            title: 'Error',
            message: e.message || 'Failed to reject step.',
            onConfirm: closeDialog
          });
        }
      }
    });
  };

  const handleRollbackClick = () => {
    if (!projectId || !activeRun) return;
    const targetStepId = stepIds[selectedStepView];

    if (!targetStepId) return;

    setDialog({
      isOpen: true,
      title: 'Confirm Rollback',
      message: `Are you sure you want to rollback to the ${steps[selectedStepView].name} stage? This will reset all steps after it.`,
      onConfirm: async () => {
        try {
          await api.rollbackRun(projectId, activeRun.id, targetStepId);
          closeDialog();
        } catch (e: any) {
          console.error(e);
          setDialog({
            isOpen: true,
            title: 'Error',
            message: e.message || 'Failed to rollback.',
            onConfirm: closeDialog
          });
        }
      }
    });
  };

  const handleRender = () => {
    setIsRendering(true);
    setTimeout(() => {
      setIsRendering(false);
      setVideoRendered(true);
    }, 3000); // Simulate rendering
  };

  const activeDraftText = draftContent[selectedStepView] || '';
  const isAutoStep = selectedStepView >= 3;
  const isViewingCurrentStep = selectedStepView === currentStep;

  return (
    <div className="editor-page animate-fade-in">
      
      {/* Header */}
      <header className="editor-header">
        <div>
          <h1 className="editorial-heading editor-title">{project?.title || 'Loading...'}</h1>
          <p className="editor-subtitle">{project?.description || 'Visualizing...'}</p>
        </div>
        <div className="editor-actions">
          <Button variant="secondary" onClick={() => setShowRaw(!showRaw)}>
            <CodeBlock size={18} />
            <span style={{ marginLeft: 8 }}>{showRaw ? 'Hide Raw' : 'Edit Raw'}</span>
          </Button>
          <Button variant="primary" onClick={handleRender} disabled={isRendering}>
            <Play size={18} weight="fill" />
            <span style={{ marginLeft: 8 }}>{isRendering ? 'Rendering...' : 'Render Full Video'}</span>
          </Button>
        </div>
      </header>

      {/* Stepper UI */}
      <div className="stepper">
        {steps.map((step, idx) => {
          let statusClass = 'step-pending';
          if (idx < currentStep) statusClass = 'step-completed';
          else if (idx === currentStep) statusClass = 'step-active';

          const isViewed = idx === selectedStepView;

          return (
            <div 
              key={step.name} 
              className={`step-item ${statusClass} ${isViewed ? 'step-viewed' : ''}`}
              onClick={() => setSelectedStepView(idx)}
              style={{ cursor: 'pointer' }}
            >
              <div className="step-circle">
                {idx < currentStep ? <Check size={12} weight="bold" /> : idx + 1}
              </div>
              <span className="step-label">{step.name}</span>
              {idx < steps.length - 1 && <div className="step-line" />}
            </div>
          );
        })}
      </div>

      {/* Main Content Area */}
      <div className="editor-content">
        
        {/* Left Col: Output & Interaction */}
        <div className="editor-main-col stagger-1 animate-fade-in">
          <Card padding="lg" className="output-card">
            <div className="output-header">
              <Badge color={isViewingCurrentStep && isGenerating ? 'blue' : (selectedStepView < currentStep ? 'green' : 'gray')}>
                {isViewingCurrentStep && isGenerating 
                  ? 'Generating...' 
                  : (selectedStepView < currentStep ? 'Approved' : 'Pending Review')}
              </Badge>
              {!isViewingCurrentStep && (
                <Button variant="ghost" size="sm" onClick={handleRollbackClick}>
                  <ArrowUUpLeft size={16} /> Rollback to this stage
                </Button>
              )}
            </div>
            
            {showRaw && isViewingCurrentStep ? (
              <textarea 
                className="raw-editor" 
                value={activeDraftText} 
                onChange={(e) => {
                  setDraftContent(prev => {
                    const copy = [...prev];
                    copy[selectedStepView] = e.target.value;
                    return copy;
                  });
                }}
              />
            ) : (
              <div className="elegant-renderer">
                <div style={{ whiteSpace: 'pre-wrap', fontFamily: selectedStepView === 3 ? 'var(--font-mono)' : 'inherit' }}>
                  {activeDraftText || (isViewingCurrentStep && isGenerating ? '' : 'Waiting for AI...')}
                  {isViewingCurrentStep && isGenerating && <span className="blinking-cursor">█</span>}
                </div>
              </div>
            )}

            {isViewingCurrentStep && !isAutoStep && (
              <div className="action-bar">
                <Button 
                  variant="ghost" 
                  className="reject-btn" 
                  onClick={handleReject} 
                  disabled={currentStep === 0 || isGenerating || !activeDraftText}
                >
                  <X size={18} weight="bold" /> Reject
                </Button>
                <Button 
                  variant="primary" 
                  className="approve-btn" 
                  onClick={handleApprove} 
                  disabled={isGenerating || !activeDraftText}
                >
                  <Check size={18} weight="bold" /> Approve
                </Button>
              </div>
            )}
          </Card>
        </div>

        {/* Right Col: Video Preview */}
        <div className="editor-side-col stagger-2 animate-fade-in">
          <Card padding="none" className="preview-card">
            {isRendering ? (
              <div className="preview-placeholder">
                <div className="spinner" />
                <span>Generating Manim Animation...</span>
              </div>
            ) : videoRendered ? (
              <video 
                src="https://media.w3.org/2010/05/sintel/trailer_hd.mp4" 
                controls 
                style={{ width: '100%', height: '100%', objectFit: 'contain' }}
              />
            ) : (
              <div className="preview-placeholder" onClick={handleRender}>
                <Play size={48} weight="thin" style={{ cursor: 'pointer' }} />
                <span>Click "Render Full Video" to preview</span>
              </div>
            )}
          </Card>
        </div>
      </div>

      <Dialog 
        {...dialog} 
        onConfirm={dialog.onConfirm || closeDialog} 
        onCancel={closeDialog} 
      />
    </div>
  );
};
