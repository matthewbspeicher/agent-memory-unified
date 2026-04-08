// frontend/src/hooks/useAchievementFeed.ts
import { useState, useEffect, useRef } from 'react';

interface AchievementEvent {
  competitor: string;
  type: string;
  earned_at: string;
}

/**
 * SSE hook with header-based auth.
 * Uses fetch + ReadableStream instead of EventSource to support custom headers.
 */
export function useAchievementFeed() {
  const [events, setEvents] = useState<AchievementEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const apiKey = import.meta.env.VITE_TRADING_API_KEY || (import.meta.env.DEV ? 'local-validator-dev' : '');
    const abort = new AbortController();
    abortRef.current = abort;

    async function connect() {
      try {
        const response = await fetch('/api/competition/achievements/feed/stream', {
          headers: {
            'X-API-Key': apiKey,
          },
          signal: abort.signal,
        });

        if (!response.ok) {
          setIsConnected(false);
          return;
        }

        setIsConnected(true);
        const reader = response.body?.getReader();
        if (!reader) return;

        const decoder = new TextDecoder();
        let buffer = '';

        while (!abort.signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('event: achievement_earned')) {
              // Parse next data line
              continue;
            }
            if (line.startsWith('data: ')) {
              try {
                const data: AchievementEvent = JSON.parse(line.slice(6));
                setEvents((prev) => [data, ...prev].slice(0, 50));
              } catch { /* ignore parse errors */ }
            }
          }
        }
      } catch (err) {
        if (!abort.signal.aborted) {
          setIsConnected(false);
        }
      }
    }

    connect();
    return () => abort.abort();
  }, []);

  return { events, isConnected };
}
