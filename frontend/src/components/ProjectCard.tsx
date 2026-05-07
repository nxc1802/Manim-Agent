import { Calendar, Play, MoreVertical } from 'lucide-react';

interface ProjectCardProps {
  title: string;
  status: string;
  date: string;
}

const ProjectCard = ({ title, status, date }: ProjectCardProps) => {
  return (
    <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <h3 style={{ fontSize: '1.1rem' }}>{title}</h3>
        <MoreVertical size={20} color="var(--text-secondary)" cursor="pointer" />
      </div>

      <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
        <span style={{
          padding: '4px 12px',
          borderRadius: '20px',
          fontSize: '0.75rem',
          fontWeight: 600,
          background: status === 'Completed' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(168, 85, 247, 0.1)',
          color: status === 'Completed' ? '#22c55e' : 'var(--accent-primary)',
          border: `1px solid ${status === 'Completed' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(168, 85, 247, 0.2)'}`
        }}>
          {status}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
          <Calendar size={14} />
          {date}
        </div>
      </div>

      <div style={{
        marginTop: '8px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '140px',
        background: 'rgba(0,0,0,0.2)',
        borderRadius: '12px',
        border: '1px dashed var(--surface-border)',
        color: 'var(--text-secondary)',
        cursor: 'pointer',
        transition: 'var(--transition)'
      }} className="project-preview">
        <Play size={24} />
      </div>
    </div>
  );
};

export default ProjectCard;
