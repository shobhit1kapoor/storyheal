import { FormEvent, useEffect, useState } from 'react';
import { Check, CircleDot, Cloud, KeyRound, LoaderCircle, RefreshCw, Webhook } from 'lucide-react';
import { knowledgeOpsApi, type StoryblokConnection } from '@/services/knowledgeOpsApi';

const initialForm = {
  region: 'eu', space_id: '', draft_token: '', publisher_token: '', delivery_token: '',
  webhook_secret: '', folder_slug: 'knowledge', rag_collection_id: '', locales: 'en,es',
  public_webhook_url: '',
};

export default function StoryblokSettings() {
  const [form, setForm] = useState(initialForm);
  const [connection, setConnection] = useState<StoryblokConnection | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    knowledgeOpsApi.getConnection().then(value => {
      setConnection(value);
      setForm(current => ({ ...current, region: value.region, space_id: value.space_id, folder_slug: value.folder_slug, rag_collection_id: value.rag_collection_id, locales: value.locales.join(','), public_webhook_url: value.public_webhook_url }));
    }).catch(() => undefined);
  }, []);

  const field = (name: keyof typeof form) => ({
    value: form[name], onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [name]: event.target.value }),
  });

  const run = async (name: string, task: () => Promise<unknown>, success: string) => {
    setBusy(name); setError(''); setMessage('');
    try { await task(); setMessage(success); setConnection(await knowledgeOpsApi.getConnection()); }
    catch (err) { setError(err instanceof Error ? err.message : 'Operation failed'); }
    finally { setBusy(null); }
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    await run('save', () => knowledgeOpsApi.saveConnection({ ...form, locales: form.locales.split(',').map(value => value.trim()).filter(Boolean) }), 'Credentials encrypted and connection saved.');
  };

  const configured = Boolean(connection);
  const tested = Boolean(connection?.last_tested_at);
  const provisioned = Boolean(connection?.folder_id && Object.keys(connection.component_ids).length);

  return (
    <main className="min-h-full bg-[#f4f6f3] px-5 py-6 text-slate-900 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <header className="border-b border-slate-200 pb-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-teal-700"><Cloud className="h-4 w-4" /> Canonical content infrastructure</div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Connect Storyblok</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Use separate drafting and publishing credentials. Secrets are encrypted server-side and are never returned to this browser.</p>
        </header>

        <div className="mt-5 grid gap-3 sm:grid-cols-4">
          {[
            ['1', 'Credentials', configured], ['2', 'Verify access', tested],
            ['3', 'Provision space', provisioned], ['4', 'Sync content', Boolean(connection?.last_synced_at)],
          ].map(([number, label, done]) => (
            <div key={String(label)} className={`rounded-xl border p-3 ${done ? 'border-teal-200 bg-teal-50' : 'border-slate-200 bg-white'}`}>
              <div className="flex items-center gap-2">{done ? <Check className="h-4 w-4 text-teal-700" /> : <span className="flex h-5 w-5 items-center justify-center rounded-full border border-slate-300 text-[11px] font-semibold text-slate-500">{number}</span>}<span className="text-sm font-semibold text-slate-800">{label}</span></div>
            </div>
          ))}
        </div>

        {message && <div className="mt-5 rounded-xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800">{message}</div>}
        {error && <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

        <form onSubmit={save} className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm lg:p-6">
          <div className="flex items-center gap-2"><KeyRound className="h-5 w-5 text-teal-700" /><h2 className="font-semibold">Space and credentials</h2></div>
          {connection && <p className="mt-2 text-xs text-slate-500">Draft, publisher, Delivery, and webhook credentials are stored. No credential fragments are returned to this browser.</p>}
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <label className="text-sm font-medium text-slate-700">Region<select {...field('region')} className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 outline-none focus:border-teal-600"><option value="eu">Europe</option><option value="us">United States</option><option value="ca">Canada</option><option value="ap">Australia / Asia Pacific</option><option value="cn">China</option></select></label>
            <label className="text-sm font-medium text-slate-700">Space ID<input required {...field('space_id')} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-600" placeholder="123456" /></label>
            <label className="text-sm font-medium text-slate-700">Draft-author Management token<input required type="password" {...field('draft_token')} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-600" autoComplete="new-password" /></label>
            <label className="text-sm font-medium text-slate-700">Publisher Management token<input required type="password" {...field('publisher_token')} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-600" autoComplete="new-password" /></label>
            <label className="text-sm font-medium text-slate-700">Public Delivery token<input required type="password" {...field('delivery_token')} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-600" autoComplete="new-password" /></label>
            <label className="text-sm font-medium text-slate-700">Webhook secret<input required minLength={16} type="password" {...field('webhook_secret')} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-600" autoComplete="new-password" /></label>
            <label className="text-sm font-medium text-slate-700">Knowledge folder slug<input required {...field('folder_slug')} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-600" /></label>
            <label className="text-sm font-medium text-slate-700">RAG collection ID<input required {...field('rag_collection_id')} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-600" /></label>
            <label className="text-sm font-medium text-slate-700">Locales<input required {...field('locales')} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-600" placeholder="en,es" /><span className="mt-1 block text-xs font-normal text-slate-500">Comma separated; English and Spanish are recommended.</span></label>
            <label className="text-sm font-medium text-slate-700">Public HTTPS webhook URL<input required type="url" {...field('public_webhook_url')} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-600" placeholder="https://support.example.com/api/v1/webhooks/storyblok" /></label>
          </div>
          <div className="mt-5 flex justify-end"><button disabled={busy !== null} className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50">{busy === 'save' && <LoaderCircle className="h-4 w-4 animate-spin" />} Save encrypted connection</button></div>
        </form>

        <section className="mt-5 grid gap-4 lg:grid-cols-3">
          <button disabled={!configured || busy !== null} onClick={() => void run('test', knowledgeOpsApi.testConnection, 'Draft, publisher, and Delivery access verified.')} className="rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm hover:border-teal-300 disabled:opacity-50">
            <CircleDot className="h-5 w-5 text-teal-700" /><strong className="mt-3 block">Test all credentials</strong><span className="mt-1 block text-sm leading-5 text-slate-500">Confirms separated author and publisher access plus public CDA reads.</span>{busy === 'test' && <LoaderCircle className="mt-3 h-4 w-4 animate-spin" />}
          </button>
          <button disabled={!tested || busy !== null} onClick={() => void run('provision', knowledgeOpsApi.provision, 'Components, folder, workflow, and signed webhook provisioned idempotently.')} className="rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm hover:border-teal-300 disabled:opacity-50">
            <Webhook className="h-5 w-5 text-teal-700" /><strong className="mt-3 block">Provision StoryHeal schema</strong><span className="mt-1 block text-sm leading-5 text-slate-500">Creates or updates components without duplicating existing resources.</span>{busy === 'provision' && <LoaderCircle className="mt-3 h-4 w-4 animate-spin" />}
          </button>
          <button disabled={!provisioned || busy !== null} onClick={() => void run('sync', knowledgeOpsApi.sync, 'Published Storyblok entries queued for canonical re-indexing.')} className="rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm hover:border-teal-300 disabled:opacity-50">
            <RefreshCw className="h-5 w-5 text-teal-700" /><strong className="mt-3 block">Sync published content</strong><span className="mt-1 block text-sm leading-5 text-slate-500">Uses the Delivery API and the same webhook-driven indexing path.</span>{busy === 'sync' && <LoaderCircle className="mt-3 h-4 w-4 animate-spin" />}
          </button>
        </section>
      </div>
    </main>
  );
}
