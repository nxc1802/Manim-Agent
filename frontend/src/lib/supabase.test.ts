import { afterEach, describe, expect, it, vi } from 'vitest';

const { createClient } = vi.hoisted(() => ({ createClient: vi.fn(() => ({ auth: {} })) }));

vi.mock('@supabase/supabase-js', () => ({ createClient }));

describe('frontend auth mode', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
    vi.resetModules();
  });

  it('boots with blank Supabase values when explicit local auth-off mode is enabled', async () => {
    vi.stubEnv('VITE_AUTH_MODE', 'off');
    vi.stubEnv('VITE_SUPABASE_URL', '');
    vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', '');
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '');
    vi.resetModules();

    const config = await import('./supabase');
    expect(config.isAuthDisabled).toBe(true);
    expect(config.hasSupabaseConfig).toBe(false);
    expect(config.supabase).toBeDefined();
    expect(createClient).toHaveBeenCalledWith(
      'http://127.0.0.1:54321',
      'local-auth-disabled-placeholder',
    );
  });

  it('prefers the current publishable key over the legacy anon key', async () => {
    vi.stubEnv('VITE_AUTH_MODE', 'jwt');
    vi.stubEnv('VITE_SUPABASE_URL', 'https://project.supabase.co');
    vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_current');
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'legacy-anon');
    vi.resetModules();

    const config = await import('./supabase');

    expect(config.hasSupabaseConfig).toBe(true);
    expect(createClient).toHaveBeenCalledWith(
      'https://project.supabase.co',
      'sb_publishable_current',
    );
  });
});
