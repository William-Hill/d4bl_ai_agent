'use client';

import { useMemo } from 'react';
import type { Node, Edge } from '@xyflow/react';
import LineageGraph from '@/components/data/LineageGraph';

export default function LineagePage() {
  const { nodes, edges } = useMemo(() => {
    const mockNodes: Node[] = [
      // Sources (x=0)
      { id: 'src-1', type: 'source', position: { x: 0, y: 0 }, data: { label: 'Census ACS API', sourceType: 'api' } },
      { id: 'src-2', type: 'source', position: { x: 0, y: 150 }, data: { label: 'OpenStates API', sourceType: 'api' } },
      { id: 'src-3', type: 'source', position: { x: 0, y: 300 }, data: { label: 'RSS Feeds', sourceType: 'rss_feed' } },
      // Assets (x=300)
      { id: 'asset-1', type: 'asset', position: { x: 300, y: 0 }, data: { label: 'census_acs_indicators', status: 'completed' } },
      { id: 'asset-2', type: 'asset', position: { x: 300, y: 150 }, data: { label: 'openstates_bills', status: 'completed' } },
      { id: 'asset-3', type: 'asset', position: { x: 300, y: 300 }, data: { label: 'rss_articles', status: 'pending' } },
      // Tables (x=600)
      { id: 'table-1', type: 'table', position: { x: 600, y: 75 }, data: { label: 'census_indicators', records: 2450 } },
      { id: 'table-2', type: 'table', position: { x: 600, y: 225 }, data: { label: 'policy_bills', records: 1832 } },
    ];

    const mockEdges: Edge[] = [
      { id: 'e1', source: 'src-1', target: 'asset-1', animated: true },
      { id: 'e2', source: 'src-2', target: 'asset-2', animated: true },
      { id: 'e3', source: 'src-3', target: 'asset-3', animated: true },
      { id: 'e4', source: 'asset-1', target: 'table-1', animated: true },
      { id: 'e5', source: 'asset-2', target: 'table-2', animated: true },
    ];

    return { nodes: mockNodes, edges: mockEdges };
  }, []);

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-white mb-2">Lineage Explorer</h1>
          <p className="text-gray-400">
            Visualize data flow from sources through processing assets to output tables.
          </p>
        </div>

        <div className="min-h-[600px] rounded-lg overflow-hidden border border-[#404040]">
          <LineageGraph nodes={nodes} edges={edges} />
        </div>

        <p className="mt-4 text-sm text-gray-500 italic">
          Lineage data will be populated as ingestion runs complete.
        </p>
      </div>
    </div>
  );
}
