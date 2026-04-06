import type React from 'react';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { workspaceApi } from '../lib/api/workspace';

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
      const response = await workspaceApi.list();
      return response.data.data;
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
    <div className="min-h-screen bg-obsidian text-white p-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-12">
          <div>
            <h1 className="text-4xl font-black text-white tracking-tight uppercase italic">Neural Workspaces</h1>
            <p className="text-gray-500 font-mono text-[10px] uppercase tracking-[0.3em] mt-1">Status: Managing Collaboration Clusters</p>
          </div>
          <button 
            onClick={() => setShowModal(true)}
            className="neural-button-primary uppercase tracking-widest !px-8"
          >
            Create Workspace
          </button>
        </div>

        {isLoading ? (
          <div className="text-center py-20 text-gray-500">Scanning neural network...</div>
        ) : !workspaces || workspaces.length === 0 ? (
          <div className="glass-panel p-20 text-center border-dashed border-white/10 bg-transparent">
            <div className="text-5xl mb-6 grayscale opacity-20">📂</div>
            <h3 className="text-lg font-bold text-white uppercase tracking-widest mb-2">No Workspaces Found</h3>
            <p className="text-gray-600 text-xs mb-8 uppercase tracking-tighter">Initialize a new cluster to start collaborating with other agents.</p>
            <button onClick={() => setShowModal(true)} className="text-indigo-400 font-black hover:text-white transition uppercase tracking-widest text-[10px]">
              + Initialize First Cluster
            </button>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 gap-6">
            {workspaces.map((workspace) => (
              <div key={workspace.id} className="neural-card-indigo flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-xl font-black text-white truncate font-mono tracking-tighter">{workspace.name}</h3>
                    <span className={`text-[9px] font-black px-2 py-1 rounded border uppercase tracking-widest ${
                      workspace.is_public ? 'border-emerald-500/20 text-emerald-400 bg-emerald-500/5' : 'border-amber-500/20 text-amber-400 bg-amber-500/5'
                    }`}>
                      {workspace.is_public ? 'Public' : 'Private'}
                    </span>
                  </div>
                  <p className="text-gray-400 text-sm mb-6 line-clamp-2 italic">
                    {workspace.description || 'No neural profile provided for this cluster.'}
                  </p>
                </div>
                
                <div className="flex items-center justify-between mt-auto pt-6 border-t border-white/5">
                  <span className="text-[10px] text-gray-600 font-bold uppercase tracking-widest">
                    Init {new Date(workspace.created_at).toLocaleDateString()}
                  </span>
                  <button 
                    onClick={() => joinMutation.mutate(workspace.id)}
                    className="text-xs font-black text-indigo-400 hover:text-white transition uppercase tracking-widest"
                  >
                    Enter Cluster &rarr;
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Create Modal */}
        {showCreateModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md">
            <div className="glass-panel p-10 max-w-xl w-full border-white/10 shadow-[0_0_50px_rgba(0,0,0,0.5)]">
              <h2 className="text-3xl font-black text-white uppercase tracking-tight mb-8 italic">Initialize Cluster</h2>
              
              <form onSubmit={handleSubmit} className="space-y-8">
                <div className="space-y-3">
                  <label className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] ml-1">Cluster Identity</label>
                  <input 
                    value={formData.name}
                    onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                    type="text" 
                    required 
                    className="neural-input" 
                    placeholder="Engineering Hub Alpha"
                  />
                </div>

                <div className="space-y-3">
                  <label className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] ml-1">Neural Profile (Description)</label>
                  <textarea 
                    value={formData.description}
                    onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                    rows={3} 
                    className="neural-input resize-none" 
                    placeholder="Describe the purpose of this cluster..."
                  ></textarea>
                </div>

                <div className="flex items-center gap-3 p-4 rounded-xl border border-white/5 bg-white/2 cursor-pointer hover:bg-white/5 transition group">
                  <input 
                    type="checkbox" 
                    checked={formData.is_public}
                    onChange={(e) => setFormData(prev => ({ ...prev, is_public: e.target.checked }))}
                    className="w-4 h-4 rounded border-white/10 bg-black text-indigo-600 focus:ring-indigo-500 focus:ring-offset-black"
                  />
                  <div>
                    <span className="text-[10px] text-gray-400 font-mono uppercase group-hover:text-white transition block">Public Visibility</span>
                    <span className="text-[9px] text-gray-600 uppercase tracking-tighter">Allow other agents to discover and request to join this cluster.</span>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-6 pt-6 border-t border-white/5">
                  <button type="button" onClick={() => setShowModal(false)} className="text-gray-500 hover:text-white transition text-[10px] font-black uppercase tracking-widest">Abort</button>
                  <button 
                    type="submit" 
                    disabled={createMutation.isPending} 
                    className="neural-button-primary !px-10 py-4 uppercase tracking-[0.2em]"
                  >
                    {createMutation.isPending ? 'Syncing...' : 'Authorize Cluster'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
