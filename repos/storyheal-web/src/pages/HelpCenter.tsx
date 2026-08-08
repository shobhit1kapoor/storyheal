import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, BookOpen, ExternalLink, LoaderCircle, Search, Sparkles } from 'lucide-react';
import { knowledgeOpsApi, type PublicStory } from '@/services/knowledgeOpsApi';

export default function HelpCenter() {
  const { '*': slug } = useParams();
  const [locale, setLocale] = useState<'en' | 'es'>('en');
  const [stories, setStories] = useState<PublicStory[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    knowledgeOpsApi.publicContent(locale).then(result => setStories(result.stories)).catch(err => setError(err instanceof Error ? err.message : 'Help center unavailable')).finally(() => setLoading(false));
  }, [locale]);

  const selected = slug ? stories.find(story => story.full_slug === slug || story.full_slug.replace(/^knowledge\//, '') === slug) : undefined;
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return stories;
    return stories.filter(story => `${story.title} ${story.text}`.toLowerCase().includes(needle));
  }, [query, stories]);

  if (selected) return (
    <main className="min-h-screen bg-[#f7f8f5] text-slate-900">
      <nav className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4"><Link to="/help" className="flex items-center gap-2 font-semibold"><span className="flex h-8 w-8 items-center justify-center rounded-xl bg-teal-700 text-white"><Sparkles className="h-4 w-4" /></span> StoryHeal Help</Link><span className="rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-700">Live from Storyblok</span></div></nav>
      <article className="mx-auto max-w-3xl px-5 py-10">
        <Link to="/help" className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-950"><ArrowLeft className="h-4 w-4" /> All articles</Link>
        <div className="mt-8 text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">{selected.content_type.replace('sh_', '').replace(/_/g, ' ')}</div>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-950">{selected.title}</h1>
        <p className="mt-3 text-sm text-slate-500">Published {selected.published_at ? new Date(selected.published_at).toLocaleDateString() : 'in Storyblok'} · {selected.locale.toUpperCase()}</p>
        <div className="mt-8 whitespace-pre-wrap text-[17px] leading-8 text-slate-700">{selected.text}</div>
        {selected.citations.length > 0 && <section className="mt-10 border-t border-slate-200 pt-6"><h2 className="font-semibold">Sources</h2><div className="mt-3 space-y-2">{selected.citations.map((citation, index) => <a key={index} href={String(citation.uri || citation.url || citation.source_url || '#')} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 hover:border-teal-300"><span>{String(citation.title || citation.label || `Source ${index + 1}`)}</span><ExternalLink className="h-4 w-4" /></a>)}</div></section>}
      </article>
    </main>
  );

  return (
    <main className="min-h-screen bg-[#f7f8f5] text-slate-900">
      <nav className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4"><Link to="/help" className="flex items-center gap-2 font-semibold"><span className="flex h-8 w-8 items-center justify-center rounded-xl bg-teal-700 text-white"><Sparkles className="h-4 w-4" /></span> StoryHeal Help</Link><div className="flex rounded-lg border border-slate-200 bg-slate-50 p-1"><button onClick={() => setLocale('en')} className={`rounded-md px-3 py-1.5 text-xs font-semibold ${locale === 'en' ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500'}`}>English</button><button onClick={() => setLocale('es')} className={`rounded-md px-3 py-1.5 text-xs font-semibold ${locale === 'es' ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500'}`}>Español</button></div></div></nav>
      <section className="border-b border-slate-200 bg-[#eaf5f1]"><div className="mx-auto max-w-4xl px-5 py-12 text-center"><div className="mx-auto flex w-fit items-center gap-2 rounded-full border border-teal-200 bg-white px-3 py-1 text-xs font-semibold text-teal-700"><BookOpen className="h-3.5 w-3.5" /> Canonical support knowledge</div><h1 className="mt-5 text-4xl font-semibold tracking-tight text-slate-950">How can we help?</h1><p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-600">The same published Storyblok content powers this help center, the AI assistant, support workspace, and widget.</p><label className="mx-auto mt-7 flex max-w-2xl items-center gap-3 rounded-xl border border-slate-300 bg-white px-4 py-3 shadow-sm focus-within:border-teal-600"><Search className="h-5 w-5 text-slate-400" /><input value={query} onChange={event => setQuery(event.target.value)} className="min-w-0 flex-1 bg-transparent text-sm outline-none" placeholder={locale === 'es' ? 'Buscar ayuda…' : 'Search for answers…'} /></label></div></section>
      <section className="mx-auto max-w-6xl px-5 py-10">
        <div className="mb-5 flex items-end justify-between"><div><h2 className="text-xl font-semibold">{query ? 'Search results' : 'Knowledge library'}</h2><p className="mt-1 text-sm text-slate-500">{filtered.length} published entries · Content Delivery API</p></div><span className="hidden rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-700 sm:block">Live from Storyblok</span></div>
        {loading && <div className="flex justify-center py-16"><LoaderCircle className="h-7 w-7 animate-spin text-teal-700" /></div>}
        {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>}
        {!loading && <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">{filtered.map(story => (
          <Link key={`${story.story_uuid}:${story.locale}`} to={`/help/${story.full_slug.replace(/^knowledge\//, '')}`} className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm hover:border-teal-300">
            <span className="text-xs font-semibold uppercase tracking-wide text-teal-700">{story.content_type.replace('sh_', '').replace(/_/g, ' ')}</span><h3 className="mt-3 font-semibold text-slate-950">{story.title}</h3><p className="mt-2 line-clamp-3 text-sm leading-6 text-slate-600">{story.text}</p><span className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-slate-800">Read article <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></span>
          </Link>
        ))}</div>}
      </section>
    </main>
  );
}
