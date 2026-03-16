'use client';

// components/ContactCard.tsx
// Displays resolved contact details with verification badge and LinkedIn link.

interface ContactCardProps {
  name: string;
  title: string;
  email: string;
  verified: boolean;
  linkedin_url?: string;
  seniority?: string;
}

function Initials({ name }: { name: string }) {
  const parts = name.trim().split(/\s+/);
  const initials = parts.length >= 2
    ? `${parts[0][0]}${parts[parts.length - 1][0]}`
    : parts[0]?.[0] ?? '?';
  return (
    <div
      className="flex items-center justify-center h-12 w-12 rounded-full text-white font-bold text-lg flex-shrink-0"
      style={{ background: 'linear-gradient(135deg, var(--accent), #c2410c)' }}
      aria-hidden="true"
    >
      {initials.toUpperCase()}
    </div>
  );
}

export default function ContactCard({
  name,
  title,
  email,
  verified,
  linkedin_url,
  seniority,
}: ContactCardProps) {
  return (
    <div className="card">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)] mb-3">
        Resolved Contact
      </h3>

      <div className="flex items-start gap-3">
        <Initials name={name} />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-[var(--text-primary)]">{name}</span>
            {seniority && (
              <span
                className="text-xs rounded px-1.5 py-0.5 font-medium"
                style={{ background: 'rgba(249,115,22,0.15)', color: 'var(--accent)' }}
              >
                {seniority.replace(/_/g, ' ').toUpperCase()}
              </span>
            )}
          </div>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5">{title}</p>

          <div className="mt-2 flex items-center gap-1.5 flex-wrap">
            <a
              href={`mailto:${email}`}
              className="text-xs text-[var(--accent)] hover:underline font-mono break-all"
            >
              {email}
            </a>
            {verified ? (
              <span
                className="inline-flex items-center gap-1 text-xs rounded-full px-2 py-0.5 font-medium"
                style={{ background: 'rgba(34,197,94,0.15)', color: 'var(--success)' }}
              >
                ✓ Verified
              </span>
            ) : (
              <span
                className="inline-flex items-center gap-1 text-xs rounded-full px-2 py-0.5 font-medium"
                style={{ background: 'rgba(234,179,8,0.15)', color: 'var(--warning)' }}
              >
                ⚠ Unverified
              </span>
            )}
          </div>

          {linkedin_url && (
            <a
              href={linkedin_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors"
            >
              <svg
                className="h-4 w-4"
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z" />
              </svg>
              LinkedIn Profile
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
