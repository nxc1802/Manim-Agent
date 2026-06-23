import { create } from 'zustand';
import type { Job } from '../types/api';

interface JobState {
  jobs: Job[];
  loading: boolean;
  error: string | null;
  fetchJobs: () => Promise<void>;
  updateJob: (job: Job) => void;
}

export const useJobStore = create<JobState>((set) => ({
  jobs: [],
  loading: false,
  error: null,

  fetchJobs: async () => {
    set({ loading: true, error: null });
    try {
      // For now, job listing is handled per project or recently, but let's keep it simple
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
