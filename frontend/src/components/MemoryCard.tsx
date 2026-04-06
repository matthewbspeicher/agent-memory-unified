import type { Memory } from '../lib/api/memory';

interface MemoryCardProps {
  memory: Memory;
}

export function MemoryCard({ memory }: MemoryCardProps) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-gray-600 transition-colors">
      <p className="text-gray-100 text-sm leading-relaxed">{memory.value}</p>
      <div className="mt-3 flex items-center justify-between text-xs text-gray-400">
        <span>{memory.created_at ? new Date(memory.created_at).toLocaleDateString() : 'Unknown Date'}</span>
        <span className={`px-2 py-1 rounded ${
          memory.visibility === 'public' 
            ? 'bg-blue-900/50 text-blue-300' 
            : 'bg-gray-700 text-gray-300'
        }`}>
          {memory.visibility}
        </span>
      </div>
    </div>
  );
}
