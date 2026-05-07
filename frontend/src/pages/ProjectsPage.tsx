import { useState, useEffect } from 'react';
import Sidebar from '../components/Sidebar';
import ProjectCard from '../components/ProjectCard';
import { Plus, Search, Filter, X, Sparkles, Layout, Video, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { projectService } from '../services/api';
import type { Project } from '../types/api';
import { useNavigate } from 'react-router-dom';

const ProjectsPage = () => {
  const [showModal, setShowModal] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetchProjects = async () => {
    try {
      const res = await projectService.getAll();
      const data = res?.data;
      setProjects(Array.isArray(data) ? data : (data as any)?.items || []);
    } catch (err) {
      console.error('Failed to fetch projects', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleProjectClick = async (projectId: string) => {
    try {
      const res = await projectService.getScenes(projectId);
      const data = res?.data;
      const scenes = Array.isArray(data) ? data : (data as any)?.items || [];
      if (scenes.length > 0) {
        navigate(`/editor/${scenes[0].id}`);
      } else {
        // If no scenes, create one? For now just alert
        alert('No scenes found for this project.');
      }
    } catch (err) {
      console.error('Failed to fetch scenes', err);
    }
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      
      <main style={{ marginLeft: '300px', padding: '40px 60px', width: '100%' }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '48px' }}>
          <div>
            <h1 style={{ fontSize: '2.5rem', marginBottom: '8px' }}>Projects</h1>
            <p style={{ color: 'var(--text-secondary)' }}>You have created {projects?.length || 0} projects in total.</p>
          </div>
          <button 
            onClick={() => setShowModal(true)}
            className="btn-primary" 
            style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '14px 24px' }}
          >
            <Plus size={20} />
            New Project
          </button>
        </header>

        <div style={{ display: 'flex', gap: '16px', marginBottom: '32px' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={18} style={{ position: 'absolute', left: '16px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
            <input
              type="text"
              placeholder="Search projects..."
              className="glass-input"
              style={{
                width: '100%',
                padding: '12px 16px 12px 48px',
                borderRadius: '12px',
                background: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid var(--surface-border)',
                color: 'white',
                outline: 'none'
              }}
            />
          </div>
          <button className="glass" style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '0 20px', borderRadius: '12px', border: '1px solid var(--surface-border)', color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <Filter size={18} />
            Filter
          </button>
        </div>

        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '100px' }}>
            <Loader2 className="spin" />
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '24px' }}>
            {projects?.map(p => (
              <div key={p.id} onClick={() => handleProjectClick(p.id)} style={{ cursor: 'pointer' }}>
                <ProjectCard 
                  title={p.title || 'Untitled Project'} 
                  status={p.status ? p.status.charAt(0).toUpperCase() + p.status.slice(1) : 'Unknown'} 
                  date={p.created_at ? new Date(p.created_at).toLocaleDateString() : 'Unknown'} 
                />
              </div>
            ))}
            {(!projects || projects.length === 0) && (
              <p style={{ color: 'var(--text-secondary)' }}>No projects found.</p>
            )}
          </div>
        )}
      </main>

      <AnimatePresence>
        {showModal && (
          <CreateProjectModal 
            onClose={() => setShowModal(false)} 
            onCreated={() => {
              setShowModal(false);
              fetchProjects();
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
};

const CreateProjectModal = ({ onClose, onCreated }: { onClose: () => void, onCreated: () => void }) => {
  const [step, setStep] = useState(1);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);

  const handleCreate = async () => {
    setLoading(true);
    try {
      console.log('Creating project...', { title, description });
      const res = await projectService.create({
        title,
        description,
        source_language: 'vi',
        target_scenes: 3
      });
      
      const projectId = res?.data?.id;
      if (!projectId) throw new Error('Project ID missing from response');

      console.log('Project created:', projectId);

      // Create initial scene (optional, don't crash if fails)
      try {
        await projectService.createScene(projectId, { scene_order: 0 });
      } catch (sceneErr) {
        console.warn('Failed to create initial scene, but project exists', sceneErr);
      }

      onCreated();
    } catch (err: any) {
      console.error('Failed to create project', err);
      alert(`Failed to create project: ${err.response?.data?.message || err.message}`);
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div style={{ 
      position: 'fixed', 
      top: 0, 
      left: 0, 
      right: 0, 
      bottom: 0, 
      background: 'rgba(0,0,0,0.8)', 
      backdropFilter: 'blur(8px)', 
      zIndex: 1000, 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center',
      padding: '20px'
    }}>
      <motion.div 
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        className="glass-card" 
        style={{ maxWidth: '600px', width: '100%', padding: '40px', position: 'relative' }}
      >
        <button 
          onClick={onClose} 
          style={{ position: 'absolute', top: '24px', right: '24px', background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
        >
          <X size={24} />
        </button>

        <div style={{ marginBottom: '32px' }}>
          <div style={{ display: 'flex', gap: '12px', marginBottom: '12px' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: step >= 1 ? 'var(--accent-primary)' : 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.9rem', fontWeight: 700 }}>1</div>
            <div style={{ flex: 1, height: '2px', background: 'rgba(255,255,255,0.1)', marginTop: '15px' }} />
            <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: step >= 2 ? 'var(--accent-primary)' : 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.9rem', fontWeight: 700 }}>2</div>
            <div style={{ flex: 1, height: '2px', background: 'rgba(255,255,255,0.1)', marginTop: '15px' }} />
            <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: step >= 3 ? 'var(--accent-primary)' : 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.9rem', fontWeight: 700 }}>3</div>
          </div>
          <h2 style={{ fontSize: '1.8rem' }}>
            {step === 1 && 'Basic Information'}
            {step === 2 && 'AI Configuration'}
            {step === 3 && 'Template Selection'}
          </h2>
        </div>

        {step === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Project Name</label>
              <input 
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="glass-input" 
                placeholder="e.g. Introduction to Quantum Computing" 
                style={{ padding: '14px', borderRadius: '12px', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--surface-border)', color: 'white' }} 
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Brief Description</label>
              <textarea 
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="glass-input" 
                placeholder="What is this video about?" 
                style={{ padding: '14px', borderRadius: '12px', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--surface-border)', color: 'white', minHeight: '100px', resize: 'vertical' }} 
              />
            </div>
          </div>
        )}

        {step === 2 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
             <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>AI Agent Persona</label>
              <select className="glass-input" style={{ padding: '14px', borderRadius: '12px', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--surface-border)', color: 'white' }}>
                <option>Professional Educator</option>
                <option>Creative Storyteller</option>
                <option>Technical Explainer</option>
              </select>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '16px', borderRadius: '12px', background: 'rgba(168, 85, 247, 0.05)', border: '1px solid rgba(168, 85, 247, 0.2)' }}>
              <Sparkles size={20} color="var(--accent-primary)" />
              <span style={{ fontSize: '0.9rem' }}>Smart orchestration will be enabled for this project.</span>
            </div>
          </div>
        )}

        {step === 3 && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <TemplateCard icon={<Layout size={20} />} title="Educational" desc="Optimized for concepts." />
            <TemplateCard icon={<Video size={20} />} title="Cinematic" desc="High visual impact." />
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '40px' }}>
          <button 
            onClick={() => step > 1 && setStep(step - 1)}
            disabled={step === 1}
            style={{ padding: '12px 24px', borderRadius: '12px', background: 'transparent', border: '1px solid var(--surface-border)', color: 'white', cursor: 'pointer', opacity: step === 1 ? 0.3 : 1 }}
          >
            Back
          </button>
          <button 
            onClick={() => {
              if (step < 3) setStep(step + 1);
              else handleCreate();
            }}
            className="btn-primary" 
            style={{ padding: '12px 32px' }}
            disabled={loading || (step === 1 && !title)}
          >
            {loading ? <Loader2 size={18} className="spin" /> : step === 3 ? 'Create Project' : 'Next Step'}
          </button>
        </div>
      </motion.div>
    </div>
  );
};

const TemplateCard = ({ icon, title, desc }: { icon: React.ReactNode, title: string, desc: string }) => (
  <div style={{ padding: '20px', borderRadius: '16px', border: '1px solid var(--surface-border)', background: 'rgba(255,255,255,0.02)', cursor: 'pointer', transition: 'var(--transition)' }}>
    <div style={{ marginBottom: '12px', color: 'var(--accent-primary)' }}>{icon}</div>
    <div style={{ fontWeight: 600, marginBottom: '4px' }}>{title}</div>
    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{desc}</div>
  </div>
);

export default ProjectsPage;
