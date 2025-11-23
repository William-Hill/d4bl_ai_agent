'use client';

interface ErrorCardProps {
  message: string;
  onDismiss: () => void;
}

export default function ErrorCard({ message, onDismiss }: ErrorCardProps) {
  return (
    <div className="bg-red-900/20 border-l-4 border-red-500 rounded-lg shadow-sm p-6 border border-red-500/30">
      <h2 className="text-xl font-bold text-red-400 mb-2">Error</h2>
      <p className="text-red-300 mb-4">{message}</p>
      <button
        onClick={onDismiss}
        className="bg-[#00ff32] text-black py-2 px-4 rounded-md hover:bg-[#00cc28] focus:outline-none focus:ring-2 focus:ring-[#00ff32] focus:ring-offset-2 focus:ring-offset-[#292929] transition-colors font-medium"
      >
        Dismiss
      </button>
    </div>
  );
}

