import { CheckCircle2, Circle, Loader2 } from 'lucide-react';

export interface Stage {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'completed';
}

const PipelineVisualizer = ({ stages }: { stages: Stage[] }) => {
  return (
    <div className="glass" style={{ padding: '32px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <h3 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>Pipeline Progress</h3>
      
      <div style={{ display: 'flex', justifyContent: 'space-between', position: 'relative' }}>
        {/* Progress Line */}
        <div style={{
          position: 'absolute',
          top: '20px',
          left: '40px',
          right: '40px',
          height: '2px',
          background: 'var(--surface-border)',
          zIndex: 0
        }}></div>

        {stages.map((stage) => (
          <div key={stage.id} style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '12px',
            zIndex: 1,
            flex: 1
          }}>
            <div style={{
              width: '40px',
              height: '40px',
              borderRadius: '50%',
              background: stage.status === 'completed' ? 'var(--accent-success)' : 
                          stage.status === 'running' ? 'var(--accent-primary)' : 'var(--bg-color)',
              border: '2px solid',
              borderColor: stage.status === 'pending' ? 'var(--surface-border)' : 'transparent',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: stage.status === 'running' ? '0 0 20px rgba(168, 85, 247, 0.4)' : 'none'
            }}>
              {stage.status === 'completed' ? <CheckCircle2 size={20} color="white" /> :
               stage.status === 'running' ? <Loader2 size={20} color="white" className="spin" /> :
               <Circle size={20} color="var(--text-secondary)" />}
            </div>
            <span style={{
              fontSize: '0.85rem',
              fontWeight: 500,
              color: stage.status === 'pending' ? 'var(--text-secondary)' : 'white'
            }}>
              {stage.label}
            </span>
          </div>
        ))}
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .spin { animation: spin 2s linear infinite; }
      `}</style>
    </div>
  );
};

export default PipelineVisualizer;
