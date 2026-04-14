import { useQuery } from '@tanstack/react-query';
import { missionControlApi, MissionControlStatus } from '../lib/api/missionControl';

/**
 * Polls the Mission Control aggregation endpoint every 15s.
 * Returns the full dashboard snapshot.
 */
export function useMissionControl() {
  return useQuery<MissionControlStatus>({
    queryKey: ['mission-control', 'status'],
    queryFn: () => missionControlApi.getStatus(),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}
