'use client';

import { useState } from 'react';

const HIDDEN_DIM = 3072; // Qwen2.5-3B
const BASE_PARAMS = 3_000_000_000;

const VRAM_TABLE: Record<number, string> = {
  4: '~0.1 GB',
  8: '~0.2 GB',
  16: '~0.4 GB',
  32: '~0.8 GB',
  64: '~1.5 GB',
};

function formatParams(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

const VRAM_KEYS = Object.keys(VRAM_TABLE).map(Number).sort((a, b) => a - b);

function nearestVram(rank: number): string {
  let closest = VRAM_KEYS[0];
  for (const k of VRAM_KEYS) {
    if (Math.abs(k - rank) <= Math.abs(closest - rank)) closest = k;
  }
  return VRAM_TABLE[closest];
}

export default function LoRAVisualizer() {
  const [rank, setRank] = useState(16);

  const adapterParams = 2 * rank * HIDDEN_DIM;
  const percentage = ((adapterParams / BASE_PARAMS) * 100).toFixed(4);
  const vram = nearestVram(rank);

  // Visual: adapter width as percentage of base block (scaled for visibility)
  const adapterWidthPct = Math.max(4, (rank / 64) * 40);

  return (
    <div>
      <div className="mb-8">
        <label htmlFor="lora-rank" className="block text-sm text-gray-400 mb-2">
          LoRA Rank: <span className="text-white font-mono font-bold">{rank}</span>
        </label>
        <input
          id="lora-rank"
          type="range"
          min={4}
          max={64}
          step={4}
          value={rank}
          onChange={(e) => setRank(Number(e.target.value))}
          className="w-full accent-[#00ff32]"
        />
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          <span>4</span>
          <span>16</span>
          <span>32</span>
          <span>48</span>
          <span>64</span>
        </div>
      </div>

      <div className="flex items-end gap-3 mb-6 h-32">
        <div className="bg-[#404040] rounded-lg flex-1 h-full flex items-center justify-center">
          <div className="text-center">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Base Model</p>
            <p className="text-lg font-mono text-white">3B params</p>
          </div>
        </div>
        <div
          className="bg-[#00ff32]/20 border border-[#00ff32]/40 rounded-lg h-full flex items-center justify-center transition-all duration-300"
          style={{ width: `${adapterWidthPct}%`, minWidth: '60px' }}
        >
          <div className="text-center px-2">
            <p className="text-xs text-[#00ff32] uppercase tracking-wide">Adapter</p>
            <p className="text-sm font-mono text-white">{formatParams(adapterParams)}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 text-center">
        <div className="bg-[#292929] rounded-lg p-4">
          <p className="text-xs text-gray-500 uppercase mb-1">Parameters</p>
          <p className="text-lg font-mono text-white">{formatParams(adapterParams)}</p>
        </div>
        <div className="bg-[#292929] rounded-lg p-4">
          <p className="text-xs text-gray-500 uppercase mb-1">% of Base</p>
          <p className="text-lg font-mono text-white">{percentage}%</p>
        </div>
        <div className="bg-[#292929] rounded-lg p-4">
          <p className="text-xs text-gray-500 uppercase mb-1">VRAM Overhead</p>
          <p className="text-lg font-mono text-white">{vram}</p>
        </div>
      </div>

      {rank === 16 && (
        <div className="mt-4 px-4 py-2 bg-[#00ff32]/10 border border-[#00ff32]/30 rounded-lg text-sm text-[#00ff32] text-center">
          This is what we use — rank 16 gives strong results with minimal overhead.
        </div>
      )}
    </div>
  );
}
