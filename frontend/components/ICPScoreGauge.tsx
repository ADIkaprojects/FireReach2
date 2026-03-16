'use client';

// components/ICPScoreGauge.tsx
// Circular SVG gauge showing ICP fit score (0–100) with tier label and color coding.

interface ICPScoreGaugeProps {
  score: number;
  tier: 'hot' | 'warm' | 'potential' | 'poor_fit';
  breakdown?: Record<string, { points: number; max: number; detail: string }>;
}

const TIER_CONFIG = {
  hot:       { color: 'var(--success)',  label: '🔥 HOT LEAD',  textColor: '#22C55E' },
  warm:      { color: 'var(--accent)',   label: '⚡ WARM LEAD', textColor: '#F97316' },
  potential: { color: 'var(--warning)',  label: '🌤 POTENTIAL', textColor: '#EAB308' },
  poor_fit:  { color: 'var(--error)',    label: '❌ POOR FIT',  textColor: '#EF4444' },
};

export default function ICPScoreGauge({
  score,
  tier,
  breakdown,
}: ICPScoreGaugeProps) {
  const config = TIER_CONFIG[tier] ?? TIER_CONFIG.potential;
  const clampedScore = Math.max(0, Math.min(100, score));

  // SVG arc parameters
  const radius = 56;
  const cx = 72;
  const cy = 72;
  const circumference = 2 * Math.PI * radius;
  // Only use the top 270° of the circle (start at 135°, sweep 270°)
  const arcLength = (clampedScore / 100) * (circumference * 0.75);
  const dashoffset = circumference * 0.75 - arcLength;

  return (
    <div className="card text-center">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)] mb-3">
        ICP Fit Score
      </h3>

      <div className="flex justify-center">
        <svg width="144" height="144" viewBox="0 0 144 144" aria-label={`ICP score ${score}/100`}>
          {/* Background track */}
          <circle
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke="var(--border)"
            strokeWidth="10"
            strokeDasharray={`${circumference * 0.75} ${circumference * 0.25}`}
            strokeDashoffset={0}
            strokeLinecap="round"
            transform={`rotate(135 ${cx} ${cy})`}
          />
          {/* Score arc */}
          <circle
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke={config.color}
            strokeWidth="10"
            strokeDasharray={`${arcLength} ${circumference - arcLength}`}
            strokeDashoffset={dashoffset}
            strokeLinecap="round"
            transform={`rotate(135 ${cx} ${cy})`}
            style={{ transition: 'stroke-dasharray 0.8s ease, stroke-dashoffset 0.8s ease' }}
          />
          {/* Score number */}
          <text
            x={cx}
            y={cy - 4}
            textAnchor="middle"
            dominantBaseline="middle"
            className="gauge-text"
            fill="var(--text-primary)"
            fontSize="28"
            fontWeight="700"
          >
            {clampedScore}
          </text>
          <text
            x={cx}
            y={cy + 18}
            textAnchor="middle"
            fill="var(--text-secondary)"
            fontSize="11"
          >
            / 100
          </text>
        </svg>
      </div>

      <p className="mt-1 text-sm font-bold" style={{ color: config.textColor }}>
        {config.label}
      </p>

      {breakdown && (
        <div className="mt-4 space-y-1.5 text-left">
          {Object.entries(breakdown).map(([key, val]) => (
            <div key={key} className="flex items-center justify-between text-xs">
              <span className="text-[var(--text-secondary)] capitalize">{key}</span>
              <div className="flex items-center gap-2">
                <div
                  className="h-1.5 rounded-full"
                  style={{
                    width: '60px',
                    background: 'var(--border)',
                    position: 'relative',
                  }}
                >
                  <div
                    className="h-1.5 rounded-full absolute left-0 top-0"
                    style={{
                      width: `${(val.points / val.max) * 100}%`,
                      background: config.color,
                      transition: 'width 0.6s ease',
                    }}
                  />
                </div>
                <span className="text-[var(--text-primary)] font-medium w-8 text-right">
                  {val.points}/{val.max}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
