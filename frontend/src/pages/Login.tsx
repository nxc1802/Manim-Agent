import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Aperture } from '@phosphor-icons/react';
import { supabase } from '../lib/supabase';
import './Login.css';

export const Login: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);

  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    setSuccessMsg('');

    if (isSignUp) {
      const { data, error: authError } = await supabase.auth.signUp({ email, password });
      setSubmitting(false);
      if (authError) {
        setError(authError.message);
        return;
      }
      if (data.user && !data.session) {
        setSuccessMsg('Registration successful! Please check your email for a confirmation link.');
      } else {
        navigate('/', { replace: true });
      }
    } else {
      const { error: authError } = await supabase.auth.signInWithPassword({ email, password });
      setSubmitting(false);
      if (authError) {
        setError(authError.message);
        return;
      }
      navigate('/', { replace: true });
    }
  };

  return (
    <div className="login-page">
      <div className="login-container animate-fade-in">
        <div className="login-brand">
          <Aperture size={48} weight="bold" />
          <h1 className="editorial-heading login-title">Manim Studio</h1>
        </div>
        
        <Card padding="lg" className="login-card">
          <h2 style={{ marginBottom: 16 }}>{isSignUp ? 'Create Account' : 'Sign In'}</h2>
          <p className="login-subtitle">
            {isSignUp ? 'Register a new account to access the workspace.' : 'Enter your credentials to access the workspace.'}
          </p>
          
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
            {error && <p role="alert" style={{ color: 'var(--color-danger, #c62828)', fontSize: '0.9rem', marginTop: 8 }}>{error}</p>}
            {successMsg && <p role="status" style={{ color: 'var(--color-success, #2e7d32)', fontSize: '0.9rem', marginTop: 8 }}>{successMsg}</p>}

            <Button type="submit" size="lg" className="login-submit" disabled={submitting}>
              {submitting ? (isSignUp ? 'Creating account…' : 'Signing in…') : (isSignUp ? 'Create Account' : 'Continue to Studio')}
            </Button>

            <div style={{ marginTop: 24, textAlign: 'center' }}>
              <button
                type="button"
                onClick={() => {
                  setIsSignUp(!isSignUp);
                  setError('');
                  setSuccessMsg('');
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--color-text-secondary)',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  textDecoration: 'underline'
                }}
              >
                {isSignUp ? 'Already have an account? Sign In' : "Don't have an account? Sign Up"}
              </button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
};
