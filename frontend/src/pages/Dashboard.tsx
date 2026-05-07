import { useEffect } from 'react';
import Sidebar from '../components/Sidebar';
import ProjectCard from '../components/ProjectCard';
import { Plus, Zap, Video, Clock, Activity, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useProjectStore } from '../store/useProjectStore';
import styles from './Dashboard.module.css';

const Dashboard = () => {
  const { projects, stats, loading, fetchProjects, fetchStats } = useProjectStore();
  const navigate = useNavigate();
  const { user } = useAuth();
  
  const userName = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'User';

  useEffect(() => {
    fetchProjects(1, 6);
    fetchStats();
  }, [fetchProjects, fetchStats]);

  return (
    <div className={styles.container}>
      <Sidebar />
      
      <main className={styles.main}>
        <header className={styles.header}>
          <div>
            <h1 className={styles.welcomeTitle}>Welcome back, <span className="glow-text">{userName}</span></h1>
            <p className={styles.subtitle}>
              You have <span className={styles.projectCount}>{projects.length} projects</span> in your workspace.
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
        <section className={styles.statsGrid}>
          <StatCard 
            icon={<Video size={20} color="#0ea5e9" />} 
            label="Total Projects" 
            value={stats?.total_projects.toString() || '0'} 
          />
          <StatCard 
            icon={<Zap size={20} color="#a855f7" />} 
            label="AI Tokens Used" 
            value={stats ? `${(stats.total_tokens_used / 1000).toFixed(1)}k` : '0'} 
          />
          <StatCard 
            icon={<Clock size={20} color="#eab308" />} 
            label="Render Time" 
            value={stats ? `${stats.total_render_time_hours}h` : '0h'} 
          />
          <StatCard 
            icon={<Activity size={20} color="#22c55e" />} 
            label="Active Jobs" 
            value={stats?.active_jobs.toString() || '0'} 
          />
        </section>

        <div className={styles.contentGrid}>
          {/* Recent Projects */}
          <section>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Recent Projects</h2>
              <span 
                onClick={() => navigate('/projects')}
                className={styles.viewAll}
              >
                View All
              </span>
            </div>
            {loading ? (
              <div className={styles.loaderContainer}>
                <Loader2 className="spin" />
              </div>
            ) : (
              <div className={styles.projectsGrid}>
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
                  <p className={styles.emptyState}>No projects found. Create your first one!</p>
                )}
              </div>
            )}
          </section>

          {/* Activity Feed */}
          <section>
            <h2 className={styles.sectionTitle} style={{ marginBottom: '24px' }}>Activity Feed</h2>
            <div className={`glass ${styles.activityFeed}`} style={{ padding: '24px', borderRadius: '20px' }}>
              <ActivityItem 
                time="Just now" 
                title="System Ready" 
                desc="Connected via Supabase Realtime." 
                type="success"
              />
              <ActivityItem 
                time="Recent" 
                title="Workspace Synced" 
                desc="Fetched latest project statistics." 
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
  <div className={`glass-card ${styles.statCard}`}>
    <div className={styles.statIconWrapper}>
      {icon}
    </div>
    <div>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statValue}>{value}</div>
    </div>
  </div>
);

const ActivityItem = ({ time, title, desc, type }: { time: string, title: string, desc: string, type: 'success' | 'info' | 'neutral' }) => (
  <div className={styles.activityItem}>
    <div className={`${styles.activityDot} ${type === 'success' ? styles.dotSuccess : type === 'info' ? styles.dotInfo : styles.dotNeutral}`} />
    <div className={styles.activityContent}>
      <div className={styles.activityHeader}>
        <span className={styles.activityTitle}>{title}</span>
        <span className={styles.activityTime}>{time}</span>
      </div>
      <p className={styles.activityDesc}>{desc}</p>
    </div>
  </div>
);

export default Dashboard;
