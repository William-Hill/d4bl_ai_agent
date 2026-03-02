'use client';

import { useState, useEffect, useCallback } from 'react';
import MetricFilterPanel, { ExploreFilters } from '@/components/explore/MetricFilterPanel';
import StateMap from '@/components/explore/StateMap';
import RacialGapChart from '@/components/explore/RacialGapChart';
import PolicyTable from '@/components/explore/PolicyTable';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

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

interface IndicatorRow {
  fips_code: string;
  geography_name: string;
  state_fips: string;
  geography_type: string;
  year: number;
  race: string;
  metric: string;
  value: number;
  margin_of_error: number | null;
}

interface PolicyBill {
  state: string;
  state_name: string;
  bill_number: string;
  title: string;
  summary: string | null;
  status: string;
  topic_tags: string[] | null;
  introduced_date: string | null;
  last_action_date: string | null;
  url: string | null;
}

export default function ExplorePage() {
  const [filters, setFilters] = useState<ExploreFilters>({
    metric: 'homeownership_rate',
    race: 'total',
    year: 2022,
    selectedState: null,
  });
  const [selectedStateName, setSelectedStateName] = useState<string>('');

  const [mapIndicators, setMapIndicators] = useState<IndicatorRow[]>([]);
  const [chartIndicators, setChartIndicators] = useState<IndicatorRow[]>([]);
  const [bills, setBills] = useState<PolicyBill[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch all-state indicators for the map (current metric + race + year)
  const fetchMapData = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        metric: filters.metric,
        race: filters.race,
        year: String(filters.year),
        geography_type: 'state',
      });
      const res = await fetch(`${API_BASE}/api/explore/indicators?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setMapIndicators(await res.json());
    } catch (e: any) {
      setError(e.message);
    }
  }, [filters.metric, filters.race, filters.year]);

  // Fetch all-race indicators for selected state (for bar chart)
  const fetchChartData = useCallback(async () => {
    if (!filters.selectedState) {
      setChartIndicators([]);
      return;
    }
    try {
      const params = new URLSearchParams({
        state_fips: filters.selectedState,
        metric: filters.metric,
        year: String(filters.year),
        geography_type: 'state',
      });
      const res = await fetch(`${API_BASE}/api/explore/indicators?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setChartIndicators(await res.json());
    } catch (e: any) {
      setError(e.message);
    }
  }, [filters.selectedState, filters.metric, filters.year]);

  // Fetch policy bills for selected state (server-side filter by state abbrev)
  const fetchBills = useCallback(async () => {
    if (!filters.selectedState) {
      setBills([]);
      return;
    }
    const abbrev = FIPS_TO_ABBREV[filters.selectedState];
    if (!abbrev) {
      setBills([]);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/explore/policies?state=${abbrev}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const stateBills: PolicyBill[] = await res.json();
      setBills(stateBills);
    } catch (e: any) {
      setError(e.message);
    }
  }, [filters.selectedState]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([fetchMapData(), fetchChartData(), fetchBills()]).finally(() =>
      setLoading(false),
    );
  }, [fetchMapData, fetchChartData, fetchBills]);

  const handleSelectState = (fips: string, name: string) => {
    setFilters((prev) => ({
      ...prev,
      selectedState: prev.selectedState === fips ? null : fips,
    }));
    setSelectedStateName((prev) => (prev === name ? '' : name));
  };

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Hero */}
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-1">Explore Data by State</h1>
          <div className="w-16 h-1 bg-[#00ff32] mb-3" />
          <p className="text-gray-400 text-sm">
            Race-disaggregated socioeconomic indicators and policy activity across the United
            States.
          </p>
        </header>

        {error && (
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
            Error loading data: {error}
          </div>
        )}

        {/* Map + Filters */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-4 mb-6">
          <div>
            {loading && !mapIndicators.length ? (
              <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg h-64 flex items-center justify-center text-gray-500 text-sm">
                Loading map data...
              </div>
            ) : (
              <StateMap
                indicators={mapIndicators}
                selectedStateFips={filters.selectedState}
                onSelectState={handleSelectState}
              />
            )}
          </div>
          <MetricFilterPanel filters={filters} onChange={setFilters} />
        </div>

        {/* Bar Chart */}
        {filters.selectedState && (
          <div className="mb-6">
            <RacialGapChart
              indicators={chartIndicators}
              metric={filters.metric}
              stateName={selectedStateName}
            />
          </div>
        )}

        {/* Policy Tracker */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
          <h2 className="text-base font-semibold text-white mb-4">
            Policy Tracker
            {selectedStateName && (
              <span className="text-[#00ff32] ml-2">— {selectedStateName}</span>
            )}
          </h2>
          {loading && !bills.length ? (
            <p className="text-gray-500 text-sm">Loading bills...</p>
          ) : (
            <PolicyTable bills={bills} />
          )}
        </div>
      </div>
    </div>
  );
}

