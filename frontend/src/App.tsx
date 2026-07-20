import React, { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
import { api, applyTheme } from './lib/api';
import { hasSupabaseConfig, isAuthDisabled, supabase } from './lib/supabase';

const Login = lazy(() => import('./pages/Login').then(module => ({ default: module.Login })));
const Dashboard = lazy(() => import('./pages/Dashboard').then(module => ({ default: module.Dashboard })));
const SceneEditor = lazy(() => import('./pages/SceneEditor').then(module => ({ default: module.SceneEditor })));
const Settings = lazy(() => import('./pages/Settings').then(module => ({ default: module.Settings })));

export const App: React.FC = () => {
  const [ready, setReady] = useState(isAuthDisabled);
  const [signedIn, setSignedIn] = useState(isAuthDisabled);

  useEffect(() => {
    if (!isAuthDisabled && !signedIn) return;
    api.getSettings()
      .then(settings => applyTheme(settings.theme))
      .catch(console.error);
  }, [signedIn]);

  useEffect(() => {
    if (isAuthDisabled) return;

    if (!hasSupabaseConfig) {
      console.error('VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are required in jwt mode.');
      setReady(true);
      return;
    }

    let live = true;
    supabase.auth.getSession().then(({ data }) => {
      if (live) {
        setSignedIn(Boolean(data.session));
        setReady(true);
      }
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setSignedIn(Boolean(session));
      setReady(true);
    });
    return () => {
      live = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  if (!ready) return null;

  return (
    <BrowserRouter>
      <Suspense fallback={<div role="status" style={{ padding: 48 }}>Loading workspace…</div>}>
        <Routes>
          <Route path="/login" element={signedIn ? <Navigate to="/" replace /> : <Login />} />

          <Route element={signedIn ? <AppLayout /> : <Navigate to="/login" replace />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/projects/:projectId" element={<SceneEditor />} />
            <Route path="/settings" element={<Settings />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
};

export default App;
