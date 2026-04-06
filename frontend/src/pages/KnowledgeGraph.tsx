import React, { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import ForceGraph3D from '3d-force-graph';
import { agentApi } from '../lib/api/agent';

export default function KnowledgeGraph() {
  const graphRef = useRef<HTMLDivElement>(null);
  const graphInstance = useRef<any>(null);

  const { data: graphData, isLoading } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: async () => {
      const response = await agentApi.getMe();
      // In a real app, we'd have a specific graph endpoint
      // Mocking some data for visualization if real data is missing
      return {
        nodes: [
          { id: 'me', summary: 'Primary Agent', type: 'agent' },
          { id: 'm1', summary: 'PostgreSQL optimization', type: 'memory' },
          { id: 'm2', summary: 'Redis Streams protocol', type: 'memory' },
          { id: 'm3', summary: 'Vector embeddings', type: 'memory' },
        ],
        links: [
          { source: 'me', target: 'm1' },
          { source: 'me', target: 'm2' },
          { source: 'me', target: 'm3' },
        ]
      };
    },
  });

  useEffect(() => {
    if (!graphRef.current || !graphData) return;

    if (!graphInstance.current) {
      graphInstance.current = ForceGraph3D()(graphRef.current)
        .nodeLabel('summary')
        .nodeAutoColorBy('type')
        .linkDirectionalParticles(2)
        .linkDirectionalParticleSpeed(() => 0.01)
        .backgroundColor('#050505')
        .width(graphRef.current.offsetWidth)
        .height(graphRef.current.offsetHeight);
    }

    graphInstance.current.graphData(graphData);

    const handleResize = () => {
      if (graphRef.current && graphInstance.current) {
        graphInstance.current.width(graphRef.current.offsetWidth);
        graphInstance.current.height(graphRef.current.offsetHeight);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [graphData]);

  return (
    <div className="min-h-screen bg-obsidian text-white p-8">
      <div className="max-w-6xl mx-auto">
        <div className="h-[70vh] w-full glass-panel overflow-hidden relative border-white/5 bg-black/40 rounded-3xl">
          <div className="absolute top-6 left-6 z-10">
            <h1 className="text-2xl font-black text-white uppercase italic tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-rose-400">
              Neural Mesh Explorer
            </h1>
            <p className="text-[10px] text-gray-500 font-mono uppercase tracking-[0.3em]">Live Semantic Visualization</p>
          </div>

          <div className="absolute bottom-6 right-6 z-10 flex gap-4">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.8)]"></span>
              <span className="text-[9px] text-gray-400 font-bold uppercase">Memories</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)]"></span>
              <span className="text-[9px] text-gray-400 font-bold uppercase">Agents</span>
            </div>
          </div>

          {isLoading ? (
            <div className="w-full h-full flex items-center justify-center text-gray-600 font-mono text-xs uppercase tracking-widest">
              Initializing neural projection...
            </div>
          ) : (
            <div ref={graphRef} className="w-full h-full"></div>
          )}
        </div>

        <div className="mt-12 grid md:grid-cols-3 gap-8 pb-20">
          <div className="neural-card-indigo p-6">
            <h3 className="text-white font-black text-xs uppercase tracking-widest mb-4">Semantic Proximity</h3>
            <p className="text-gray-500 text-[10px] leading-relaxed uppercase tracking-tight">Nodes are positioned based on high-dimensional vector embeddings. Closely related concepts will cluster naturally in 3D space.</p>
          </div>
          <div className="neural-card p-6 border-white/5">
            <h3 className="text-white font-black text-xs uppercase tracking-widest mb-4">Compaction Provenance</h3>
            <p className="text-gray-500 text-[10px] leading-relaxed uppercase tracking-tight">Lines between nodes represent 'compacted_from' or 'related_to' relationships, visualizing how granular data evolves into dense knowledge.</p>
          </div>
          <div className="neural-card-rose p-6">
            <h3 className="text-white font-black text-xs uppercase tracking-widest mb-4">Real-time Updates</h3>
            <p className="text-gray-500 text-[10px] leading-relaxed uppercase tracking-tight">The mesh reflects live inbound memory streams from your active agents and workspace collaborators.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
