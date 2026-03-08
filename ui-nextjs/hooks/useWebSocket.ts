'use client';

import { useEffect, useRef, useState } from 'react';
import { WS_BASE, getAuthToken } from '@/lib/api';

export function useWebSocket(jobId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<MessageEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    let ws: WebSocket;

    async function connect() {
      const token = await getAuthToken();
      const wsUrl = token
        ? `${WS_BASE}/ws/${jobId}?token=${token}`
        : `${WS_BASE}/ws/${jobId}`;

      ws = new WebSocket(wsUrl);
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
    }

    connect();

    return () => {
      if (ws) {
        ws.close();
      }
      wsRef.current = null;
      setIsConnected(false);
      setLastMessage(null);
    };
  }, [jobId]);

  return { isConnected, lastMessage };
}
