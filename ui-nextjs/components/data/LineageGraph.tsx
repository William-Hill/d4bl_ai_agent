'use client';

import { useState, useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeTypes,
  type NodeProps,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

/* ---------- node data types ---------- */

type SourceNodeData = { label: string; sourceType: string };
type AssetNodeData = { label: string; status: string };
type TableNodeData = { label: string; records: number };

type SourceNodeType = Node<SourceNodeData, 'source'>;
type AssetNodeType = Node<AssetNodeData, 'asset'>;
type TableNodeType = Node<TableNodeData, 'table'>;
export type LineageNode = SourceNodeType | AssetNodeType | TableNodeType;

/* ---------- custom node components ---------- */

function SourceNode({ data, selected }: NodeProps<SourceNodeType>) {
  return (
    <div
      className={`px-4 py-3 rounded-lg border bg-blue-900/60 border-blue-500 min-w-[160px]
        ${selected ? 'ring-2 ring-blue-400' : ''}`}
    >
      <p className="text-xs text-blue-300 uppercase tracking-wide mb-1">Source</p>
      <p className="text-sm font-semibold text-white">{data.label}</p>
      <p className="text-xs text-gray-400 mt-1">{data.sourceType}</p>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function AssetNode({ data, selected }: NodeProps<AssetNodeType>) {
  const statusColor = data.status === 'completed' ? 'text-green-400' : data.status === 'running' ? 'text-yellow-300' : 'text-gray-400';
  return (
    <div
      className={`px-4 py-3 rounded-lg border bg-yellow-900/60 border-yellow-500 min-w-[160px]
        ${selected ? 'ring-2 ring-yellow-400' : ''}`}
    >
      <Handle type="target" position={Position.Left} />
      <p className="text-xs text-yellow-300 uppercase tracking-wide mb-1">Asset</p>
      <p className="text-sm font-semibold text-white">{data.label}</p>
      <p className={`text-xs mt-1 ${statusColor}`}>{data.status}</p>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function TableNode({ data, selected }: NodeProps<TableNodeType>) {
  return (
    <div
      className={`px-4 py-3 rounded-lg border bg-green-900/60 border-green-500 min-w-[160px]
        ${selected ? 'ring-2 ring-green-400' : ''}`}
    >
      <Handle type="target" position={Position.Left} />
      <p className="text-xs text-green-300 uppercase tracking-wide mb-1">Table</p>
      <p className="text-sm font-semibold text-white">{data.label}</p>
      <p className="text-xs text-gray-400 mt-1">{data.records.toLocaleString()} records</p>
    </div>
  );
}

/* ---------- main component ---------- */

interface LineageGraphProps {
  nodes: LineageNode[];
  edges: Edge[];
}

export default function LineageGraph({ nodes: initialNodes, edges: initialEdges }: LineageGraphProps) {
  const [selectedNode, setSelectedNode] = useState<LineageNode | null>(null);

  const nodeTypes: NodeTypes = useMemo(
    () => ({
      source: SourceNode,
      asset: AssetNode,
      table: TableNode,
    }),
    [],
  );

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedNode(node as LineageNode);
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
              <span className="text-gray-200">{selectedNode.data.label}</span>
            </div>
            {'sourceType' in selectedNode.data && (
              <div>
                <span className="text-gray-400">Source Type:</span>{' '}
                <span className="text-gray-200">{selectedNode.data.sourceType}</span>
              </div>
            )}
            {'status' in selectedNode.data && (
              <div>
                <span className="text-gray-400">Status:</span>{' '}
                <span className="text-gray-200">{selectedNode.data.status}</span>
              </div>
            )}
            {'records' in selectedNode.data && (
              <div>
                <span className="text-gray-400">Records:</span>{' '}
                <span className="text-gray-200">{selectedNode.data.records.toLocaleString()}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
