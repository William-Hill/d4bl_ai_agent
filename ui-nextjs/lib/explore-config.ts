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
