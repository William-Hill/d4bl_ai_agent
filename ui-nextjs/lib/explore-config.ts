import { ExploreRow, IndicatorRow } from './types';

/** 2-digit FIPS code → 2-letter state abbreviation for API filtering */
export const FIPS_TO_ABBREV: Record<string, string> = {
  '01': 'AL', '02': 'AK', '04': 'AZ', '05': 'AR', '06': 'CA', '08': 'CO', '09': 'CT',
  '10': 'DE', '11': 'DC', '12': 'FL', '13': 'GA', '15': 'HI', '16': 'ID', '17': 'IL',
  '18': 'IN', '19': 'IA', '20': 'KS', '21': 'KY', '22': 'LA', '23': 'ME', '24': 'MD',
  '25': 'MA', '26': 'MI', '27': 'MN', '28': 'MS', '29': 'MO', '30': 'MT', '31': 'NE',
  '32': 'NV', '33': 'NH', '34': 'NJ', '35': 'NM', '36': 'NY', '37': 'NC', '38': 'ND',
  '39': 'OH', '40': 'OK', '41': 'OR', '42': 'PA', '44': 'RI', '45': 'SC', '46': 'SD',
  '47': 'TN', '48': 'TX', '49': 'UT', '50': 'VT', '51': 'VA', '53': 'WA', '54': 'WV',
  '55': 'WI', '56': 'WY',
};

/** Convert an ExploreRow to the IndicatorRow shape expected by map / chart components. */
export function toIndicatorRow(r: ExploreRow): IndicatorRow {
  return {
    fips_code: r.state_fips,
    geography_name: r.state_name,
    state_fips: r.state_fips,
    geography_type: 'state',
    year: r.year,
    race: r.race ?? 'total',
    metric: r.metric,
    value: r.value,
    margin_of_error: null,
  };
}

/** When year is null, collapse multi-year rows to the latest year per state+metric+race. */
export function collapseToLatestYear(rows: ExploreRow[]): ExploreRow[] {
  const byKey = new Map<string, ExploreRow>();
  for (const row of rows) {
    const key = `${row.state_fips}|${row.metric}|${row.race ?? ''}`;
    const prev = byKey.get(key);
    if (!prev || row.year > prev.year) byKey.set(key, row);
  }
  return [...byKey.values()];
}

export interface DataSourceConfig {
  key: string;
  label: string;
  accent: string;
  endpoint: string;
  hasRace: boolean;
  primaryFilterKey: string;
  primaryFilterLabel: string;
}

export const DATA_SOURCES: DataSourceConfig[] = [
  {
    key: "census",
    label: "Census ACS",
    accent: "#00ff32",
    endpoint: "/api/explore/indicators",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
  },
  {
    key: "cdc",
    label: "CDC Health",
    accent: "#ff6b6b",
    endpoint: "/api/explore/cdc",
    hasRace: false,
    primaryFilterKey: "measure",
    primaryFilterLabel: "Measure",
  },
  {
    key: "epa",
    label: "EPA Environment",
    accent: "#4ecdc4",
    endpoint: "/api/explore/epa",
    hasRace: false,
    primaryFilterKey: "indicator",
    primaryFilterLabel: "Indicator",
  },
  {
    key: "fbi",
    label: "FBI Crime",
    accent: "#ffd93d",
    endpoint: "/api/explore/fbi",
    hasRace: true,
    primaryFilterKey: "offense",
    primaryFilterLabel: "Offense",
  },
  {
    key: "bls",
    label: "BLS Labor",
    accent: "#6c5ce7",
    endpoint: "/api/explore/bls",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
  },
  {
    key: "hud",
    label: "HUD Housing",
    accent: "#fd79a8",
    endpoint: "/api/explore/hud",
    hasRace: false,
    primaryFilterKey: "indicator",
    primaryFilterLabel: "Indicator",
  },
  {
    key: "usda",
    label: "USDA Food",
    accent: "#00b894",
    endpoint: "/api/explore/usda",
    hasRace: false,
    primaryFilterKey: "indicator",
    primaryFilterLabel: "Indicator",
  },
  {
    key: "doe",
    label: "DOE Education",
    accent: "#fdcb6e",
    endpoint: "/api/explore/doe",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
  },
  {
    key: "police",
    label: "Police Violence",
    accent: "#e17055",
    endpoint: "/api/explore/police-violence",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
  },
];
