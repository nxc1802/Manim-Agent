import { create } from 'zustand';
import { jobService } from '../services/api';
import { RenderJob } from '../types/api';

interface JobState {
  jobs: RenderJob[];
  loading: boolean;
  error: string | null;
  fetchJobs: () => Promise<void>;
  updateJob: (job: RenderJob) => void;
}

export const useJobStore = create<JobState>((set) => ({
  jobs: [],
  loading: false,
  error: null,

  fetchJobs: async () => {
    set({ loading: true, error: null });
    try {
      // Assuming we want to fetch recent jobs, maybe add a list method to jobService if missing
      // For now, let's just keep it as a placeholder or use it for active jobs
      set({ loading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch jobs', loading: false });
    }
  },

  updateJob: (job) => {
    set((state) => ({
      jobs: state.jobs.map((j) => (j.id === job.id ? job : j)),
    }));
  },
}));
