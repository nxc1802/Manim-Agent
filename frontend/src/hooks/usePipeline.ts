import { useEffect, useState, useCallback } from 'react';

interface PipelineEvent {
  ts: string;
  component: string;
  phase: string;
  message: string;
  scene_id: string;
}

export const usePipeline = (sceneId: string | null) => {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [status, setStatus] = useState<'idle' | 'connecting' | 'connected' | 'error'>('idle');

  const connect = useCallback(() => {
    if (!sceneId) return;

    const token = localStorage.getItem('supabase_token');
    const wsUrl = `${import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000/v1'}/ws/${sceneId}${token ? `?token=${token}` : ''}`;
    
    setStatus('connecting');
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => setStatus('connected');
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data === 'pong') return;
        setEvents((prev) => [...prev, data]);
      } catch (err) {
        console.error('Failed to parse WS message:', err);
      }
    };
    ws.onerror = () => setStatus('error');
    ws.onclose = () => setStatus('idle');

    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      ws.close();
    };
  }, [sceneId]);

  useEffect(() => {
    const cleanup = connect();
    return () => cleanup && cleanup();
  }, [connect]);

  return { events, status };
};
