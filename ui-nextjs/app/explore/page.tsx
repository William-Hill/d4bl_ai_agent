'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import MetricFilterPanel, { ExploreFilters } from '@/components/explore/MetricFilterPanel';
import StateMap from '@/components/explore/StateMap';
import RacialGapChart from '@/components/explore/RacialGapChart';
import DataSourceTabs from '@/components/explore/DataSourceTabs';
import EmptyDataState from '@/components/explore/EmptyDataState';
import StateVsNationalChart from '@/components/explore/StateVsNationalChart';
import PolicyBadge from '@/components/explore/PolicyBadge';
import { IndicatorRow, PolicyBill, ExploreRow, ExploreResponse } from '@/lib/types';
import { DATA_SOURCES, DataSourceConfig } from '@/lib/explore-config';
import { API_BASE } from '@/lib/api';
import { useAuthHeaders } from '@/hooks/useAuthHeaders';

/** 2-digit FIPS code → 2-letter state abbreviation for API filtering */
const FIPS_TO_ABBREV: Record<string, string> = {
  '01': 'AL', '02': 'AK', '04': 'AZ', '05': 'AR', '06': 'CA', '08': 'CO', '09': 'CT',
  '10': 'DE', '11': 'DC', '12': 'FL', '13': 'GA', '15': 'HI', '16': 'ID', '17': 'IL',
  '18': 'IN', '19': 'IA', '20': 'KS', '21': 'KY', '22': 'LA', '23': 'ME', '24': 'MD',
  '25': 'MA', '26': 'MI', '27': 'MN', '28': 'MS', '29': 'MO', '30': 'MT', '31': 'NE',
  '32': 'NV', '33': 'NH', '34': 'NJ', '35': 'NM', '36': 'NY', '37': 'NC', '38': 'ND',
  '39': 'OH', '40': 'OK', '41': 'OR', '42': 'PA', '44': 'RI', '45': 'SC', '46': 'SD',
  '47': 'TN', '48': 'TX', '49': 'UT', '50': 'VT', '51': 'VA', '53': 'WA', '54': 'WV',
  '55': 'WI', '56': 'WY',
};

export default function ExplorePage() {
  const { session, getHeaders } = useAuthHeaders();
  const [activeSource, setActiveSource] = useState<DataSourceConfig>(DATA_SOURCES[0]);
  const [exploreData, setExploreData] = useState<ExploreResponse | null>(null);
  const [bills, setBills] = useState<PolicyBill[]>([]);
  const [chartIndicators, setChartIndicators] = useState<IndicatorRow[]>([]);
  const [filters, setFilters] = useState<ExploreFilters>({
    metric: '',
    race: 'total',
    year: 2022,
    selectedState: null,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Reset filters when switching data sources. */
  const handleSourceChange = (src: DataSourceConfig) => {
    setActiveSource(src);
    setFilters({
      metric: '',
      race: src.hasRace ? 'total' : null,
      year: 2022,
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
      if (activeSource.key === 'census') {
        // Legacy Census endpoint returns IndicatorRow[]
        const params = new URLSearchParams({
          geography_type: 'state',
          year: String(filters.year),
        });
        if (filters.metric) params.set('metric', filters.metric);
        if (filters.race) params.set('race', filters.race);

        const res = await fetch(`${API_BASE}/api/explore/indicators?${params}`, {
          signal, headers: getHeaders(),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const rows: IndicatorRow[] = await res.json();

        // Normalize to ExploreResponse
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

        setExploreData({
          rows: exploreRows,
          national_average: avgVal,
          available_metrics: [...new Set(rows.map(r => r.metric))].sort(),
          available_years: [...new Set(rows.map(r => r.year))].sort((a, b) => a - b),
          available_races: [...new Set(rows.map(r => r.race))].sort(),
        });

        // Fetch racial breakdown for selected state (Census-specific)
        if (filters.selectedState) {
          const chartParams = new URLSearchParams({
            state_fips: filters.selectedState,
            metric: filters.metric || 'homeownership_rate',
            year: String(filters.year),
            geography_type: 'state',
          });
          const chartRes = await fetch(`${API_BASE}/api/explore/indicators?${chartParams}`, {
            signal, headers: getHeaders(),
          });
          if (chartRes.ok) setChartIndicators(await chartRes.json());
        } else {
          setChartIndicators([]);
        }
      } else {
        // New endpoints return ExploreResponse directly
        const params = new URLSearchParams({ year: String(filters.year) });
        if (filters.metric) params.set(activeSource.primaryFilterKey, filters.metric);
        if (filters.race) params.set('race', filters.race);
        if (filters.selectedState) params.set('state_fips', filters.selectedState);

        const res = await fetch(`${API_BASE}${activeSource.endpoint}?${params}`, {
          signal, headers: getHeaders(),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setExploreData(await res.json());
        setChartIndicators([]);
      }

      // Fetch bills if state selected
      if (filters.selectedState) {
        const abbrev = FIPS_TO_ABBREV[filters.selectedState];
        if (abbrev) {
          const billRes = await fetch(`${API_BASE}/api/explore/policies?state=${abbrev}`, {
            signal, headers: getHeaders(),
          });
          if (billRes.ok) setBills(await billRes.json());
        }
      } else {
        setBills([]);
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

  /** Auto-select first available metric when data loads. */
  useEffect(() => {
    if (exploreData && !filters.metric && exploreData.available_metrics.length > 0) {
      setFilters(prev => ({ ...prev, metric: exploreData.available_metrics[0] }));
    }
  }, [exploreData, filters.metric]);

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
    return exploreData.rows.map(r => ({
      state_fips: r.state_fips,
      fips_code: r.state_fips,
      geography_name: r.state_name,
      geography_type: 'state',
      year: r.year,
      race: r.race ?? 'total',
      metric: r.metric,
      value: r.value,
      margin_of_error: null,
    }));
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
              <PolicyBadge bills={bills} stateName={selectedStateName} />
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
                    .map(r => ({
                      fips_code: r.state_fips,
                      geography_name: r.state_name,
                      state_fips: r.state_fips,
                      geography_type: 'state',
                      year: r.year,
                      race: r.race ?? 'total',
                      metric: r.metric,
                      value: r.value,
                      margin_of_error: null,
                    }))}
                  metric={filters.metric}
                  stateName={selectedStateName}
                />
              )
            ) : (
              <StateVsNationalChart
                stateValue={stateDetailValue}
                nationalAverage={exploreData.national_average ?? 0}
                stateName={selectedStateName}
                metric={filters.metric}
                accent={activeSource.accent}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
