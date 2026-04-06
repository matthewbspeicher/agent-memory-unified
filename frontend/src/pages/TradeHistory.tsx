import { useQuery } from '@tanstack/react-query'
import { tradingApi } from '../lib/api/trading'
import { TradeList } from '../components/TradeList'

export default function TradeHistory() {
  const { data: trades, isLoading, error } = useQuery({
    queryKey: ['trades'],
    queryFn: async () => {
      return await tradingApi.listTrades();
    },
  })

  return (
    <>
        <h2 className="text-3xl font-bold mb-6">Trade History</h2>

        {isLoading && (
          <div className="text-center py-12 text-gray-400">Loading trades...</div>
        )}

        {error && (
          <div className="bg-red-900/20 border border-red-700 rounded-lg p-4 text-red-300">
            Error loading trades: {error instanceof Error ? error.message : 'Unknown error'}
          </div>
        )}

        {trades && <TradeList trades={trades} />}
      </>
  )
}
