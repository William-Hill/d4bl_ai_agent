'use client';

import { useState } from 'react';

interface CronBuilderProps {
  value: string | null;
  onChange: (cron: string | null) => void;
}

const PRESETS = [
  { label: 'Every hour', cron: '0 * * * *', description: 'Runs at the start of every hour' },
  { label: 'Daily at 2am', cron: '0 2 * * *', description: 'Runs every day at 2:00 AM' },
  { label: 'Weekly on Monday', cron: '0 2 * * 1', description: 'Runs every Monday at 2:00 AM' },
  { label: 'Monthly on 1st', cron: '0 2 1 * *', description: 'Runs on the 1st of every month at 2:00 AM' },
];

export function describeCron(cron: string | null): string {
  if (!cron) return 'No schedule set';
  const preset = PRESETS.find((p) => p.cron === cron);
  if (preset) return preset.description;
  return `Custom: ${cron}`;
}

export default function CronBuilder({ value, onChange }: CronBuilderProps) {
  const isCustomValue = value !== null && !PRESETS.some((p) => p.cron === value);
  const [customInput, setCustomInput] = useState(isCustomValue ? value : '');

  return (
    <div className="space-y-4">
      {/* Preset buttons */}
      <div className="grid grid-cols-2 gap-3">
        {PRESETS.map((preset) => (
          <button
            key={preset.cron}
            type="button"
            onClick={() => {
              onChange(preset.cron);
              setCustomInput('');
            }}
            className={`px-4 py-3 rounded-lg border text-left transition-colors ${
              value === preset.cron
                ? 'border-[#00ff32] bg-[#00ff32]/10 text-white'
                : 'border-[#404040] bg-[#1a1a1a] text-gray-300 hover:border-gray-500'
            }`}
          >
            <span className="block text-sm font-medium">{preset.label}</span>
            <span className="block text-xs text-gray-500 mt-0.5">{preset.cron}</span>
          </button>
        ))}
      </div>

      {/* Custom cron input */}
      <div>
        <label className="block text-sm text-gray-400 mb-1">Custom cron expression</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={customInput}
            onChange={(e) => setCustomInput(e.target.value)}
            placeholder="e.g. */15 * * * *"
            className="flex-1 px-3 py-2 bg-[#1a1a1a] border border-[#404040] rounded text-white text-sm placeholder-gray-600 focus:border-[#00ff32] focus:outline-none"
          />
          <button
            type="button"
            onClick={() => {
              if (customInput.trim()) {
                onChange(customInput.trim());
              }
            }}
            className="px-4 py-2 bg-[#404040] text-gray-300 rounded text-sm hover:bg-[#505050] transition-colors"
          >
            Apply
          </button>
        </div>
      </div>

      {/* No schedule option */}
      <button
        type="button"
        onClick={() => {
          onChange(null);
          setCustomInput('');
        }}
        className={`w-full px-4 py-2 rounded-lg border text-sm transition-colors ${
          value === null
            ? 'border-[#00ff32] bg-[#00ff32]/10 text-white'
            : 'border-[#404040] bg-[#1a1a1a] text-gray-400 hover:border-gray-500'
        }`}
      >
        No schedule (manual triggers only)
      </button>

      {/* Preview */}
      <div className="px-3 py-2 bg-[#292929] border border-[#404040] rounded text-sm">
        <span className="text-gray-500">Preview: </span>
        <span className="text-gray-300">{describeCron(value)}</span>
      </div>
    </div>
  );
}
