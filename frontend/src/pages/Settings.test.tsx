// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getSettings, updateSettings } = vi.hoisted(() => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
}));

vi.mock('../lib/api', () => ({
  api: { getSettings, updateSettings },
  applyTheme: vi.fn(),
}));

import { Settings } from './Settings';

const defaults = {
  theme: 'dark',
  language: 'en',
  hitl_enabled: true,
  ai_agent_persona: 'Professional Educator',
  template_selection: 'Educational',
  visual_review_enabled: true,
  code_review_enabled: true,
  max_review_attempts: 3,
  video_quality: '720p',
  fps: 30,
  llm_model: null,
  llm_temperature: null,
  llm_max_tokens: null,
  llm_agent_configs: {},
  tts_enabled: false,
  tts_voice: 'auto',
  tts_speaking_rate: 1,
  tts_pitch: 0,
} as const;

describe('Settings autosave', () => {
  beforeEach(() => {
    getSettings.mockReset();
    updateSettings.mockReset();
    getSettings.mockResolvedValue({ ...defaults });
    updateSettings.mockImplementation(async patch => ({ ...defaults, ...patch }));
  });

  it('persists a changed option immediately as a partial update', async () => {
    render(<Settings />);

    await screen.findByRole('heading', { name: 'Studio Settings' });
    fireEvent.click(screen.getByRole('button', { name: '60' }));

    await waitFor(() => expect(updateSettings).toHaveBeenCalledWith({ fps: 60 }));
    await screen.findByText('Changes save automatically.');
  });

  it('persists the global reviewer cap separately from tier retry counts', async () => {
    render(<Settings />);

    await screen.findByRole('heading', { name: 'Studio Settings' });
    fireEvent.click(screen.getAllByRole('tab', { name: 'Code review' }).at(-1)!);
    fireEvent.change(screen.getByLabelText('Global review attempt cap'), {
      target: { value: '5' },
    });

    await waitFor(() => expect(updateSettings).toHaveBeenCalledWith({ max_review_attempts: 5 }));
  });
});
