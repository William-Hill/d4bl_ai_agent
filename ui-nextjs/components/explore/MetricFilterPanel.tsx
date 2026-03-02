'use client';

export type Metric = 'homeownership_rate' | 'median_household_income' | 'poverty_rate';
export type Race = 'total' | 'black' | 'white' | 'hispanic';

export interface ExploreFilters {
  metric: Metric;
  race: Race;
  year: number;
  selectedState: string | null;
}

interface Props {
  filters: ExploreFilters;
  onChange: (filters: ExploreFilters) => void;
}

const METRICS: { value: Metric; label: string }[] = [
  { value: 'homeownership_rate', label: 'Homeownership Rate' },
  { value: 'median_household_income', label: 'Median Household Income' },
  { value: 'poverty_rate', label: 'Poverty Rate' },
];

const RACES: { value: Race; label: string }[] = [
  { value: 'total', label: 'All' },
  { value: 'black', label: 'Black' },
  { value: 'white', label: 'White' },
  { value: 'hispanic', label: 'Hispanic/Latino' },
];

const YEARS = [2022, 2021, 2020, 2019];

export default function MetricFilterPanel({ filters, onChange }: Props) {
  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4 space-y-5">
      {/* Metric */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Metric
        </p>
        <div className="space-y-1">
          {METRICS.map((m) => (
            <label key={m.value} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="metric"
                value={m.value}
                checked={filters.metric === m.value}
                onChange={() => onChange({ ...filters, metric: m.value })}
                className="accent-[#00ff32]"
              />
              <span className="text-sm text-gray-300">{m.label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="border-t border-[#404040]" />

      {/* Race */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Race / Ethnicity
        </p>
        <div className="space-y-1">
          {RACES.map((r) => (
            <label key={r.value} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="race"
                value={r.value}
                checked={filters.race === r.value}
                onChange={() => onChange({ ...filters, race: r.value })}
                className="accent-[#00ff32]"
              />
              <span className="text-sm text-gray-300">{r.label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="border-t border-[#404040]" />

      {/* Year */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Year
        </p>
        <select
          value={filters.year}
          onChange={(e) => onChange({ ...filters, year: Number(e.target.value) })}
          className="w-full bg-[#292929] border border-[#404040] rounded px-2 py-1.5 text-sm text-gray-300 focus:outline-none focus:border-[#00ff32]"
        >
          {YEARS.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

