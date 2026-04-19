'use client';

import { useRef, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import UploadHistory from './UploadHistory';

function formatUploadError(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      if (typeof d === 'string') return d;
      if (d && typeof d === 'object' && 'msg' in d) return String((d as { msg: unknown }).msg);
      return JSON.stringify(d);
    }).join('; ');
  }
  if (typeof detail === 'object') {
    const obj = detail as Record<string, unknown>;
    if (Array.isArray(obj.missing_columns)) {
      return `Missing columns in file header: ${(obj.missing_columns as string[]).join(', ')}`;
    }
    if (obj.dropped && typeof obj.dropped === 'object') {
      const d = obj.dropped as Record<string, unknown>;
      return `Too many invalid rows (${d.reason}): ${d.count} of ${d.total}`;
    }
    if (obj.reason === 'too_few_rows') {
      return `Only ${obj.valid} valid rows after validation — need at least 10.`;
    }
    if (obj.reason === 'no_data_rows') {
      return 'The file has a header but no data rows.';
    }
    if (typeof obj.message === 'string') return obj.message;
  }
  return JSON.stringify(detail);
}

export default function UploadDataSource() {
  const { session } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
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
  const [geoColumn, setGeoColumn] = useState('');
  const [metricValueColumn, setMetricValueColumn] = useState('');
  const [metricName, setMetricName] = useState('');
  const [hasRaceColumn, setHasRaceColumn] = useState(false);
  const [raceColumn, setRaceColumn] = useState('');
  const [hasYearColumn, setHasYearColumn] = useState(false);
  const [yearColumn, setYearColumn] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session?.access_token) {
      setError('Session expired. Please sign in again.');
      return;
    }
    if (!file) return;

    setLoading(true);
    setSuccess(null);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('source_name', sourceName);
      formData.append('description', description);
      formData.append('geographic_level', geographicLevel);
      if (!hasYearColumn) {
        formData.append('data_year', String(dataYear));
      }
      formData.append('geo_column', geoColumn);
      formData.append('metric_value_column', metricValueColumn);
      formData.append('metric_name', metricName);
      if (hasRaceColumn && raceColumn) formData.append('race_column', raceColumn);
      if (hasYearColumn && yearColumn) formData.append('year_column', yearColumn);
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
        if (fileInputRef.current) fileInputRef.current.value = '';
        setSourceName('');
        setDescription('');
        setGeographicLevel('state');
        setDataYear(new Date().getFullYear());
        setSourceUrl('');
        setCategoryTags('');
        setGeoColumn('');
        setMetricValueColumn('');
        setMetricName('');
        setHasRaceColumn(false);
        setRaceColumn('');
        setHasYearColumn(false);
        setYearColumn('');
        setRefreshKey((k) => k + 1);
      } else {
        const data = await resp.json().catch(() => ({}));
        setError(formatUploadError(data.detail) || 'Upload failed. Please try again.');
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
            ref={fileInputRef}
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

          {/* Data year (constant) — omitted when a per-row year column is mapped */}
          {!hasYearColumn ? (
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
                max={new Date().getFullYear() + 1}
                className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                           focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
              />
            </div>
          ) : (
            <div className="flex items-end pb-2 text-xs text-gray-500">
              Year values come from the year column below (no single constant year).
            </div>
          )}
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

        <div className="pt-3 border-t border-[#404040]">
          <h3 className="text-sm font-semibold text-white mb-2">Column mapping</h3>
          <p className="text-xs text-gray-500 mb-3">
            Tell the admin which column means what. Missing or incorrect mappings
            show up as an error immediately.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="ds-geo-column" className="block text-sm font-medium text-gray-300 mb-1">
                Geo column name <span className="text-red-400">*</span>
              </label>
              <input
                id="ds-geo-column"
                type="text"
                value={geoColumn}
                onChange={(e) => setGeoColumn(e.target.value)}
                required
                placeholder="e.g. county_fips"
                className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                           focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
              />
              <p className="mt-1 text-xs text-gray-500">
                State (2-digit), county (5-digit), or tract (11-digit) FIPS code column.
              </p>
            </div>

            <div>
              <label htmlFor="ds-metric-value-column" className="block text-sm font-medium text-gray-300 mb-1">
                Metric value column <span className="text-red-400">*</span>
              </label>
              <input
                id="ds-metric-value-column"
                type="text"
                value={metricValueColumn}
                onChange={(e) => setMetricValueColumn(e.target.value)}
                required
                placeholder="e.g. filing_rate"
                className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                           focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
              />
              <p className="mt-1 text-xs text-gray-500">
                The numeric column to plot on the map.
              </p>
            </div>
          </div>

          <div className="mt-4">
            <label htmlFor="ds-metric-name" className="block text-sm font-medium text-gray-300 mb-1">
              Metric name <span className="text-red-400">*</span>
            </label>
            <input
              id="ds-metric-name"
              type="text"
              value={metricName}
              onChange={(e) => setMetricName(e.target.value)}
              required
              pattern="[a-z0-9_]{1,64}"
              placeholder="e.g. eviction_filing_rate"
              className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                         focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
            />
            <p className="mt-1 text-xs text-gray-500">
              Lowercase, snake_case, 1–64 chars. Becomes the metric identifier on /explore.
            </p>
          </div>

          <div className="mt-4 space-y-3">
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={hasRaceColumn}
                onChange={(e) => setHasRaceColumn(e.target.checked)}
              />
              This dataset has a racial/ethnic breakdown column
            </label>
            {hasRaceColumn && (
              <div>
                <label htmlFor="ds-race-column" className="block text-sm font-medium text-gray-300 mb-1">
                  Race/ethnicity column <span className="text-red-400">*</span>
                </label>
                <input
                  id="ds-race-column"
                  type="text"
                  value={raceColumn}
                  onChange={(e) => setRaceColumn(e.target.value)}
                  required
                  placeholder="e.g. race"
                  className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                             focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
                />
              </div>
            )}

            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={hasYearColumn}
                onChange={(e) => setHasYearColumn(e.target.checked)}
              />
              This dataset has a year column
            </label>
            {hasYearColumn && (
              <div>
                <label htmlFor="ds-year-column" className="block text-sm font-medium text-gray-300 mb-1">
                  Year column <span className="text-red-400">*</span>
                </label>
                <input
                  id="ds-year-column"
                  type="text"
                  value={yearColumn}
                  onChange={(e) => setYearColumn(e.target.value)}
                  required
                  placeholder="e.g. year"
                  className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                             focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
                />
              </div>
            )}
          </div>
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
