import { useState, type ReactNode } from 'react';
import Sidebar from '../components/Sidebar';
import { Save, User, Shield, Zap, Globe } from 'lucide-react';

const SettingsPage = () => {
  const [activeTab, setActiveTab] = useState('profile');

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      
      <main style={{ marginLeft: '300px', padding: '40px 60px', width: '100%' }}>
        <header style={{ marginBottom: '40px' }}>
          <h1 style={{ fontSize: '2.5rem', marginBottom: '8px' }}>Settings</h1>
          <p style={{ color: 'var(--text-secondary)' }}>Manage your account and system preferences.</p>
        </header>

        <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: '48px' }}>
          {/* Navigation */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <SettingsTab id="profile" icon={<User size={18} />} label="Profile" active={activeTab === 'profile'} onClick={setActiveTab} />
            <SettingsTab id="api" icon={<Zap size={18} />} label="API Config" active={activeTab === 'api'} onClick={setActiveTab} />
            <SettingsTab id="security" icon={<Shield size={18} />} label="Security" active={activeTab === 'security'} onClick={setActiveTab} />
            <SettingsTab id="system" icon={<Globe size={18} />} label="System" active={activeTab === 'system'} onClick={setActiveTab} />
          </div>

          {/* Content */}
          <div className="glass-card" style={{ padding: '40px' }}>
            {activeTab === 'profile' && <ProfileSettings />}
            {activeTab === 'api' && <ApiSettings />}
            {activeTab === 'security' && <SecuritySettings />}
            {activeTab === 'system' && <SystemSettings />}
            
            <div style={{ marginTop: '40px', paddingTop: '24px', borderTop: '1px solid var(--surface-border)', display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Save size={18} />
                Save Changes
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

const SettingsTab = ({ id, icon, label, active, onClick }: { id: string, icon: ReactNode, label: string, active: boolean, onClick: (id: string) => void }) => (
  <div
    onClick={() => onClick(id)}
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      padding: '12px 16px',
      borderRadius: '12px',
      cursor: 'pointer',
      color: active ? 'white' : 'var(--text-secondary)',
      background: active ? 'rgba(168, 85, 247, 0.15)' : 'transparent',
      transition: 'var(--transition)'
    }}
  >
    {icon}
    <span style={{ fontWeight: 500 }}>{label}</span>
  </div>
);

const ProfileSettings = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
    <h3 style={{ fontSize: '1.25rem' }}>Personal Information</h3>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
      <InputGroup label="Full Name" placeholder="John Doe" />
      <InputGroup label="Email Address" placeholder="john@example.com" disabled />
    </div>
  </div>
);

const ApiSettings = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
    <h3 style={{ fontSize: '1.25rem' }}>AI Model Configuration</h3>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <InputGroup label="OpenRouter API Key" placeholder="sk-or-v1-..." type="password" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <label style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Preferred Model (Standard)</label>
        <select className="glass-input" style={{
          padding: '12px',
          borderRadius: '10px',
          background: 'rgba(255, 255, 255, 0.05)',
          border: '1px solid var(--surface-border)',
          color: 'white',
          outline: 'none'
        }}>
          <option>google/gemini-pro-1.5</option>
          <option>anthropic/claude-3-sonnet</option>
          <option>openai/gpt-4-turbo</option>
        </select>
      </div>
    </div>
  </div>
);

const SecuritySettings = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
    <h3 style={{ fontSize: '1.25rem' }}>Security & Authentication</h3>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <InputGroup label="Current Password" placeholder="••••••••" type="password" />
      <InputGroup label="New Password" placeholder="••••••••" type="password" />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', borderRadius: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--surface-border)' }}>
        <div>
          <div style={{ fontWeight: 600, marginBottom: '4px' }}>Two-Factor Authentication</div>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Add an extra layer of security to your account.</div>
        </div>
        <button className="btn-primary" style={{ padding: '8px 16px', fontSize: '0.85rem' }}>Enable</button>
      </div>
    </div>
  </div>
);

const SystemSettings = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
    <h3 style={{ fontSize: '1.25rem' }}>System Preferences</h3>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <label style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Interface Theme</label>
        <select className="glass-input" style={{ padding: '12px', borderRadius: '10px', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--surface-border)', color: 'white' }}>
          <option>Deep Space (Dark)</option>
          <option>Cyberpunk (Neon)</option>
          <option>Light Matter (Light)</option>
        </select>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <label style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Language</label>
        <select className="glass-input" style={{ padding: '12px', borderRadius: '10px', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--surface-border)', color: 'white' }}>
          <option>English (US)</option>
          <option>Vietnamese</option>
          <option>Japanese</option>
        </select>
      </div>
    </div>
  </div>
);

const InputGroup = ({ label, placeholder, type = 'text', disabled = false }: { label: string, placeholder: string, type?: string, disabled?: boolean }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
    <label style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>{label}</label>
    <input
      type={type}
      placeholder={placeholder}
      disabled={disabled}
      className="glass-input"
      style={{
        padding: '12px',
        borderRadius: '10px',
        background: disabled ? 'rgba(255, 255, 255, 0.02)' : 'rgba(255, 255, 255, 0.05)',
        border: '1px solid var(--surface-border)',
        color: disabled ? 'var(--text-secondary)' : 'white',
        outline: 'none',
        transition: 'var(--transition)'
      }}
    />
  </div>
);

export default SettingsPage;

