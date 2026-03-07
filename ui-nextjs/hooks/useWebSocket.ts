'use client';

import { useEffect, useRef, useState } from 'react';
import { WS_BASE } from '@/lib/api';

export function useWebSocket(jobId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<MessageEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!jobId) {
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
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    return () => {
      ws.close();
      wsRef.current = null;
      setIsConnected(false);
      setLastMessage(null);
    };
  }, [jobId]);

  return { isConnected, lastMessage };
}

