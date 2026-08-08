import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity, ArrowUpRight, BookOpenCheck, CheckCircle2, Clock3, FileEdit,
  RefreshCw, ShieldCheck, Sparkles, TriangleAlert,
} from 'lucide-react';
import {
  knowledgeOpsApi, type AnalyticsSummary, type AuditEvent, type Finding, type Proposal,
  type StoryblokOperation,
} from '@/services/knowledgeOpsApi';

const EMPTY: AnalyticsSummary = {
  questions_processed: 0, gaps_detected: 0, contradictions_detected: 0,
  stale_content_detected: 0, drafts_generated: 0, drafts_approved: 0,
  drafts_rejected: 0, stories_published: 0, stories_indexed: 0,
  storyblok_api_operations: 0, storyblok_api_failures: 0, response_accuracy: 0,
  resolution_rate: 0, helpful_rate: 0, average_response_time_ms: null,
  average_indexing_time_ms: null, improvement_percentage_points: 0,
  findings_by_type: {}, proposals_by_status: {}, content_types: {}, locales_indexed: {},
  channels_published: {}, daily_activity: [], paired_evaluations: [],
};

const statusStyle: Record<string, string> = {
  reviewing: 'bg-amber-50 text-amber-700 border-amber-200',
  indexed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  publishing: 'bg-blue-50 text-blue-700 border-blue-200',
  indexing: 'bg-sky-50 text-sky-700 border-sky-200',
  rejected: 'bg-rose-50 text-rose-700 border-rose-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
};

function MetricCard({ label, value, note, icon: Icon }: {
  label: string; value: string; note: string; icon: typeof Activity;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{value}</p>
        </div>
        <span className="rounded-xl bg-teal-50 p-2.5 text-teal-700"><Icon className="h-5 w-5" /></span>
      </div>
      <p className="mt-3 text-sm text-slate-500">{note}</p>
    </div>
  );
}

export default function KnowledgeOpsDashboard() {
  const [analytics, setAnalytics] = useState(EMPTY);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [operations, setOperations] = useState<StoryblokOperation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [nextAnalytics, nextFindings, nextProposals, nextEvents, nextOperations] = await Promise.all([
        knowledgeOpsApi.analytics(), knowledgeOpsApi.findings(),
        knowledgeOpsApi.proposals(), knowledgeOpsApi.audit(), knowledgeOpsApi.operations(),
      ]);
      setAnalytics(nextAnalytics);
      setFindings(nextFindings);
      setProposals(nextProposals);
      setEvents(nextEvents);
      setOperations(nextOperations);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load knowledge operations');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const funnel = useMemo(() => [
    ['Questions', analytics.questions_processed],
    ['Failures detected', analytics.gaps_detected + analytics.contradictions_detected + analytics.stale_content_detected],
    ['Drafts', analytics.drafts_generated],
    ['Approved', analytics.drafts_approved],
    ['Indexed', analytics.stories_indexed],
  ] as const, [analytics]);
  const maxFunnel = Math.max(...funnel.map(([, value]) => value), 1);

  return (
    <main className="min-w-0 flex-1 overflow-y-auto bg-[#f4f6f3] text-slate-900">
      <div className="mx-auto max-w-[1500px] px-5 py-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b border-slate-200 pb-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-teal-700">
              <Sparkles className="h-4 w-4" /> Closed-loop knowledge operations
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Usefulness control room</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
              Every number follows the same evidence chain: conversation, finding, Storyblok review, publication, and indexed improvement.
            </p>
          </div>
          <div className="flex gap-2">
            <Link to="/settings/storyblok" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-400">
              Storyblok setup
            </Link>
            <button onClick={() => void load()} disabled={loading} className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </button>
          </div>
        </header>

        {error && <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

        <section className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Response accuracy" value={`${analytics.response_accuracy.toFixed(1)}%`} note={`${analytics.improvement_percentage_points >= 0 ? '+' : ''}${analytics.improvement_percentage_points.toFixed(1)} points after publication`} icon={ShieldCheck} />
          <MetricCard label="Resolution rate" value={`${analytics.resolution_rate.toFixed(1)}%`} note="Resolved without handoff or 24h reopen" icon={CheckCircle2} />
          <MetricCard label="Helpful responses" value={`${analytics.helpful_rate.toFixed(1)}%`} note="Direct visitor feedback, not inferred sentiment" icon={BookOpenCheck} />
          <MetricCard label="First response" value={analytics.average_response_time_ms == null ? '—' : `${Math.round(analytics.average_response_time_ms)} ms`} note="Visitor receipt to first AI token" icon={Clock3} />
        </section>

        <section className="mt-5 grid gap-5 xl:grid-cols-[1.05fr_1.45fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-semibold text-slate-950">Healing funnel</h2>
                <p className="mt-1 text-sm text-slate-500">No draft is counted before it exists in Storyblok.</p>
              </div>
              <Activity className="h-5 w-5 text-teal-700" />
            </div>
            <div className="mt-6 space-y-4">
              {funnel.map(([label, value], index) => (
                <div key={label}>
                  <div className="mb-1.5 flex items-center justify-between text-sm">
                    <span className="font-medium text-slate-700">{index + 1}. {label}</span>
                    <span className="font-semibold tabular-nums text-slate-950">{value}</span>
                  </div>
                  <div className="h-2.5 rounded-full bg-slate-100">
                    <div className="h-2.5 rounded-full bg-teal-600 transition-all" style={{ width: `${Math.max(value / maxFunnel * 100, value ? 4 : 0)}%` }} />
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-6 grid grid-cols-2 gap-3 border-t border-slate-100 pt-5 text-sm">
              <div className="rounded-xl bg-slate-50 p-3"><span className="block text-slate-500">Storyblok calls</span><strong className="mt-1 block text-lg">{analytics.storyblok_api_operations}</strong></div>
              <div className="rounded-xl bg-slate-50 p-3"><span className="block text-slate-500">API failures</span><strong className="mt-1 block text-lg">{analytics.storyblok_api_failures}</strong></div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
              <div><h2 className="font-semibold text-slate-950">Review queue</h2><p className="mt-1 text-sm text-slate-500">AI drafts waiting for an accountable human decision.</p></div>
              <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">{proposals.filter(p => p.status === 'reviewing').length} waiting</span>
            </div>
            <div className="divide-y divide-slate-100">
              {proposals.slice(0, 6).map((proposal) => (
                <Link key={proposal.id} to={`/knowledge-ops/proposals/${proposal.id}`} className="group flex items-center gap-4 px-5 py-4 hover:bg-slate-50">
                  <span className="rounded-xl bg-slate-100 p-2.5 text-slate-600"><FileEdit className="h-5 w-5" /></span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-slate-950">{proposal.title}</p>
                    <p className="mt-1 text-xs text-slate-500">{proposal.content_type.replace('sh_', '').replace(/_/g, ' ')} · evidence {(proposal.evidence_score * 100).toFixed(0)} · quality {proposal.quality_score.toFixed(0)}</p>
                  </div>
                  <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${statusStyle[proposal.status] || 'border-slate-200 bg-slate-50 text-slate-600'}`}>{proposal.status}</span>
                  <ArrowUpRight className="h-4 w-4 text-slate-400 group-hover:text-slate-700" />
                </Link>
              ))}
              {!proposals.length && <div className="px-5 py-12 text-center text-sm text-slate-500">No proposals yet. Close a real support session to start the loop.</div>}
            </div>
          </div>
        </section>

        <section className="mt-5 grid gap-5 xl:grid-cols-[1.4fr_1fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between"><div><h2 className="font-semibold">30-day loop activity</h2><p className="mt-1 text-sm text-slate-500">Questions, findings, drafts, and publications from durable domain records.</p></div><Activity className="h-5 w-5 text-teal-700" /></div>
            <div className="mt-6 flex h-44 items-end gap-2 overflow-x-auto border-b border-slate-200 pb-1">
              {analytics.daily_activity.map(day => {
                const peak = Math.max(...analytics.daily_activity.flatMap(item => [item.questions, item.findings, item.drafts, item.published]), 1);
                return <div key={day.date} className="group flex min-w-8 flex-1 items-end justify-center gap-0.5" title={`${day.date}: ${day.questions} questions, ${day.findings} findings, ${day.drafts} drafts, ${day.published} published`}>
                  <span className="w-1.5 rounded-t bg-slate-300" style={{height: `${Math.max(day.questions / peak * 100, day.questions ? 4 : 0)}%`}} />
                  <span className="w-1.5 rounded-t bg-amber-400" style={{height: `${Math.max(day.findings / peak * 100, day.findings ? 4 : 0)}%`}} />
                  <span className="w-1.5 rounded-t bg-teal-500" style={{height: `${Math.max(day.published / peak * 100, day.published ? 4 : 0)}%`}} />
                </div>;
              })}
              {!analytics.daily_activity.length && <div className="m-auto text-sm text-slate-500">Activity appears after real conversations are processed.</div>}
            </div>
            <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500"><span>● Questions</span><span className="text-amber-600">● Findings</span><span className="text-teal-700">● Published</span></div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="font-semibold">Canonical coverage</h2>
            <div className="mt-4 space-y-4 text-sm">
              {[['Content types', analytics.content_types], ['Locales indexed', analytics.locales_indexed], ['Published channels', analytics.channels_published]].map(([label, values]) => <div key={label as string}><p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{label as string}</p><div className="flex flex-wrap gap-2">{Object.entries(values as Record<string, number>).map(([key, value]) => <span key={key} className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1"><strong>{value}</strong> {key.replace('sh_', '').replace(/_/g, ' ')}</span>)}{!Object.keys(values as object).length && <span className="text-slate-400">No indexed content yet</span>}</div></div>)}
            </div>
          </div>
        </section>

        <section className="mt-5 rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><div><h2 className="font-semibold">Storyblok operation log</h2><p className="mt-1 text-sm text-slate-500">Authenticated Management and Delivery API attempts, including retries and failures.</p></div><span className="text-xs font-semibold text-slate-500">{operations.length} recent</span></div>
          <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3">Operation</th><th>Result</th><th>Status</th><th>Latency</th><th>Attempt</th><th>Time</th></tr></thead><tbody className="divide-y divide-slate-100">{operations.slice(0, 10).map(operation => <tr key={operation.id}><td className="px-5 py-3 font-medium text-slate-800">{operation.operation}</td><td><span className={operation.success ? 'text-emerald-700' : 'text-rose-700'}>{operation.success ? 'Success' : 'Failed'}</span></td><td>{operation.status_code || 'network'}</td><td>{operation.duration_ms == null ? '—' : `${operation.duration_ms} ms`}</td><td>{operation.attempt}</td><td className="pr-5 text-slate-500">{new Date(operation.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>
        </section>

        <section className="mt-5 grid gap-5 lg:grid-cols-2">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2"><TriangleAlert className="h-5 w-5 text-amber-600" /><h2 className="font-semibold">Recent knowledge failures</h2></div>
            <div className="mt-4 space-y-3">
              {findings.slice(0, 5).map(finding => (
                <div key={finding.id} className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-3"><p className="font-medium text-slate-900">{finding.title}</p><span className="text-xs font-semibold uppercase text-slate-500">{finding.kind}</span></div>
                  <p className="mt-2 line-clamp-2 text-sm leading-5 text-slate-600">{finding.summary}</p>
                  <p className="mt-2 text-xs text-slate-500">{Math.round(finding.confidence * 100)}% confidence · {finding.occurrence_count} occurrence{finding.occurrence_count === 1 ? '' : 's'}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="font-semibold">Append-only activity</h2>
            <div className="mt-4 space-y-4">
              {events.slice(0, 7).map(event => (
                <div key={event.id} className="flex gap-3">
                  <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-teal-600" />
                  <div className="min-w-0"><p className="text-sm font-medium text-slate-800">{event.action.replace(/\./g, ' ')}</p><p className="mt-0.5 text-xs text-slate-500">{event.actor_type} · {new Date(event.created_at).toLocaleString()}</p></div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
