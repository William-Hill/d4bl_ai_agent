'use client';

interface ProgressCardProps {
  progress: string;
  isConnected: boolean;
}

export default function ProgressCard({ progress, isConnected }: ProgressCardProps) {
  return (
    <div className="bg-[#333333] border border-[#404040] rounded-lg p-8 shadow-sm">
      <h2 className="text-2xl font-bold text-white mb-6">
        Research Progress
      </h2>
      <div className="space-y-4">
        <div className="w-full bg-[#1a1a1a] rounded-full h-2">
          <div
            className="bg-[#00ff32] h-2 rounded-full transition-all duration-300 animate-pulse"
            style={{ width: '75%' }}
          />
        </div>
        <div className="flex items-center justify-between">
          <p className="text-gray-200 font-medium">{progress || 'Processing...'}</p>
          <div className="flex items-center space-x-2">
            <div
              className={`w-2 h-2 rounded-full ${
                isConnected ? 'bg-[#00ff32]' : 'bg-red-500'
              }`}
            />
            <span className="text-sm text-gray-300 font-medium">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

