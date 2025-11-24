'use client';

import { useState, useEffect } from 'react';
import ResearchForm from '@/components/ResearchForm';
import ProgressCard from '@/components/ProgressCard';
import ResultsCard from '@/components/ResultsCard';
import ErrorCard from '@/components/ErrorCard';
import LiveLogs from '@/components/LiveLogs';
import JobHistory from '@/components/JobHistory';
import D4BLLogo from '@/components/D4BLLogo';
import { useWebSocket } from '@/hooks/useWebSocket';
import { createResearchJob, getJobStatus, JobStatus } from '@/lib/api';

export default function Home() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<any>(null);
  const [progress, setProgress] = useState<string>('');
  const [liveLogs, setLiveLogs] = useState<string[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true);

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

  const handleSelectJob = async (job: JobStatus) => {
    try {
      setError(null);
      setJobId(null);
      setProgress('');
      setLiveLogs([]);
      
      // If job is completed, show results
      if (job.status === 'completed' && job.result) {
        setResults(job.result);
        // Scroll main content area to top to show results
        setTimeout(() => {
          const mainContent = document.querySelector('[data-main-content]');
          mainContent?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
      } else if (job.status === 'error') {
        setError(job.error || 'Job failed');
      } else {
        // For running/pending jobs, fetch latest status
        const latestStatus = await getJobStatus(job.job_id);
        if (latestStatus.status === 'completed' && latestStatus.result) {
          setResults(latestStatus.result);
        } else if (latestStatus.status === 'error') {
          setError(latestStatus.error || 'Job failed');
        } else {
          // Job is still running, set it as current job
          setJobId(job.job_id);
          setProgress(latestStatus.progress || 'Processing...');
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load job details');
    }
  };

  const clearError = () => {
    setError(null);
  };

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="flex flex-col lg:flex-row h-screen">
        {/* Left Sidebar - Job History */}
        <aside 
          className={`${
            sidebarOpen ? 'w-full lg:w-80 xl:w-96' : 'w-0 lg:w-0'
          } bg-[#1a1a1a] border-r border-[#404040] flex flex-col overflow-hidden transition-all duration-300 ease-in-out`}
        >
          <div className={`${sidebarOpen ? 'flex' : 'hidden'} flex-col h-full`}>
            <div className="p-4 border-b border-[#404040] flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">Query History</h2>
              <button
                onClick={() => setSidebarOpen(false)}
                className="p-1.5 hover:bg-[#404040] rounded transition-colors"
                aria-label="Close sidebar"
              >
                <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <JobHistory onSelectJob={handleSelectJob} />
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <div className="flex-1 overflow-y-auto relative" data-main-content>
          {/* Sidebar Toggle Button */}
          {!sidebarOpen && (
            <button
              onClick={() => setSidebarOpen(true)}
              className="absolute top-4 left-4 z-10 p-2 bg-[#1a1a1a] hover:bg-[#2a2a2a] border border-[#404040] rounded-md transition-colors"
              aria-label="Open sidebar"
            >
              <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          )}
          <div className="max-w-5xl mx-auto px-4 py-8">
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

              {results && (
                <div data-results>
                  <ResultsCard results={results} />
                </div>
              )}

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
      </div>
    </div>
  );
}
