import { useState, useEffect } from 'react';
import Sidebar from '../components/Sidebar';
import ProjectCard from '../components/ProjectCard';
import { Plus, Zap, Video, Clock, Activity, Loader2 } from 'lucide-react';
import { projectService } from '../services/api';
import type { Project } from '../types/api';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const Dashboard = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { user } = useAuth();
  
  const userName = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'User';

  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const res = await projectService.getAll(1, 6);
        const data = res?.data;
        setProjects(Array.isArray(data) ? data : (data as any)?.items || []);
      } catch (err) {
        console.error('Failed to fetch projects', err);
      } finally {
        setLoading(false);
      }
    };
    fetchProjects();
  }, []);

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      
      <main style={{ marginLeft: '300px', padding: '40px 60px', width: '100%' }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '40px' }}>
          <div>
            <h1 style={{ fontSize: '2.5rem', marginBottom: '8px' }}>Welcome back, <span className="glow-text">{userName}</span></h1>
            <p style={{ color: 'var(--text-secondary)' }}>
              You have <span style={{ color: 'white', fontWeight: 600 }}>{projects.length} projects</span> in your workspace.
            </p>
          </div>
          <button 
            onClick={() => navigate('/projects')}
            className="btn-primary" 
            style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '14px 24px' }}
          >
            <Plus size={20} />
            New Project
          </button>
        </header>

        {/* Quick Stats */}
        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '24px', marginBottom: '48px' }}>
          <StatCard icon={<Video size={20} color="#0ea5e9" />} label="Total Projects" value={projects.length.toString()} />
          <StatCard icon={<Zap size={20} color="#a855f7" />} label="AI Tokens Used" value="45.2k" />
          <StatCard icon={<Clock size={20} color="#eab308" />} label="Render Time" value="4.2h" />
          <StatCard icon={<Activity size={20} color="#22c55e" />} label="Active Jobs" value="2" />
        </section>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '48px' }}>
          {/* Recent Projects */}
          <section>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '1.5rem' }}>Recent Projects</h2>
              <span 
                onClick={() => navigate('/projects')}
                style={{ color: 'var(--accent-primary)', cursor: 'pointer', fontWeight: 600, fontSize: '0.9rem' }}
              >
                View All
              </span>
            </div>
            {loading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}>
                <Loader2 className="spin" />
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '24px' }}>
                {projects?.map(p => (
                  <div key={p.id} onClick={() => navigate(`/projects`)} style={{ cursor: 'pointer' }}>
                    <ProjectCard 
                      title={p.title || 'Untitled Project'} 
                      status={p.status ? p.status.charAt(0).toUpperCase() + p.status.slice(1) : 'Unknown'} 
                      date={p.created_at ? new Date(p.created_at).toLocaleDateString() : 'Unknown'} 
                    />
                  </div>
                ))}
                {(!projects || projects.length === 0) && (
                  <p style={{ color: 'var(--text-secondary)' }}>No projects found. Create your first one!</p>
                )}
              </div>
            )}
          </section>

          {/* Activity Feed */}
          <section>
            <h2 style={{ fontSize: '1.5rem', marginBottom: '24px' }}>Activity Feed</h2>
            <div className="glass" style={{ padding: '24px', borderRadius: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <ActivityItem 
                time="Just now" 
                title="System Ready" 
                desc="Backend API is connected." 
                type="success"
              />
              <ActivityItem 
                time="Recent" 
                title="Project List" 
                desc="Successfully fetched workspace." 
                type="info"
              />
            </div>
          </section>
        </div>
      </main>
    </div>
  );
};

const StatCard = ({ icon, label, value }: { icon: React.ReactNode, label: string, value: string }) => (
  <div className="glass-card" style={{ padding: '24px', display: 'flex', alignItems: 'center', gap: '20px' }}>
    <div style={{ 
      width: '48px', 
      height: '48px', 
      borderRadius: '14px', 
      background: 'rgba(255,255,255,0.03)', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center',
      border: '1px solid var(--surface-border)'
    }}>
      {icon}
    </div>
    <div>
      <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{value}</div>
    </div>
  </div>
);

const ActivityItem = ({ time, title, desc, type }: { time: string, title: string, desc: string, type: 'success' | 'info' | 'neutral' }) => (
  <div style={{ display: 'flex', gap: '16px' }}>
    <div style={{ 
      width: '8px', 
      height: '8px', 
      borderRadius: '50%', 
      marginTop: '6px',
      background: type === 'success' ? '#22c55e' : type === 'info' ? 'var(--accent-primary)' : 'var(--text-secondary)'
    }} />
    <div style={{ flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
        <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{title}</span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{time}</span>
      </div>
      <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>{desc}</p>
    </div>
  </div>
);

export default Dashboard;
