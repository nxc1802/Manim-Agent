import { create } from 'zustand';
import { sceneService } from '../services/api';
import type { Scene } from '../types/api';

interface SceneState {
  currentScene: Scene | null;
  loading: boolean;
  error: string | null;
  fetchScene: (sceneId: string) => Promise<void>;
  updateSceneState: (scene: Scene) => void;
  generateStoryboard: (sceneId: string, briefOverride?: string) => Promise<void>;
  approveStoryboard: (sceneId: string) => Promise<void>;
  planBeats: (sceneId: string) => Promise<void>;
  approvePlan: (sceneId: string) => Promise<void>;
}

export const useSceneStore = create<SceneState>((set) => ({
  currentScene: null,
  loading: false,
  error: null,

  fetchScene: async (sceneId) => {
    set({ loading: true, error: null });
    try {
      const response = await sceneService.getById(sceneId);
      set({ currentScene: response.data, loading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch scene', loading: false });
    }
  },

  updateSceneState: (scene) => {
    set({ currentScene: scene });
  },

  generateStoryboard: async (sceneId, briefOverride) => {
    set({ loading: true, error: null });
    try {
      const response = await sceneService.generateStoryboard(sceneId, briefOverride);
      set({ currentScene: response.data, loading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to generate storyboard', loading: false });
    }
  },

  approveStoryboard: async (sceneId) => {
    set({ loading: true, error: null });
    try {
      const response = await sceneService.approveStoryboard(sceneId);
      set({ currentScene: response.data, loading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to approve storyboard', loading: false });
    }
  },

  planBeats: async (sceneId) => {
    set({ loading: true, error: null });
    try {
      const response = await sceneService.plan(sceneId);
      set({ currentScene: response.data, loading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to plan beats', loading: false });
    }
  },

  approvePlan: async (sceneId) => {
    set({ loading: true, error: null });
    try {
      const response = await sceneService.approvePlan(sceneId);
      set({ currentScene: response.data, loading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to approve plan', loading: false });
    }
  },
}));
