'use client';

import { useState, useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  type Node,
  type Edge,
  type NodeTypes,
  type NodeProps,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

/* ---------- custom node components ---------- */

function SourceNode({ data, selected }: NodeProps) {
  return (
    <div
      className={`px-4 py-3 rounded-lg border bg-blue-900/60 border-blue-500 min-w-[160px]
        ${selected ? 'ring-2 ring-blue-400' : ''}`}
    >
      <p className="text-xs text-blue-300 uppercase tracking-wide mb-1">Source</p>
      <p className="text-sm font-semibold text-white">{data.label as string}</p>
      <p className="text-xs text-gray-400 mt-1">{data.sourceType as string}</p>
    </div>
  );
}

function AssetNode({ data, selected }: NodeProps) {
  const status = data.status as string;
  const statusColor = status === 'completed' ? 'text-green-400' : status === 'running' ? 'text-yellow-300' : 'text-gray-400';
  return (
    <div
      className={`px-4 py-3 rounded-lg border bg-yellow-900/60 border-yellow-500 min-w-[160px]
        ${selected ? 'ring-2 ring-yellow-400' : ''}`}
    >
      <p className="text-xs text-yellow-300 uppercase tracking-wide mb-1">Asset</p>
      <p className="text-sm font-semibold text-white">{data.label as string}</p>
      <p className={`text-xs mt-1 ${statusColor}`}>{status}</p>
    </div>
  );
}

function TableNode({ data, selected }: NodeProps) {
  return (
    <div
      className={`px-4 py-3 rounded-lg border bg-green-900/60 border-green-500 min-w-[160px]
        ${selected ? 'ring-2 ring-green-400' : ''}`}
    >
      <p className="text-xs text-green-300 uppercase tracking-wide mb-1">Table</p>
      <p className="text-sm font-semibold text-white">{data.label as string}</p>
      <p className="text-xs text-gray-400 mt-1">{(data.records as number).toLocaleString()} records</p>
    </div>
  );
}

/* ---------- main component ---------- */

interface LineageGraphProps {
  nodes: Node[];
  edges: Edge[];
}

export default function LineageGraph({ nodes: initialNodes, edges: initialEdges }: LineageGraphProps) {
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  const nodeTypes: NodeTypes = useMemo(
    () => ({
      source: SourceNode,
      asset: AssetNode,
      table: TableNode,
    }),
    [],
  );

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  return (
    <div className="flex flex-col h-full min-h-[600px]">
      <div className="flex-1 bg-[#1a1a1a]">
        <ReactFlow
          nodes={initialNodes}
          edges={initialEdges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          fitView
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{ style: { stroke: '#404040', strokeWidth: 2 } }}
        >
          <Controls className="!bg-[#292929] !border-[#404040] !rounded-lg [&>button]:!bg-[#292929] [&>button]:!border-[#404040] [&>button]:!text-gray-300 [&>button:hover]:!bg-[#333]" />
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#333" />
        </ReactFlow>
      </div>

      {selectedNode && (
        <div className="border-t border-[#404040] bg-[#1a1a1a] px-6 py-4">
          <h3 className="text-sm font-semibold text-white mb-2">Node Details</h3>
          <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm">
            <div>
              <span className="text-gray-400">Type:</span>{' '}
              <span className="text-gray-200 capitalize">{selectedNode.type}</span>
            </div>
            <div>
              <span className="text-gray-400">Name:</span>{' '}
              <span className="text-gray-200">{selectedNode.data.label as string}</span>
            </div>
            {selectedNode.data.sourceType != null && (
              <div>
                <span className="text-gray-400">Source Type:</span>{' '}
                <span className="text-gray-200">{String(selectedNode.data.sourceType)}</span>
              </div>
            )}
            {selectedNode.data.status != null && (
              <div>
                <span className="text-gray-400">Status:</span>{' '}
                <span className="text-gray-200">{String(selectedNode.data.status)}</span>
              </div>
            )}
            {selectedNode.data.records !== undefined && (
              <div>
                <span className="text-gray-400">Records:</span>{' '}
                <span className="text-gray-200">{(selectedNode.data.records as number).toLocaleString()}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
