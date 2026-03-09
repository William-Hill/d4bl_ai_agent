interface SourceHealthCardsProps {
  totalSources: number;
  enabledSources: number;
  recentFailures: number;
}

export default function SourceHealthCards({
  totalSources,
  enabledSources,
  recentFailures,
}: SourceHealthCardsProps) {
  const healthy = Math.max(0, enabledSources - recentFailures);
  const disabled = totalSources - enabledSources;

  const cards = [
    { label: 'Total Sources', value: totalSources, color: 'text-gray-300' },
    { label: 'Healthy', value: healthy, color: 'text-[#00ff32]' },
    { label: 'Failing', value: recentFailures, color: 'text-red-400' },
    { label: 'Disabled', value: disabled, color: 'text-gray-500' },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4"
        >
          <p className="text-xs text-gray-400 mb-1">{card.label}</p>
          <p className={`text-2xl font-bold ${card.color}`}>{card.value}</p>
        </div>
      ))}
    </div>
  );
}
