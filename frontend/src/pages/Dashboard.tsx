import { useQuery } from '@tanstack/react-query'
import { memoryApi } from '../lib/api/memory'
import { MemoryCard } from '../components/MemoryCard'

export default function Dashboard() {
  const { data: memories, isLoading } = useQuery({
    queryKey: ['memories'],
    queryFn: async () => {
      const response = await memoryApi.list()
      return response.data.data
    },
  })

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <div className="max-w-6xl mx-auto">
        <h2 className="text-3xl font-bold mb-6">Dashboard</h2>

        {/* Stats cards */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-3 mb-8">
          <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-5">
            <dt className="text-sm font-medium text-gray-400 truncate">
              Total Memories
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-white">
              {memories?.length || 0}
            </dd>
          </div>

          <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-5">
            <dt className="text-sm font-medium text-gray-400 truncate">
              Active Agents
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-white">
              -
            </dd>
          </div>

          <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-5">
            <dt className="text-sm font-medium text-gray-400 truncate">
              Active Trades
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-white">
              -
            </dd>
          </div>
        </div>

        {/* Memory feed */}
        <div>
          <h3 className="text-xl font-semibold mb-4">Recent Memories</h3>

          {isLoading && (
            <div className="text-center py-12 text-gray-400">Loading...</div>
          )}

          {memories && memories.length === 0 && (
            <div className="text-center py-12 text-gray-400">No memories yet</div>
          )}

          <div className="space-y-4">
            {memories?.map((memory) => (
              <MemoryCard key={memory.id} memory={memory} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
