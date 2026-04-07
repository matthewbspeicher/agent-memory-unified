import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { memoryApi } from '../lib/api/memory';

export function CreateMemoryForm() {
  const [value, setValue] = useState('');
  const [visibility, setVisibility] = useState<'private' | 'public'>('private');
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: (data: { value: string; visibility: 'private' | 'public' }) =>
      memoryApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] });
      setValue('');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim()) {
      createMutation.mutate({ value, visibility });
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-slate-900/40 border border-white/10 rounded-xl p-4 mb-6 backdrop-blur-md">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="What do you want to remember?"
        className="w-full px-3 py-2 bg-slate-950/60 border border-white/10 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50 min-h-[100px] font-mono text-sm transition-all"
      />
      
      <div className="mt-3 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <label className="flex items-center text-sm text-slate-300">
            <input
              type="radio"
              value="private"
              checked={visibility === 'private'}
              onChange={(e) => setVisibility(e.target.value as 'private')}
              className="mr-2"
            />
            Private
          </label>
          <label className="flex items-center text-sm text-slate-300">
            <input
              type="radio"
              value="public"
              checked={visibility === 'public'}
              onChange={(e) => setVisibility(e.target.value as 'public')}
              className="mr-2"
            />
            Public
          </label>
        </div>
        
        <button
          type="submit"
          disabled={!value.trim() || createMutation.isPending}
          className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed font-mono text-sm tracking-wide transition-colors"
        >
          {createMutation.isPending ? 'Saving...' : 'Save Memory'}
        </button>
      </div>
      
      {createMutation.isError && (
        <div className="mt-2 text-red-400 text-sm">
          Error: {createMutation.error instanceof Error ? createMutation.error.message : 'Failed to save'}
        </div>
      )}
    </form>
  );
}
