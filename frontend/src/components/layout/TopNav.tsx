import React from 'react';
import { useNavigate } from 'react-router-dom';
import { SignOut, Gear, Aperture } from '@phosphor-icons/react';
import { Button } from '../ui/Button';
import './TopNav.css';

export const TopNav: React.FC = () => {
  const navigate = useNavigate();

  return (
    <nav className="topnav">
      <div className="topnav-container">
        <div className="topnav-brand" onClick={() => navigate('/')}>
          <Aperture size={24} weight="bold" />
          <span className="editorial-heading topnav-title">Manim Studio</span>
        </div>
        
        <div className="topnav-actions">
          <Button variant="ghost" size="sm" onClick={() => navigate('/settings')}>
            <Gear size={20} weight="fill" />
            <span style={{ marginLeft: 8 }}>Settings</span>
          </Button>
          <Button variant="ghost" size="sm" onClick={() => console.log('Logout')}>
            <SignOut size={20} weight="fill" />
            <span style={{ marginLeft: 8 }}>Logout</span>
          </Button>
        </div>
      </div>
    </nav>
  );
};
