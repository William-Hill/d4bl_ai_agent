'use client';

interface ProgressCardProps {
  progress: string;
  isConnected: boolean;
  phase?: string | null;
}

export default function ProgressCard({ progress, isConnected, phase }: ProgressCardProps) {
  const isWarmup = isConnected && phase === 'warmup';

  // Disconnected always wins, then warmup, then connected
  const dotClass = !isConnected
    ? 'bg-red-500'
    : isWarmup
      ? 'bg-amber-500 animate-pulse'
      : 'bg-[#00ff32]';

  const statusLabel = !isConnected
    ? 'Disconnected'
    : isWarmup
      ? 'Warming up...'
      : 'Connected';

  // Progress bar: amber during warmup, green otherwise
  const barColor = isWarmup ? 'bg-amber-500/50' : 'bg-[#00ff32]/50';

  return (
    <div className="bg-[#333333] border border-[#404040] rounded-lg p-8 shadow-sm">
      <h2 className="text-2xl font-bold text-white mb-6">
        Research Progress
      </h2>
      <div className="space-y-4">
        <div className="w-full bg-[#1a1a1a] rounded-full h-2">
          <div className={`${barColor} h-2 rounded-full w-full animate-pulse`} />
        </div>
        <div className="flex items-center justify-between" role="status" aria-live="polite" aria-atomic="true">
          <p className="text-gray-200 font-medium">{progress || 'Processing...'}</p>
          <div className="flex items-center space-x-2">
            <div className={`w-2 h-2 rounded-full ${dotClass}`} />
            <span className="text-sm text-gray-300 font-medium">
              {statusLabel}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
