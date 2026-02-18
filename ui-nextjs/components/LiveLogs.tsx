'use client';

import { useEffect, useRef } from 'react';

interface LiveLogsProps {
  logs: string[];
}

export default function LiveLogs({ logs }: LiveLogsProps) {
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  if (!logs || logs.length === 0) {
    return null;
  }

  return (
    <div className="bg-[#333333] rounded-lg p-6 border border-[#404040]">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
        <span className="w-2 h-2 bg-[#00ff32] rounded-full mr-2 animate-pulse"></span>
        Live Agent Output
      </h3>
      <div className="bg-[#1a1a1a] rounded p-4 max-h-96 overflow-y-auto font-mono text-sm">
        <div className="space-y-1">
          {logs.map((log, index) => (
            <div
              key={index}
              className="text-gray-300 whitespace-pre-wrap break-words"
            >
              {log}
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      </div>
    </div>
  );
}

