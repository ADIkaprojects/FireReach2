'use client';

// components/SignalSummaryPanel.tsx
// Displays S1–S6 signal types with status icons and detail text.

interface SignalItem {
  type: string;
  found: boolean;
  detail: string;
}

interface SignalSummaryPanelProps {
  signals: SignalItem[];
}

const SIGNAL_ICONS: Record<string, string> = {
  S1: '📋',
  S2: '💰',
  S3: '🔒',
  S4: '🤝',
  S5: '🖥️',
  S6: '📰',
};

export default function SignalSummaryPanel({ signals }: SignalSummaryPanelProps) {
  if (!signals.length) return null;

  return (
    <div className="card">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)] mb-3">
        Signal Summary
      </h3>

      <div className="space-y-2">
        {signals.map((signal) => {
          const icon = SIGNAL_ICONS[signal.type] ?? '•';
          return (
            <div
              key={signal.type}
              className="flex items-start gap-3 rounded-lg p-2.5 text-sm"
              style={{
                background: signal.found
                  ? 'rgba(34,197,94,0.06)'
                  : 'rgba(255,255,255,0.03)',
                border: `1px solid ${signal.found ? 'rgba(34,197,94,0.2)' : 'var(--border)'}`,
              }}
            >
              <span className="text-lg leading-none flex-shrink-0 mt-0.5">{icon}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold text-[var(--text-secondary)]">
                    {signal.type}
                  </span>
                  <span
                    className="text-xs font-medium"
                    style={{ color: signal.found ? 'var(--success)' : 'var(--text-secondary)' }}
                  >
                    {signal.found ? '● Found' : '○ Not found'}
                  </span>
                </div>
                {signal.detail && (
                  <p className="mt-0.5 text-xs text-[var(--text-secondary)] leading-relaxed">
                    {signal.detail}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
