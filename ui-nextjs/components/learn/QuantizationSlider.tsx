'use client';

import { useState } from 'react';

interface QuantLevel {
  label: string;
  fileSize: number;  // GB
  quality: number;   // percentage
}

const LEVELS: QuantLevel[] = [
  { label: 'FP16',   fileSize: 6.2, quality: 100 },
  { label: 'Q8',     fileSize: 3.3, quality: 99 },
  { label: 'Q6_K',   fileSize: 2.5, quality: 97 },
  { label: 'Q5_K_M', fileSize: 2.1, quality: 95 },
  { label: 'Q4_K_M', fileSize: 1.8, quality: 93 },
  { label: 'Q3_K',   fileSize: 1.4, quality: 85 },
  { label: 'Q2',     fileSize: 1.1, quality: 72 },
];

const OUR_PICK = 'Q4_K_M';

function qualityColor(quality: number): string {
  if (quality >= 93) return '#00ff32';
  if (quality >= 85) return '#fbbf24';
  return '#ef4444';
}

export default function QuantizationSlider() {
  const [index, setIndex] = useState(4); // default to Q4_K_M
  const level = LEVELS[index];
  const isOurPick = level.label === OUR_PICK;

  return (
    <div>
      {/* Slider */}
      <div className="mb-8">
        <label className="block text-sm text-gray-400 mb-2">
          Quantization:{' '}
          <span className="text-white font-mono font-bold">{level.label}</span>
        </label>
        <input
          type="range"
          min={0}
          max={LEVELS.length - 1}
          step={1}
          value={index}
          onChange={(e) => setIndex(Number(e.target.value))}
          className="w-full accent-[#00ff32]"
          aria-label="Quantization level slider"
        />
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          {LEVELS.map((l) => (
            <span key={l.label}>{l.label}</span>
          ))}
        </div>
      </div>

      {/* Bar chart + quality */}
      <div className="grid md:grid-cols-2 gap-6 mb-6">
        {/* File size bar */}
        <div className="bg-[#292929] rounded-lg p-6">
          <p className="text-xs text-gray-500 uppercase mb-3">Model File Size</p>
          <div className="relative h-8 bg-[#404040] rounded-full overflow-hidden">
            <div
              className="h-full bg-[#00ff32]/60 rounded-full transition-all duration-300"
              style={{ width: `${(level.fileSize / 6.2) * 100}%` }}
            />
          </div>
          <p className="text-right text-lg font-mono text-white mt-2">
            {level.fileSize} GB
          </p>
        </div>

        {/* Quality indicator */}
        <div className="bg-[#292929] rounded-lg p-6">
          <p className="text-xs text-gray-500 uppercase mb-3">Quality Retained</p>
          <div className="relative h-8 bg-[#404040] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${level.quality}%`,
                backgroundColor: qualityColor(level.quality),
                opacity: 0.6,
              }}
            />
          </div>
          <p
            className="text-right text-lg font-mono mt-2"
            style={{ color: qualityColor(level.quality) }}
          >
            {level.quality}%
          </p>
        </div>
      </div>

      {/* Callout */}
      {isOurPick && (
        <div className="px-4 py-2 bg-[#00ff32]/10 border border-[#00ff32]/30 rounded-lg text-sm text-[#00ff32] text-center">
          This is what we use — Q4_K_M cuts the file size by 70% while keeping 93% quality.
          The sweet spot for running on a laptop or affordable GPU.
        </div>
      )}
    </div>
  );
}
