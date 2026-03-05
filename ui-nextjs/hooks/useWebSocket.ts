'use client';

import { useEffect, useRef, useState } from 'react';
import { WS_BASE } from '@/lib/api';

export function useWebSocket(jobId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<MessageEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!jobId) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setIsConnected(false);
      setLastMessage(null);
      return;
    }

    // Connect directly to the backend API (Next.js rewrites don't support WebSocket)
    const wsUrl = `${WS_BASE}/ws/${jobId}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      setLastMessage(event);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };

    ws.onclose = () => {
      setIsConnected(false);
      // Reconnect if job is still active
      if (jobId) {
        setTimeout(() => {
          if (jobId && !wsRef.current) {
            // Trigger reconnection by updating state
            setIsConnected(false);
          }
        }, 3000);
      }
    };

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [jobId]);

  return { isConnected, lastMessage };
}

