import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

interface Stats {
  total_memories: number
  total_agents: number
  active_trades: number
}

export default function Dashboard() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: async () => {
      const { data } = await axios.get<Stats>('/api/v1/stats')
      return data
    },
  })

  if (isLoading) {
    return <div className="text-center py-10">Loading...</div>
  }

  return (
    <div>
      <h2 className="text-3xl font-bold text-gray-900 mb-6">Dashboard</h2>
      
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">
              Total Memories
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-gray-900">
              {stats?.total_memories || 0}
            </dd>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">
              Active Agents
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-gray-900">
              {stats?.total_agents || 0}
            </dd>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">
              Active Trades
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-gray-900">
              {stats?.active_trades || 0}
            </dd>
          </div>
        </div>
      </div>
    </div>
  )
}
