import { useEffect, useRef, useState } from 'preact/hooks';
import { api, type SiteContent, type SitePerson } from '../../api';
import { DEFAULT_SITE, ProtectedImage, refreshSiteContent } from '../../photos';
import { Field, inputValue, Notice, PageHead } from '../../ui';

const LIMITS = { team: 8, guides: 4 };
type Group = 'team' | 'guides';

function PersonEditor({ person, onChange, onRemove, label }: {
  person: SitePerson; onChange: (patch: Partial<SitePerson>) => void; onRemove: () => void; label: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);

  async function upload(file: File) {
    setBusy(true);
    setError('');
    try {
      const out = await api.uploadSitePhoto(file);
      onChange({ photo_id: out.id, photo_url: out.url });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  }

  return (
    <article class="person-editor">
      <div class="person-photo">
        {person.photo_url ? <ProtectedImage class="photo-frame has-photo" src={person.photo_url} alt={`Photo of ${person.name}`} />
          : <div class="photo-frame" aria-hidden="true" />}
        <input ref={input} type="file" class="sr-only" id={`file-${label}`} accept="image/jpeg,image/png,image/webp"
          onChange={(event) => { const file = (event.currentTarget as HTMLInputElement).files?.[0]; if (file) void upload(file); }} />
        <label class="btn btn-small" for={`file-${label}`}>{busy ? 'Uploading…' : person.photo_id ? 'Change' : 'Add photo'}</label>
        {person.photo_id && <button class="btn btn-small btn-ghost" type="button" onClick={() => onChange({ photo_id: null, photo_url: null })}>Clear</button>}
      </div>
      <div class="person-fields">
        <Notice>{error}</Notice>
        <Field label="Name"><input required maxLength={80} value={person.name} onInput={(e) => onChange({ name: inputValue(e) })} /></Field>
        <Field label="Role"><input maxLength={120} value={person.role} onInput={(e) => onChange({ role: inputValue(e) })} /></Field>
        <button class="btn btn-small btn-ghost" type="button" onClick={onRemove}>Remove {label}</button>
      </div>
    </article>
  );
}

export function SiteEditor() {
  const [content, setContentState] = useState<SiteContent | null>(null);
  const latest = useRef<SiteContent | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  // Every edit merges into the newest state, and saving reads that state, so quick edits,
  // autofill and slow photo uploads can never overwrite each other.
  const setContent = (update: (prev: SiteContent | null) => SiteContent | null) =>
    setContentState((prev) => { const next = update(prev); latest.current = next; return next; });

  useEffect(() => {
    api.siteContent().then((value) => setContent(() => value))
      .catch((err) => { setError((err as Error).message); setContent(() => DEFAULT_SITE); });
  }, []);
  if (!content) return <p class="muted">Loading…</p>;

  const setPerson = (group: Group, index: number, patch: Partial<SitePerson>) =>
    setContent((prev) => prev && { ...prev, [group]: prev[group].map((item, i) => (i === index ? { ...item, ...patch } : item)) });
  const remove = (group: Group, index: number) =>
    setContent((prev) => prev && { ...prev, [group]: prev[group].filter((_, i) => i !== index) });
  const add = (group: Group) =>
    setContent((prev) => prev && { ...prev, [group]: [...prev[group], { name: group === 'team' ? 'New member' : 'New guide', role: '', photo_id: null, photo_url: null }] });
  const setBusiness = (key: keyof SiteContent['business']) => (event: Event) => {
    const value = inputValue(event);
    setContent((prev) => prev && { ...prev, business: { ...prev.business, [key]: value } });
  };

  async function save(event: Event) {
    event.preventDefault();
    const current = latest.current;
    if (!current) return;
    setBusy(true);
    setError('');
    setMessage('');
    const strip = (people: SitePerson[]) => people.map(({ name, role, photo_id }) => ({ name, role, photo_id }));
    try {
      const saved = await api.saveSiteContent({ ...current, team: strip(current.team), guides: strip(current.guides) });
      setContent(() => saved);
      refreshSiteContent();
      setMessage('Saved. The public website now shows these details.');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const group = (key: Group, title: string, label: string) => (
    <section class="card">
      <div class="card-head"><h2>{title}</h2><span class="muted small">{content[key].length} of {LIMITS[key]}</span></div>
      <div class="person-list">
        {content[key].map((person, index) => (
          <PersonEditor key={`${key}-${index}`} label={`${label} ${index + 1}`} person={person}
            onChange={(next) => setPerson(key, index, next)} onRemove={() => remove(key, index)} />
        ))}
      </div>
      {content[key].length < LIMITS[key] && <button class="btn btn-ghost" type="button" onClick={() => add(key)}>Add {label}</button>}
    </section>
  );

  return (
    <form onSubmit={save} class="site-editor">
      <PageHead title="Site content" subtitle="Team, project guides and business details shown on the public website. Superadmins only.">
        <button class="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button>
      </PageHead>
      <Notice>{error}</Notice>
      <Notice kind="success">{message}</Notice>
      <Notice kind="info">Team photos are public on the website. They are re-encoded, cropped square and stripped of location and camera data, and other websites cannot embed them. Visitors can still take screenshots, as on any website.</Notice>
      {group('team', 'Team members', 'member')}
      {group('guides', 'Project guides', 'guide')}
      <section class="card">
        <h2>Business details (legal and contact pages)</h2>
        <div class="form-grid">
          <Field label="Business or owner name"><input maxLength={120} value={content.business.name} onInput={setBusiness('name')} /></Field>
          <Field label="Support email"><input maxLength={254} value={content.business.email} onInput={setBusiness('email')} /></Field>
          <Field label="Support phone"><input maxLength={40} value={content.business.phone} onInput={setBusiness('phone')} /></Field>
          <Field label="Policies last updated"><input maxLength={40} value={content.business.last_updated} onInput={setBusiness('last_updated')} /></Field>
        </div>
        <Field label="Registered address"><textarea rows={2} maxLength={300} value={content.business.address} onInput={setBusiness('address')} /></Field>
      </section>
    </form>
  );
}
