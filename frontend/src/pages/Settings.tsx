import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Card } from '../components/ui/Card';
import { api, applyTheme } from '../lib/api';
import type { AgentLlmConfig, GenerationAgent, ReasoningEffort, ReviewTierConfig, UserSettings } from '../lib/api';
import './Settings.css';

const GENERATION_AGENTS: Array<{ id: GenerationAgent; label: string; description: string }> = [
  { id: 'idea_sketcher', label: 'Idea sketch', description: 'Creates a concise factual blueprint before the Master directs scenes.' },
  { id: 'storyboarder', label: 'Storyboard', description: 'Plans scenes, narration, and continuity.' },
  { id: 'builder', label: 'Builder', description: 'Writes the final Manim scene source.' },
  { id: 'code_reviewer', label: 'Code review', description: 'Diagnoses and repairs render errors.' },
  { id: 'visual_reviewer', label: 'Visual review', description: 'Checks rendered frames and repairs visual defects.' },
];
const AVAILABLE_MODELS: ReviewTierConfig['model'][] = [
  'gemini-3.5-flash-lite',
  'gemini-3-flash-preview',
  'gemini-3.5-flash',
  'gemini-3.6-flash',
  'gemma-4-31b-it',
];
const DEFAULT_REVIEW_TIERS: ReviewTierConfig[] = [
  { model: 'gemini-3.5-flash-lite', max_attempts: 1, reasoning_effort: 'high' },
  { model: 'gemini-3.5-flash', max_attempts: 1, reasoning_effort: 'high' },
  { model: 'gemini-3.6-flash', max_attempts: 3, reasoning_effort: 'high' },
];
const DEFAULT_AGENT_MODELS: Record<GenerationAgent, ReviewTierConfig['model']> = {
  idea_sketcher: 'gemini-3-flash-preview',
  storyboarder: 'gemini-3.5-flash',
  builder: 'gemini-3.6-flash',
  code_reviewer: 'gemini-3.5-flash-lite',
  visual_reviewer: 'gemma-4-31b-it',
};
const GEMINI_REASONING_OPTIONS: Array<{ value: ReasoningEffort; label: string }> = [
  { value: 'minimal', label: 'Minimal' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
];
const reasoningOptionsForModel = (model: ReviewTierConfig['model']) => (
  model.startsWith('gemma')
    ? [{ value: 'none' as const, label: 'Not supported' }]
    : GEMINI_REASONING_OPTIONS
);

export const Settings: React.FC = () => {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'error'>('saved');
  const [activeGenerationAgent, setActiveGenerationAgent] = useState<GenerationAgent>('storyboarder');
  const pendingSave = useRef<Partial<UserSettings>>({});
  const saveInFlight = useRef<Promise<void> | null>(null);
  const saveVersion = useRef(0);
  const mounted = useRef(true);

  const flushPendingSave = useCallback((): Promise<void> => {
    if (saveInFlight.current) return saveInFlight.current;

    const operation = (async () => {
      while (Object.keys(pendingSave.current).length > 0) {
        const attemptVersion = saveVersion.current;
        const patch = pendingSave.current;
        pendingSave.current = {};
        try {
          await api.updateSettings(patch);
        } catch (error) {
          pendingSave.current = { ...patch, ...pendingSave.current };
          console.error(error);
          if (mounted.current) setSaveState('error');
          // A setting changed while this request was failing: immediately try
          // the newly merged state once. Otherwise wait for the user's retry.
          if (saveVersion.current === attemptVersion) return;
        }
      }
      if (mounted.current) setSaveState('saved');
    })().finally(() => {
      saveInFlight.current = null;
    });
    saveInFlight.current = operation;
    return operation;
  }, []);

  const enqueueSave = useCallback((patch: Partial<UserSettings>) => {
    pendingSave.current = { ...pendingSave.current, ...patch };
    saveVersion.current += 1;
    if (mounted.current) setSaveState('saving');
    void flushPendingSave();
  }, [flushPendingSave]);

  useEffect(() => {
    mounted.current = true;
    void api.getSettings()
      .then(setSettings)
      .catch(console.error);

    const flushOnPageExit = () => {
      if (Object.keys(pendingSave.current).length > 0) void flushPendingSave();
    };
    window.addEventListener('pagehide', flushOnPageExit);
    return () => {
      window.removeEventListener('pagehide', flushOnPageExit);
      flushOnPageExit();
      mounted.current = false;
    };
  }, [flushPendingSave]);

  if (!settings) {
    return <div className="settings-page">Loading settings...</div>;
  }

  const updateSetting = <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => {
    const nextSettings = { ...settings, [key]: value } as UserSettings;
    setSettings(nextSettings);
    if (key === 'theme') applyTheme(value as UserSettings['theme']);
    enqueueSave({ [key]: value });
  };

  const updateAgentSetting = <K extends keyof AgentLlmConfig>(key: K, value: AgentLlmConfig[K]) => {
    const currentConfig = settings.llm_agent_configs?.[activeGenerationAgent] || {};
    updateSetting('llm_agent_configs', {
      ...(settings.llm_agent_configs || {}),
      [activeGenerationAgent]: { ...currentConfig, [key]: value },
    });
  };

  const activeAgent = GENERATION_AGENTS.find(agent => agent.id === activeGenerationAgent)!;
  const activeAgentConfig = settings.llm_agent_configs?.[activeGenerationAgent] || {};
  const isReviewer = activeGenerationAgent === 'code_reviewer' || activeGenerationAgent === 'visual_reviewer';
  const reviewTiers = activeAgentConfig.review_tiers || [];

  const updateReviewTiers = (tiers: ReviewTierConfig[]) => {
    updateAgentSetting('review_tiers', tiers);
  };

  const moveReviewTier = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= reviewTiers.length) return;
    const tiers = [...reviewTiers];
    [tiers[index], tiers[target]] = [tiers[target], tiers[index]];
    updateReviewTiers(tiers);
  };

  return (
    <div className="settings-page animate-fade-in">
      <header className="settings-header">
        <h1 className="editorial-heading settings-title">Studio Settings</h1>
        <p className="settings-subtitle">Only options that are saved and used by the rendering or generation pipeline are shown.</p>
        <p className={`settings-save-state settings-save-state-${saveState}`} role="status">
          {saveState === 'saving' && 'Saving changes…'}
          {saveState === 'saved' && 'Changes save automatically.'}
          {saveState === 'error' && 'Could not save changes. Adjust a setting to retry.'}
        </p>
      </header>

      <div className="settings-bento-grid">
        <Card padding="lg" className="settings-card bento-item">
          <h2>Workspace & Projects</h2>
          <p className="section-desc">Visual preference and defaults applied when creating a project.</p>
          <div className="settings-stack">
            <div className="settings-item">
              <div>
                <h3>Theme</h3>
                <p>Applied immediately and persisted automatically.</p>
              </div>
              <div className="segmented-control">
                {(['dark', 'light'] as const).map(theme => (
                  <button
                    type="button"
                    key={theme}
                    className={`segment ${settings.theme === theme ? 'active' : ''}`}
                    onClick={() => updateSetting('theme', theme)}
                  >
                    {theme === 'dark' ? 'Dark' : 'Light'}
                  </button>
                ))}
              </div>
            </div>

            <div className="divider" />

            <div className="settings-item">
              <div>
                <h3>Default project language</h3>
                <p>Language used for narration and on-screen text in new projects.</p>
              </div>
              <select
                className="select-field"
                value={settings.language}
                onChange={event => updateSetting('language', event.target.value as UserSettings['language'])}
              >
                <option value="vi">Vietnamese</option>
                <option value="en">English</option>
              </select>
            </div>
          </div>
        </Card>

        <Card padding="lg" className="settings-card bento-item">
          <h2>Video Rendering</h2>
          <p className="section-desc">Passed to the Manim render worker for every new render.</p>
          <div className="settings-stack">

            <div className="settings-item">
              <div>
                <h3>Resolution Quality</h3>
                <p>Output video dimensions and detail.</p>
              </div>
              <div className="segmented-control">
                {['480p', '720p', '1080p', '4k'].map(q => (
                  <button
                    type="button"
                    key={q}
                    className={`segment ${settings.video_quality === q ? 'active' : ''}`}
                    onClick={() => updateSetting('video_quality', q as UserSettings['video_quality'])}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>

            <div className="divider" />

            <div className="settings-item">
              <div>
                <h3>Frames Per Second (FPS)</h3>
                <p>Animation smoothness.</p>
              </div>
              <div className="segmented-control">
                {[15, 30, 60].map(fps => (
                  <button
                    type="button"
                    key={fps}
                    className={`segment ${settings.fps === fps ? 'active' : ''}`}
                    onClick={() => updateSetting('fps', fps as UserSettings['fps'])}
                  >
                    {fps}
                  </button>
                ))}
              </div>
            </div>

          </div>
        </Card>

        <Card padding="lg" className="settings-card bento-item">
          <h2>Generation Model</h2>
          <p className="section-desc">Select an agent to configure it independently. Backend default keeps the exact model profile declared for that agent.</p>
          <div className="generation-agent-tabs" role="tablist" aria-label="Generation agents">
            {GENERATION_AGENTS.map(agent => (
              <button
                type="button"
                role="tab"
                aria-selected={activeGenerationAgent === agent.id}
                className={`generation-agent-tab ${activeGenerationAgent === agent.id ? 'active' : ''}`}
                key={agent.id}
                onClick={() => setActiveGenerationAgent(agent.id)}
              >
                {agent.label}
              </button>
            ))}
          </div>
          <div className="generation-agent-heading">
            <h3>{activeAgent.label}</h3>
            <p>{activeAgent.description}</p>
          </div>
          <div className="settings-stack">
            {isReviewer ? (
              <>
                <div className="settings-item">
                  <div>
                    <h3>Use backend default chain</h3>
                    <p>Uses the ordered escalation chain declared by the worker.</p>
                  </div>
                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={activeAgentConfig.review_tiers == null}
                      onChange={event => updateAgentSetting(
                        'review_tiers',
                        event.target.checked ? null : DEFAULT_REVIEW_TIERS,
                      )}
                    />
                    <span className="slider"></span>
                  </label>
                </div>

                {activeAgentConfig.review_tiers != null && (
                  <div className="review-tier-list" aria-label="Custom escalation tiers">
                    <p className="review-tier-note">Models are tried from top to bottom. A tier receives its configured number of repair attempts before escalation; Max Review Attempts remains the global safety cap.</p>
                    {reviewTiers.map((tier, index) => (
                      <div className="review-tier-row" key={tier.model}>
                        <span className="review-tier-order">{index + 1}</span>
                        <select
                          className="select-field"
                          value={tier.model}
                          onChange={event => updateReviewTiers(reviewTiers.map((item, itemIndex) => (
                            itemIndex === index
                              ? {
                                ...item,
                                model: event.target.value as ReviewTierConfig['model'],
                                reasoning_effort: event.target.value.startsWith('gemma')
                                  ? 'none'
                                  : item.reasoning_effort && item.reasoning_effort !== 'none'
                                    ? item.reasoning_effort
                                    : 'low',
                              }
                              : item
                          )))}
                        >
                          {AVAILABLE_MODELS.map(model => (
                            <option
                              key={model}
                              value={model}
                              disabled={model !== tier.model && reviewTiers.some(item => item.model === model)}
                            >
                              {model}
                            </option>
                          ))}
                        </select>
                        <select
                          className="select-field review-tier-reasoning"
                          value={tier.reasoning_effort || 'none'}
                          onChange={event => updateReviewTiers(reviewTiers.map((item, itemIndex) => (
                            itemIndex === index
                              ? { ...item, reasoning_effort: event.target.value as ReasoningEffort }
                              : item
                          )))}
                          aria-label={`Reasoning for tier ${index + 1}`}
                        >
                          {reasoningOptionsForModel(tier.model).map(option => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                        <div className="review-tier-actions">
                          <button type="button" className="tier-action" disabled={index === 0} onClick={() => moveReviewTier(index, -1)}>↑</button>
                          <button type="button" className="tier-action" disabled={index === reviewTiers.length - 1} onClick={() => moveReviewTier(index, 1)}>↓</button>
                          <button type="button" className="tier-action" disabled={reviewTiers.length === 1} onClick={() => updateReviewTiers(reviewTiers.filter((_, itemIndex) => itemIndex !== index))}>×</button>
                        </div>
                      </div>
                    ))}
                    {reviewTiers.length < AVAILABLE_MODELS.length && (
                      <button
                        type="button"
                        className="add-tier-button"
                        onClick={() => {
                          const model = AVAILABLE_MODELS.find(candidate => !reviewTiers.some(tier => tier.model === candidate));
                          if (model) updateReviewTiers([
                            ...reviewTiers,
                            { model, max_attempts: 1, reasoning_effort: model.startsWith('gemma') ? 'none' : 'low' },
                          ]);
                        }}
                      >
                        Add tier
                      </button>
                    )}
                  </div>
                )}
              </>
            ) : (
              <>
                <div className="settings-item">
                  <div>
                    <h3>LLM</h3>
                    <p>Only models declared in the AI worker configuration are available.</p>
                  </div>
                  <select
                    className="select-field"
                    value={activeAgentConfig.model ?? ''}
                    onChange={event => {
                      const model = (event.target.value || null) as AgentLlmConfig['model'];
                      const currentConfig = settings.llm_agent_configs?.[activeGenerationAgent] || {};
                      updateSetting('llm_agent_configs', {
                        ...(settings.llm_agent_configs || {}),
                        [activeGenerationAgent]: {
                          ...currentConfig,
                          model,
                          ...(model?.startsWith('gemma') ? { reasoning_effort: 'none' as const } : {}),
                        },
                      });
                    }}
                  >
                    <option value="">Backend default</option>
                    <option value="gemini-3-flash-preview">Gemini 3 Flash Preview</option>
                    <option value="gemini-3.5-flash">Gemini 3.5 Flash</option>
                    <option value="gemma-4-31b-it">Gemma 4 31B IT</option>
                  </select>
                </div>
                <div className="divider" />
                <div className="settings-item">
                  <div>
                    <h3>Thinking / reasoning</h3>
                    <p>Gemini supports Minimal, Low, Medium, and High. Gemma does not expose this option.</p>
                  </div>
                  <select
                    className="select-field"
                    value={activeAgentConfig.reasoning_effort ?? ''}
                    onChange={event => updateAgentSetting(
                      'reasoning_effort',
                      (event.target.value || null) as AgentLlmConfig['reasoning_effort'],
                    )}
                  >
                    <option value="">Backend default</option>
                    {reasoningOptionsForModel(
                      activeAgentConfig.model || DEFAULT_AGENT_MODELS[activeGenerationAgent],
                    ).map(option => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>
                <div className="divider" />
              </>
            )}

            <div className="settings-item">
              <div>
                <h3>Temperature</h3>
                <p>Controls variation for this agent. Default uses its backend profile.</p>
              </div>
              <select
                className="select-field"
                value={activeAgentConfig.temperature ?? ''}
                onChange={event => updateAgentSetting('temperature', event.target.value === '' ? null : Number(event.target.value))}
              >
                <option value="">Backend default</option>
                <option value="0">0.0 — deterministic</option>
                <option value="0.1">0.1 — precise</option>
                <option value="0.3">0.3 — balanced</option>
                <option value="0.7">0.7 — exploratory</option>
                <option value="1">1.0 — varied</option>
              </select>
            </div>

            <div className="divider" />

            <div className="settings-item">
              <div>
                <h3>Maximum output tokens</h3>
                <p>Caps each response emitted by this agent.</p>
              </div>
              <select
                className="select-field"
                value={activeAgentConfig.max_tokens ?? ''}
                onChange={event => updateAgentSetting('max_tokens', event.target.value === '' ? null : Number(event.target.value))}
              >
                <option value="">Backend default</option>
                <option value="4096">4,096</option>
                <option value="8192">8,192</option>
                <option value="16384">16,384</option>
              </select>
            </div>
          </div>
        </Card>

        <Card padding="lg" className="settings-card bento-item">
          <h2>Voice-over (TTS)</h2>
          <p className="section-desc">When enabled, the render worker synthesizes each scene narration with Google Cloud Text-to-Speech and muxes it into the MP4.</p>
          <div className="settings-stack">
            <div className="settings-item">
              <div>
                <h3>Enable TTS</h3>
                <p>Requires a server Google API key with Cloud Text-to-Speech enabled.</p>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={settings.tts_enabled}
                  onChange={event => updateSetting('tts_enabled', event.target.checked)}
                />
                <span className="slider"></span>
              </label>
            </div>

            <div className="divider" />

            <div className={`settings-item ${!settings.tts_enabled ? 'settings-item-disabled' : ''}`}>
              <div>
                <h3>Voice</h3>
                <p>Auto selects the matching Standard voice for the project language.</p>
              </div>
              <select
                className="select-field"
                disabled={!settings.tts_enabled}
                value={settings.tts_voice}
                onChange={event => updateSetting('tts_voice', event.target.value as UserSettings['tts_voice'])}
              >
                <option value="auto">Auto by project language</option>
                <option value="vi-VN-Standard-A">Vietnamese — Standard A</option>
                <option value="vi-VN-Standard-B">Vietnamese — Standard B</option>
                <option value="en-US-Standard-C">English (US) — Standard C</option>
                <option value="en-US-Standard-D">English (US) — Standard D</option>
              </select>
            </div>

            <div className="divider" />

            <div className={`settings-item ${!settings.tts_enabled ? 'settings-item-disabled' : ''}`}>
              <div>
                <h3>Speaking rate</h3>
                <p>Applied directly to the speech synthesis request.</p>
              </div>
              <div className="segmented-control">
                {[0.75, 1, 1.25].map(rate => (
                  <button
                    type="button"
                    disabled={!settings.tts_enabled}
                    key={rate}
                    className={`segment ${settings.tts_speaking_rate === rate ? 'active' : ''}`}
                    onClick={() => updateSetting('tts_speaking_rate', rate)}
                  >
                    {rate}×
                  </button>
                ))}
              </div>
            </div>

            <div className="divider" />

            <div className={`settings-item ${!settings.tts_enabled ? 'settings-item-disabled' : ''}`}>
              <div>
                <h3>Pitch</h3>
                <p>Semitone adjustment for the selected voice.</p>
              </div>
              <div className="segmented-control">
                {[-2, 0, 2].map(pitch => (
                  <button
                    type="button"
                    disabled={!settings.tts_enabled}
                    key={pitch}
                    className={`segment ${settings.tts_pitch === pitch ? 'active' : ''}`}
                    onClick={() => updateSetting('tts_pitch', pitch)}
                  >
                    {pitch > 0 ? `+${pitch}` : pitch}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Card>

        <Card padding="lg" className="settings-card bento-item">
          <h2>AI Auto-Review</h2>
          <p className="section-desc">Controls executed by the Builder worker after it generates code.</p>
          <div className="settings-stack">

            <div className="settings-item">
              <div>
                <h3>Code Review Loop</h3>
                <p>Automatically fix syntax and compilation errors.</p>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={settings.code_review_enabled}
                  onChange={(e) => updateSetting('code_review_enabled', e.target.checked)}
                />
                <span className="slider"></span>
              </label>
            </div>

            <div className="divider" />

            <div className="settings-item">
              <div>
                <h3>Visual Review Loop</h3>
                <p>Analyze rendered video frames for aesthetics.</p>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={settings.visual_review_enabled}
                  onChange={(e) => updateSetting('visual_review_enabled', e.target.checked)}
                />
                <span className="slider"></span>
              </label>
            </div>

            <div className="divider" />

            <div className="settings-item">
              <div>
                <h3>Max Review Attempts</h3>
                <p>Maximum retries before falling back to HITL.</p>
              </div>
              <div className="segmented-control">
                {[1, 2, 3, 4, 5].map(num => (
                  <button
                    key={num}
                    className={`segment ${settings.max_review_attempts === num ? 'active' : ''}`}
                    onClick={() => updateSetting('max_review_attempts', num)}
                  >
                    {num}
                  </button>
                ))}
              </div>
            </div>

          </div>
        </Card>

        <Card padding="lg" className="settings-card bento-item">
          <h2>Storyboard Direction</h2>
          <p className="section-desc">Passed as explicit instructions to the storyboarder and Builder.</p>
          <div className="settings-stack">
            <div className="settings-item">
              <div>
                <h3>AI Persona</h3>
                <p>Sets the tone and level of explanation.</p>
              </div>
              <select
                className="select-field"
                value={settings.ai_agent_persona}
                onChange={event => updateSetting(
                  'ai_agent_persona',
                  event.target.value as UserSettings['ai_agent_persona'],
                )}
              >
                <option value="Professional Educator">Professional Educator</option>
                <option value="Creative Storyteller">Creative Storyteller</option>
                <option value="Technical Explainer">Technical Explainer</option>
              </select>
            </div>

            <div className="divider" />

            <div className="settings-item">
              <div>
                <h3>Storyboard template</h3>
                <p>Defines the instructional structure and pacing.</p>
              </div>
              <select
                className="select-field"
                value={settings.template_selection}
                onChange={event => updateSetting(
                  'template_selection',
                  event.target.value as UserSettings['template_selection'],
                )}
              >
                <option value="Educational">Educational</option>
                <option value="Conceptual walkthrough">Conceptual walkthrough</option>
                <option value="Worked example">Worked example</option>
              </select>
            </div>

            <div className="divider" />

            <div className="settings-item">
              <div>
                <h3>Human-in-the-Loop (HITL)</h3>
                <p>Require manual approval before applying each generated draft.</p>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={settings.hitl_enabled}
                  onChange={(e) => updateSetting('hitl_enabled', e.target.checked)}
                />
                <span className="slider"></span>
              </label>
            </div>

          </div>
        </Card>
      </div>
    </div>
  );
};
