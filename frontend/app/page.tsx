'use client';

// app/page.tsx — FireReach v3 — two-panel live outreach UI

import { useState } from 'react';
import { useAgentStream } from '../hooks/useAgentStream';
import ICPForm, { ICPFormValues } from '../components/ICPForm';
import LaunchButton from '../components/LaunchButton';
import PipelineStageCard from '../components/PipelineStageCard';
import ICPScoreGauge from '../components/ICPScoreGauge';
import ContactCard from '../components/ContactCard';
import SignalSummaryPanel from '../components/SignalSummaryPanel';
import EmailPreviewCard from '../components/EmailPreviewCard';
import AuditTimeline from '../components/AuditTimeline';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ─── Validation ───────────────────────────────────────────────────────────────

function validate(v: ICPFormValues): Partial<Record<keyof ICPFormValues, string>> {
  const e: Partial<Record<keyof ICPFormValues, string>> = {};
  if (!v.company_name.trim()) e.company_name = 'Company name is required.';
  if (!v.company_domain.trim()) e.company_domain = 'Domain is required.';
  else if (!/^[a-z0-9-]+\.[a-z]{2,}$/i.test(v.company_domain.trim()))
    e.company_domain = 'Enter a valid domain (e.g. acme.com).';
  if (!v.industry) e.industry = 'Select an industry.';
  if (!v.size_range) e.size_range = 'Select a company size.';
  if (!v.funding_stage) e.funding_stage = 'Select a funding stage.';
  if (v.geography.length === 0) e.geography = 'Select at least one geography.';
  if (v.target_titles.length === 0) e.target_titles = 'Select at least one title.';
  if (!v.pain_points.trim()) e.pain_points = 'Describe the pain points you solve.';
  if (!v.your_product.trim()) e.your_product = 'Describe your product or service.';
  return e;
}

const EMPTY_FORM: ICPFormValues = {
  company_name: '',
  company_domain: '',
  industry: '',
  size_range: '',
  funding_stage: '',
  geography: [],
  pain_points: '',
  your_product: '',
  target_titles: [],
  tone: 'consultative',
};

// ─── Stage config ─────────────────────────────────────────────────────────────

const STAGES = [
  { stage: 1, title: 'Signal Harvester', tool: 'signal_harvester', key: 'stage_1' },
  { stage: 2, title: 'Contact Resolver', tool: 'contact_resolver', key: 'stage_2' },
  { stage: 3, title: 'Research Analyst', tool: 'research_analyst', key: 'stage_3' },
  { stage: 4, title: 'Outreach Sender',  tool: 'outreach_sender',  key: 'stage_4' },
] as const;

type StageKey = (typeof STAGES)[number]['key'];
type StageStatus = 'idle' | 'active' | 'complete' | 'error';

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function Home() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<ICPFormValues>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof ICPFormValues, string>>>({});

  const { events, status, reset } = useAgentStream(jobId);

  const isRunning = isSubmitting || status === 'connecting' || status === 'running';
  const isDone = status === 'done' || status === 'error';

  // ── derive per-stage status from SSE events ──
  const stageStatuses = STAGES.reduce<Record<StageKey, StageStatus>>(
    (acc, s) => { acc[s.key] = 'idle'; return acc; },
    {} as Record<StageKey, StageStatus>
  );
  for (const evt of events) {
    const key = evt.stage as StageKey | null;
    if (!key || !(key in stageStatuses)) continue;
    if (evt.status === 'error') stageStatuses[key] = 'error';
    else if (evt.status === 'done') stageStatuses[key] = 'complete';
    else stageStatuses[key] = 'active';
  }

  // ── derive per-stage latest output message ──
  const stageOutputs = STAGES.reduce<Record<StageKey, string>>(
    (acc, s) => { acc[s.key] = ''; return acc; },
    {} as Record<StageKey, string>
  );
  for (const evt of events) {
    const key = evt.stage as StageKey | null;
    if (key && key in stageOutputs && evt.message) stageOutputs[key] = evt.message;
  }

  // ── parse result data from last relevant events ──
  const lastByStage = (key: string) =>
    [...events].reverse().find((e) => e.stage === key);

  const icpScoreEvent = lastByStage('icp_score');
  const icpScoreResult = icpScoreEvent?.data as Record<string, unknown> | null | undefined;

  const stage2Event = lastByStage('stage_2');
  let contact = stage2Event?.data as Record<string, unknown> | null | undefined;
  if (contact && 'contact' in contact) {
    contact = contact.contact as Record<string, unknown>;
  }

  const stage1Event = lastByStage('stage_1');
  const signalsData = stage1Event?.data as Record<string, unknown> | null | undefined;

  const stage4Event = lastByStage('stage_4');
  const emailData = stage4Event?.data as Record<string, unknown> | null | undefined;

  // ── signal list for SignalSummaryPanel ──
  const signalRows = signalsData
    ? [
        { type: 'Funding Signal (S1)', found: !!signalsData.funding_signal, detail: signalsData.funding_signal ? String((signalsData.funding_signal as Record<string, unknown>).summary ?? '') : '' },
        { type: 'Hiring Signal (S2)',  found: !!signalsData.hiring_signal,  detail: signalsData.hiring_signal  ? `${(signalsData.hiring_signal as Record<string, unknown>).open_roles ?? 0} roles` : '' },
        { type: 'Security Signal (S3)', found: !!signalsData.security_signal, detail: signalsData.security_signal ? String((signalsData.security_signal as Record<string, unknown>).summary ?? '') : '' },
        { type: 'Sales Signal (S4)',  found: !!signalsData.sales_signal,  detail: signalsData.sales_signal   ? String((signalsData.sales_signal as Record<string, unknown>).summary ?? '') : '' },
        { type: 'Tech Stack (S5)',    found: Array.isArray(signalsData.tech_stack) && (signalsData.tech_stack as unknown[]).length > 0, detail: Array.isArray(signalsData.tech_stack) ? (signalsData.tech_stack as string[]).slice(0, 5).join(', ') : '' },
        { type: 'Market Signal (S6)', found: !!signalsData.market_signal,  detail: signalsData.market_signal  ? String((signalsData.market_signal as Record<string, unknown>).headline ?? '') : '' },
      ]
    : [];

  async function handleLaunch() {
    const errs = validate(formValues);
    if (Object.keys(errs).length > 0) { setFormErrors(errs); return; }
    setFormErrors({});
    setFormError(null);
    reset();

    const payload = {
      company_name: formValues.company_name.trim(),
      company_domain: formValues.company_domain.trim(),
      tone: formValues.tone,
      icp: {
        industry: formValues.industry,
        size_range: formValues.size_range,
        funding_stage: formValues.funding_stage,
        geography: formValues.geography,
        pain_points: formValues.pain_points.trim(),
        your_product: formValues.your_product.trim(),
        target_titles: formValues.target_titles,
      },
    };

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

  function handleReset() {
    setJobId(null);
    reset();
    setFormValues(EMPTY_FORM);
    setFormErrors({});
    setFormError(null);
  }

  return (
    <div
      className="min-h-screen"
      style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
    >
      {/* ── Top Nav ── */}
      <nav
        className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b"
        style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <span style={{ fontSize: '1.3rem' }}>🔥</span>
          <span className="font-bold tracking-wide" style={{ color: 'var(--accent)' }}>
            FireReach
          </span>
          <span
            className="text-xs rounded-full px-2 py-0.5 ml-1"
            style={{ background: 'rgba(249,115,22,0.15)', color: 'var(--accent)' }}
          >
            v3.0
          </span>
        </div>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          Autonomous outreach engine
        </span>
      </nav>

      {/* ── Two-panel body ── */}
      <div className="flex flex-col md:flex-row gap-6 p-6 max-w-[1400px] mx-auto">

        {/* ─── LEFT PANEL (30%) — ICP Form + Launch ─── */}
        <aside
          className="w-full md:w-[30%] shrink-0 rounded-xl p-5 self-start sticky top-[73px]"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        >
          <h2
            className="text-sm font-bold uppercase tracking-widest mb-4"
            style={{ color: 'var(--text-muted)' }}
          >
            Target Profile
          </h2>

          <ICPForm
            values={formValues}
            onChange={setFormValues}
            errors={formErrors}
            disabled={isRunning}
          />

          {formError && (
            <p
              className="mt-3 text-xs rounded-lg px-3 py-2"
              style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--error)' }}
            >
              {formError}
            </p>
          )}

          <div className="mt-5">
            {isDone ? (
              <button
                onClick={handleReset}
                className="w-full rounded-xl py-3 text-sm font-semibold transition"
                style={{
                  background: 'rgba(255,255,255,0.07)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                }}
              >
                ↩ Run Another
              </button>
            ) : (
              <LaunchButton
                isLoading={isRunning}
                disabled={isRunning}
                onClick={handleLaunch}
              />
            )}
          </div>
        </aside>

        {/* ─── RIGHT PANEL (70%) — Pipeline + Results ─── */}
        <main className="flex-1 min-w-0 space-y-6">

          {/* ── Pipeline stages ── */}
          <section>
            <h2
              className="text-sm font-bold uppercase tracking-widest mb-3"
              style={{ color: 'var(--text-muted)' }}
            >
              Pipeline
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {STAGES.map(({ stage, title, tool, key }) => (
                <PipelineStageCard
                  key={key}
                  stage={stage}
                  title={title}
                  tool={tool}
                  status={stageStatuses[key]}
                  output={stageOutputs[key]}
                />
              ))}
            </div>
          </section>

          {/* ── ICP Score — shown after icp_score event ── */}
          {icpScoreResult && (
            <section>
              <h2
                className="text-sm font-bold uppercase tracking-widest mb-3"
                style={{ color: 'var(--text-muted)' }}
              >
                ICP Fit Score
              </h2>
              <ICPScoreGauge
                score={Number(icpScoreResult.total_score ?? 0)}
                tier={String(icpScoreResult.tier ?? 'poor_fit') as 'hot' | 'warm' | 'potential' | 'poor_fit'}
                breakdown={
                  icpScoreResult.breakdown as Record<string, { score: number; max: number; label: string }> | undefined
                }
              />
              {icpScoreResult.why_now && (
                <p
                  className="mt-3 text-sm rounded-lg px-4 py-3"
                  style={{ background: 'rgba(249,115,22,0.08)', color: 'var(--text-secondary)', border: '1px solid rgba(249,115,22,0.2)' }}
                >
                  <span style={{ color: 'var(--accent)', fontWeight: 600 }}>Why now: </span>
                  {String(icpScoreResult.why_now)}
                </p>
              )}
            </section>
          )}

          {/* ── Results row: Contact + Signals ── */}
          {(contact || signalRows.length > 0) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {contact && (
                <section>
                  <h2
                    className="text-sm font-bold uppercase tracking-widest mb-3"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    Contact
                  </h2>
                  <ContactCard
                    name={contact.name ? String(contact.name) : "Contact Not Found"}
                    title={contact.title ? String(contact.title) : "Could not resolve decision-maker"}
                    email={contact.email ? String(contact.email) : "No email found"}
                    verified={!!contact.smtp_verified}
                    linkedin_url={contact.linkedin_url ? String(contact.linkedin_url) : undefined}
                    seniority={contact.seniority ? String(contact.seniority) : undefined}
                  />
                </section>
              )}
              {signalRows.length > 0 && (
                <section>
                  <h2
                    className="text-sm font-bold uppercase tracking-widest mb-3"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    Signals
                  </h2>
                  <SignalSummaryPanel signals={signalRows} />
                </section>
              )}
            </div>
          )}

          {/* ── Email preview ── */}
          {emailData && emailData.email_preview && (
            <section>
              <h2
                className="text-sm font-bold uppercase tracking-widest mb-3"
                style={{ color: 'var(--text-muted)' }}
              >
                Generated Email
              </h2>
              <EmailPreviewCard
                subject={emailData.subject ? String(emailData.subject) : 'Outreach from FireReach'}
                body={String(emailData.email_preview)}
                recipient={contact?.email ? String(contact.email) : ''}
              />
            </section>
          )}

          {/* ── Audit Timeline (always visible when events exist) ── */}
          {events.length > 0 && (
            <section>
              <AuditTimeline events={events} />
            </section>
          )}

          {/* ── Empty state ── */}
          {!jobId && events.length === 0 && (
            <div
              className="flex flex-col items-center justify-center rounded-xl py-20 text-center"
              style={{ border: '1px dashed var(--border)' }}
            >
              <span style={{ fontSize: '3rem' }}>🔥</span>
              <p className="mt-4 text-lg font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Configure your target profile
              </p>
              <p className="mt-1 text-sm" style={{ color: 'var(--text-muted)' }}>
                Fill in the ICP form on the left and click Launch FireReach
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
