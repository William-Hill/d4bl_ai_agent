'use client';

import { useEffect, useRef, useState } from 'react';

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
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const wsProtocol = apiUrl.startsWith('https') ? 'wss:' : 'ws:';
    const wsHost = apiUrl.replace(/^https?:\/\//, ''); // Remove http:// or https://
    const wsUrl = `${wsProtocol}//${wsHost}/ws/${jobId}`;

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

