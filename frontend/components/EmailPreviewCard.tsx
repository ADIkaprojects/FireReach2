'use client';

// components/EmailPreviewCard.tsx
// Styled email preview card with copy-to-clipboard and resend capabilities.

import { useState, useCallback } from 'react';

interface EmailPreviewCardProps {
  subject: string;
  body: string;
  recipient: string;
  onResend?: () => void;
  isSending?: boolean;
}

export default function EmailPreviewCard({
  subject,
  body,
  recipient,
  onResend,
  isSending = false,
}: EmailPreviewCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard not available — silently ignore
    }
  }, [subject, body]);

  return (
    <div className="card">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)] mb-3">
        Email Preview
      </h3>

      {/* Header */}
      <div
        className="rounded-t-lg px-4 py-3"
        style={{ background: 'rgba(249,115,22,0.1)', borderBottom: '1px solid var(--border)' }}
      >
        <p className="text-xs text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--text-primary)]">To:</span>{' '}
          {recipient}
        </p>
        <p className="mt-1 text-sm font-semibold text-[var(--text-primary)] leading-snug">
          {subject}
        </p>
      </div>

      {/* Body */}
      <div
        className="rounded-b-lg px-4 py-4"
        style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderTop: 'none' }}
      >
        <pre
          className="text-sm leading-relaxed whitespace-pre-wrap break-words font-mono"
          style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono, monospace)' }}
        >
          {body}
        </pre>
      </div>

      {/* Actions */}
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
          style={{
            background: copied ? 'rgba(34,197,94,0.15)' : 'rgba(255,255,255,0.07)',
            color: copied ? 'var(--success)' : 'var(--text-secondary)',
            border: '1px solid var(--border)',
          }}
        >
          {copied ? '✓ Copied' : '📋 Copy'}
        </button>

        {onResend && (
          <button
            type="button"
            onClick={onResend}
            disabled={isSending}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50"
            style={{
              background: 'rgba(249,115,22,0.15)',
              color: 'var(--accent)',
              border: '1px solid rgba(249,115,22,0.3)',
            }}
          >
            {isSending ? '⏳ Sending…' : '🔁 Resend'}
          </button>
        )}
      </div>
    </div>
  );
}
