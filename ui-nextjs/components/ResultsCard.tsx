'use client';

import { useEffect, useRef } from 'react';

interface ResultsCardProps {
  results: any;
}

export default function ResultsCard({ results }: ResultsCardProps) {
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [results]);

  const formatMarkdown = (text: string) => {
    if (!text) return '';

    // Simple markdown to HTML conversion
    let html = text
      // Headers
      .replace(/^### (.*$)/gim, '<h3 class="text-xl font-semibold mt-4 mb-2 text-white">$1</h3>')
      .replace(/^## (.*$)/gim, '<h2 class="text-2xl font-semibold mt-6 mb-3 border-b border-[#404040] pb-2 text-white">$1</h2>')
      .replace(/^# (.*$)/gim, '<h1 class="text-3xl font-bold mt-8 mb-4 text-[#00ff32]">$1</h1>')
      // Bold
      .replace(/\*\*(.*?)\*\*/g, '<strong class="text-white font-semibold">$1</strong>')
      // Italic
      .replace(/\*(.*?)\*/g, '<em class="text-gray-300">$1</em>')
      // Links
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="text-[#00ff32] hover:text-[#00cc28] hover:underline font-medium transition-colors">$1</a>')
      // Code blocks
      .replace(/```([\s\S]*?)```/g, '<pre class="bg-[#1a1a1a] p-4 rounded overflow-x-auto my-4 border border-[#404040]"><code class="text-gray-200 text-sm">$1</code></pre>')
      // Inline code
      .replace(/`([^`]+)`/g, '<code class="bg-[#1a1a1a] px-1.5 py-0.5 rounded text-sm text-[#00ff32] border border-[#404040] font-mono">$1</code>')
      // Line breaks
      .replace(/\n\n/g, '</p><p class="mb-4 text-gray-300 leading-relaxed">')
      .replace(/\n/g, '<br>');

    // Wrap in paragraph
    html = '<p class="mb-4 text-gray-300 leading-relaxed">' + html + '</p>';

    // Lists
    html = html.replace(/^\- (.*$)/gim, '<li class="ml-4 mb-1 text-gray-300">$1</li>');
    html = html.replace(/(<li.*<\/li>)/s, '<ul class="list-disc ml-6 mb-4 text-gray-300">$1</ul>');

    return html;
  };

  return (
    <div ref={resultsRef} className="bg-[#333333] border border-[#404040] rounded-lg p-8 shadow-sm">
      <h2 className="text-2xl font-bold text-white mb-6">
        Research Results
      </h2>
      <div className="space-y-6">
        {results.report && (
          <div className="border-b border-[#404040] pb-6">
            <h3 className="text-xl font-bold text-[#00ff32] mb-4 border-b border-[#404040] pb-2">
              📄 Research Report
            </h3>
            <div
              className="prose max-w-none prose-invert"
              dangerouslySetInnerHTML={{ __html: formatMarkdown(results.report) }}
            />
          </div>
        )}

        {results.tasks_output && results.tasks_output.length > 0 && (
          <div className="space-y-4">
            {results.tasks_output.map((task: any, index: number) => (
              <div key={index} className="border-b border-[#404040] pb-4 last:border-b-0">
                <h3 className="text-lg font-bold text-[#00ff32] mb-3">
                  {task.agent || `Task ${index + 1}`}
                </h3>
                <pre className="bg-[#1a1a1a] p-4 rounded-md overflow-x-auto text-sm whitespace-pre-wrap text-gray-200 border border-[#404040]">
                  {task.output || 'No output available'}
                </pre>
              </div>
            ))}
          </div>
        )}

        {!results.report && (!results.tasks_output || results.tasks_output.length === 0) && (
          <div>
            <h3 className="text-lg font-bold text-[#00ff32] mb-3">
              Research Output
            </h3>
            <pre className="bg-[#1a1a1a] p-4 rounded-md overflow-x-auto text-sm whitespace-pre-wrap text-gray-200 border border-[#404040]">
              {results.raw_output || 'No output available'}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

