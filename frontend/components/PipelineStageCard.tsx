'use client';

// components/PipelineStageCard.tsx
// Animated card for each of the 4 pipeline stages.

interface PipelineStageCardProps {
  stage: number;
  title: string;
  tool: string;
  status: 'idle' | 'active' | 'complete' | 'error';
  output: string;
}

const STATUS_ICONS: Record<PipelineStageCardProps['status'], string> = {
  idle: '○',
  active: '◉',
  complete: '✅',
  error: '❌',
};

export default function PipelineStageCard({
  stage,
  title,
  tool,
  status,
  output,
}: PipelineStageCardProps) {
  const borderClass =
    status === 'active'
      ? 'stage-active border-[var(--accent)]'
      : status === 'complete'
      ? 'border-[var(--success)]'
      : status === 'error'
      ? 'border-[var(--error)]'
      : 'border-[var(--border)]';

  const iconColor =
    status === 'complete'
      ? 'text-[var(--success)]'
      : status === 'error'
      ? 'text-[var(--error)]'
      : status === 'active'
      ? 'text-[var(--accent)]'
      : 'text-[var(--text-secondary)]';

  return (
    <div
      className={`card transition-all duration-300 ${borderClass}`}
      style={{
        boxShadow:
          status === 'complete'
            ? 'var(--glow-success)'
            : undefined,
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span
            className={`flex-shrink-0 text-xs font-bold rounded px-1.5 py-0.5 ${
              status === 'active'
                ? 'bg-[var(--accent)] text-white'
                : 'bg-[var(--border)] text-[var(--text-secondary)]'
            }`}
          >
            S{stage}
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)] truncate">{title}</p>
            <p className="text-xs text-[var(--text-secondary)] truncate">{tool}</p>
          </div>
        </div>
        <span className={`text-lg flex-shrink-0 ${iconColor}`}>{STATUS_ICONS[status]}</span>
      </div>

      {output && (
        <div
          className={`mt-3 rounded-lg p-3 text-xs leading-relaxed font-mono whitespace-pre-wrap break-words max-h-40 overflow-y-auto ${
            status === 'active' ? 'cursor' : ''
          }`}
          style={{
            background: 'rgba(255,255,255,0.03)',
            color: 'var(--text-secondary)',
            border: '1px solid var(--border)',
          }}
        >
          {output}
        </div>
      )}

      {status === 'active' && !output && (
        <div className="mt-3 flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <span
            className="inline-block h-2 w-2 rounded-full bg-[var(--accent)] animate-pulse"
          />
          Running…
        </div>
      )}
    </div>
  );
}
