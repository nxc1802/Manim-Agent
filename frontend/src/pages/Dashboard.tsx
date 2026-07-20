import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Plus, Video, Code, Trash, X } from '@phosphor-icons/react';
import { Dialog } from '../components/ui/Dialog';
import { api } from '../lib/api';
import type { DashboardStats, Project } from '../lib/api';
import './Dashboard.css';

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [defaultLanguage, setDefaultLanguage] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectBrief, setNewProjectBrief] = useState('');
  const [loading, setLoading] = useState(true);
  const [errorDialog, setErrorDialog] = useState<{ isOpen: boolean; message: string }>({ isOpen: false, message: '' });
  const [selectedProjects, setSelectedProjects] = useState<Set<string>>(new Set());
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [isDeleteMode, setIsDeleteMode] = useState(false);

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    try {
      // Do not hold the project grid behind the more expensive render-job
      // aggregation. The dashboard becomes usable as soon as cards arrive.
      const data = await api.getProjects();
      setProjects(data);
      void api.getSettings()
        .then(settings => setDefaultLanguage(settings.language))
        .catch(error => console.error('Failed to load default project language:', error));
      void api.getDashboardStats()
        .then(setStats)
        .catch(error => console.error('Failed to load dashboard stats:', error));
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
      let sourceLanguage = defaultLanguage;
      if (!sourceLanguage) {
        sourceLanguage = await api.getSettings()
          .then(settings => settings.language)
          .catch(() => 'vi');
      }
      const created = await api.createProject(newProjectName, newProjectBrief, sourceLanguage);
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

  const handleDeleteSelected = async () => {
    if (selectedProjects.size === 0) return;

    setLoading(true);
    try {
      const promises = Array.from(selectedProjects).map(id => api.deleteProject(id));
      await Promise.all(promises);
      setSelectedProjects(new Set());
      setIsDeleteMode(false);
      await loadProjects();
    } catch (e: any) {
      console.error(e);
      setErrorDialog({
        isOpen: true,
        message: e.message || 'Failed to delete some projects'
      });
      setLoading(false);
    }
  };

  return (
    <div className="dashboard-page animate-fade-in">
      <header className="dashboard-header">
        <div>
          <h1 className="editorial-heading dashboard-title">Projects</h1>
          <p className="dashboard-subtitle">Manage your animation sequences</p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          {isDeleteMode && (
            <>
              <Button
                variant="secondary"
                onClick={() => {
                  setIsDeleteMode(false);
                  setSelectedProjects(new Set());
                }}
              >
                Cancel
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  const allIds = new Set(projects.map(p => p.id));
                  setSelectedProjects(allIds);
                  setDeleteDialogOpen(true);
                }}
                style={{
                  backgroundColor: '#ff4d4f',
                  color: '#ffffff',
                  borderColor: '#ff4d4f'
                }}
              >
                Delete All
              </Button>
            </>
          )}
          <Button
            variant="secondary"
            onClick={() => {
              if (!isDeleteMode) {
                setIsDeleteMode(true);
              } else {
                if (selectedProjects.size > 0) {
                  setDeleteDialogOpen(true);
                } else {
                  setIsDeleteMode(false);
                }
              }
            }}
            style={isDeleteMode ? {
              backgroundColor: '#ffa940',
              color: '#ffffff',
              borderColor: '#ffa940'
            } : undefined}
          >
            <Trash size={16} weight="bold" />
            <span style={{ marginLeft: 8 }}>
              {isDeleteMode ? `Delete (${selectedProjects.size})` : 'Delete'}
            </span>
          </Button>
          <Button onClick={() => setIsModalOpen(true)} disabled={isDeleteMode}>
            <Plus size={16} weight="bold" />
            <span style={{ marginLeft: 8 }}>New Project</span>
          </Button>
        </div>
      </header>

      <section className="stats-grid">
        <Card className="stat-card stagger-1 animate-fade-in">
          <div className="stat-icon"><Video size={24} weight="light" /></div>
          <div className="stat-value">{stats?.total_projects ?? 0}</div>
          <div className="stat-label">Total Projects</div>
        </Card>
        <Card className="stat-card stagger-2 animate-fade-in">
          <div className="stat-icon"><Code size={24} weight="light" /></div>
          <div className="stat-value">{stats?.total_render_time_hours ?? 0}h</div>
          <div className="stat-label">Render Time</div>
        </Card>
        <Card className="stat-card stagger-3 animate-fade-in">
          <div className="stat-value">{stats?.active_jobs ?? 0}</div>
          <div className="stat-label">Active Jobs</div>
        </Card>
      </section>

      <section className="projects-section">
        <h2 className="section-title">Recent Work</h2>
        {loading ? (
          <p>Loading projects...</p>
        ) : (
          <div className="bento-grid">
            {projects.map((project, idx) => {
              const isSelected = selectedProjects.has(project.id);
              return (
                <Card
                  key={project.id}
                  interactive
                  padding="lg"
                  className={`project-card stagger-${(idx % 4) + 1} animate-fade-in ${
                    isSelected ? 'selected-delete' : ''
                  }`}
                  onClick={() => {
                    if (isDeleteMode) {
                      const newSet = new Set(selectedProjects);
                      if (isSelected) {
                        newSet.delete(project.id);
                      } else {
                        newSet.add(project.id);
                      }
                      setSelectedProjects(newSet);
                    } else {
                      navigate(`/projects/${project.id}`);
                    }
                  }}
                >
                  <div className="project-card-header" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <h3 style={{ margin: 0, flex: 1 }}>{project.title}</h3>
                    <Badge color={project.status === 'processing' ? 'blue' : (project.status === 'completed' ? 'green' : 'gray')}>
                      {project.status || 'Draft'}
                    </Badge>
                  </div>
                  <p className="project-card-desc">
                    {project.description || 'No storyboard brief provided yet.'}
                  </p>
                  <div className="project-card-meta" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto' }}>
                    <span className="meta-text">{project.created_at ? new Date(project.created_at).toLocaleDateString() : 'Recently updated'}</span>
                  </div>
                </Card>
              );
            })}
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
      <Dialog
        isOpen={deleteDialogOpen}
        title="Delete selected projects"
        message={`Delete ${selectedProjects.size} selected project${selectedProjects.size === 1 ? '' : 's'}? This cannot be undone.`}
        confirmText="Delete projects"
        onConfirm={() => {
          setDeleteDialogOpen(false);
          void handleDeleteSelected();
        }}
        onCancel={() => setDeleteDialogOpen(false)}
      />
    </div>
  );
};
