'use client';

// components/AuditTimeline.tsx
// Collapsible vertical timeline built from SSE agent events.

import { useState } from 'react';
import type { AgentEvent } from '../hooks/useAgentStream';

interface AuditTimelineProps {
  events: AgentEvent[];
}

const STAGE_LABELS: Record<string, string> = {
  init: '🚀 Init',
  stage_1: '📡 Signals',
  stage_2: '🔍 Contact',
  stage_3: '🧠 Research',
  stage_4: '📧 Outreach',
  icp_score: '📊 ICP Score',
  error: '❌ Error',
};

function EventRow({ event }: { event: AgentEvent }) {
  const label = STAGE_LABELS[event.stage ?? ''] ?? event.stage ?? '•';
  const isError = event.status === 'error';
  const isDone = event.status === 'done';

  return (
    <div className="flex gap-3 py-2">
      {/* Timeline dot */}
      <div className="flex flex-col items-center">
        <div
          className="mt-1 h-2.5 w-2.5 rounded-full flex-shrink-0"
          style={{
            background: isError
              ? 'var(--error)'
              : isDone
              ? 'var(--success)'
              : 'var(--accent)',
          }}
        />
        <div className="flex-1 w-px mt-1" style={{ background: 'var(--border)' }} />
      </div>

      <div className="pb-3 min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-[var(--text-secondary)]">{label}</span>
          <span className="text-xs text-[var(--text-secondary)] opacity-60">
            {new Date(event.timestamp).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            })}
          </span>
        </div>
        <p className="mt-0.5 text-xs text-[var(--text-primary)] leading-relaxed">
          {event.message}
        </p>
      </div>
    </div>
  );
}

export default function AuditTimeline({ events }: AuditTimelineProps) {
  const [expanded, setExpanded] = useState(false);

  if (!events.length) return null;

  const visible = expanded ? events : events.slice(-5);
  const hidden = events.length - visible.length;

  return (
    <div className="card">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        onClick={() => setExpanded((p) => !p)}
      >
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
          Audit Timeline
          <span
            className="ml-2 rounded-full px-2 py-0.5 text-xs font-medium"
            style={{ background: 'rgba(249,115,22,0.15)', color: 'var(--accent)' }}
          >
            {events.length}
          </span>
        </h3>
        <span className="text-[var(--text-secondary)] text-xs">
          {expanded ? '▲ Collapse' : '▼ Expand'}
        </span>
      </button>

      {expanded || visible.length > 0 ? (
        <div className="mt-3">
          {!expanded && hidden > 0 && (
            <p className="text-xs text-[var(--text-secondary)] mb-2">
              … {hidden} earlier events hidden
            </p>
          )}
          {visible.map((evt, i) => (
            <EventRow key={evt.id ?? `${evt.stage}-${i}`} event={evt} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
