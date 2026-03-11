'use client';

// app/page.tsx — FireReach main UI
// ICP form + live agent step stream + email result display

import { useState, FormEvent } from 'react';
import { useAgentStream, AgentEvent } from '../hooks/useAgentStream';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ─── Types ───────────────────────────────────────────────────────────────────

interface OutreachRequest {
  company_name: string;
  company_domain: string;
  icp_description: string;
  tone: 'warm' | 'direct' | 'consultative';
}

// ─── Stage labels for the progress timeline ──────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  init: '🚀 Initialising',
  stage_1: '📡 Signal Harvester',
  stage_2: '🔍 Contact Resolver',
  stage_3: '🧠 Research Analyst',
  stage_4: '📧 Outreach Sender',
  error: '❌ Error',
};

// ─── Sub-components ──────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    idle: 'bg-gray-100 text-gray-600',
    connecting: 'bg-yellow-100 text-yellow-700',
    running: 'bg-blue-100 text-blue-700',
    done: 'bg-green-100 text-green-700',
    error: 'bg-red-100 text-red-700',
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-medium ${colors[status] ?? colors.idle}`}
    >
      {status === 'running' && (
        <span className="mr-2 h-2 w-2 animate-pulse rounded-full bg-blue-500" />
      )}
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function IcpScoreBadge({ score, label }: { score: number; label: string }) {
  const color =
    score >= 8
      ? 'bg-green-100 text-green-700 border-green-300'
      : score >= 5
      ? 'bg-yellow-100 text-yellow-700 border-yellow-300'
      : 'bg-red-100 text-red-700 border-red-300';
  return (
    <span
      className={`inline-flex items-center rounded-lg border px-3 py-1 text-sm font-semibold ${color}`}
    >
      ICP Match: {score}/10 — {label}
    </span>
  );
}

function QualityBadge({ score }: { score: number }) {
  const color =
    score >= 8
      ? 'bg-indigo-100 text-indigo-700'
      : score >= 6
      ? 'bg-blue-100 text-blue-700'
      : 'bg-gray-100 text-gray-600';
  return (
    <span className={`inline-flex items-center rounded-lg px-3 py-1 text-sm font-semibold ${color}`}>
      Quality Score: {score.toFixed(1)} / 10
    </span>
  );
}

function EventRow({ event }: { event: AgentEvent }) {
  const label = STAGE_LABELS[event.stage ?? ''] ?? event.stage ?? '•';
  const isError = event.status === 'error';
  const isDone = event.status === 'done';

  return (
    <div
      className={`rounded-lg border p-4 text-sm ${
        isError
          ? 'border-red-200 bg-red-50'
          : isDone
          ? 'border-green-200 bg-green-50'
          : 'border-gray-200 bg-white'
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <span className="font-medium text-gray-800">{label}</span>
        <span className="shrink-0 text-xs text-gray-400">
          {new Date(event.timestamp).toLocaleTimeString()}
        </span>
      </div>
      <p className="mt-1 text-gray-600">{event.message}</p>

      {/* Stage-specific data cards */}
      {event.stage === 'stage_1' && event.data != null && event.data.icp_score !== undefined ? (
        <div className="mt-2">
          <IcpScoreBadge
            score={Number(event.data.icp_score)}
            label={String(event.data.icp_label ?? '')}
          />
          {Array.isArray(event.data.tech_stack) && event.data.tech_stack.length > 0 ? (
            <p className="mt-1 text-xs text-gray-500">
              Tech: {(event.data.tech_stack as string[]).slice(0, 5).join(', ')}
            </p>
          ) : null}
        </div>
      ) : null}

      {event.stage === 'stage_2' && event.data?.name != null ? (
        <p className="mt-1 text-xs text-gray-500">
          {String(event.data.name)} · {String(event.data.title ?? '')} ·{' '}
          {event.data.smtp_verified ? '✓ SMTP verified' : '⚠ unverified'}
        </p>
      ) : null}

      {event.stage === 'stage_4' && event.data?.quality_score !== undefined && (
        <div className="mt-2 space-y-2">
          <QualityBadge score={Number(event.data.quality_score)} />
          {!!event.data.email_preview && (
            <pre className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700 font-mono">
              {String(event.data.email_preview)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function Home() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const { events, status, reset } = useAgentStream(jobId);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    reset();

    const form = e.currentTarget;
    const data = new FormData(form);

    const payload: OutreachRequest = {
      company_name: (data.get('company_name') as string).trim(),
      company_domain: (data.get('company_domain') as string).trim(),
      icp_description: (data.get('icp_description') as string).trim(),
      tone: data.get('tone') as OutreachRequest['tone'],
    };

    if (!payload.company_name || !payload.company_domain || !payload.icp_description) {
      setFormError('All fields are required.');
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/run-outreach`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error((err as { detail: string }).detail ?? 'Request failed');
      }

      const { job_id } = (await res.json()) as { job_id: string };
      setJobId(job_id);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setIsSubmitting(false);
    }
  }

  const isDone = status === 'done' || status === 'error';
  const lastStage4 = [...events].reverse().find((e) => e.stage === 'stage_4');
  const emailSent =
    lastStage4?.data?.status === 'sent' ||
    (lastStage4?.status === 'done' && lastStage4?.data?.message_id);

  return (
    <main className="min-h-screen bg-gradient-to-br from-orange-50 to-amber-50 px-4 py-12">
      <div className="mx-auto max-w-2xl space-y-8">
        {/* Header */}
        <header className="text-center">
          <h1 className="text-4xl font-bold text-orange-600">🔥 FireReach</h1>
          <p className="mt-2 text-gray-600 text-lg">
            Autonomous outreach engine — signals → contact → brief → email
          </p>
        </header>

        {/* Input Form */}
        <section className="rounded-2xl border border-orange-100 bg-white p-6 shadow-sm">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="company_name" className="block text-sm font-medium text-gray-700">
                Company Name
              </label>
              <input
                id="company_name"
                name="company_name"
                type="text"
                placeholder="Acme Corp"
                required
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-400 focus:outline-none focus:ring-1 focus:ring-orange-400"
              />
            </div>

            <div>
              <label htmlFor="company_domain" className="block text-sm font-medium text-gray-700">
                Company Domain
              </label>
              <input
                id="company_domain"
                name="company_domain"
                type="text"
                placeholder="acme.com"
                required
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-400 focus:outline-none focus:ring-1 focus:ring-orange-400"
              />
            </div>

            <div>
              <label htmlFor="icp_description" className="block text-sm font-medium text-gray-700">
                Your ICP &amp; Value Proposition
              </label>
              <textarea
                id="icp_description"
                name="icp_description"
                rows={4}
                placeholder="e.g. We sell a cloud security posture management platform to Series B–D SaaS companies scaling their infrastructure. Our ICP is security engineers and CTOs concerned about compliance and infrastructure exposure as headcount grows."
                required
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-400 focus:outline-none focus:ring-1 focus:ring-orange-400"
              />
            </div>

            <div>
              <label htmlFor="tone" className="block text-sm font-medium text-gray-700">
                Email Tone
              </label>
              <select
                id="tone"
                name="tone"
                defaultValue="consultative"
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-400 focus:outline-none focus:ring-1 focus:ring-orange-400"
              >
                <option value="consultative">Consultative</option>
                <option value="direct">Direct</option>
                <option value="warm">Warm</option>
              </select>
            </div>

            {formError && (
              <p className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">{formError}</p>
            )}

            <button
              type="submit"
              disabled={isSubmitting || (!!jobId && !isDone)}
              className="w-full rounded-lg bg-orange-500 px-4 py-3 font-semibold text-white transition hover:bg-orange-600 disabled:opacity-50"
            >
              {isSubmitting ? 'Starting…' : jobId && !isDone ? 'Running…' : '🔥 Run FireReach'}
            </button>
          </form>
        </section>

        {/* Live Agent Stream */}
        {jobId && (
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-800">Agent Live Stream</h2>
              <StatusBadge status={status} />
            </div>

            <div className="space-y-3">
              {events.map((evt, i) => (
                <EventRow key={evt.id ?? i} event={evt} />
              ))}
              {status === 'connecting' && (
                <div className="rounded-lg border border-dashed border-gray-300 p-4 text-center text-sm text-gray-400">
                  Connecting to agent stream…
                </div>
              )}
            </div>

            {/* Final summary */}
            {isDone && (
              <div
                className={`rounded-xl border-2 p-5 text-center ${
                  emailSent
                    ? 'border-green-300 bg-green-50'
                    : 'border-yellow-300 bg-yellow-50'
                }`}
              >
                {emailSent ? (
                  <>
                    <p className="text-2xl">✅</p>
                    <p className="mt-1 font-semibold text-green-700">Email dispatched successfully</p>
                    {lastStage4?.data?.quality_score !== undefined && (
                      <div className="mt-2 flex justify-center">
                        <QualityBadge score={Number(lastStage4.data.quality_score)} />
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <p className="text-2xl">⚠️</p>
                    <p className="mt-1 font-semibold text-yellow-700">
                      {String(lastStage4?.message ?? 'Pipeline complete — check logs for details')}
                    </p>
                  </>
                )}
                <button
                  onClick={() => {
                    setJobId(null);
                    reset();
                  }}
                  className="mt-4 rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200"
                >
                  Run another
                </button>
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
