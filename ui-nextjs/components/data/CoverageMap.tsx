'use client';

import { useState } from 'react';
import { ComposableMap, Geographies, Geography, ZoomableGroup } from 'react-simple-maps';

const GEO_URL = 'https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json';

interface CoverageEntry {
  covered: boolean;
  records: number;
  lastUpdated: string | null;
}

interface Props {
  coverage: Record<string, CoverageEntry>;
}

function getFillColor(entry: CoverageEntry | undefined): string {
  if (!entry) return '#333';
  if (entry.covered) return '#00ff32';
  return '#991b1b';
}

export default function CoverageMap({ coverage }: Props) {
  const [tooltip, setTooltip] = useState<{
    name: string;
    covered: boolean;
    records: number;
    lastUpdated: string | null;
  } | null>(null);

  const isEmpty = Object.keys(coverage).length === 0;

  return (
    <div className="relative bg-[#1a1a1a] rounded-lg border border-[#404040] overflow-hidden">
      {isEmpty && (
        <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
          <p className="text-gray-500 text-sm">No coverage data available</p>
        </div>
      )}

      {tooltip && (
        <div className="absolute top-2 left-2 z-10 bg-[#292929] border border-[#404040] rounded px-3 py-2 text-sm text-gray-200 pointer-events-none">
          <p className="font-semibold text-white">{tooltip.name}</p>
          <p className="mt-1">
            <span className="text-gray-400">Status: </span>
            <span className={tooltip.covered ? 'text-[#00ff32]' : 'text-red-400'}>
              {tooltip.covered ? 'Covered' : 'Missing'}
            </span>
          </p>
          <p>
            <span className="text-gray-400">Records: </span>
            <span>{tooltip.records.toLocaleString()}</span>
          </p>
          <p>
            <span className="text-gray-400">Last Updated: </span>
            <span>{tooltip.lastUpdated ? new Date(tooltip.lastUpdated).toLocaleDateString() : 'N/A'}</span>
          </p>
        </div>
      )}

      <ComposableMap projection="geoAlbersUsa" style={{ width: '100%', height: 'auto' }}>
        <ZoomableGroup zoom={1}>
          <Geographies geography={GEO_URL}>
            {({ geographies }) =>
              geographies.map((geo) => {
                const fips = geo.id as string;
                const entry = coverage[fips];
                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={getFillColor(entry)}
                    stroke="#404040"
                    strokeWidth={0.5}
                    style={{
                      default: { outline: 'none' },
                      hover: { fill: entry?.covered ? '#00cc28' : entry ? '#b91c1c' : '#444', outline: 'none' },
                      pressed: { outline: 'none' },
                    }}
                    onMouseEnter={() => {
                      if (entry) {
                        setTooltip({
                          name: geo.properties.name,
                          covered: entry.covered,
                          records: entry.records,
                          lastUpdated: entry.lastUpdated,
                        });
                      } else if (!isEmpty) {
                        setTooltip({
                          name: geo.properties.name,
                          covered: false,
                          records: 0,
                          lastUpdated: null,
                        });
                      }
                    }}
                    onMouseLeave={() => setTooltip(null)}
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
