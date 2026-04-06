import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';

interface QueryWrapperProps<T> {
  query: UseQueryResult<T>;
  emptyMessage?: string;
  children: (data: T) => ReactNode;
}

export function QueryWrapper<T>({
  query,
  emptyMessage = 'No data found.',
  children,
}: QueryWrapperProps<T>) {
  if (query.isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-pulse text-gray-500">Loading...</div>
      </div>
    );
  }

  if (query.error) {
    return (
      <div className="glass-panel p-6 text-center">
        <p className="text-red-400">Error: {query.error.message}</p>
        <button
          onClick={() => query.refetch()}
          className="mt-4 neural-button-secondary px-4 py-2"
        >
          Retry
        </button>
      </div>
    );
  }

  const data = query.data;
  if (data == null || (Array.isArray(data) && data.length === 0)) {
    return (
      <div className="glass-panel p-6 text-center">
        <p className="text-gray-500">{emptyMessage}</p>
      </div>
    );
  }

  return <>{children(data)}</>;
}