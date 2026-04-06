import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { webhookApi, Webhook } from '../lib/api/webhook';

export default function Webhooks() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [showingSecret, setShowingSecret] = useState<string | null>(null);
  
  const [formData, setFormData] = useState({
    url: '',
    events: [] as string[],
    semantic_query: '',
  });

  const availableEvents = [
    'memory.created',
    'memory.updated',
    'memory.deleted',
    'memory.semantic_match',
    'agent.activated',
    'agent.deactivated'
  ];

  const { data: webhooks, isLoading } = useQuery({
    queryKey: ['webhooks'],
    queryFn: async () => {
      const response = await webhookApi.list();
      return response.data.data;
    },
  });

  const createMutation = useMutation({
    mutationFn: webhookApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks'] });
      setShowModal(false);
      setFormData({ url: '', events: [], semantic_query: '' });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: webhookApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks'] });
    },
  });

  const testMutation = useMutation({
    mutationFn: webhookApi.test,
  });

  const toggleEvent = (event: string) => {
    setFormData(prev => ({
      ...prev,
      events: prev.events.includes(event)
        ? prev.events.filter(e => e !== event)
        : [...prev.events, event]
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate(formData);
  };

  return (
    <div className="min-h-screen bg-obsidian text-white p-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-12">
          <div>
            <h1 className="text-4xl font-black text-white tracking-tight uppercase italic">Live Listeners</h1>
            <p className="text-gray-500 font-mono text-[10px] uppercase tracking-[0.3em] mt-1">Status: Monitoring Outbound Streams</p>
          </div>
          <button 
            onClick={() => setShowModal(true)}
            className="neural-button-primary uppercase tracking-widest !px-8"
          >
            Initialize Listener
          </button>
        </div>

        {isLoading ? (
          <div className="text-center py-20 text-gray-500">Scanning for listeners...</div>
        ) : !webhooks || webhooks.length === 0 ? (
          <div className="glass-panel p-20 text-center border-dashed border-white/10 bg-transparent">
            <div className="text-5xl mb-6 grayscale opacity-20">🪝</div>
            <h3 className="text-lg font-bold text-white uppercase tracking-widest mb-2">No Listeners Configured</h3>
            <p className="text-gray-600 text-xs mb-8 uppercase tracking-tighter">Register an endpoint to receive real-time neural events.</p>
            <button onClick={() => setShowModal(true)} className="text-indigo-400 font-black hover:text-white transition uppercase tracking-widest text-[10px]">
              + Start First Stream
            </button>
          </div>
        ) : (
          <div className="grid gap-8">
            {webhooks.map((webhook) => (
              <div key={webhook.id} className="neural-card-indigo group !p-0 overflow-hidden">
                <div className="p-8">
                  <div className="flex items-start justify-between gap-12">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-4 mb-4">
                        <div className={`w-2 h-2 rounded-full shadow-[0_0_8px_rgba(16,185,129,0.8)] ${webhook.is_active ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`}></div>
                        <h3 className="text-xl font-black text-white truncate font-mono tracking-tighter">{webhook.url}</h3>
                      </div>
                      
                      <div className="flex flex-wrap gap-2 mb-8">
                        {webhook.events.map(event => (
                          <span key={event} className="bg-indigo-500/5 text-indigo-300 text-[9px] font-black px-2 py-1 rounded border border-indigo-500/10 uppercase tracking-widest">
                            {event}
                          </span>
                        ))}
                      </div>

                      {webhook.semantic_query && (
                        <div className="mb-8 p-4 bg-black/40 rounded-xl border border-white/5">
                          <span className="text-[9px] text-gray-600 uppercase tracking-[0.2em] font-black block mb-2">Semantic Filter</span>
                          <p className="text-sm text-indigo-200 italic font-medium leading-relaxed">"{webhook.semantic_query}"</p>
                        </div>
                      )}

                      <div className="mb-8">
                        <span className="text-[9px] text-gray-600 uppercase tracking-[0.2em] font-black block mb-2">Encryption Secret</span>
                        <div className="flex items-center gap-3">
                          <code className="text-xs font-mono text-gray-500 bg-black/60 px-3 py-2 rounded-lg border border-white/5 min-w-[280px]">
                            {showingSecret === webhook.id ? webhook.secret : 'whsec_••••••••••••••••••••••••••••••••'}
                          </code>
                          <button 
                            onClick={() => setShowingSecret(showingSecret === webhook.id ? null : webhook.id)}
                            className="text-[9px] text-indigo-400 hover:text-white transition uppercase font-black tracking-widest ml-2"
                          >
                            {showingSecret === webhook.id ? 'Hide' : 'Reveal'}
                          </button>
                        </div>
                      </div>

                      <div className="flex items-center gap-6 text-[10px] text-gray-600 font-bold uppercase tracking-widest">
                        <span>Initialized {new Date(webhook.created_at).toLocaleDateString()}</span>
                        {webhook.failure_count > 0 && (
                          <div className="flex items-center gap-2 text-rose-500/80">
                            <span className="w-1 h-1 rounded-full bg-rose-500"></span>
                            <span>{webhook.failure_count} Interruptions</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="shrink-0 flex flex-col gap-3">
                      <button 
                        onClick={() => testMutation.mutate(webhook.id)}
                        className="neural-button-secondary !py-2 uppercase !text-[10px] tracking-widest"
                      >
                        Ping
                      </button>
                      <button 
                        onClick={() => {
                          if (confirm('Are you sure you want to delete this webhook?')) {
                            deleteMutation.mutate(webhook.id);
                          }
                        }}
                        className="neural-button-danger !py-2 uppercase !text-[10px] tracking-widest"
                      >
                        Purge
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add Webhook Modal */}
        {showModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md">
            <div className="glass-panel p-10 max-w-xl w-full border-white/10 shadow-[0_0_50px_rgba(0,0,0,0.5)]">
              <h2 className="text-3xl font-black text-white uppercase tracking-tight mb-8 italic">New Listener</h2>
              
              <form onSubmit={handleSubmit} className="space-y-8">
                <div className="space-y-3">
                  <label className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] ml-1">Endpoint Protocol (HTTPS)</label>
                  <input 
                    value={formData.url}
                    onChange={(e) => setFormData(prev => ({ ...prev, url: e.target.value }))}
                    type="url" 
                    required 
                    className="neural-input" 
                    placeholder="https://api.your-agent.io/v1/hooks"
                  />
                </div>

                <div className="space-y-3">
                  <label className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] ml-1">Subscription Matrix</label>
                  <div className="grid grid-cols-2 gap-4">
                    {availableEvents.map(event => (
                      <label key={event} className="flex items-center gap-3 p-4 rounded-xl border border-white/5 bg-white/2 cursor-pointer hover:bg-white/5 transition group">
                        <input 
                          type="checkbox" 
                          checked={formData.events.includes(event)}
                          onChange={() => toggleEvent(event)}
                          className="w-4 h-4 rounded border-white/10 bg-black text-indigo-600 focus:ring-indigo-500 focus:ring-offset-black"
                        />
                        <span className="text-[10px] text-gray-400 font-mono uppercase group-hover:text-white transition">{event}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {formData.events.includes('memory.semantic_match') && (
                  <div className="space-y-3 animate-in fade-in slide-in-from-top-4 duration-500">
                    <label className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] ml-1">Semantic Resonance Query</label>
                    <textarea 
                      value={formData.semantic_query}
                      onChange={(e) => setFormData(prev => ({ ...prev, semantic_query: e.target.value }))}
                      rows={2} 
                      className="neural-input h-24 resize-none" 
                      placeholder="What conceptual triggers should activate this listener?"
                    ></textarea>
                  </div>
                )}

                <div className="flex items-center justify-end gap-6 pt-6 border-t border-white/5">
                  <button type="button" onClick={() => setShowModal(false)} className="text-gray-500 hover:text-white transition text-[10px] font-black uppercase tracking-widest">Abort</button>
                  <button 
                    type="submit" 
                    disabled={createMutation.isPending} 
                    className="neural-button-primary !px-10 py-4 uppercase tracking-[0.2em]"
                  >
                    {createMutation.isPending ? 'Syncing...' : 'Authorize Listener'}
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
