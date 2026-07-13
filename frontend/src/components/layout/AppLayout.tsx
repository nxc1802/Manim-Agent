import React from 'react';
import { Outlet } from 'react-router-dom';
import { TopNav } from './TopNav';
import './AppLayout.css';

export const AppLayout: React.FC = () => {
  return (
    <div className="app-layout">
      <TopNav />
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
};
