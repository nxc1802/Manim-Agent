import { useState } from 'react';
import Sidebar from '../components/Sidebar';
import { Clock, CheckCircle2, XCircle, Loader2, Play, Square, Download, ChevronDown, ChevronUp, Terminal } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const JobsPage = () => {
  const [expandedJob, setExpandedJob] = useState<string | null>(null);

  const mockJobs = [
    { id: '1', type: 'Render', title: 'Binary Search Visualization', status: 'completed', date: '10:45 AM', quality: '1080p', logs: ['Scene setup complete', 'Rendering frame 0-120', 'Finalizing MP4...'] },
    { id: '2', type: 'Voice', title: 'Quick Sort Deep Dive', status: 'running', date: '11:20 AM', progress: 45, logs: ['Text normalized', 'Generating voice-o-matic...', 'Encoding audio'] },
    { id: '3', type: 'Render', title: 'Neural Network Basics', status: 'queued', date: '11:30 AM', quality: '720p', logs: ['Waiting for worker availability'] },
    { id: '4', type: 'Render', title: 'Pythagorean Theorem', status: 'failed', date: 'Yesterday', error: 'Render Timeout', logs: ['Rendering failed at frame 450', 'Error: Memory limit exceeded'] },
  ];

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      
      <main style={{ marginLeft: '300px', padding: '40px 60px', width: '100%' }}>
        <header style={{ marginBottom: '48px' }}>
          <h1 style={{ fontSize: '2.5rem', marginBottom: '8px' }}>Jobs Queue</h1>
          <p style={{ color: 'var(--text-secondary)' }}>Track your video rendering and TTS synthesis tasks.</p>
        </header>

        <div className="glass-card" style={{ overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--surface-border)', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                <th style={{ padding: '20px 24px' }}>Type</th>
                <th style={{ padding: '20px 24px' }}>Project / Task</th>
                <th style={{ padding: '20px 24px' }}>Status</th>
                <th style={{ padding: '20px 24px' }}>Info</th>
                <th style={{ padding: '20px 24px' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {mockJobs.map(job => (
                <React.Fragment key={job.id}>
                  <tr 
                    style={{ 
                      borderBottom: expandedJob === job.id ? 'none' : '1px solid rgba(255,255,255,0.02)', 
                      transition: 'var(--transition)',
                      background: expandedJob === job.id ? 'rgba(255,255,255,0.02)' : 'transparent'
                    }}
                  >
                    <td style={{ padding: '20px 24px' }}>
                      <span style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        background: job.type === 'Render' ? 'rgba(14, 165, 233, 0.1)' : 'rgba(168, 85, 247, 0.1)',
                        color: job.type === 'Render' ? 'var(--accent-secondary)' : 'var(--accent-primary)',
                        border: `1px solid ${job.type === 'Render' ? 'rgba(14, 165, 233, 0.2)' : 'rgba(168, 85, 247, 0.2)'}`
                      }}>
                        {job.type}
                      </span>
                    </td>
                    <td style={{ padding: '20px 24px' }}>
                      <div style={{ fontWeight: 600 }}>{job.title}</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '4px' }}>Started at {job.date}</div>
                    </td>
                    <td style={{ padding: '20px 24px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {job.status === 'completed' && <CheckCircle2 size={16} color="#22c55e" />}
                        {job.status === 'running' && <Loader2 size={16} color="var(--accent-primary)" className="animate-spin" />}
                        {job.status === 'queued' && <Clock size={16} color="var(--text-secondary)" />}
                        {job.status === 'failed' && <XCircle size={16} color="#ef4444" />}
                        <span style={{
                          fontSize: '0.9rem',
                          fontWeight: 500,
                          color: job.status === 'completed' ? '#22c55e' : job.status === 'failed' ? '#ef4444' : 'white'
                        }}>
                          {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
                          {job.progress && ` (${job.progress}%)`}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '20px 24px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                      {job.quality || job.error || '-'}
                    </td>
                    <td style={{ padding: '20px 24px' }}>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        {job.status === 'completed' && (
                          <button title="Download" style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}><Download size={18} /></button>
                        )}
                        {job.status === 'running' && (
                          <button title="Stop" style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}><Square size={18} /></button>
                        )}
                        {job.status === 'failed' && (
                          <button title="Retry" style={{ background: 'none', border: 'none', color: 'var(--accent-primary)', cursor: 'pointer' }}><Play size={18} /></button>
                        )}
                        <button 
                          onClick={() => setExpandedJob(expandedJob === job.id ? null : job.id)}
                          style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
                        >
                          {expandedJob === job.id ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                        </button>
                      </div>
                    </td>
                  </tr>
                  
                  {/* Expandable Log Area */}
                  <AnimatePresence>
                    {expandedJob === job.id && (
                      <tr>
                        <td colSpan={5} style={{ padding: '0 24px 24px 24px', background: 'rgba(255,255,255,0.02)' }}>
                          <motion.div 
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            style={{ 
                              overflow: 'hidden', 
                              padding: '20px', 
                              borderRadius: '12px', 
                              background: 'rgba(0,0,0,0.2)',
                              border: '1px solid var(--surface-border)'
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', color: 'var(--accent-primary)', fontSize: '0.85rem', fontWeight: 600 }}>
                              <Terminal size={14} />
                              Execution Logs
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontFamily: 'monospace', fontSize: '0.85rem' }}>
                              {job.logs.map((log, index) => (
                                <div key={index} style={{ color: 'var(--text-secondary)' }}>
                                  <span style={{ color: 'rgba(255,255,255,0.2)', marginRight: '10px' }}>{index + 1}</span>
                                  {log}
                                </div>
                              ))}
                            </div>
                          </motion.div>
                        </td>
                      </tr>
                    )}
                  </AnimatePresence>
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
};

import React from 'react';
export default JobsPage;

