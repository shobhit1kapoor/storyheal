import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, ArrowUpRight, CheckCircle2, ExternalLink, FileDiff, Languages,
  LoaderCircle, Quote, ShieldCheck, Sparkles, XCircle,
} from 'lucide-react';
import { knowledgeOpsApi, type ReviewContext } from '@/services/knowledgeOpsApi';

function Score({ label, value, suffix = '' }: { label: string; value: number; suffix?: string }) {
  const normalized = suffix === '%' ? value : value * 100;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between"><span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</span><span className="font-semibold text-slate-950">{suffix === '%' ? value.toFixed(0) : `${normalized.toFixed(0)}%`}</span></div>
      <div className="mt-3 h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-teal-600" style={{ width: `${Math.min(normalized, 100)}%` }} /></div>
    </div>
  );
}

function JsonPanel({ title, data }: { title: string; data: unknown }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-950">
      <div className="border-b border-slate-800 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</div>
      <pre className="max-h-[420px] overflow-auto p-4 text-xs leading-5 text-slate-200">{data ? JSON.stringify(data, null, 2) : 'No published entry exists yet.'}</pre>
    </div>
  );
}

export default function ProposalReview() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [context, setContext] = useState<ReviewContext | null>(null);
  const [reason, setReason] = useState('');
  const [action, setAction] = useState<'approve' | 'reject' | null>(null);
  const [error, setError] = useState('');

  const load = async () => {
    try { setContext(await knowledgeOpsApi.reviewContext(id)); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not load proposal'); }
  };
  useEffect(() => { void load(); }, [id]);

  const changedFields = useMemo(() => {
    if (!context) return [] as string[];
    const draft = context.proposal.content_payload;
    const published = context.published_entry && typeof context.published_entry.story === 'object'
      ? (context.published_entry.story as Record<string, unknown>).content as Record<string, unknown> | undefined
      : undefined;
    const keys = new Set([...Object.keys(published || {}), ...Object.keys(draft)]);
    return [...keys].filter(key => JSON.stringify(published?.[key]) !== JSON.stringify(draft[key]));
  }, [context]);

  const decide = async (nextAction: 'approve' | 'reject') => {
    if (nextAction === 'reject' && reason.trim().length < 3) {
      setError('A specific rejection reason is required.');
      return;
    }
    setAction(nextAction);
    setError('');
    try {
      if (nextAction === 'approve') await knowledgeOpsApi.approve(id, reason.trim());
      else await knowledgeOpsApi.reject(id, reason.trim());
      navigate('/knowledge-ops');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The decision could not be recorded');
    } finally { setAction(null); }
  };

  if (!context) return (
    <main className="flex flex-1 items-center justify-center bg-[#f4f6f3]">
      {error ? <div className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-rose-700">{error}</div> : <LoaderCircle className="h-7 w-7 animate-spin text-teal-700" />}
    </main>
  );

  const { proposal, finding } = context;
  return (
    <main className="min-w-0 flex-1 overflow-y-auto bg-[#f4f6f3] text-slate-900">
      <div className="mx-auto max-w-[1460px] px-5 py-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b border-slate-200 pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <Link to="/knowledge-ops" className="mb-3 inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-950"><ArrowLeft className="h-4 w-4" /> Control room</Link>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold capitalize text-amber-700">{proposal.status}</span>
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{proposal.content_type.replace('sh_', '').replace(/_/g, ' ')}</span>
            </div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{proposal.title}</h1>
            <p className="mt-2 text-sm text-slate-600">Review the current Storyblok draft against evidence and the last published truth.</p>
          </div>
          {context.editor_url && <a href={context.editor_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-400">Open visual editor <ExternalLink className="h-4 w-4" /></a>}
        </header>

        {error && <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

        <section className="mt-5 grid gap-5 xl:grid-cols-[1fr_350px]">
          <div className="space-y-5">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between"><div className="flex items-center gap-2"><FileDiff className="h-5 w-5 text-teal-700" /><h2 className="font-semibold">Published vs. live draft</h2></div><span className="text-xs font-semibold text-slate-500">{changedFields.length} changed fields</span></div>
              <div className="mt-4 flex flex-wrap gap-2">{changedFields.map(field => <span key={field} className="rounded-md bg-teal-50 px-2 py-1 text-xs font-medium text-teal-700">{field}</span>)}</div>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <JsonPanel title="Currently published (CDA)" data={context.published_entry} />
                <JsonPanel title="Live Storyblok draft (MAPI)" data={context.live_draft} />
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2"><Quote className="h-5 w-5 text-teal-700" /><h2 className="font-semibold">Conversation evidence</h2></div>
              <p className="mt-1 text-sm text-slate-500">PII-redacted excerpts are encrypted at rest and automatically purged after 30 days.</p>
              <div className="mt-4 space-y-3">
                {context.evidence.map((evidence, index) => (
                  <blockquote key={String(evidence.id || index)} className="rounded-xl border-l-4 border-teal-600 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
                    “{String(evidence.excerpt || '[Evidence purged]')}”
                    <footer className="mt-2 text-xs text-slate-500">Evidence {index + 1} · {String(evidence.content_hash || '').slice(0, 12)}</footer>
                  </blockquote>
                ))}
              </div>
            </div>

            <details className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <summary className="cursor-pointer font-semibold text-slate-900">Typed agent outputs and prompt evidence</summary>
              <pre className="mt-4 max-h-[520px] overflow-auto rounded-xl bg-slate-950 p-4 text-xs leading-5 text-slate-200">{JSON.stringify(context.agent_outputs, null, 2)}</pre>
            </details>
          </div>

          <aside className="space-y-5">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-teal-700" /><h2 className="font-semibold">Approval gates</h2></div>
              <div className="mt-4 space-y-3">
                <Score label="Evidence" value={proposal.evidence_score} />
                <Score label="Quality" value={proposal.quality_score} suffix="%" />
                <Score label="Localization" value={proposal.localization_score} />
              </div>
              <div className="mt-4 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">Approval re-fetches this draft and reruns evidence verification and QC. The displayed score cannot authorize stale content.</div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-teal-700" /><h2 className="font-semibold">Finding</h2></div>
              <p className="mt-3 font-medium text-slate-900">{finding?.title}</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">{finding?.summary}</p>
              <p className="mt-3 text-xs text-slate-500">{finding ? Math.round(finding.confidence * 100) : 0}% confidence · {finding?.occurrence_count || 0} occurrences</p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <label className="text-sm font-semibold text-slate-900" htmlFor="decision-reason">Reviewer note</label>
              <p className="mt-1 text-xs leading-5 text-slate-500">Required for rejection and permanently retained in the audit timeline.</p>
              <textarea id="decision-reason" value={reason} onChange={event => setReason(event.target.value)} rows={5} className="mt-3 w-full resize-none rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100" placeholder="Explain the decision or required correction…" />
              <div className="mt-3 grid gap-2">
                <button disabled={action !== null || proposal.status !== 'reviewing'} onClick={() => void decide('approve')} className="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50">
                  {action === 'approve' ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />} Approve and publish
                </button>
                <button disabled={action !== null || proposal.status !== 'reviewing'} onClick={() => void decide('reject')} className="inline-flex items-center justify-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2.5 text-sm font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-50">
                  {action === 'reject' ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />} Reject draft
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-[#eff8f5] p-5">
              <div className="flex items-center gap-2 text-sm font-semibold text-teal-800"><Languages className="h-4 w-4" /> English + Spanish</div>
              <p className="mt-2 text-xs leading-5 text-teal-900/70">Localized fields use Storyblok’s field-level <code>__i18n__</code> representation and publish as one canonical entry.</p>
              {context.editor_url && <a href={context.editor_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-teal-800">Inspect translations <ArrowUpRight className="h-3.5 w-3.5" /></a>}
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}
