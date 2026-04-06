'use client';

interface ProgressCardProps {
  progress: string;
  isConnected: boolean;
  phase?: string | null;
}

export default function ProgressCard({ progress, isConnected, phase }: ProgressCardProps) {
  const isWarmup = phase === 'warmup';

  // Dot: amber pulsing during warmup, green when connected, red when disconnected
  const dotClass = isWarmup
    ? 'bg-amber-500 animate-pulse'
    : isConnected
      ? 'bg-[#00ff32]'
      : 'bg-red-500';

  const statusLabel = isWarmup
    ? 'Warming up...'
    : isConnected
      ? 'Connected'
      : 'Disconnected';

  // Progress bar: amber during warmup, green otherwise
  const baseBar = 'h-2 rounded-full w-full animate-pulse';
  const colorClass = isWarmup ? 'bg-amber-500/50' : 'bg-[#00ff32]/50';
  const barClass = `${colorClass} ${baseBar}`;

  return (
    <div className="bg-[#333333] border border-[#404040] rounded-lg p-8 shadow-sm">
      <h2 className="text-2xl font-bold text-white mb-6">
        Research Progress
      </h2>
      <div className="space-y-4">
        <div className="w-full bg-[#1a1a1a] rounded-full h-2">
          <div className={barClass} />
        </div>
        <div className="flex items-center justify-between">
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
