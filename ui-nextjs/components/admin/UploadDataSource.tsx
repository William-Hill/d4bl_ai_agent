'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import UploadHistory from './UploadHistory';

export default function UploadDataSource() {
  const { session } = useAuth();
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [sourceName, setSourceName] = useState('');
  const [description, setDescription] = useState('');
  const [geographicLevel, setGeographicLevel] = useState('state');
  const [dataYear, setDataYear] = useState(() => new Date().getFullYear());
  const [sourceUrl, setSourceUrl] = useState('');
  const [categoryTags, setCategoryTags] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !session?.access_token) return;

    setLoading(true);
    setSuccess(null);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('source_name', sourceName);
      formData.append('description', description);
      formData.append('geographic_level', geographicLevel);
      formData.append('data_year', String(dataYear));
      if (sourceUrl) formData.append('source_url', sourceUrl);
      if (categoryTags) formData.append('category_tags', categoryTags);

      const resp = await fetch(`${API_BASE}/api/admin/uploads/datasource`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
        body: formData,
      });

      if (resp.ok) {
        setSuccess('Data source uploaded successfully. It will be reviewed before going live.');
        setFile(null);
        setSourceName('');
        setDescription('');
        setGeographicLevel('state');
        setDataYear(new Date().getFullYear());
        setSourceUrl('');
        setCategoryTags('');
        setRefreshKey((k) => k + 1);
      } else {
        const data = await resp.json().catch(() => ({}));
        setError(data.detail || 'Upload failed. Please try again.');
      }
    } catch {
      setError('Upload failed. Please check your connection and try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* File input */}
        <div>
          <label htmlFor="ds-file" className="block text-sm font-medium text-gray-300 mb-1">
            File <span className="text-red-400">*</span>
          </label>
          <input
            id="ds-file"
            type="file"
            accept=".csv,.xlsx"
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
          <p className="mt-1 text-xs text-gray-500">Accepted formats: .csv, .xlsx</p>
        </div>

        {/* Source name */}
        <div>
          <label htmlFor="ds-source-name" className="block text-sm font-medium text-gray-300 mb-1">
            Source Name <span className="text-red-400">*</span>
          </label>
          <input
            id="ds-source-name"
            type="text"
            value={sourceName}
            onChange={(e) => setSourceName(e.target.value)}
            required
            placeholder="e.g. CDC Health Outcomes 2023"
            className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
          />
        </div>

        {/* Description */}
        <div>
          <label htmlFor="ds-description" className="block text-sm font-medium text-gray-300 mb-1">
            Description <span className="text-red-400">*</span>
          </label>
          <textarea
            id="ds-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
            rows={3}
            placeholder="Describe the data source, what it contains, and how it should be used."
            className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors text-sm resize-none"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Geographic level */}
          <div>
            <label htmlFor="ds-geo-level" className="block text-sm font-medium text-gray-300 mb-1">
              Geographic Level <span className="text-red-400">*</span>
            </label>
            <select
              id="ds-geo-level"
              value={geographicLevel}
              onChange={(e) => setGeographicLevel(e.target.value)}
              required
              className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                         focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
            >
              <option value="state">State</option>
              <option value="county">County</option>
              <option value="tract">Tract</option>
            </select>
          </div>

          {/* Data year */}
          <div>
            <label htmlFor="ds-data-year" className="block text-sm font-medium text-gray-300 mb-1">
              Data Year <span className="text-red-400">*</span>
            </label>
            <input
              id="ds-data-year"
              type="number"
              value={dataYear}
              onChange={(e) => setDataYear(Number(e.target.value))}
              required
              min={1990}
              max={2030}
              className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                         focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
            />
          </div>
        </div>

        {/* Source URL (optional) */}
        <div>
          <label htmlFor="ds-source-url" className="block text-sm font-medium text-gray-300 mb-1">
            Source URL <span className="text-gray-500">(optional)</span>
          </label>
          <input
            id="ds-source-url"
            type="url"
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            placeholder="https://..."
            className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
          />
        </div>

        {/* Category tags (optional) */}
        <div>
          <label htmlFor="ds-tags" className="block text-sm font-medium text-gray-300 mb-1">
            Category Tags <span className="text-gray-500">(optional, comma-separated)</span>
          </label>
          <input
            id="ds-tags"
            type="text"
            value={categoryTags}
            onChange={(e) => setCategoryTags(e.target.value)}
            placeholder="e.g. health, housing, racial equity"
            className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
          />
        </div>

        <button
          type="submit"
          disabled={loading || !file}
          className="px-5 py-2 bg-[#00ff32] text-black font-semibold rounded
                     hover:bg-[#00cc28] disabled:opacity-50 transition-colors text-sm"
        >
          {loading ? 'Uploading...' : 'Upload Data Source'}
        </button>

        {success && <p className="text-sm text-green-400">{success}</p>}
        {error && <p className="text-sm text-red-400">{error}</p>}
      </form>

      <UploadHistory uploadType="datasource" refreshKey={refreshKey} />
    </div>
  );
}
