import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Aperture } from '@phosphor-icons/react';
import './Login.css';

export const Login: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Simulate successful login and redirect to Dashboard
    navigate('/');
  };

  return (
    <div className="login-page">
      <div className="login-container animate-fade-in">
        <div className="login-brand">
          <Aperture size={48} weight="bold" />
          <h1 className="editorial-heading login-title">Manim Studio</h1>
        </div>
        
        <Card padding="lg" className="login-card">
          <h2 style={{ marginBottom: 16 }}>Sign In</h2>
          <p className="login-subtitle">Enter your credentials to access the workspace.</p>
          
          <form onSubmit={handleSubmit} className="login-form">
            <div className="form-group">
              <label>Email Address</label>
              <input 
                type="email" 
                className="input-field" 
                placeholder="name@example.com" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label>Password</label>
              <input 
                type="password" 
                className="input-field" 
                placeholder="••••••••" 
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <Button type="submit" size="lg" className="login-submit">Continue to Studio</Button>
          </form>
        </Card>
      </div>
    </div>
  );
};

