'use client';

import { useState, useEffect } from 'react';
import ResearchForm from '@/components/ResearchForm';
import ProgressCard from '@/components/ProgressCard';
import ResultsCard from '@/components/ResultsCard';
import ErrorCard from '@/components/ErrorCard';
import LiveLogs from '@/components/LiveLogs';
import D4BLLogo from '@/components/D4BLLogo';
import { useWebSocket } from '@/hooks/useWebSocket';
import { createResearchJob, getJobStatus } from '@/lib/api';

export default function Home() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<any>(null);
  const [progress, setProgress] = useState<string>('');
  const [liveLogs, setLiveLogs] = useState<string[]>([]);

  const { isConnected, lastMessage } = useWebSocket(jobId);

  // Handle WebSocket messages
  useEffect(() => {
    if (lastMessage) {
      try {
        const data = JSON.parse(lastMessage.data);
        console.log('WebSocket message received:', data);
        
        if (data.type === 'log') {
          // Append new log message
          setLiveLogs(prev => [...prev, data.message]);
        } else if (data.type === 'progress' || data.type === 'status') {
          setProgress(data.progress || 'Processing...');
          // Initialize logs if provided
          if (data.logs && Array.isArray(data.logs)) {
            setLiveLogs(data.logs);
          }
        } else if (data.type === 'complete') {
          setProgress('Research completed!');
          setResults(data.result);
          // Keep logs from completion message
          if (data.logs && Array.isArray(data.logs)) {
            setLiveLogs(data.logs);
          }
          setJobId(null);
        } else if (data.type === 'error') {
          setError(data.error || 'An error occurred during research');
          // Keep logs from error message
          if (data.logs && Array.isArray(data.logs)) {
            setLiveLogs(data.logs);
          }
          setJobId(null);
        }
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    }
  }, [lastMessage]);

  // Fallback: Poll job status if WebSocket is not connected
  useEffect(() => {
    if (jobId && !isConnected) {
      const pollInterval = setInterval(async () => {
        try {
          const status = await getJobStatus(jobId);
          if (status.status === 'completed') {
            setProgress('Research completed!');
            setResults(status.result);
            setJobId(null);
            clearInterval(pollInterval);
          } else if (status.status === 'error') {
            setError(status.error || 'An error occurred during research');
            setJobId(null);
            clearInterval(pollInterval);
          } else if (status.progress) {
            setProgress(status.progress);
          }
        } catch (err) {
          console.error('Error polling job status:', err);
        }
      }, 2000); // Poll every 2 seconds

      return () => clearInterval(pollInterval);
    }
  }, [jobId, isConnected]);

  const handleSubmit = async (query: string, summaryFormat: string) => {
    try {
      setError(null);
      setResults(null);
      setProgress('Creating research job...');
      setLiveLogs([]); // Clear previous logs

      const response = await createResearchJob(query, summaryFormat);
      setJobId(response.job_id);
      setProgress('Job created, starting research...');
    } catch (err: any) {
      setError(err.message || 'Failed to create research job');
      setJobId(null);
      setLiveLogs([]);
    }
  };

  const clearError = () => {
    setError(null);
  };

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <header className="text-center mb-12">
          <div className="flex justify-center mb-8">
            <D4BLLogo />
          </div>
          <div className="mb-6">
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-3 tracking-tight">
              AI Research & Analysis Tool
            </h1>
            <div className="w-24 h-1 bg-[#00ff32] mx-auto mb-4"></div>
          </div>
          <p className="text-lg text-gray-300 max-w-2xl mx-auto leading-relaxed">
            Using data to create concrete and measurable change in the lives of Black people
          </p>
        </header>

        <main className="space-y-6">
          <ResearchForm onSubmit={handleSubmit} disabled={!!jobId} />

          {jobId && (
            <>
              <ProgressCard
                progress={progress}
                isConnected={isConnected}
              />
              <LiveLogs logs={liveLogs} />
            </>
          )}

          {results && <ResultsCard results={results} />}

          {error && <ErrorCard message={error} onDismiss={clearError} />}
        </main>

        <footer className="mt-16 pt-8 border-t border-[#404040]">
          <div className="text-center space-y-4">
            <p className="text-sm text-gray-400">
              Part of the <span className="font-semibold text-[#00ff32]">Data for Black Lives</span> movement
            </p>
            <p className="text-xs text-gray-500">
              Powered by CrewAI & Ollama
            </p>
            <div className="flex justify-center space-x-6 mt-6">
              <a 
                href="https://d4bl.org" 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-sm text-gray-400 hover:text-[#00ff32] transition-colors"
              >
                Visit d4bl.org
              </a>
              <span className="text-gray-600">|</span>
              <a 
                href="https://d4bl.org/get-involved" 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-sm text-gray-400 hover:text-[#00ff32] transition-colors"
              >
                Get Involved
              </a>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}
