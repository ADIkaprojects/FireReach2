'use client';

// components/LaunchButton.tsx
// Primary CTA — large orange button with animated rocket/fire icon and spinner.

interface LaunchButtonProps {
  isLoading: boolean;
  disabled?: boolean;
  onClick?: () => void;
}

export default function LaunchButton({ isLoading, disabled, onClick }: LaunchButtonProps) {
  const isDisabled = disabled || isLoading;

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={isDisabled}
      className="relative w-full flex items-center justify-center gap-2.5 rounded-xl font-semibold text-sm tracking-wide transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2"
      style={{
        padding: '14px 24px',
        background: isDisabled
          ? 'rgba(249,115,22,0.35)'
          : 'var(--accent)',
        color: '#ffffff',
        cursor: isDisabled ? 'not-allowed' : 'pointer',
        boxShadow: isDisabled ? 'none' : '0 4px 24px rgba(249,115,22,0.35)',
        focusRingColor: 'var(--accent)',
        focusRingOffsetColor: 'var(--bg-primary)',
      } as React.CSSProperties}
    >
      {isLoading ? (
        <>
          <Spinner />
          <span>Agent Running…</span>
          <span className="absolute right-4 text-xs text-orange-200/70 font-mono">
            analyzing
          </span>
        </>
      ) : (
        <>
          <span style={{ fontSize: '1.1rem' }}>🔥</span>
          <span>Launch FireReach</span>
        </>
      )}
    </button>
  );
}

function Spinner() {
  return (
    <svg
      className="animate-spin"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="8"
        cy="8"
        r="6"
        stroke="rgba(255,255,255,0.3)"
        strokeWidth="2.5"
      />
      <path
        d="M8 2 A6 6 0 0 1 14 8"
        stroke="white"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
