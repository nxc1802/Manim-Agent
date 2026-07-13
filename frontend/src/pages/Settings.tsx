import React, { useEffect, useState } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { api, applyTheme } from '../lib/api';
import type { UserSettings } from '../lib/api';
import './Settings.css';

export const Settings: React.FC = () => {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [toastMessage, setToastMessage] = useState('');

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const data = await api.getSettings();
      setSettings(data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSave = async () => {
    if (!settings) return;
    try {
      await api.updateSettings(settings);
      applyTheme(settings.theme);
      setToastMessage('Settings saved successfully.');
      setTimeout(() => setToastMessage(''), 3000);
    } catch (e) {
      console.error(e);
      setToastMessage('Failed to save settings.');
      setTimeout(() => setToastMessage(''), 3000);
    }
  };

  if (!settings) {
    return <div className="settings-page">Loading settings...</div>;
  }

  return (
    <div className="settings-page animate-fade-in">
      <header className="settings-header">
        <h1 className="editorial-heading settings-title">Settings</h1>
        <p className="settings-subtitle">Configure your studio defaults and preferences.</p>
      </header>

      {toastMessage && (
        <div style={{
          padding: '12px 16px',
          backgroundColor: 'var(--color-pastel-green-bg)',
          color: 'var(--color-pastel-green-text)',
          borderRadius: '4px',
          fontSize: '0.875rem',
          fontWeight: 500,
          border: '1px solid var(--color-border)'
        }}>
          {toastMessage}
        </div>
      )}

      <div className="settings-content">
        <section className="settings-section">
          <h2>Studio Defaults</h2>
          <Card padding="md" className="settings-card">
            <div className="settings-item">
              <div>
                <h3>Human-in-the-Loop (HITL)</h3>
                <p>Pause AI generation at key steps for human review.</p>
              </div>
              <label className="switch">
                <input 
                  type="checkbox" 
                  checked={settings.hitl_enabled} 
                  onChange={(e) => setSettings({ ...settings, hitl_enabled: e.target.checked })}
                />
                <span className="slider"></span>
              </label>
            </div>
            
            <div className="divider" />
            
            <div className="settings-item">
              <div>
                <h3>AI Persona</h3>
                <p>The character the AI adopts when responding and generating scripts.</p>
              </div>
              <select 
                className="select-field"
                value={settings.ai_agent_persona}
                onChange={(e) => setSettings({ ...settings, ai_agent_persona: e.target.value })}
              >
                <option>Professional Educator</option>
                <option>Creative Storyteller</option>
                <option>Technical Explainer</option>
              </select>
            </div>
            
            <div className="divider" />
            
            <div className="settings-item">
              <div>
                <h3>Default Template</h3>
                <p>Visual style applied to new animations.</p>
              </div>
              <select 
                className="select-field"
                value={settings.template_selection}
                onChange={(e) => setSettings({ ...settings, template_selection: e.target.value })}
              >
                <option>Educational</option>
                <option>Cinematic</option>
              </select>
            </div>
          </Card>
        </section>

        <section className="settings-section stagger-1 animate-fade-in">
          <h2>General</h2>
          <Card padding="md" className="settings-card">
            <div className="settings-item">
              <div>
                <h3>Theme</h3>
                <p>Interface color mode.</p>
              </div>
              <select 
                className="select-field"
                value={settings.theme}
                onChange={(e) => setSettings({ ...settings, theme: e.target.value })}
              >
                <option value="system">System Default</option>
                <option value="light">Light (Warm Monochrome)</option>
                <option value="dark">Dark</option>
              </select>
            </div>
          </Card>
        </section>
        
        <div className="settings-actions stagger-2 animate-fade-in">
          <Button variant="primary" onClick={handleSave}>Save Changes</Button>
        </div>
      </div>
    </div>
  );
};

