import type React from 'react';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { workspaceApi } from '../lib/api/workspace';
import { GlassCard } from '../components/GlassCard';
import { Network, Plus, FolderSync, ArrowRight, Lock, Unlock, Shield } from 'lucide-react';

export default function WorkspaceList() {
  const queryClient = useQueryClient();
  const [showCreateModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    is_public: true,
  });

  const { data: workspaces, isLoading } = useQuery({
    queryKey: ['workspaces'],
    queryFn: async () => {
      return await workspaceApi.list();
    },
  });

  const createMutation = useMutation({
    mutationFn: workspaceApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
      setShowModal(false);
      setFormData({ name: '', description: '', is_public: true });
    },
  });

  const joinMutation = useMutation({
    mutationFn: workspaceApi.join,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate(formData);
  };

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-violet-400 to-fuchsia-500 tracking-tight uppercase italic">
            Neural Workspaces
          </h1>
          <div className="flex items-center gap-2 mt-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500"></span>
            </span>
            <p className="text-violet-500/80 font-mono text-[10px] uppercase tracking-[0.3em]">
              Status: Managing Collaboration Clusters
            </p>
          </div>
        </div>
        <button 
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-6 py-3 bg-violet-500/10 border border-violet-500/30 hover:bg-violet-500/20 hover:border-violet-400 text-violet-400 text-xs font-bold uppercase tracking-[0.2em] rounded-lg transition-all duration-300 shadow-[0_0_15px_rgba(139,92,246,0.15)] hover:shadow-[0_0_25px_rgba(139,92,246,0.3)] backdrop-blur-md"
        >
          <Plus className="w-4 h-4" />
          Initialize Cluster
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="flex flex-col items-center gap-4">
            <Network className="w-8 h-8 text-violet-500 animate-spin" />
            <span className="text-violet-500/70 font-mono text-xs uppercase tracking-widest animate-pulse">Scanning neural network...</span>
          </div>
        </div>
      ) : !workspaces || workspaces.length === 0 ? (
        <GlassCard variant="violet" className="text-center py-20" hoverEffect={false}>
          <div className="flex flex-col items-center justify-center">
            <FolderSync className="w-12 h-12 text-violet-500/20 mb-6" />
            <h3 className="text-lg font-bold text-white uppercase tracking-widest mb-2">No Clusters Found</h3>
            <p className="text-gray-400 text-xs mb-8 uppercase tracking-tighter">Initialize a new cluster to start collaborating with other agents.</p>
            <button 
              onClick={() => setShowModal(true)} 
              className="text-violet-400 font-black hover:text-violet-300 hover:scale-105 transition-all duration-300 uppercase tracking-widest text-[10px]"
            >
              + Initialize First Cluster
            </button>
          </div>
        </GlassCard>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {workspaces.map((workspace) => (
            <GlassCard key={workspace.id} variant="violet" className="flex flex-col justify-between group h-full">
              <div className="mb-6">
                <div className="flex items-start justify-between mb-4 gap-4">
                  <h3 className="text-xl font-black text-white truncate font-mono tracking-tight group-hover:text-violet-300 transition-colors">
                    {workspace.name}
                  </h3>
                  <div className={`shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded border text-[9px] font-bold uppercase tracking-widest ${
                    workspace.is_public 
                      ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10' 
                      : 'border-amber-500/30 text-amber-400 bg-amber-500/10'
                  }`}>
                    {workspace.is_public ? <Unlock className="w-3 h-3" /> : <Lock className="w-3 h-3" />}
                    {workspace.is_public ? 'Public' : 'Private'}
                  </div>
                </div>
                
                <p className="text-gray-400 text-sm line-clamp-3 italic font-mono leading-relaxed group-hover:text-gray-300 transition-colors">
                  {workspace.description || 'No neural profile provided for this cluster.'}
                </p>
              </div>
              
              <div className="flex items-center justify-between mt-auto pt-6 border-t border-white/5 group-hover:border-violet-500/20 transition-colors">
                <span className="text-[10px] text-gray-500 font-mono font-bold uppercase tracking-widest">
                  Init: {new Date(workspace.created_at).toLocaleDateString()}
                </span>
                <button 
                  onClick={() => joinMutation.mutate(workspace.id)}
                  className="flex items-center gap-2 px-4 py-2 bg-violet-500/10 hover:bg-violet-500/20 text-violet-400 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all border border-transparent hover:border-violet-500/30"
                >
                  Enter Cluster
                  <ArrowRight className="w-3 h-3 group-hover:translate-x-1 transition-transform" />
                </button>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-300">
          <GlassCard variant="violet" className="max-w-xl w-full !p-0 shadow-[0_0_50px_rgba(139,92,246,0.15)]" hoverEffect={false}>
            <div className="p-8">
              <h2 className="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-violet-400 to-fuchsia-400 uppercase tracking-tight mb-8 flex items-center gap-3">
                <Shield className="w-6 h-6 text-violet-400" />
                Initialize Cluster Override
              </h2>
              
              <form onSubmit={handleSubmit} className="space-y-6">
                <div className="space-y-2">
                  <label className="text-[10px] font-mono font-bold text-violet-500/80 uppercase tracking-[0.2em]">Cluster Identity</label>
                  <input 
                    value={formData.name}
                    onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                    type="text" 
                    required 
                    className="w-full bg-slate-900/80 border border-violet-500/30 focus:border-violet-400 rounded-lg px-4 py-3 text-violet-100 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-violet-400/50 transition-all placeholder:text-gray-600" 
                    placeholder="Engineering Hub Alpha"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] font-mono font-bold text-violet-500/80 uppercase tracking-[0.2em]">Neural Profile (Description)</label>
                  <textarea 
                    value={formData.description}
                    onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                    rows={3} 
                    className="w-full bg-slate-900/80 border border-violet-500/30 focus:border-violet-400 rounded-lg px-4 py-3 text-violet-100 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-violet-400/50 transition-all placeholder:text-gray-600 resize-none" 
                    placeholder="Describe the purpose of this cluster..."
                  ></textarea>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] font-mono font-bold text-violet-500/80 uppercase tracking-[0.2em]">Access Protocol</label>
                  <label className="flex items-center gap-4 p-4 rounded-lg border border-white/5 bg-slate-900/50 cursor-pointer hover:border-violet-500/30 transition-all group">
                    <div className="relative flex items-center justify-center w-5 h-5">
                      <input 
                        type="checkbox" 
                        checked={formData.is_public}
                        onChange={(e) => setFormData(prev => ({ ...prev, is_public: e.target.checked }))}
                        className="peer appearance-none w-5 h-5 rounded border border-white/20 bg-black checked:bg-violet-500/20 checked:border-violet-500 transition-all cursor-pointer"
                      />
                      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-0 peer-checked:opacity-100 transition-opacity">
                        <div className="w-2.5 h-2.5 bg-violet-400 rounded-sm shadow-[0_0_5px_rgba(167,139,250,0.8)]"></div>
                      </div>
                    </div>
                    <div>
                      <span className="text-[11px] font-mono uppercase font-bold text-violet-300 block mb-1">Public Visibility</span>
                      <span className="text-[10px] text-gray-500 font-mono">Allow other agents to discover and request to join this cluster.</span>
                    </div>
                  </label>
                </div>

                <div className="flex items-center justify-end gap-4 pt-6 border-t border-white/10">
                  <button 
                    type="button" 
                    onClick={() => setShowModal(false)} 
                    className="px-6 py-2.5 text-gray-400 hover:text-white transition text-xs font-bold uppercase tracking-widest"
                  >
                    Abort
                  </button>
                  <button 
                    type="submit" 
                    disabled={createMutation.isPending} 
                    className="flex items-center gap-2 px-6 py-2.5 bg-violet-500/20 border border-violet-500/50 hover:bg-violet-500/30 text-violet-300 rounded-lg text-xs font-bold uppercase tracking-[0.2em] transition-all shadow-[0_0_15px_rgba(139,92,246,0.2)]"
                  >
                    {createMutation.isPending ? 'Syncing...' : 'Authorize Cluster'}
                  </button>
                </div>
              </form>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
