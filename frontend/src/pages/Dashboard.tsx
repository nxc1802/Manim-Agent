import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Plus, Video, Code, Lightning, X } from '@phosphor-icons/react';
import { Dialog } from '../components/ui/Dialog';
import { api } from '../lib/api';
import type { Project } from '../lib/api';
import './Dashboard.css';

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectBrief, setNewProjectBrief] = useState('');
  const [loading, setLoading] = useState(true);
  const [errorDialog, setErrorDialog] = useState<{ isOpen: boolean; message: string }>({ isOpen: false, message: '' });

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    try {
      const data = await api.getProjects();
      setProjects(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;

    try {
      const created = await api.createProject(newProjectName, newProjectBrief);
      setProjects([created, ...projects]);
      setIsModalOpen(false);
      setNewProjectName('');
      setNewProjectBrief('');
      // Navigate to the newly created project Scene Editor
      navigate(`/projects/${created.id}`);
    } catch (e: any) {
      console.error(e);
      setErrorDialog({
        isOpen: true,
        message: e.message || 'Failed to create project. Please verify backend is running.'
      });
    }
  };

  return (
    <div className="dashboard-page animate-fade-in">
      <header className="dashboard-header">
        <div>
          <h1 className="editorial-heading dashboard-title">Projects</h1>
          <p className="dashboard-subtitle">Manage your animation sequences</p>
        </div>
        <Button onClick={() => setIsModalOpen(true)}>
          <Plus size={16} weight="bold" />
          <span style={{ marginLeft: 8 }}>New Project</span>
        </Button>
      </header>

      <section className="stats-grid">
        <Card className="stat-card stagger-1 animate-fade-in">
          <div className="stat-icon"><Video size={24} weight="light" /></div>
          <div className="stat-value">{projects.length}</div>
          <div className="stat-label">Total Projects</div>
        </Card>
        <Card className="stat-card stagger-2 animate-fade-in">
          <div className="stat-icon"><Lightning size={24} weight="light" /></div>
          <div className="stat-value">84k</div>
          <div className="stat-label">Tokens Used</div>
        </Card>
        <Card className="stat-card stagger-3 animate-fade-in">
          <div className="stat-icon"><Code size={24} weight="light" /></div>
          <div className="stat-value">4</div>
          <div className="stat-label">Active Jobs</div>
        </Card>
      </section>

      <section className="projects-section">
        <h2 className="section-title">Recent Work</h2>
        {loading ? (
          <p>Loading projects...</p>
        ) : (
          <div className="bento-grid">
            {projects.map((project, idx) => (
              <Card 
                key={project.id} 
                interactive 
                padding="lg" 
                className={`project-card stagger-${(idx % 4) + 1} animate-fade-in`}
                onClick={() => navigate(`/projects/${project.id}`)}
              >
                <div className="project-card-header">
                  <h3>{project.title}</h3>
                  <Badge color={project.status === 'generating' ? 'blue' : (project.status === 'completed' ? 'green' : 'gray')}>
                    {project.status || 'Draft'}
                  </Badge>
                </div>
                <p className="project-card-desc">
                  {project.description || 'No storyboard brief provided yet.'}
                </p>
                <div className="project-card-meta">
                  <span className="meta-text">{project.created_at || 'Recently updated'}</span>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* New Project Modal */}
      {isModalOpen && ReactDOM.createPortal(
        <div className="modal-overlay" onClick={() => setIsModalOpen(false)}>
          <div className="modal-container animate-fade-in" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create New Project</h2>
              <button className="modal-close-btn" onClick={() => setIsModalOpen(false)}>
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleCreateProject}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Project Name</label>
                  <input 
                    type="text" 
                    className="input-field" 
                    placeholder="e.g. Calculus Intro Part 1" 
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    required
                    autoFocus
                  />
                </div>
                <div className="form-group">
                  <label>Storyboard Text / Brief</label>
                  <textarea 
                    className="input-field" 
                    rows={4}
                    placeholder="Explain the concepts, shapes, or transitions you want the AI to generate..." 
                    value={newProjectBrief}
                    onChange={(e) => setNewProjectBrief(e.target.value)}
                    style={{ resize: 'vertical', fontFamily: 'inherit' }}
                  />
                </div>
              </div>
              <div className="modal-footer">
                <Button type="button" variant="secondary" onClick={() => setIsModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary">
                  Create Project
                </Button>
              </div>
            </form>
          </div>
        </div>,
        document.body
      )}

      <Dialog
        isOpen={errorDialog.isOpen}
        title="Creation Error"
        message={errorDialog.message}
        onConfirm={() => setErrorDialog({ isOpen: false, message: '' })}
        onCancel={() => setErrorDialog({ isOpen: false, message: '' })}
        confirmText="OK"
      />
    </div>
  );
};

