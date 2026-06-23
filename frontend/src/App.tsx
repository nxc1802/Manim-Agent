import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { useAuth } from './hooks/useAuth';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const SceneEditor = lazy(() => import('./pages/SceneEditor'));
const LoginPage = lazy(() => import('./pages/Auth/LoginPage'));
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'));
const JobsPage = lazy(() => import('./pages/JobsPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));

const PageFallback = () => (
  <div style={{ display: 'grid', minHeight: '100vh', placeItems: 'center', color: 'white' }}>
    Loading page...
  </div>
);

function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', color: 'white' }}>
        <div className="animated-bg" />
        <p>Loading session...</p>
      </div>
    );
  }

  return (
    <Router>
      <div className="app-container">
        <div className="animated-bg" />
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/login" element={!user ? <LoginPage /> : <Navigate to="/" />} />

            <Route path="/" element={user ? <Dashboard /> : <Navigate to="/login" />} />
            <Route path="/projects" element={user ? <ProjectsPage /> : <Navigate to="/login" />} />
            <Route path="/jobs" element={user ? <JobsPage /> : <Navigate to="/login" />} />
            <Route path="/settings" element={user ? <SettingsPage /> : <Navigate to="/login" />} />
            <Route path="/editor/:sceneId" element={user ? <SceneEditor /> : <Navigate to="/login" />} />

            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </Suspense>
      </div>
    </Router>
  );
}

export default App;
