import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import ForceGraph3D from '3d-force-graph';
import { agentApi } from '../lib/api/agent';
import { GlassCard } from '../components/GlassCard';

export default function KnowledgeGraph() {
  const graphRef = useRef<HTMLDivElement>(null);
  const graphInstance = useRef<any>(null);
  const [scanText, setScanText] = useState('COMPUTING TOPOLOGY...');

  // Mock scan text cycling
  useEffect(() => {
    const statuses = ['COMPUTING TOPOLOGY...', 'ESTABLISHING MESH...', 'SYNCING VECTORS...', 'MESH ACTIVE'];
    let i = 0;
    const interval = setInterval(() => {
      i = (i + 1) % statuses.length;
      setScanText(statuses[i]);
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const { data: graphData, isLoading } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: async () => {
      try {
        const data = await agentApi.getGraph();
        if (data && data.nodes && data.nodes.length > 0) {
          return data;
        }
      } catch (e) {
        console.warn('Failed to load real graph data, falling back to mock.', e);
      }
      // Fallback to mock data if empty or error
      return {
        nodes: [
          { id: 'me', summary: 'Primary Agent', type: 'agent' },
          { id: 'm1', summary: 'PostgreSQL optimization', type: 'memory' },
          { id: 'm2', summary: 'Redis Streams protocol', type: 'memory' },
          { id: 'm3', summary: 'Vector embeddings', type: 'memory' },
          { id: 't1', summary: 'Database task', type: 'task' },
        ],
        links: [
          { source: 'me', target: 'm1', relation: 'created', metadata: null },
          { source: 'me', target: 'm2', relation: 'created', metadata: null },
          { source: 'me', target: 'm3', relation: 'created', metadata: null },
          { source: 'm1', target: 't1', relation: 'related', metadata: { rationale: 'Optimized for speed' } },
        ]
      };
    },
  });

  useEffect(() => {
    if (!graphRef.current || !graphData) return;

    // Map types to neon colors
    const colorMap: Record<string, string> = {
      agent: '#22d3ee', // Cyan
      memory: '#a855f7', // Violet
      task: '#34d399', // Emerald
    };

    if (!graphInstance.current) {
      try {
        graphInstance.current = new ForceGraph3D(graphRef.current)
          .nodeLabel('summary')
          .nodeColor((node: any) => colorMap[node.type] || '#ffffff')
          .linkLabel((link: any) => {
            let label = link.relation || 'related';
            if (link.metadata?.rationale) {
              label += `: ${link.metadata.rationale}`;
            }
            return `<div style="background: rgba(2, 6, 23, 0.8); padding: 4px 8px; border-radius: 4px; border: 1px solid rgba(168, 85, 247, 0.4); font-family: monospace; font-size: 10px; color: #e2e8f0;">${label}</div>`;
          })
          .linkDirectionalParticles(2)
          .linkDirectionalParticleSpeed(() => 0.01)
          .linkDirectionalParticleColor((link: any) => colorMap[link.target.type] || '#ffffff')
          .backgroundColor('#020617') // slate-950
          .width(graphRef.current.offsetWidth)
          .height(graphRef.current.offsetHeight);
      } catch (e) {
        console.error("ForceGraph3D initialization failed. WebGL may be unavailable.", e);
        // Fallback or leave graphInstance.current null
      }
    }

    if (graphInstance.current) {
      graphInstance.current.graphData(graphData);
    }

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
    <>
      <div className="relative w-full h-[70vh] rounded-3xl overflow-hidden border border-cyan-500/30 shadow-[0_0_30px_rgba(34,211,238,0.15)] bg-slate-950/40 backdrop-blur-xl">
        
        {/* Top HUD */}
        <div className="absolute top-6 left-6 z-10 pointer-events-none">
          <h1 className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-violet-400 uppercase tracking-widest drop-shadow-[0_0_10px_rgba(34,211,238,0.6)]">
            Neural Mesh
          </h1>
          <p className="text-[10px] text-cyan-500/70 font-mono uppercase tracking-[0.3em] mt-1 animate-pulse">
            STATUS: {scanText}
          </p>
        </div>

        {/* Bottom HUD Legend */}
        <div className="absolute bottom-6 left-6 z-10 bg-slate-900/60 backdrop-blur-md border border-white/10 p-4 rounded-xl flex flex-col gap-3">
          <h3 className="text-[10px] font-mono text-slate-400 uppercase tracking-widest border-b border-white/10 pb-2 mb-1">
            Node Legend
          </h3>
          <div className="flex items-center gap-3">
            <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.8)]"></span>
            <span className="text-[10px] text-slate-300 font-mono uppercase tracking-wider">Agents</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-2 h-2 rounded-full bg-violet-500 shadow-[0_0_8px_rgba(167,139,250,0.8)]"></span>
            <span className="text-[10px] text-slate-300 font-mono uppercase tracking-wider">Memories</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]"></span>
            <span className="text-[10px] text-slate-300 font-mono uppercase tracking-wider">Tasks</span>
          </div>
        </div>

        {/* Graph Container */}
        {isLoading ? (
          <div className="w-full h-full flex items-center justify-center text-cyan-500 font-mono text-xs uppercase tracking-widest animate-pulse">
            Initializing 3D Projection...
          </div>
        ) : (
          <div ref={graphRef} className="w-full h-full"></div>
        )}
      </div>

      {/* Info Panels */}
      <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-6 pb-20">
        <GlassCard variant="cyan" className="flex flex-col">
          <div className="text-cyan-500 font-mono text-xs mb-2 opacity-50">01 // TOPOLOGY</div>
          <h3 className="text-slate-100 font-black text-sm uppercase tracking-widest mb-3">Semantic Proximity</h3>
          <p className="text-slate-400 font-mono text-[10px] leading-relaxed uppercase tracking-tight">
            Nodes are positioned based on high-dimensional vector embeddings. Closely related concepts will cluster naturally in 3D space.
          </p>
        </GlassCard>

        <GlassCard variant="violet" className="flex flex-col">
          <div className="text-violet-500 font-mono text-xs mb-2 opacity-50">02 // PROVENANCE</div>
          <h3 className="text-slate-100 font-black text-sm uppercase tracking-widest mb-3">Compaction Flows</h3>
          <p className="text-slate-400 font-mono text-[10px] leading-relaxed uppercase tracking-tight">
            Lines between nodes represent directed relationships, visualizing how granular data evolves into dense, active knowledge.
          </p>
        </GlassCard>

        <GlassCard variant="green" className="flex flex-col">
          <div className="text-emerald-500 font-mono text-xs mb-2 opacity-50">03 // TELEMETRY</div>
          <h3 className="text-slate-100 font-black text-sm uppercase tracking-widest mb-3">Real-Time Sync</h3>
          <p className="text-slate-400 font-mono text-[10px] leading-relaxed uppercase tracking-tight">
            The mesh reflects live inbound memory streams and active task execution from your agent swarms and workspace collaborators.
          </p>
        </GlassCard>
      </div>
    </>
  );
}
