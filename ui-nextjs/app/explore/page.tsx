'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import MetricFilterPanel, { ExploreFilters } from '@/components/explore/MetricFilterPanel';
import StateMap from '@/components/explore/StateMap';
import RacialGapChart from '@/components/explore/RacialGapChart';
import DataSourceTabs from '@/components/explore/DataSourceTabs';
import EmptyDataState from '@/components/explore/EmptyDataState';
import StateVsNationalChart from '@/components/explore/StateVsNationalChart';
import PolicyBadge from '@/components/explore/PolicyBadge';
import { IndicatorRow, PolicyBill, ExploreRow, ExploreResponse } from '@/lib/types';
import { DATA_SOURCES, DataSourceConfig, FIPS_TO_ABBREV, toIndicatorRow } from '@/lib/explore-config';
import { API_BASE } from '@/lib/api';
import { useAuthHeaders } from '@/hooks/useAuthHeaders';

export default function ExplorePage() {
  const { session, getHeaders } = useAuthHeaders();
  const [activeSource, setActiveSource] = useState<DataSourceConfig>(DATA_SOURCES[0]);
  const [exploreData, setExploreData] = useState<ExploreResponse | null>(null);
  const [bills, setBills] = useState<PolicyBill[]>([]);
  const [chartIndicators, setChartIndicators] = useState<IndicatorRow[]>([]);
  const [filters, setFilters] = useState<ExploreFilters>({
    metric: '',
    race: 'total',
    year: null,
    selectedState: null,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const didAutoSelectDefaults = useRef(false);

  /** Reset filters when switching data sources. */
  const handleSourceChange = (src: DataSourceConfig) => {
    setActiveSource(src);
    didAutoSelectDefaults.current = false;
    setFilters({
      metric: '',
      race: src.hasRace ? 'total' : null,
      year: null,
      selectedState: null,
    });
    setExploreData(null);
    setBills([]);
    setChartIndicators([]);
  };

  /** Unified data fetching for all sources. */
  const fetchData = useCallback(async (signal: AbortSignal) => {
    if (!session?.access_token) return;
    setLoading(true);
    setError(null);

    try {
      // Build the main data promise
      let dataPromise: Promise<{ data: ExploreResponse; chartRows: IndicatorRow[] }>;

      if (activeSource.key === 'census') {
        // Legacy Census endpoint returns IndicatorRow[]
        const params = new URLSearchParams({ geography_type: 'state' });
        if (filters.year != null) params.set('year', String(filters.year));
        if (filters.metric) params.set('metric', filters.metric);
        if (filters.race) params.set('race', filters.race);

        dataPromise = fetch(`${API_BASE}/api/explore/indicators?${params}`, {
          signal, headers: getHeaders(),
        }).then(async res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const rows: IndicatorRow[] = await res.json();

          const exploreRows: ExploreRow[] = rows.map(r => ({
            state_fips: r.state_fips,
            state_name: r.geography_name,
            value: r.value,
            metric: r.metric,
            year: r.year,
            race: r.race,
          }));
          const avgVal = exploreRows.length
            ? exploreRows.reduce((s, r) => s + r.value, 0) / exploreRows.length
            : null;

          const data: ExploreResponse = {
            rows: exploreRows,
            national_average: avgVal,
            available_metrics: [...new Set(rows.map(r => r.metric))].sort(),
            available_years: [...new Set(rows.map(r => r.year))].sort((a, b) => a - b),
            available_races: [...new Set(rows.map(r => r.race))].sort(),
          };

          // Fetch racial breakdown for selected state (Census-specific)
          let chartRows: IndicatorRow[] = [];
          if (filters.selectedState) {
            const chartParams = new URLSearchParams({
              state_fips: filters.selectedState,
              metric: filters.metric || 'homeownership_rate',
              geography_type: 'state',
            });
            if (filters.year != null) chartParams.set('year', String(filters.year));
            const chartRes = await fetch(`${API_BASE}/api/explore/indicators?${chartParams}`, {
              signal, headers: getHeaders(),
            });
            if (chartRes.ok) chartRows = await chartRes.json();
          }

          return { data, chartRows };
        });
      } else {
        // New endpoints return ExploreResponse directly
        const params = new URLSearchParams();
        if (filters.year != null) params.set('year', String(filters.year));
        if (filters.metric) params.set(activeSource.primaryFilterKey, filters.metric);
        if (filters.race) params.set('race', filters.race);
        if (filters.selectedState) params.set('state_fips', filters.selectedState);

        dataPromise = fetch(`${API_BASE}${activeSource.endpoint}?${params}`, {
          signal, headers: getHeaders(),
        }).then(async res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data: ExploreResponse = await res.json();
          return { data, chartRows: [] };
        });
      }

      // Build bills promise (runs in parallel with data fetch)
      const abbrev = filters.selectedState ? FIPS_TO_ABBREV[filters.selectedState] : null;
      const billsPromise: Promise<PolicyBill[]> = abbrev
        ? fetch(`${API_BASE}/api/explore/policies?state=${abbrev}`, {
            signal, headers: getHeaders(),
          }).then(res => (res.ok ? res.json() : []))
        : Promise.resolve([]);

      const [{ data, chartRows }, billsData] = await Promise.all([dataPromise, billsPromise]);

      setExploreData(data);
      setChartIndicators(chartRows);
      setBills(billsData);

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

        {error && (
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
            Error loading data: {error}
          </div>
        )}

        {/* Map + Filters */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-4 mb-6">
          <div>
            {loading && (!exploreData || !exploreData.rows.length) ? (
              <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg h-64 flex items-center justify-center text-gray-500 text-sm">
                Loading map data...
              </div>
            ) : exploreData && exploreData.rows.length > 0 ? (
              <StateMap
                indicators={mapIndicators}
                selectedStateFips={filters.selectedState}
                onSelectState={handleSelectState}
                accent={activeSource.accent}
                nationalAverage={exploreData.national_average}
              />
            ) : (
              <EmptyDataState sourceName={activeSource.label} accent={activeSource.accent} />
            )}
          </div>
          <MetricFilterPanel
            filters={filters}
            onChange={setFilters}
            availableMetrics={exploreData?.available_metrics}
            availableYears={exploreData?.available_years}
            availableRaces={exploreData?.available_races}
            primaryFilterLabel={activeSource.primaryFilterLabel}
            accent={activeSource.accent}
          />
        </div>

        {/* Detail Chart + Policy Badge */}
        {filters.selectedState && exploreData && exploreData.rows.length > 0 && (
          <div className="mb-6">
            <div className="flex items-center gap-3 mb-3">
              <h2 className="text-base font-semibold text-white">{selectedStateName}</h2>
              <PolicyBadge bills={bills} stateName={selectedStateName} accent={activeSource.accent} />
            </div>
            {activeSource.hasRace ? (
              activeSource.key === 'census' ? (
                <RacialGapChart
                  indicators={chartIndicators}
                  metric={filters.metric || 'homeownership_rate'}
                  stateName={selectedStateName}
                />
              ) : (
                /* For non-Census race sources, build chart from exploreData rows filtered to state */
                <RacialGapChart
                  indicators={exploreData.rows
                    .filter(r => r.state_fips === filters.selectedState)
                    .map(toIndicatorRow)}
                  metric={filters.metric || exploreData.available_metrics?.[0] || ''}
                  stateName={selectedStateName}
                />
              )
            ) : (
              <StateVsNationalChart
                stateValue={stateDetailValue}
                nationalAverage={exploreData.national_average ?? 0}
                stateName={selectedStateName}
                metric={filters.metric || exploreData.available_metrics?.[0] || ''}
                accent={activeSource.accent}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
