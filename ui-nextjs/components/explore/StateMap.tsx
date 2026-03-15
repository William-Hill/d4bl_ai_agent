'use client';

import { useMemo, useState } from 'react';
import { ComposableMap, Geographies, Geography, ZoomableGroup } from 'react-simple-maps';
import { interpolateRgb } from 'd3-interpolate';
import { IndicatorRow } from '@/lib/types';

const GEO_URL = 'https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json';

interface Props {
  indicators: IndicatorRow[];
  selectedStateFips: string | null;
  onSelectState: (fips: string, name: string) => void;
  accent?: string;
  nationalAverage?: number | null;
  colorStart?: string;
  colorEnd?: string;
}

export default function StateMap({
  indicators,
  selectedStateFips,
  onSelectState,
  accent,
  nationalAverage: _nationalAverage, // eslint-disable-line @typescript-eslint/no-unused-vars
  colorStart,
  colorEnd,
}: Props) {
  const [tooltip, setTooltip] = useState<{ name: string; value: number } | null>(null);

  const accentColor = accent ?? '#00ff32';

  const { valueByFips, colorScale } = useMemo(() => {
    const vByFips: Record<string, number> = {};
    for (const row of indicators) {
      const fips = row.fips_code ?? row.state_fips;
      if (typeof fips === 'string' && fips.length === 2) {
        vByFips[fips] = row.value;
      }
    }

    const values = Object.values(vByFips);
    const min = values.length ? Math.min(...values) : 0;
    const max = values.length ? Math.max(...values) : 100;

    const start = colorStart || '#444';
    const end = colorEnd || accentColor;

    const scale = (val: number): string => {
      if (min === max) return end;
      const t = (val - min) / (max - min);
      return interpolateRgb(start, end)(Math.min(Math.max(t, 0), 1));
    };

    return { valueByFips: vByFips, colorScale: scale };
  }, [indicators, accentColor, colorStart, colorEnd]);

  return (
    <div className="relative bg-[#1a1a1a] rounded-lg border border-[#404040] overflow-hidden">
      {tooltip && (
        <div className="absolute top-2 left-2 z-10 bg-[#292929] border border-[#404040] rounded px-3 py-1.5 text-sm text-gray-200 pointer-events-none">
          <span className="font-semibold" style={{ color: accentColor }}>{tooltip.name}</span>
          <span className="ml-2">{tooltip.value.toLocaleString()}</span>
        </div>
      )}
      <ComposableMap projection="geoAlbersUsa" style={{ width: '100%', height: 'auto' }}>
        <ZoomableGroup zoom={1}>
          <Geographies geography={GEO_URL}>
            {({ geographies }) =>
              geographies.map((geo) => {
                const fips = geo.id as string;
                const value = valueByFips[fips];
                const isSelected = fips === selectedStateFips;
                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    role="button"
                    tabIndex={0}
                    aria-label={`Select ${geo.properties.name}`}
                    fill={value !== undefined ? colorScale(value) : '#333'}
                    stroke={isSelected ? accentColor : '#404040'}
                    strokeWidth={isSelected ? 2 : 0.5}
                    style={{
                      default: { cursor: 'pointer' },
                      hover: { fill: accentColor, outline: 'none', cursor: 'pointer', opacity: 0.8 },
                      pressed: { outline: 'none' },
                    }}
                    onMouseEnter={() => {
                      if (value !== undefined) {
                        setTooltip({ name: geo.properties.name, value });
                      }
                    }}
                    onMouseLeave={() => setTooltip(null)}
                    onClick={() => onSelectState(fips, geo.properties.name)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onSelectState(fips, geo.properties.name);
                      }
                    }}
                  />
                );
              })
            }
          </Geographies>
        </ZoomableGroup>
      </ComposableMap>
    </div>
  );
}
