// hooks/useAgentStream.ts
// FireReach — SSE consumer hook
// Subscribes to the /stream/:jobId endpoint and accumulates agent events.

import { useState, useEffect, useCallback } from 'react';

export interface AgentEvent {
  id?: number;
  job_id: string;
  stage: string | null;
  message: string | null;
  data: Record<string, unknown> | null;
  status: 'queued' | 'running' | 'done' | 'error';
  timestamp: string;
}

type StreamStatus = 'idle' | 'connecting' | 'running' | 'done' | 'error';

interface UseAgentStreamResult {
  events: AgentEvent[];
  status: StreamStatus;
  latestEvent: AgentEvent | null;
  reset: () => void;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export function useAgentStream(jobId: string | null): UseAgentStreamResult {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [status, setStatus] = useState<StreamStatus>('idle');

  const reset = useCallback(() => {
    setEvents([]);
    setStatus('idle');
  }, []);

  useEffect(() => {
    if (!jobId) return;

    setStatus('connecting');
    const es = new EventSource(`${API_BASE}/stream/${jobId}`);

    es.onopen = () => setStatus('running');

    es.onmessage = (e: MessageEvent) => {
      try {
        const event: AgentEvent = JSON.parse(e.data as string);
        setEvents((prev) => [...prev, event]);

        if (event.status === 'done') {
          setStatus('done');
          es.close();
        } else if (event.status === 'error') {
          setStatus('error');
          es.close();
        }
      } catch {
        // malformed event — skip silently
      }
    };

    es.onerror = () => {
      setStatus('error');
      es.close();
    };

    return () => {
      es.close();
    };
  }, [jobId]);

  const latestEvent = events.length > 0 ? events[events.length - 1] : null;

  return { events, status, latestEvent, reset };
}
