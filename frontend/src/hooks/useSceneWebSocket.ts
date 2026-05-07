import { useState, useEffect, useRef, useCallback } from 'react';
import { supabase } from '../services/supabase';
import type { PipelineEvent } from '../types/api';

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000/v1/ws';

export function useSceneWebSocket(sceneId: string | undefined) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<PipelineEvent | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(async () => {
    if (!sceneId) return;
    
    // Get fresh token
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    
    if (!token) return;

    const url = `${WS_BASE_URL}/${sceneId}?token=${token}`;
    const socket = new WebSocket(url);

    socket.onopen = () => {
      console.log('WS Connected');
      setIsConnected(true);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };

    socket.onmessage = (event) => {
      if (event.data === 'pong') return;
      
      try {
        const data: PipelineEvent = JSON.parse(event.data);
        setEvents((prev) => [...prev, data]);
        setLastEvent(data);
      } catch (err) {
        console.error('Failed to parse WS message', err);
      }
    };

    socket.onclose = () => {
      console.log('WS Disconnected');
      setIsConnected(false);
      // Simple reconnect
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    };

    socket.onerror = (err) => {
      console.error('WS Error', err);
      socket.close();
    };

    socketRef.current = socket;

    // Heartbeat
    const pingInterval = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send('ping');
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      socket.close();
    };
  }, [sceneId]);

  useEffect(() => {
    connect();
    return () => {
      if (socketRef.current) socketRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };
  }, [connect]);

  const clearEvents = () => setEvents([]);

  return { events, isConnected, lastEvent, clearEvents };
}
