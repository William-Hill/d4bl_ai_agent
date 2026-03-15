'use client';

import { DATA_SOURCES, DataSourceConfig } from '@/lib/explore-config';

interface Props {
  activeKey: string;
  onSelect: (source: DataSourceConfig) => void;
}

export default function DataSourceTabs({ activeKey, onSelect }: Props) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-2 mb-6 scrollbar-thin">
      {DATA_SOURCES.filter((src) => src.hasData).map((src) => {
        const isActive = src.key === activeKey;
        return (
          <button
            key={src.key}
            type="button"
            onClick={() => onSelect(src)}
            className={`
              relative flex-shrink-0 px-4 py-2 rounded-full text-sm font-medium
              transition-all duration-200 border
              ${isActive
                ? 'text-white border-transparent'
                : 'text-gray-400 border-[#404040] hover:text-white hover:border-gray-500'
              }
            `}
            style={isActive ? {
              backgroundColor: `${src.accent}20`,
              borderColor: src.accent,
              color: src.accent,
            } : undefined}
          >
            {src.label}
            {isActive && (
              <span
                className="absolute bottom-0 left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-full"
                style={{ backgroundColor: src.accent, boxShadow: `0 0 8px ${src.accent}60` }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
