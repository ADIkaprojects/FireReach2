'use client';

// components/ICPForm.tsx
// Full ICP form with all 7 fields, client-side validation, and disabled state.

import { useId } from 'react';

export interface ICPFormValues {
  company_name: string;
  company_domain: string;
  industry: string;
  size_range: string;
  funding_stage: string;
  geography: string[];
  pain_points: string;
  your_product: string;
  target_titles: string[];
  tone: 'warm' | 'direct' | 'consultative';
}

interface ICPFormProps {
  values: ICPFormValues;
  onChange: (values: ICPFormValues) => void;
  errors: Partial<Record<keyof ICPFormValues, string>>;
  disabled?: boolean;
}

const INDUSTRIES = ['SaaS', 'Fintech', 'Healthcare', 'E-commerce', 'Cybersecurity', 'Logistics', 'Other'];
const SIZE_RANGES = ['1-10', '10-50', '50-200', '200-500', '500-1000', '1000+'];
const FUNDING_STAGES = ['Bootstrapped', 'Pre-Seed', 'Seed', 'Series A', 'Series B', 'Series C+', 'IPO'];
const GEOGRAPHIES = ['US', 'Europe', 'India', 'Asia', 'LatAm', 'Global'];
const TARGET_TITLES = ['CTO', 'VP Engineering', 'CISO', 'Head of Security', 'VP Product', 'CEO', 'CFO', 'DevOps Lead', 'Other'];

function FieldLabel({ htmlFor, text }: { htmlFor: string; text: string }) {
  return (
    <label htmlFor={htmlFor} className="block text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-1.5">
      {text}
    </label>
  );
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="mt-1 text-xs text-[var(--error)]">{message}</p>;
}

function MultiSelect({
  id,
  options,
  selected,
  onChange,
  disabled,
}: {
  id: string;
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
  disabled?: boolean;
}) {
  const toggle = (opt: string) => {
    if (disabled) return;
    onChange(
      selected.includes(opt)
        ? selected.filter((s) => s !== opt)
        : [...selected, opt]
    );
  };

  return (
    <div id={id} className="flex flex-wrap gap-1.5" role="group">
      {options.map((opt) => {
        const isActive = selected.includes(opt);
        return (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            disabled={disabled}
            className="rounded-full px-2.5 py-1 text-xs font-medium transition-all disabled:opacity-50"
            style={{
              background: isActive ? 'var(--accent)' : 'rgba(255,255,255,0.06)',
              color: isActive ? '#fff' : 'var(--text-secondary)',
              border: `1px solid ${isActive ? 'var(--accent)' : 'var(--border)'}`,
            }}
          >
            {opt}
          </button>
        );
      })}
    </div>
  );
}

export default function ICPForm({ values, onChange, errors, disabled }: ICPFormProps) {
  const uid = useId();

  const set = <K extends keyof ICPFormValues>(key: K, val: ICPFormValues[K]) =>
    onChange({ ...values, [key]: val });

  return (
    <div className="space-y-4">
      {/* Company Name */}
      <div>
        <FieldLabel htmlFor={`${uid}-company`} text="Target Company" />
        <input
          id={`${uid}-company`}
          type="text"
          placeholder="Acme Corp"
          value={values.company_name}
          onChange={(e) => set('company_name', e.target.value)}
          disabled={disabled}
          className="input-base"
        />
        <FieldError message={errors.company_name} />
      </div>

      {/* Company Domain */}
      <div>
        <FieldLabel htmlFor={`${uid}-domain`} text="Company Domain" />
        <input
          id={`${uid}-domain`}
          type="text"
          placeholder="acme.com"
          value={values.company_domain}
          onChange={(e) => set('company_domain', e.target.value)}
          disabled={disabled}
          className="input-base"
        />
        <FieldError message={errors.company_domain} />
      </div>

      {/* Industry */}
      <div>
        <FieldLabel htmlFor={`${uid}-industry`} text="Industry / Vertical" />
        <select
          id={`${uid}-industry`}
          value={values.industry}
          onChange={(e) => set('industry', e.target.value)}
          disabled={disabled}
          className="input-base"
          style={{ appearance: 'none', cursor: 'pointer' }}
        >
          <option value="" disabled>Select industry…</option>
          {INDUSTRIES.map((i) => <option key={i} value={i}>{i}</option>)}
        </select>
        <FieldError message={errors.industry} />
      </div>

      {/* Company Size */}
      <div>
        <FieldLabel htmlFor={`${uid}-size`} text="Company Size Range" />
        <select
          id={`${uid}-size`}
          value={values.size_range}
          onChange={(e) => set('size_range', e.target.value)}
          disabled={disabled}
          className="input-base"
          style={{ appearance: 'none', cursor: 'pointer' }}
        >
          <option value="" disabled>Select size…</option>
          {SIZE_RANGES.map((s) => <option key={s} value={s}>{s} employees</option>)}
        </select>
        <FieldError message={errors.size_range} />
      </div>

      {/* Funding Stage */}
      <div>
        <FieldLabel htmlFor={`${uid}-stage`} text="Funding Stage" />
        <select
          id={`${uid}-stage`}
          value={values.funding_stage}
          onChange={(e) => set('funding_stage', e.target.value)}
          disabled={disabled}
          className="input-base"
          style={{ appearance: 'none', cursor: 'pointer' }}
        >
          <option value="" disabled>Select stage…</option>
          {FUNDING_STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <FieldError message={errors.funding_stage} />
      </div>

      {/* Geography */}
      <div>
        <FieldLabel htmlFor={`${uid}-geo`} text="Target Geography" />
        <MultiSelect
          id={`${uid}-geo`}
          options={GEOGRAPHIES}
          selected={values.geography}
          onChange={(v) => set('geography', v)}
          disabled={disabled}
        />
        <FieldError message={errors.geography} />
      </div>

      {/* Target Job Titles */}
      <div>
        <FieldLabel htmlFor={`${uid}-titles`} text="Target Job Titles" />
        <MultiSelect
          id={`${uid}-titles`}
          options={TARGET_TITLES}
          selected={values.target_titles}
          onChange={(v) => set('target_titles', v)}
          disabled={disabled}
        />
        <FieldError message={errors.target_titles} />
      </div>

      {/* Pain Points */}
      <div>
        <FieldLabel htmlFor={`${uid}-pain`} text="Pain Points You Solve" />
        <textarea
          id={`${uid}-pain`}
          rows={3}
          placeholder="e.g. Scaling infrastructure securely without slowing down developer velocity"
          value={values.pain_points}
          onChange={(e) => set('pain_points', e.target.value)}
          disabled={disabled}
          className="input-base resize-none"
        />
        <FieldError message={errors.pain_points} />
      </div>

      {/* Your Product */}
      <div>
        <FieldLabel htmlFor={`${uid}-product`} text="Your Product / Service" />
        <textarea
          id={`${uid}-product`}
          rows={3}
          placeholder="e.g. Cloud security posture management platform for Series B+ SaaS companies"
          value={values.your_product}
          onChange={(e) => set('your_product', e.target.value)}
          disabled={disabled}
          className="input-base resize-none"
        />
        <FieldError message={errors.your_product} />
      </div>

      {/* Email Tone */}
      <div>
        <FieldLabel htmlFor={`${uid}-tone`} text="Email Tone" />
        <select
          id={`${uid}-tone`}
          value={values.tone}
          onChange={(e) => set('tone', e.target.value as ICPFormValues['tone'])}
          disabled={disabled}
          className="input-base"
          style={{ appearance: 'none', cursor: 'pointer' }}
        >
          <option value="consultative">Consultative</option>
          <option value="direct">Direct</option>
          <option value="warm">Warm</option>
        </select>
      </div>
    </div>
  );
}
