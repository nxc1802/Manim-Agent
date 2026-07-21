import { createClient } from '@supabase/supabase-js';

const configuredUrl = (import.meta.env.VITE_SUPABASE_URL || '').trim();
const configuredPublishableKey = (
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
  || import.meta.env.VITE_SUPABASE_ANON_KEY
  || ''
).trim();

export const frontendAuthMode = (import.meta.env.VITE_AUTH_MODE || 'jwt').trim().toLowerCase();
export const isAuthDisabled = frontendAuthMode === 'off';
export const hasSupabaseConfig = Boolean(configuredUrl && configuredPublishableKey);

// Supabase validates its constructor arguments eagerly. A local Backend running
// with AUTH_MODE=off must therefore still be able to boot the frontend without
// copying cloud credentials into a development machine. The placeholder client
// is never contacted while VITE_AUTH_MODE=off.
const supabaseUrl = configuredUrl || 'http://127.0.0.1:54321';
const supabasePublishableKey = configuredPublishableKey || 'local-auth-disabled-placeholder';

export const supabase = createClient(supabaseUrl, supabasePublishableKey);
