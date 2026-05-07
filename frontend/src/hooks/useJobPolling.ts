import { useState, useEffect, useRef } from 'react';

interface PollingOptions<T> {
  fetchFn: () => Promise<any>;
  isCompleted: (data: T) => boolean;
  isFailed: (data: T) => boolean;
  interval?: number;
  timeout?: number;
  onSuccess?: (data: T) => void;
  onError?: (error: any) => void;
}

export function useJobPolling<T>({
  fetchFn,
  isCompleted,
  isFailed,
  interval = 3000,
  timeout = 300000,
  onSuccess,
  onError
}: PollingOptions<T>) {
  const [data, setData] = useState<T | null>(null);
  const [status, setStatus] = useState<'idle' | 'polling' | 'success' | 'error' | 'timeout'>('idle');
  const [error, setError] = useState<any>(null);
  
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const startPolling = () => {
    setStatus('polling');
    const startTime = Date.now();

    const poll = async () => {
      if (Date.now() - startTime > timeout) {
        setStatus('timeout');
        stopPolling();
        return;
      }

      try {
        const response = await fetchFn();
        const result = response.data;
        setData(result);

        if (isCompleted(result)) {
          setStatus('success');
          onSuccess?.(result);
          stopPolling();
        } else if (isFailed(result)) {
          setStatus('error');
          setError(result.error_code || 'Job failed');
          onError?.(result);
          stopPolling();
        }
      } catch (err) {
        setStatus('error');
        setError(err);
        onError?.(err);
        stopPolling();
      }
    };

    poll(); // Initial call
    intervalRef.current = setInterval(poll, interval);
  };

  const stopPolling = () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  };

  useEffect(() => {
    return () => stopPolling();
  }, []);

  return { data, status, error, startPolling, stopPolling };
}
