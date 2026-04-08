// frontend/src/hooks/useAchievementFeed.ts
import { useState, useEffect, useRef } from 'react';

interface AchievementEvent {
  competitor: string;
  type: string;
  earned_at: string;
}

export function useAchievementFeed() {
  const [events, setEvents] = useState<AchievementEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const apiKey = import.meta.env.VITE_TRADING_API_KEY || (import.meta.env.DEV ? 'local-validator-dev' : '');
    const es = new EventSource(`/api/competition/achievements/feed/stream?api_key=${apiKey}`);
    esRef.current = es;

    es.onopen = () => setIsConnected(true);
    es.onerror = () => setIsConnected(false);

    es.addEventListener('achievement_earned', (e: MessageEvent) => {
      try {
        const data: AchievementEvent = JSON.parse(e.data);
        setEvents((prev) => [data, ...prev].slice(0, 50));
      } catch { /* ignore parse errors */ }
    });

    return () => es.close();
  }, []);

  return { events, isConnected };
}
