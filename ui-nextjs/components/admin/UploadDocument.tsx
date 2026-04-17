'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import UploadHistory from './UploadHistory';

type InputMode = 'file' | 'url';

export default function UploadDocument() {
  const { session } = useAuth();
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [mode, setMode] = useState<InputMode>('file');
  const [file, setFile] = useState<File | null>(null);
  const [urlInput, setUrlInput] = useState('');
  const [title, setTitle] = useState('');
  const [documentType, setDocumentType] = useState('report');
  const [topicTags, setTopicTags] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session?.access_token) return;
    if (mode === 'file' && !file) return;
    if (mode === 'url' && !urlInput) return;

    setLoading(true);
    setSuccess(null);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('title', title);
      formData.append('document_type', documentType);
      if (topicTags) formData.append('topic_tags', topicTags);

      if (mode === 'file' && file) {
        formData.append('file', file);
      } else {
        formData.append('source_url', urlInput);
      }

      const resp = await fetch(`${API_BASE}/api/admin/uploads/document`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
        body: formData,
      });

      if (resp.ok) {
        setSuccess('Document submitted successfully. It will be reviewed before going live.');
        setFile(null);
        setUrlInput('');
        setTitle('');
        setDocumentType('report');
        setTopicTags('');
        setRefreshKey((k) => k + 1);
      } else {
        const data = await resp.json().catch(() => ({}));
        setError(data.detail || 'Submission failed. Please try again.');
      }
    } catch {
      setError('Submission failed. Please check your connection and try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Mode toggle */}
        <div>
          <span className="block text-sm font-medium text-gray-300 mb-2">Input Method</span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setMode('file')}
              className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                mode === 'file'
                  ? 'bg-[#00ff32] text-black'
                  : 'bg-[#404040] text-gray-300 hover:bg-[#505050]'
              }`}
            >
              Upload File
            </button>
            <button
              type="button"
              onClick={() => setMode('url')}
              className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                mode === 'url'
                  ? 'bg-[#00ff32] text-black'
                  : 'bg-[#404040] text-gray-300 hover:bg-[#505050]'
              }`}
            >
              Submit URL
            </button>
          </div>
        </div>

        {/* File or URL input */}
        {mode === 'file' ? (
          <div>
            <label htmlFor="doc-file" className="block text-sm font-medium text-gray-300 mb-1">
              File <span className="text-red-400">*</span>
            </label>
            <input
              id="doc-file"
              type="file"
              accept=".pdf,.docx"
              required
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-gray-300
                         file:mr-3 file:py-1.5 file:px-3
                         file:rounded file:border-0
                         file:text-sm file:font-medium
                         file:bg-[#404040] file:text-white
                         hover:file:bg-[#505050]
                         file:cursor-pointer cursor-pointer"
            />
            <p className="mt-1 text-xs text-gray-500">Accepted formats: .pdf, .docx</p>
          </div>
        ) : (
          <div>
            <label htmlFor="doc-url" className="block text-sm font-medium text-gray-300 mb-1">
              Document URL <span className="text-red-400">*</span>
            </label>
            <input
              id="doc-url"
              type="url"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              required
              placeholder="https://..."
              className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                         focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
            />
          </div>
        )}

        {/* Title */}
        <div>
          <label htmlFor="doc-title" className="block text-sm font-medium text-gray-300 mb-1">
            Title <span className="text-red-400">*</span>
          </label>
          <input
            id="doc-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="e.g. 2023 State of Housing Equity Report"
            className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
          />
        </div>

        {/* Document type */}
        <div>
          <label htmlFor="doc-type" className="block text-sm font-medium text-gray-300 mb-1">
            Document Type <span className="text-red-400">*</span>
          </label>
          <select
            id="doc-type"
            value={documentType}
            onChange={(e) => setDocumentType(e.target.value)}
            required
            className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
          >
            <option value="report">Report</option>
            <option value="article">Article</option>
            <option value="policy_brief">Policy Brief</option>
            <option value="other">Other</option>
          </select>
        </div>

        {/* Topic tags (optional) */}
        <div>
          <label htmlFor="doc-tags" className="block text-sm font-medium text-gray-300 mb-1">
            Topic Tags <span className="text-gray-500">(optional, comma-separated)</span>
          </label>
          <input
            id="doc-tags"
            type="text"
            value={topicTags}
            onChange={(e) => setTopicTags(e.target.value)}
            placeholder="e.g. housing, health disparities, criminal justice"
            className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
          />
        </div>

        <button
          type="submit"
          disabled={loading || (mode === 'file' && !file) || (mode === 'url' && !urlInput)}
          className="px-5 py-2 bg-[#00ff32] text-black font-semibold rounded
                     hover:bg-[#00cc28] disabled:opacity-50 transition-colors text-sm"
        >
          {loading ? 'Submitting...' : 'Submit Document'}
        </button>

        {success && <p className="text-sm text-green-400">{success}</p>}
        {error && <p className="text-sm text-red-400">{error}</p>}
      </form>

      <UploadHistory uploadType="document" refreshKey={refreshKey} />
    </div>
  );
}
