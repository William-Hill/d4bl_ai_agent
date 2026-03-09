'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import CronBuilder from '@/components/data/CronBuilder';

type SourceType = 'api' | 'file_upload' | 'web_scrape' | 'rss_feed' | 'database' | 'mcp';

const SOURCE_TYPES: { type: SourceType; label: string; description: string }[] = [
  { type: 'api', label: 'API', description: 'Connect to REST APIs' },
  { type: 'file_upload', label: 'File Upload', description: 'Upload CSV, Excel, or JSON' },
  { type: 'web_scrape', label: 'Web Scrape', description: 'Crawl web pages' },
  { type: 'rss_feed', label: 'RSS Feed', description: 'Monitor RSS/Atom feeds' },
  { type: 'database', label: 'Database', description: 'Connect to external databases' },
  { type: 'mcp', label: 'MCP', description: 'Model Context Protocol sources' },
];

const STEPS = ['Source Type', 'Configuration', 'Schedule', 'Review'];

interface FormConfig {
  name: string;
  // api
  url?: string;
  method?: string;
  headers?: string;
  response_path?: string;
  // web_scrape
  urls?: string;
  depth?: number;
  css_selectors?: string;
  // rss_feed
  feed_url?: string;
  // database
  connection_string?: string;
  query?: string;
  // mcp
  server_name?: string;
  tool_name?: string;
  tool_params?: string;
}

export default function SourceWizard() {
  const router = useRouter();
  const { session } = useAuth();
  const [step, setStep] = useState(0);
  const [sourceType, setSourceType] = useState<SourceType | null>(null);
  const [config, setConfig] = useState<FormConfig>({ name: '' });
  const [schedule, setSchedule] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jsonErrors, setJsonErrors] = useState<{ headers: string | null; tool_params: string | null }>({
    headers: null,
    tool_params: null,
  });

  const updateConfig = (field: string, value: string | number) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
    if (field === 'headers' || field === 'tool_params') {
      const str = String(value).trim();
      const label = field === 'headers' ? 'Headers' : 'Tool Params';
      setJsonErrors((prev) => ({
        ...prev,
        [field]: !str ? null : (() => { try { JSON.parse(str); return null; } catch { return `Invalid JSON in ${label}`; } })(),
      }));
    }
  };

  const canProceed = (): boolean => {
    if (step === 0) return sourceType !== null;
    if (step === 1) {
      if (!config.name.trim()) return false;
      if (sourceType === 'api' && jsonErrors.headers) return false;
      if (sourceType === 'mcp' && jsonErrors.tool_params) return false;
      if (sourceType === 'api' && !config.url?.trim()) return false;
      if (sourceType === 'rss_feed' && !config.feed_url?.trim()) return false;
      if (sourceType === 'database' && !config.connection_string?.trim()) return false;
      if (sourceType === 'web_scrape' && !config.urls?.trim()) return false;
      return true;
    }
    return true;
  };

  const buildPayload = () => {
    const typeConfig: Record<string, unknown> = {};

    if (sourceType === 'api') {
      if (config.url) typeConfig.url = config.url;
      if (config.method) typeConfig.method = config.method;
      if (config.headers) {
        try { typeConfig.headers = JSON.parse(config.headers); } catch { /* validated in canProceed */ }
      }
      if (config.response_path) typeConfig.response_path = config.response_path;
    } else if (sourceType === 'web_scrape') {
      if (config.urls) typeConfig.urls = config.urls.split('\n').map((u) => u.trim()).filter(Boolean);
      if (config.depth != null) typeConfig.depth = config.depth;
      if (config.css_selectors) typeConfig.css_selectors = config.css_selectors;
    } else if (sourceType === 'rss_feed') {
      if (config.feed_url) typeConfig.feed_url = config.feed_url;
    } else if (sourceType === 'database') {
      if (config.connection_string) typeConfig.connection_string = config.connection_string;
      if (config.query) typeConfig.query = config.query;
    } else if (sourceType === 'mcp') {
      if (config.server_name) typeConfig.server_name = config.server_name;
      if (config.tool_name) typeConfig.tool_name = config.tool_name;
      if (config.tool_params) {
        try { typeConfig.tool_params = JSON.parse(config.tool_params); } catch { /* validated in canProceed */ }
      }
    }

    return {
      name: config.name.trim(),
      source_type: sourceType,
      config: typeConfig,
      default_schedule: schedule,
      enabled: true,
    };
  };

  const handleCreate = async () => {
    if (!session?.access_token) return;
    setSubmitting(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/data/sources`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(buildPayload()),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }

      router.push('/data/sources');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create source');
    } finally {
      setSubmitting(false);
    }
  };

  const renderStepIndicator = () => (
    <div className="flex items-center justify-center mb-8">
      {STEPS.map((label, i) => (
        <div key={label} className="flex items-center">
          <div className="flex flex-col items-center">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium border transition-colors ${
                i < step
                  ? 'bg-[#00ff32]/20 border-[#00ff32] text-[#00ff32]'
                  : i === step
                  ? 'bg-[#00ff32] border-[#00ff32] text-black'
                  : 'bg-[#1a1a1a] border-[#404040] text-gray-500'
              }`}
            >
              {i < step ? '\u2713' : i + 1}
            </div>
            <span className={`text-xs mt-1 ${i === step ? 'text-white' : 'text-gray-500'}`}>
              {label}
            </span>
          </div>
          {i < STEPS.length - 1 && (
            <div
              className={`w-12 h-0.5 mx-2 mb-5 ${
                i < step ? 'bg-[#00ff32]' : 'bg-[#404040]'
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );

  const renderStep0 = () => (
    <div>
      <h2 className="text-lg font-semibold text-white mb-4">Select Source Type</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {SOURCE_TYPES.map((st) => (
          <button
            key={st.type}
            type="button"
            onClick={() => setSourceType(st.type)}
            className={`p-4 rounded-lg border text-left transition-colors ${
              sourceType === st.type
                ? 'border-[#00ff32] bg-[#00ff32]/10'
                : 'border-[#404040] bg-[#1a1a1a] hover:border-gray-500'
            }`}
          >
            <span className="block text-sm font-medium text-white">{st.label}</span>
            <span className="block text-xs text-gray-400 mt-1">{st.description}</span>
          </button>
        ))}
      </div>
    </div>
  );

  const inputClass =
    'w-full px-3 py-2 bg-[#1a1a1a] border border-[#404040] rounded text-white text-sm placeholder-gray-600 focus:border-[#00ff32] focus:outline-none';
  const labelClass = 'block text-sm text-gray-400 mb-1';

  const renderStep1 = () => (
    <div>
      <h2 className="text-lg font-semibold text-white mb-4">Configuration</h2>
      <div className="space-y-4">
        <div>
          <label htmlFor="source-name" className={labelClass}>Name *</label>
          <input
            id="source-name"
            type="text"
            value={config.name}
            onChange={(e) => updateConfig('name', e.target.value)}
            placeholder="My data source"
            className={inputClass}
          />
        </div>

        {sourceType === 'api' && (
          <>
            <div>
              <label htmlFor="source-url" className={labelClass}>URL</label>
              <input
                id="source-url"
                type="text"
                value={config.url ?? ''}
                onChange={(e) => updateConfig('url', e.target.value)}
                placeholder="https://api.example.com/data"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="source-method" className={labelClass}>Method</label>
              <select
                id="source-method"
                value={config.method ?? 'GET'}
                onChange={(e) => updateConfig('method', e.target.value)}
                className={inputClass}
              >
                <option value="GET">GET</option>
                <option value="POST">POST</option>
              </select>
            </div>
            <div>
              <label htmlFor="source-headers" className={labelClass}>Headers (JSON)</label>
              <textarea
                id="source-headers"
                value={config.headers ?? ''}
                onChange={(e) => updateConfig('headers', e.target.value)}
                placeholder='{"Authorization": "Bearer ..."}'
                rows={3}
                className={inputClass}
              />
              {jsonErrors.headers && config.headers?.trim() && (
                <p className="text-red-400 text-xs mt-1">{jsonErrors.headers}</p>
              )}
            </div>
            <div>
              <label htmlFor="source-response-path" className={labelClass}>Response Path (JSONPath)</label>
              <input
                id="source-response-path"
                type="text"
                value={config.response_path ?? ''}
                onChange={(e) => updateConfig('response_path', e.target.value)}
                placeholder="$.data.results"
                className={inputClass}
              />
            </div>
          </>
        )}

        {sourceType === 'file_upload' && (
          <p className="text-gray-500 text-sm">
            Files can be uploaded after the source is created.
          </p>
        )}

        {sourceType === 'web_scrape' && (
          <>
            <div>
              <label htmlFor="source-urls" className={labelClass}>URLs (one per line)</label>
              <textarea
                id="source-urls"
                value={config.urls ?? ''}
                onChange={(e) => updateConfig('urls', e.target.value)}
                placeholder={'https://example.com/page1\nhttps://example.com/page2'}
                rows={4}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="source-depth" className={labelClass}>Depth</label>
              <input
                id="source-depth"
                type="number"
                value={config.depth ?? 1}
                onChange={(e) => updateConfig('depth', parseInt(e.target.value) || 0)}
                min={0}
                max={10}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="source-css-selectors" className={labelClass}>CSS Selectors</label>
              <input
                id="source-css-selectors"
                type="text"
                value={config.css_selectors ?? ''}
                onChange={(e) => updateConfig('css_selectors', e.target.value)}
                placeholder="article, .content"
                className={inputClass}
              />
            </div>
          </>
        )}

        {sourceType === 'rss_feed' && (
          <div>
            <label htmlFor="source-feed-url" className={labelClass}>Feed URL</label>
            <input
              id="source-feed-url"
              type="text"
              value={config.feed_url ?? ''}
              onChange={(e) => updateConfig('feed_url', e.target.value)}
              placeholder="https://example.com/feed.xml"
              className={inputClass}
            />
          </div>
        )}

        {sourceType === 'database' && (
          <>
            <div>
              <label htmlFor="source-connection-string" className={labelClass}>Connection String</label>
              <input
                id="source-connection-string"
                type="text"
                value={config.connection_string ?? ''}
                onChange={(e) => updateConfig('connection_string', e.target.value)}
                placeholder="postgresql://user:pass@host:5432/db"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="source-query" className={labelClass}>Query</label>
              <textarea
                id="source-query"
                value={config.query ?? ''}
                onChange={(e) => updateConfig('query', e.target.value)}
                placeholder="SELECT * FROM table LIMIT 1000"
                rows={3}
                className={inputClass}
              />
            </div>
          </>
        )}

        {sourceType === 'mcp' && (
          <>
            <div>
              <label htmlFor="source-server-name" className={labelClass}>Server Name</label>
              <input
                id="source-server-name"
                type="text"
                value={config.server_name ?? ''}
                onChange={(e) => updateConfig('server_name', e.target.value)}
                placeholder="my-mcp-server"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="source-tool-name" className={labelClass}>Tool Name</label>
              <input
                id="source-tool-name"
                type="text"
                value={config.tool_name ?? ''}
                onChange={(e) => updateConfig('tool_name', e.target.value)}
                placeholder="fetch_data"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="source-tool-params" className={labelClass}>Tool Params (JSON)</label>
              <textarea
                id="source-tool-params"
                value={config.tool_params ?? ''}
                onChange={(e) => updateConfig('tool_params', e.target.value)}
                placeholder='{"param1": "value1"}'
                rows={3}
                className={inputClass}
              />
              {jsonErrors.tool_params && config.tool_params?.trim() && (
                <p className="text-red-400 text-xs mt-1">{jsonErrors.tool_params}</p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );

  const renderStep2 = () => (
    <div>
      <h2 className="text-lg font-semibold text-white mb-4">Schedule (Optional)</h2>
      <p className="text-gray-400 text-sm mb-4">
        Set a cron schedule for automatic ingestion, or skip to trigger manually.
      </p>
      <CronBuilder value={schedule} onChange={setSchedule} />
    </div>
  );

  const renderStep3 = () => {
    const payload = buildPayload();
    const selectedType = SOURCE_TYPES.find((st) => st.type === sourceType);

    return (
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">Review & Create</h2>
        <div className="space-y-3">
          <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4 space-y-3">
            <div>
              <span className="text-xs text-gray-500">Name</span>
              <p className="text-white text-sm">{payload.name}</p>
            </div>
            <div>
              <span className="text-xs text-gray-500">Source Type</span>
              <p className="text-white text-sm">{selectedType?.label ?? sourceType}</p>
            </div>
            <div>
              <span className="text-xs text-gray-500">Schedule</span>
              <p className="text-white text-sm">{payload.default_schedule ?? 'None (manual)'}</p>
            </div>
            {Object.keys(payload.config).length > 0 && (
              <div>
                <span className="text-xs text-gray-500">Configuration</span>
                <pre className="text-gray-300 text-xs mt-1 bg-[#292929] rounded p-2 overflow-x-auto">
                  {JSON.stringify(payload.config, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const stepRenderers = [renderStep0, renderStep1, renderStep2, renderStep3];

  return (
    <div>
      {renderStepIndicator()}

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6">
        {stepRenderers[step]()}
      </div>

      {/* Navigation */}
      <div className="flex justify-between mt-6">
        <button
          type="button"
          onClick={() => setStep((s) => s - 1)}
          disabled={step === 0}
          className={`px-4 py-2 rounded text-sm transition-colors ${
            step === 0
              ? 'text-gray-600 cursor-not-allowed'
              : 'text-gray-300 border border-[#404040] hover:border-gray-500'
          }`}
        >
          Back
        </button>

        {step < STEPS.length - 1 ? (
          <button
            type="button"
            onClick={() => setStep((s) => s + 1)}
            disabled={!canProceed()}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              canProceed()
                ? 'bg-[#00ff32] text-black hover:bg-[#00dd2b]'
                : 'bg-[#404040] text-gray-500 cursor-not-allowed'
            }`}
          >
            {step === 2 ? 'Skip & Next' : 'Next'}
          </button>
        ) : (
          <button
            type="button"
            onClick={handleCreate}
            disabled={submitting}
            className={`px-6 py-2 rounded text-sm font-medium transition-colors ${
              submitting
                ? 'bg-[#404040] text-gray-500 cursor-wait'
                : 'bg-[#00ff32] text-black hover:bg-[#00dd2b]'
            }`}
          >
            {submitting ? 'Creating...' : 'Create Source'}
          </button>
        )}
      </div>
    </div>
  );
}
