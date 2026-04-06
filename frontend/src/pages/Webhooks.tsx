import type React from 'react';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { webhookApi } from '../lib/api/webhook';
import { GlassCard } from '../components/GlassCard';
import { Activity, ShieldAlert, Plus, Zap, Trash2, KeyRound } from 'lucide-react';

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
      return await webhookApi.list();
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
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-violet-500 tracking-tight uppercase italic">
            Live Listeners
          </h1>
          <div className="flex items-center gap-2 mt-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
            </span>
            <p className="text-cyan-500/80 font-mono text-[10px] uppercase tracking-[0.3em]">
              Status: Monitoring Outbound Streams
            </p>
          </div>
        </div>
        <button 
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-6 py-3 bg-cyan-500/10 border border-cyan-500/30 hover:bg-cyan-500/20 hover:border-cyan-400 text-cyan-400 text-xs font-bold uppercase tracking-[0.2em] rounded-lg transition-all duration-300 shadow-[0_0_15px_rgba(6,182,212,0.15)] hover:shadow-[0_0_25px_rgba(6,182,212,0.3)] backdrop-blur-md"
        >
          <Plus className="w-4 h-4" />
          Initialize Listener
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="flex flex-col items-center gap-4">
            <Activity className="w-8 h-8 text-cyan-500 animate-spin" />
            <span className="text-cyan-500/70 font-mono text-xs uppercase tracking-widest animate-pulse">Scanning for listeners...</span>
          </div>
        </div>
      ) : !webhooks || webhooks.length === 0 ? (
        <GlassCard variant="cyan" className="text-center py-20" hoverEffect={false}>
          <div className="flex flex-col items-center justify-center">
            <Activity className="w-12 h-12 text-cyan-500/20 mb-6" />
            <h3 className="text-lg font-bold text-white uppercase tracking-widest mb-2">No Listeners Configured</h3>
            <p className="text-gray-400 text-xs mb-8 uppercase tracking-tighter">Register an endpoint to receive real-time neural events.</p>
            <button 
              onClick={() => setShowModal(true)} 
              className="text-cyan-400 font-black hover:text-cyan-300 hover:scale-105 transition-all duration-300 uppercase tracking-widest text-[10px]"
            >
              + Start First Stream
            </button>
          </div>
        </GlassCard>
      ) : (
        <div className="grid gap-6">
          {webhooks.map((webhook) => (
            <GlassCard key={webhook.id} variant={webhook.failure_count > 0 ? 'red' : 'cyan'} className="!p-0 overflow-hidden group">
              <div className="p-6 md:p-8">
                <div className="flex flex-col lg:flex-row items-start justify-between gap-8">
                  <div className="flex-1 min-w-0 w-full">
                    <div className="flex items-center gap-4 mb-6">
                      <div className="relative flex items-center justify-center">
                        <div className={`w-2 h-2 rounded-full shadow-[0_0_8px_currentColor] ${webhook.is_active ? 'bg-emerald-500 text-emerald-500 animate-pulse' : 'bg-rose-500 text-rose-500'}`}></div>
                      </div>
                      <h3 className="text-lg md:text-xl font-bold text-white truncate font-mono tracking-tight">{webhook.url}</h3>
                    </div>
                    
                    <div className="flex flex-wrap gap-2 mb-6">
                      {webhook.events.map(event => (
                        <span key={event} className="bg-cyan-500/10 text-cyan-300 text-[10px] font-mono px-2 py-1 rounded border border-cyan-500/20 uppercase tracking-widest">
                          {event}
                        </span>
                      ))}
                    </div>

                    {webhook.semantic_query && (
                      <div className="mb-6 p-4 bg-slate-900/50 rounded-lg border border-cyan-500/20">
                        <span className="text-[10px] text-cyan-500/70 uppercase tracking-[0.2em] font-bold block mb-2 flex items-center gap-2">
                          <Activity className="w-3 h-3" />
                          Semantic Filter
                        </span>
                        <p className="text-sm text-cyan-100/90 italic font-mono leading-relaxed">"{webhook.semantic_query}"</p>
                      </div>
                    )}

                    <div className="mb-6">
                      <span className="text-[10px] text-gray-500 uppercase tracking-[0.2em] font-bold block mb-2 flex items-center gap-2">
                        <KeyRound className="w-3 h-3" />
                        Encryption Secret
                      </span>
                      <div className="flex items-center gap-3">
                        <code className="text-xs font-mono text-gray-400 bg-slate-900/80 px-4 py-2.5 rounded-lg border border-white/10 overflow-hidden text-ellipsis whitespace-nowrap max-w-full md:max-w-md flex-1">
                          {showingSecret === webhook.id ? webhook.secret : 'whsec_••••••••••••••••••••••••••••••••'}
                        </code>
                        <button 
                          onClick={() => setShowingSecret(showingSecret === webhook.id ? null : webhook.id)}
                          className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-[10px] font-bold uppercase tracking-widest border border-white/10 transition-colors"
                        >
                          {showingSecret === webhook.id ? 'Hide' : 'Reveal'}
                        </button>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-4 text-[10px] text-gray-500 font-mono uppercase tracking-widest">
                      <span>Init: {new Date(webhook.created_at).toLocaleDateString()}</span>
                      {webhook.failure_count > 0 && (
                        <div className="flex items-center gap-2 text-rose-400 bg-rose-500/10 px-2 py-1 rounded border border-rose-500/20">
                          <ShieldAlert className="w-3 h-3" />
                          <span>{webhook.failure_count} Interruptions</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="shrink-0 flex flex-row lg:flex-col gap-3 w-full lg:w-auto">
                    <button 
                      onClick={() => testMutation.mutate(webhook.id)}
                      className="flex-1 lg:flex-none flex justify-center items-center gap-2 px-4 py-3 bg-violet-500/10 border border-violet-500/30 hover:bg-violet-500/20 text-violet-400 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all"
                    >
                      <Zap className="w-3 h-3" />
                      Ping
                    </button>
                    <button 
                      onClick={() => {
                        if (confirm('Are you sure you want to severe this connection?')) {
                          deleteMutation.mutate(webhook.id);
                        }
                      }}
                      className="flex-1 lg:flex-none flex justify-center items-center gap-2 px-4 py-3 bg-rose-500/10 border border-rose-500/30 hover:bg-rose-500/20 text-rose-400 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all"
                    >
                      <Trash2 className="w-3 h-3" />
                      Purge
                    </button>
                  </div>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Add Webhook Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-300">
          <GlassCard variant="cyan" className="max-w-xl w-full !p-0 shadow-[0_0_50px_rgba(6,182,212,0.15)]" hoverEffect={false}>
            <div className="p-8">
              <h2 className="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-emerald-400 uppercase tracking-tight mb-8 flex items-center gap-3">
                <Activity className="w-6 h-6 text-cyan-400" />
                New Listener Config
              </h2>
              
              <form onSubmit={handleSubmit} className="space-y-6">
                <div className="space-y-2">
                  <label className="text-[10px] font-mono font-bold text-cyan-500/80 uppercase tracking-[0.2em]">Endpoint Protocol (HTTPS)</label>
                  <input 
                    value={formData.url}
                    onChange={(e) => setFormData(prev => ({ ...prev, url: e.target.value }))}
                    type="url" 
                    required 
                    className="w-full bg-slate-900/80 border border-cyan-500/30 focus:border-cyan-400 rounded-lg px-4 py-3 text-cyan-100 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400/50 transition-all placeholder:text-gray-600" 
                    placeholder="https://api.your-agent.io/v1/hooks"
                  />
                </div>

                <div className="space-y-3">
                  <label className="text-[10px] font-mono font-bold text-cyan-500/80 uppercase tracking-[0.2em]">Subscription Matrix</label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {availableEvents.map(event => (
                      <label key={event} className="flex items-center gap-3 p-3 rounded-lg border border-white/5 bg-slate-900/50 cursor-pointer hover:border-cyan-500/30 transition-all group">
                        <div className="relative flex items-center justify-center w-4 h-4">
                          <input 
                            type="checkbox" 
                            checked={formData.events.includes(event)}
                            onChange={() => toggleEvent(event)}
                            className="peer appearance-none w-4 h-4 rounded border border-white/20 bg-black checked:bg-cyan-500/20 checked:border-cyan-500 transition-all cursor-pointer"
                          />
                          <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-0 peer-checked:opacity-100 transition-opacity">
                            <div className="w-2 h-2 bg-cyan-400 rounded-sm shadow-[0_0_5px_rgba(34,211,238,0.8)]"></div>
                          </div>
                        </div>
                        <span className={`text-[10px] font-mono uppercase transition-colors ${formData.events.includes(event) ? 'text-cyan-300 font-bold' : 'text-gray-400 group-hover:text-gray-300'}`}>
                          {event}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                {formData.events.includes('memory.semantic_match') && (
                  <div className="space-y-2 animate-in fade-in slide-in-from-top-2 duration-300">
                    <label className="text-[10px] font-mono font-bold text-violet-400/80 uppercase tracking-[0.2em]">Semantic Resonance Query</label>
                    <textarea 
                      value={formData.semantic_query}
                      onChange={(e) => setFormData(prev => ({ ...prev, semantic_query: e.target.value }))}
                      rows={3} 
                      className="w-full bg-slate-900/80 border border-violet-500/30 focus:border-violet-400 rounded-lg px-4 py-3 text-violet-100 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-violet-400/50 transition-all placeholder:text-gray-600 resize-none" 
                      placeholder="e.g. Topics related to artificial intelligence and ethics"
                    ></textarea>
                  </div>
                )}

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
                    className="flex items-center gap-2 px-6 py-2.5 bg-cyan-500/20 border border-cyan-500/50 hover:bg-cyan-500/30 text-cyan-300 rounded-lg text-xs font-bold uppercase tracking-[0.2em] transition-all shadow-[0_0_15px_rgba(6,182,212,0.2)]"
                  >
                    {createMutation.isPending ? 'Syncing...' : 'Authorize Listener'}
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
