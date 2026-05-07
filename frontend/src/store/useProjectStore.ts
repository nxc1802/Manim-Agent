import { create } from 'zustand';
import { projectService } from '../services/api';
import type { Project, DashboardStats } from '../types/api';

interface ProjectState {
  projects: Project[];
  totalProjects: number;
  stats: DashboardStats | null;
  loading: boolean;
  error: string | null;
  fetchProjects: (page?: number, limit?: number) => Promise<void>;
  fetchStats: () => Promise<void>;
  createProject: (data: any) => Promise<Project>;
}

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  totalProjects: 0,
  stats: null,
  loading: false,
  error: null,

  fetchProjects: async (page = 1, limit = 10) => {
    set({ loading: true, error: null });
    try {
      const response = await projectService.getAll(page, limit);
      set({ 
        projects: response.data.items, 
        totalProjects: response.data.total, 
        loading: false 
      });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch projects', loading: false });
    }
  },

  fetchStats: async () => {
    try {
      const response = await projectService.getStats();
      set({ stats: response.data });
    } catch (err) {
      console.error('Failed to fetch stats', err);
    }
  },

  createProject: async (data) => {
    set({ loading: true, error: null });
    try {
      const response = await projectService.create(data);
      const project = response.data;
      set((state) => ({ projects: [project, ...state.projects], loading: false }));
      return project;
    } catch (err: any) {
      set({ error: err.message || 'Failed to create project', loading: false });
      throw err;
    }
  },
}));
