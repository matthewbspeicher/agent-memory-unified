import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

interface Memory {
  id: string
  value: string
  visibility: string
  created_at: string
}

export default function MemoryList() {
  const { data: memories, isLoading } = useQuery({
    queryKey: ['memories'],
    queryFn: async () => {
      const { data } = await axios.get<Memory[]>('/api/v1/memories')
      return data
    },
  })

  if (isLoading) {
    return <div className="text-center py-10">Loading...</div>
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-3xl font-bold text-gray-900">Memories</h2>
        <button className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-medium">
          New Memory
        </button>
      </div>

      <div className="bg-white shadow overflow-hidden sm:rounded-md">
        <ul className="divide-y divide-gray-200">
          {memories?.map((memory) => (
            <li key={memory.id}>
              <div className="px-4 py-4 sm:px-6">
                <div className="flex items-center justify-between">
                  <p className="text-sm text-gray-900 truncate">
                    {memory.value}
                  </p>
                  <div className="ml-2 flex-shrink-0 flex">
                    <p className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">
                      {memory.visibility}
                    </p>
                  </div>
                </div>
                <div className="mt-2 sm:flex sm:justify-between">
                  <div className="sm:flex">
                    <p className="text-sm text-gray-500">
                      {new Date(memory.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
