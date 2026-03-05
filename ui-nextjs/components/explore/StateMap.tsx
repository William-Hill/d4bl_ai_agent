'use client';

import { useState } from 'react';
import { ComposableMap, Geographies, Geography, ZoomableGroup } from 'react-simple-maps';
import { scaleLinear } from 'd3-scale';
import { IndicatorRow } from '@/lib/types';

const GEO_URL = 'https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json';

interface Props {
  indicators: IndicatorRow[];
  selectedStateFips: string | null;
  onSelectState: (fips: string, name: string) => void;
}

export default function StateMap({ indicators, selectedStateFips, onSelectState }: Props) {
  const [tooltip, setTooltip] = useState<{ name: string; value: number } | null>(null);

  const valueByFips: Record<string, number> = {};
  for (const row of indicators) {
    if (row.fips_code.length === 2) {
      valueByFips[row.fips_code] = row.value;
    }
  }

  const values = Object.values(valueByFips);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 100;

  const colorScale = scaleLinear<string>().domain([min, max]).range(['#1a3a1a', '#00ff32']);

  return (
    <div className="relative bg-[#1a1a1a] rounded-lg border border-[#404040] overflow-hidden">
      {tooltip && (
        <div className="absolute top-2 left-2 z-10 bg-[#292929] border border-[#404040] rounded px-3 py-1.5 text-sm text-gray-200 pointer-events-none">
          <span className="font-semibold text-[#00ff32]">{tooltip.name}</span>
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
                    stroke={isSelected ? '#00ff32' : '#404040'}
                    strokeWidth={isSelected ? 2 : 0.5}
                    style={{
                      default: { cursor: 'pointer' },
                      hover: { fill: '#00cc28', outline: 'none', cursor: 'pointer' },
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

