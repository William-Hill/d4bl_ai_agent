'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { DATA_SOURCES, DataSourceConfig } from '@/lib/explore-config';

interface Props {
  activeKey: string;
  onSelect: (source: DataSourceConfig) => void;
}

const SCROLL_STEP = 240;

export default function DataSourceTabs({ activeKey, onSelect }: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateOverflow = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 2);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 2);
  }, []);

  useEffect(() => {
    updateOverflow();
    const el = scrollerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(updateOverflow);
    ro.observe(el);
    el.addEventListener('scroll', updateOverflow, { passive: true });
    return () => {
      ro.disconnect();
      el.removeEventListener('scroll', updateOverflow);
    };
  }, [updateOverflow]);

  const scrollBy = (delta: number) => {
    scrollerRef.current?.scrollBy({ left: delta, behavior: 'smooth' });
  };

  return (
    <div className="relative mb-6">
      {canScrollLeft && (
        <>
          <div
            aria-hidden
            className="pointer-events-none absolute left-0 top-0 bottom-2 w-12 z-10
                       bg-gradient-to-r from-[#1a1a1a] to-transparent"
          />
          <button
            type="button"
            aria-label="Scroll tabs left"
            onClick={() => scrollBy(-SCROLL_STEP)}
            className="absolute left-0 top-1/2 -translate-y-1/2 z-20
                       w-8 h-8 rounded-full bg-[#262626] border border-[#404040]
                       text-gray-300 hover:text-white hover:border-gray-500
                       flex items-center justify-center
                       transition-colors shadow-lg shadow-black/40"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
        </>
      )}

      <div
        ref={scrollerRef}
        className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin scroll-smooth"
      >
        {DATA_SOURCES.filter((src) => src.hasData).map((src) => {
          const isActive = src.key === activeKey;
          const isPolicy = src.key === 'policy';
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
              {isPolicy && !isActive && (
                <span className="relative inline-flex mr-2 align-middle" aria-hidden>
                  <span
                    className="absolute inline-flex h-2 w-2 rounded-full opacity-60 animate-ping"
                    style={{ backgroundColor: src.accent }}
                  />
                  <span
                    className="relative inline-flex h-2 w-2 rounded-full"
                    style={{ backgroundColor: src.accent }}
                  />
                </span>
              )}
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

      {canScrollRight && (
        <>
          <div
            aria-hidden
            className="pointer-events-none absolute right-0 top-0 bottom-2 w-12 z-10
                       bg-gradient-to-l from-[#1a1a1a] to-transparent"
          />
          <button
            type="button"
            aria-label="Scroll tabs right"
            onClick={() => scrollBy(SCROLL_STEP)}
            className="absolute right-0 top-1/2 -translate-y-1/2 z-20
                       w-8 h-8 rounded-full bg-[#262626] border border-[#404040]
                       text-gray-300 hover:text-white hover:border-gray-500
                       flex items-center justify-center
                       transition-colors shadow-lg shadow-black/40"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </>
      )}
    </div>
  );
}
