import { useState, useEffect } from 'react';
import { supabase } from '../services/supabase';
import type { User } from '@supabase/supabase-js';

export const useAuth = () => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check for "Guest" session in localStorage for dev testing
    const guestUser = localStorage.getItem('manim_guest_user');
    if (guestUser) {
      setUser(JSON.parse(guestUser));
      setLoading(false);
    }

    // Real Supabase session check
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        setUser(session.user);
      }
      setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        setUser(session.user);
      } else {
        // If not a guest, clear user
        if (!localStorage.getItem('manim_guest_user')) {
          setUser(null);
        }
      }
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  const signOut = async () => {
    localStorage.removeItem('manim_guest_user');
    await supabase.auth.signOut();
    setUser(null);
  };

  return { user, loading, signOut };
};
