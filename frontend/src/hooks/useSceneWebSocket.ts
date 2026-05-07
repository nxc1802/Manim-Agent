import { useState, useEffect } from 'react';
import { supabase } from '../services/supabase';
import type { PipelineEvent } from '../types/api';

export function useSceneWebSocket(sceneId: string | undefined) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<PipelineEvent | null>(null);

  useEffect(() => {
    if (!sceneId) return;

    console.log(`Subscribing to Supabase Realtime for scene: ${sceneId}`);

    const channel = supabase
      .channel(`scene_events:${sceneId}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'pipeline_events',
          filter: `scene_id=eq.${sceneId}`,
        },
        (payload) => {
          console.log('New pipeline event received:', payload.new);
          const newEvent = payload.new as PipelineEvent;
          setEvents((prev) => [...prev, newEvent]);
          setLastEvent(newEvent);
        }
      )
      .subscribe((status) => {
        console.log(`Supabase Realtime status: ${status}`);
        setIsConnected(status === 'SUBSCRIBED');
      });

    return () => {
      console.log(`Unsubscribing from Supabase Realtime for scene: ${sceneId}`);
      supabase.removeChannel(channel);
    };
  }, [sceneId]);

  const clearEvents = () => setEvents([]);

  return { events, isConnected, lastEvent, clearEvents };
}
