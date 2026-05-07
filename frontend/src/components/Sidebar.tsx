import type { ReactNode } from 'react';
import { LayoutDashboard, Video, Activity, Settings, HelpCircle, LogOut } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const Sidebar = () => {
  const location = useLocation();
  const { signOut } = useAuth();

  return (
    <aside className="glass" style={{
      width: '280px',
      height: '100vh',
      position: 'fixed',
      left: 0,
      top: 0,
      padding: '32px 24px',
      display: 'flex',
      flexDirection: 'column',
      borderRight: '1px solid var(--surface-border)',
      zIndex: 100
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '48px', padding: '0 8px' }}>
        <div style={{ width: '32px', height: '32px', background: 'var(--accent-gradient)', borderRadius: '8px' }} />
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, letterSpacing: '-0.02em' }}>Manim Agent</h2>
      </div>

      <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
        <NavItem icon={<LayoutDashboard size={20} />} label="Dashboard" to="/" active={location.pathname === '/'} />
        <NavItem icon={<Video size={20} />} label="Projects" to="/projects" active={location.pathname === '/projects'} />
        <NavItem icon={<Activity size={20} />} label="Jobs" to="/jobs" active={location.pathname === '/jobs'} />
      </nav>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingTop: '24px', borderTop: '1px solid var(--surface-border)' }}>
        <NavItem icon={<Settings size={20} />} label="Settings" to="/settings" active={location.pathname === '/settings'} />
        <NavItem icon={<HelpCircle size={20} />} label="Documentation" to="/docs" />
        <div 
          onClick={signOut}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '12px 16px',
            borderRadius: '12px',
            cursor: 'pointer',
            color: '#ef4444',
            transition: 'var(--transition)',
            marginTop: '8px'
          }}
        >
          <LogOut size={20} />
          <span style={{ fontWeight: 500 }}>Logout</span>
        </div>
      </div>
    </aside>
  );
};

const NavItem = ({ icon, label, to, active = false }: { icon: ReactNode, label: string, to: string, active?: boolean }) => (
  <Link 
    to={to}
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      padding: '12px 16px',
      borderRadius: '12px',
      textDecoration: 'none',
      color: active ? 'white' : 'var(--text-secondary)',
      background: active ? 'rgba(168, 85, 247, 0.15)' : 'transparent',
      transition: 'var(--transition)',
    }}
  >
    {icon}
    <span style={{ fontWeight: 500 }}>{label}</span>
  </Link>
);

export default Sidebar;
