interface Props {
  sourceName: string;
  accent: string;
}

export default function EmptyDataState({ sourceName, accent }: Props) {
  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-12 text-center">
      <div
        className="inline-block w-12 h-12 rounded-full mb-4 opacity-30"
        style={{ backgroundColor: accent }}
      />
      <h3 className="text-lg font-semibold text-white mb-2">
        No {sourceName} data available
      </h3>
      <p className="text-gray-500 text-sm max-w-md mx-auto">
        This data source has not been ingested yet. Run the corresponding
        Dagster pipeline to populate it.
      </p>
    </div>
  );
}
