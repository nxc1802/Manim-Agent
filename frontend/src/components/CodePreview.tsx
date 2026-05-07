import { useState } from 'react';
import { Copy, Check, Code } from 'lucide-react';

const CodePreview = ({ code }: { code: string }) => {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="glass-card" style={{ padding: '0', overflow: 'hidden' }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '12px 20px',
        borderBottom: '1px solid var(--surface-border)',
        background: 'rgba(255, 255, 255, 0.02)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Code size={16} color="var(--accent-primary)" />
          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>manim_scene.py</span>
        </div>
        <button
          onClick={copyToClipboard}
          style={{
            background: 'transparent',
            border: 'none',
            color: copied ? '#22c55e' : 'var(--text-secondary)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '0.8rem',
            padding: '4px 8px',
            borderRadius: '6px',
            transition: 'var(--transition)'
          }}
          className="nav-item-hover"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? 'Copied!' : 'Copy Code'}
        </button>
      </div>
      <div style={{ padding: '24px', background: 'rgba(0,0,0,0.3)' }}>
        <pre style={{
          margin: 0,
          fontFamily: "'Fira Code', monospace",
          fontSize: '0.9rem',
          lineHeight: '1.6',
          color: '#e2e8f0',
          overflowX: 'auto'
        }}>
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
};

export default CodePreview;
