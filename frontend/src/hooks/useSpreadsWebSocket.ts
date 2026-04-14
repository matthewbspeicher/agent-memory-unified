import { useState, useEffect, useRef, useCallback } from 'react';

interface SpreadData {
  kalshi_ticker: string;
  poly_ticker: string;
  kalshi_cents: number;
  poly_cents: number;
  gap_cents: number;
  observed_at: string;
}

interface SpreadEvent {
  topic?: string;
  event_type?: string;
  data: SpreadData;
}

interface UseSpreadsWebSocketOptions {
  tickers?: string[];
  minGap?: number;
  maxEvents?: number;
}

export function useSpreadsWebSocket(options: UseSpreadsWebSocketOptions = {}) {
  const { tickers, minGap = 3, maxEvents = 50 } = options;
  const [events, setEvents] = useState<SpreadEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    const apiKey = import.meta.env.VITE_TRADING_API_KEY || (import.meta.env.DEV ? 'local-validator-dev' : '');
    const wsUrl = `ws://${window.location.hostname}:8080/engine/v1/ws/spreads`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', api_key: apiKey }));

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'auth_ok') {
            setIsConnected(true);
            if (tickers?.length) ws.send(JSON.stringify({ type: 'subscribe', tickers }));
            if (minGap > 3) ws.send(JSON.stringify({ type: 'min_gap', value: minGap }));
          } else if (data.topic || data.event_type) {
            setEvents((prev) => [data, ...prev].slice(0, maxEvents));
          }
        } catch {}
      };

      ws.onclose = () => {
        setIsConnected(false);
        reconnectTimeoutRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => { setIsConnected(false); ws.close(); };
    } catch {
      setIsConnected(false);
    }
  }, [tickers, minGap, maxEvents]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { events, isConnected };
}
