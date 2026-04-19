'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import MetricFilterPanel, { ExploreFilters } from '@/components/explore/MetricFilterPanel';
import StaffDatasetPicker, { StaffDatasetSummary } from '@/components/explore/StaffDatasetPicker';
import StateMap from '@/components/explore/StateMap';
import RacialGapChart from '@/components/explore/RacialGapChart';
import DataSourceTabs from '@/components/explore/DataSourceTabs';
import EmptyDataState from '@/components/explore/EmptyDataState';
import StateVsNationalChart from '@/components/explore/StateVsNationalChart';
import PolicyBadge from '@/components/explore/PolicyBadge';
import PolicyExploreView from '@/components/explore/PolicyExploreView';
import StateAnnotation from '@/components/explore/StateAnnotation';
import ExplainPanel from '@/components/explore/ExplainPanel';
import ExploreQueryBar from '@/components/explore/ExploreQueryBar';
import MapLegend from '@/components/explore/MapLegend';
import DataTable from '@/components/explore/DataTable';
import { IndicatorRow, PolicyBill, ExploreResponse } from '@/lib/types';
import { DATA_SOURCES, DataSourceConfig, FIPS_TO_ABBREV, toIndicatorRow, collapseToLatestYear, getDirectionalColors, getChartType, getMetricDirection } from '@/lib/explore-config';
import { API_BASE } from '@/lib/api';
import { useAuthHeaders } from '@/hooks/useAuthHeaders';

const STORAGE_KEY = 'd4bl-explore-filters';

interface PersistedFilters {
  sourceKey: string;
  metric: string | null;
  race: string | null;
  year: number | null;
  selectedState: string | null;
  uploadId?: string | null;
}

function loadPersistedFilters(): PersistedFilters | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedFilters;
  } catch {
    return null;
  }
}

function persistFilters(sourceKey: string, filters: ExploreFilters): void {
  if (typeof window === 'undefined') return;
  try {
    const data: PersistedFilters = {
      sourceKey,
      metric: filters.metric || null,
      race: filters.race,
      year: filters.year,
      selectedState: filters.selectedState,
      uploadId: filters.uploadId ?? null,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // Quota exceeded or storage unavailable — silently ignore
  }
}

/** Reusable shimmer skeleton block. */
function SkeletonBlock({ className = '' }: { className?: string }) {
  return (
    <div
      className={`bg-[#333] rounded animate-pulse ${className}`}
    />
  );
}

const DEFAULT_SOURCE_KEY = 'census';
const DEFAULT_METRIC = 'median_household_income';

function resolveInitialState(): { source: DataSourceConfig; filters: ExploreFilters } {
  const persisted = loadPersistedFilters();
  const defaultSource =
    DATA_SOURCES.find(s => s.key === DEFAULT_SOURCE_KEY) ?? DATA_SOURCES[0];

  if (persisted) {
    const savedSource = DATA_SOURCES.find(s => s.key === persisted.sourceKey);
    const source = savedSource ?? defaultSource;
    return {
      source,
      filters: {
        metric: persisted.metric ?? '',
        race:
          persisted.race ??
          (source.key === 'staff-uploads'
            ? null
            : source.hasRace
              ? 'total'
              : null),
        year: persisted.year,
        selectedState: persisted.selectedState,
        uploadId: persisted.uploadId && source.key === 'staff-uploads' ? persisted.uploadId : null,
      },
    };
  }

  return {
    source: defaultSource,
    filters: {
      metric: DEFAULT_METRIC,
      race: 'total',
      year: null,
      selectedState: null,
      uploadId: null,
    },
  };
}

export default function ExplorePage() {
  const { session, getHeaders } = useAuthHeaders();

  const initialState = useRef(resolveInitialState());
  const [activeSource, setActiveSource] = useState<DataSourceConfig>(initialState.current.source);
  const [exploreData, setExploreData] = useState<ExploreResponse | null>(null);
  const [bills, setBills] = useState<PolicyBill[]>([]);

  const [filters, setFilters] = useState<ExploreFilters>(initialState.current.filters);
  const [activeUploadSummary, setActiveUploadSummary] = useState<StaffDatasetSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const didAutoSelectDefaults = useRef(false);
  const initialized = useRef(false);

  /** Persist filters to localStorage after initialization. */
  useEffect(() => {
    if (!initialized.current) return;
    persistFilters(activeSource.key, filters);
  }, [activeSource.key, filters]);

  /** Reset filters when switching data sources. */
  const handleSourceChange = (src: DataSourceConfig) => {
    setActiveSource(src);
    didAutoSelectDefaults.current = false;
    setFilters({
      metric: '',
      race: src.hasRace ? 'total' : null,
      year: null,
      selectedState: null,
      uploadId: null,
    });
    setActiveUploadSummary(null);
    setExploreData(null);
    setBills([]);

  };

  /** Unified data fetching for all sources. */
  const fetchData = useCallback(async (signal: AbortSignal) => {
    if (!session?.access_token) return;
    // Policy tab owns its own bills fetch in PolicyExploreView — skip the
    // metric-oriented fetch entirely so we don't hit a metric endpoint that
    // doesn't exist for 'policy'.
    if (activeSource.key === 'policy') {
      setLoading(false);
      return;
    }
    if (activeSource.key === 'staff-uploads' && !filters.uploadId) {
      setLoading(false);
      setExploreData(null);
      return;
    }
    setLoading(true);
    setError(null);

    try {
      // All endpoints (including Census) now return ExploreResponse directly
      const params = new URLSearchParams();
      if (filters.year != null) params.set('year', String(filters.year));
      if (filters.metric) params.set(activeSource.primaryFilterKey, filters.metric);
      if (filters.race) params.set('race', filters.race);
      if (filters.selectedState) params.set('state_fips', filters.selectedState);
      if (activeSource.key === 'staff-uploads' && filters.uploadId) {
        params.set('upload_id', filters.uploadId);
      }

      const dataPromise = fetch(`${API_BASE}${activeSource.endpoint}?${params}`, {
        signal, headers: getHeaders(),
      }).then(async res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json() as ExploreResponse;
      });

      // Build bills promise (runs in parallel with data fetch)
      const abbrev = filters.selectedState ? FIPS_TO_ABBREV[filters.selectedState] : null;
      const billsPromise: Promise<PolicyBill[]> = abbrev
        ? fetch(`${API_BASE}/api/explore/policies?state=${abbrev}`, {
            signal, headers: getHeaders(),
          }).then(res => (res.ok ? res.json() : []))
        : Promise.resolve([]);

      const [data, billsData] = await Promise.all([dataPromise, billsPromise]);

      // When no year filter, collapse multi-year rows to latest per state+metric+race
      const normalizedRows = filters.year == null ? collapseToLatestYear(data.rows) : data.rows;
      const normalizedData: ExploreResponse = normalizedRows === data.rows ? data : {
        ...data,
        rows: normalizedRows,
        national_average: normalizedRows.length
          ? normalizedRows.reduce((s, r) => s + r.value, 0) / normalizedRows.length
          : null,
      };

      setExploreData(normalizedData);
      setBills(billsData);

      // Mark as initialized after first successful data load so persistence kicks in
      initialized.current = true;

      // Auto-select first metric if none selected (year stays null = "all years")
      if (!didAutoSelectDefaults.current && !filters.metric && data.available_metrics?.length > 0) {
        didAutoSelectDefaults.current = true;
        setFilters(prev => ({ ...prev, metric: data.available_metrics[0] }));
      }
    } catch (e: unknown) {
      if (signal.aborted) return;
      setError(e instanceof Error ? e.message : 'Failed to load data');
    } finally {
      if (!signal.aborted) setLoading(false);
    }
  }, [activeSource, filters, session?.access_token, getHeaders]);

  /** Trigger fetch when dependencies change. */
  useEffect(() => {
    const controller = new AbortController();
    fetchData(controller.signal);
    return () => controller.abort();
  }, [fetchData]);

  /** Restore staff-upload summary after refresh (localStorage has uploadId only). */
  useEffect(() => {
    if (activeSource.key !== 'staff-uploads' || !filters.uploadId || !session?.access_token) {
      return;
    }
    let cancelled = false;
    fetch(`${API_BASE}/api/explore/staff-uploads/available`, { headers: getHeaders() })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: StaffDatasetSummary[]) => {
        if (cancelled || !Array.isArray(data)) return;
        const s = data.find((d) => d.upload_id === filters.uploadId) ?? null;
        setActiveUploadSummary(s);
      });
    return () => {
      cancelled = true;
    };
  }, [activeSource.key, filters.uploadId, session?.access_token, getHeaders]);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleSelectState = (fips: string, _name?: string) => {
    setFilters((prev) => ({
      ...prev,
      selectedState: prev.selectedState === fips ? null : fips,
    }));
  };

  /** Derive state name from the selected FIPS code + loaded data. */
  const selectedStateName = useMemo(() => {
    if (!filters.selectedState || !exploreData) return '';
    const match = exploreData.rows.find(r => r.state_fips === filters.selectedState);
    return match?.state_name ?? '';
  }, [filters.selectedState, exploreData]);

  /** State detail value for StateVsNationalChart. */
  const stateDetailValue = useMemo(() => {
    if (!filters.selectedState || !exploreData) return 0;
    const match = exploreData.rows.find(
      r => r.state_fips === filters.selectedState && r.metric === filters.metric,
    );
    return match?.value ?? 0;
  }, [filters.selectedState, filters.metric, exploreData]);

  /** Map ExploreRows to IndicatorRow shape for StateMap (needs fips_code). */
  const mapIndicators: IndicatorRow[] = useMemo(() => {
    if (!exploreData) return [];
    return exploreData.rows.map(toIndicatorRow);
  }, [exploreData]);

  /** Pre-compute min/max for the MapLegend so the IIFE is not re-run in JSX. */
  const legendData = useMemo(() => {
    if (!exploreData || !filters.metric) return null;
    const values = exploreData.rows
      .filter((r) => r.metric === filters.metric)
      .map((r) => r.value)
      .filter((v): v is number => v != null);
    if (values.length === 0) return null;
    return { min: Math.min(...values), max: Math.max(...values) };
  }, [exploreData, filters.metric]);

  /** Directional colors based on current source + metric. */
  const dirColors = filters.metric
    ? getDirectionalColors(activeSource.key, filters.metric, activeSource.accent)
    : { colorStart: '#444', colorEnd: activeSource.accent };

  /** Resolved metric and year for consistent AI feature context. */
  const resolvedMetric = filters.metric || exploreData?.available_metrics?.[0] || '';
  const resolvedYear = filters.year ?? exploreData?.available_years?.[exploreData.available_years.length - 1] ?? 2022;

  const effectiveHasRace =
    activeSource.key === 'staff-uploads'
      ? (activeUploadSummary?.has_race ?? false)
      : activeSource.hasRace;

  const staffUploadRaces =
    activeSource.key === 'staff-uploads'
      ? (effectiveHasRace ? (exploreData?.available_races ?? []) : [])
      : exploreData?.available_races;

  const staffUploadMetrics =
    activeSource.key === 'staff-uploads'
      ? (filters.uploadId ? (exploreData?.available_metrics ?? []) : [])
      : exploreData?.available_metrics;

  const staffUploadYears =
    activeSource.key === 'staff-uploads'
      ? (filters.uploadId ? (exploreData?.available_years ?? []) : [])
      : exploreData?.available_years;

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Hero */}
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-1">Explore Data by State</h1>
          <div className="w-16 h-1 mb-3" style={{ backgroundColor: activeSource.accent }} />
          <p className="text-gray-400 text-sm">
            Race-disaggregated socioeconomic indicators and policy activity across the United
            States.
          </p>
        </header>

        {/* Data Source Tabs */}
        <DataSourceTabs activeKey={activeSource.key} onSelect={handleSourceChange} />

        {/* Source description banner */}
        <div className="mb-4 px-4 py-3 bg-[#1a1a1a] border border-[#404040] rounded-lg flex items-start gap-3">
          <div
            className="mt-0.5 w-2 h-2 rounded-full flex-shrink-0"
            style={{ backgroundColor: activeSource.accent }}
          />
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-300">{activeSource.description}</p>
            <a
              href={activeSource.sourceUrl || '/guide'}
              {...(activeSource.sourceUrl.startsWith('http')
                ? { target: '_blank' as const, rel: 'noopener noreferrer' }
                : {})}
              className="text-xs mt-1 inline-block hover:underline"
              style={{ color: activeSource.accent }}
            >
              Learn more
            </a>
          </div>
        </div>

        {error && activeSource.key !== 'policy' && (
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
            Error loading data: {error}
          </div>
        )}

        {activeSource.key === 'policy' ? (
          <PolicyExploreView />
        ) : (
          <>
        {activeSource.key === 'staff-uploads' && (
          <div className="mb-4">
            <StaffDatasetPicker
              value={filters.uploadId}
              onChange={(id, summary) => {
                setActiveUploadSummary(summary);
                setFilters((prev) => ({
                  ...prev,
                  uploadId: id,
                  metric: '',
                  race: null,
                  year: null,
                  selectedState: null,
                }));
              }}
            />
          </div>
        )}
        {/* Map + Filters */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-4 mb-6">
          <div>
            {loading && (!exploreData || !exploreData.rows.length) ? (
              <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 space-y-4">
                <SkeletonBlock className="h-6 w-48" />
                <SkeletonBlock className="h-48 w-full" />
                <div className="flex gap-2">
                  <SkeletonBlock className="h-4 w-20" />
                  <SkeletonBlock className="h-4 w-24" />
                  <SkeletonBlock className="h-4 w-16" />
                </div>
              </div>
            ) : activeSource.key === 'staff-uploads' && !filters.uploadId ? (
              <div className="text-gray-400 text-sm py-12 text-center">
                Pick a dataset from the Dataset dropdown above to view it on the map.
              </div>
            ) : exploreData && exploreData.rows.length > 0 ? (
              <div className="relative">
                <StateMap
                  indicators={mapIndicators}
                  selectedStateFips={filters.selectedState}
                  onSelectState={handleSelectState}
                  accent={activeSource.accent}
                  colorStart={dirColors.colorStart}
                  colorEnd={dirColors.colorEnd}
                />
                {legendData && (
                  <MapLegend
                    min={legendData.min}
                    max={legendData.max}
                    nationalAverage={exploreData.national_average}
                    metric={filters.metric}
                    colorStart={dirColors.colorStart}
                    colorEnd={dirColors.colorEnd}
                    accent={activeSource.accent}
                  />
                )}
                {loading && (
                  <div
                    className="absolute inset-0 bg-[#292929]/60 rounded-lg flex items-center justify-center"
                    role="status"
                    aria-live="polite"
                  >
                    <div
                      className="w-6 h-6 border-2 border-gray-500 border-t-white rounded-full animate-spin"
                      aria-hidden="true"
                    />
                    <span className="sr-only">Updating map data</span>
                  </div>
                )}
              </div>
            ) : (
              <EmptyDataState sourceName={activeSource.label} accent={activeSource.accent} />
            )}
          </div>
          {loading && (!exploreData || !exploreData.rows.length) ? (
            <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4 space-y-4">
              <SkeletonBlock className="h-4 w-20" />
              <SkeletonBlock className="h-3 w-full" />
              <SkeletonBlock className="h-3 w-full" />
              <SkeletonBlock className="h-3 w-3/4" />
              <div className="h-px w-full bg-[#404040]" />
              <SkeletonBlock className="h-4 w-16" />
              <SkeletonBlock className="h-3 w-full" />
              <SkeletonBlock className="h-3 w-full" />
            </div>
          ) : (
            <MetricFilterPanel
              filters={filters}
              onChange={setFilters}
              availableMetrics={staffUploadMetrics}
              availableYears={staffUploadYears}
              availableRaces={staffUploadRaces}
              primaryFilterLabel={activeSource.primaryFilterLabel}
              accent={activeSource.accent}
              sourceKey={activeSource.key}
            />
          )}
        </div>

        {/* Data Table */}
        {exploreData && (
          <DataTable
            rows={exploreData.rows}
            nationalAverage={exploreData.national_average}
            metric={filters.metric}
            selectedStateFips={filters.selectedState}
            onSelectState={handleSelectState}
            accent={activeSource.accent}
            sourceKey={activeSource.key}
          />
        )}

        {/* Detail Chart + Policy Badge */}
        {filters.selectedState && exploreData && exploreData.rows.length > 0 && (
          <div className="mb-6">
            <div className="flex items-center gap-3 mb-3">
              <h2 className="text-base font-semibold text-white">{selectedStateName}</h2>
              <PolicyBadge bills={bills} stateName={selectedStateName} accent={activeSource.accent} />
            </div>
            <StateAnnotation
              source={activeSource.key}
              stateFips={filters.selectedState}
              metric={resolvedMetric}
              accent={activeSource.accent}
            />
            <ExplainPanel
              source={activeSource.key}
              metric={resolvedMetric}
              stateFips={filters.selectedState}
              stateName={selectedStateName}
              value={stateDetailValue}
              nationalAverage={exploreData.national_average ?? 0}
              year={resolvedYear}
              accent={activeSource.accent}
            />
            {getChartType(activeSource.key, effectiveHasRace) === "racial-gap" ? (
              <RacialGapChart
                indicators={exploreData.rows
                  .filter(
                    (r) =>
                      r.state_fips === filters.selectedState &&
                      r.metric === (resolvedMetric),
                  )
                  .map(toIndicatorRow)}
                metric={resolvedMetric}
                stateName={selectedStateName}
              />
            ) : (
              <StateVsNationalChart
                stateValue={stateDetailValue}
                nationalAverage={exploreData.national_average ?? 0}
                stateName={selectedStateName}
                metric={resolvedMetric}
                accent={activeSource.accent}
                metricDirection={getMetricDirection(activeSource.key, resolvedMetric)}
              />
            )}
          </div>
        )}

        {/* Conversational Query Bar */}
        {exploreData && (
          <ExploreQueryBar
            source={activeSource.key}
            metric={resolvedMetric || null}
            stateFips={filters.selectedState}
            race={filters.race}
            year={resolvedYear}
            accent={activeSource.accent}
          />
        )}
          </>
        )}
      </div>
    </div>
  );
}
