import type { ComponentChildren } from 'preact';
import { createContext } from 'preact';
import { useCallback, useContext, useEffect, useRef, useState } from 'preact/hooks';
import type { ClassifyResult, EnginePath, Session, User } from './api';

export interface Auth {
  user: User;
  session: Session;
  updateSession: (session: Session) => void;
  signOut: () => void;
}
export const AuthContext = createContext<Auth | null>(null);
export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error('Auth context missing');
  return auth;
}

export const inputValue = (event: Event) => (event.currentTarget as HTMLInputElement).value;

export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const latest = useRef(0);

  const reload = useCallback(async () => {
    const id = ++latest.current;
    setLoading(true);
    try {
      const value = await load();
      if (id === latest.current) { setData(value); setError(''); }
    } catch (err) {
      if (id === latest.current) setError((err as Error).message);
    } finally {
      if (id === latest.current) setLoading(false);
    }
  }, deps);

  useEffect(() => { void reload(); }, [reload]);
  return { data, error, loading, reload };
}

const dateFormat = new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
export const formatDate = (iso: string | null | undefined) => (iso ? dateFormat.format(new Date(iso)) : '—');
export const formatNumber = (value: number | null | undefined, digits = 2) =>
  value === null || value === undefined ? '—' : value.toFixed(digits);
export const percent = (value: number | null | undefined, digits = 1) =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`;

const ICONS: Record<string, string> = {
  home: 'M3 11l9-8 9 8M5 9.5V21h5v-6h4v6h5V9.5',
  book: 'M4 19.5A2.500 2.500 0 016.500 17H20V3H6.500A2.500 2.500 0 004 5.500zM4 19.500A2.500 2.500 0 006.500 22H20v-5',
  flask: 'M9 3h6M10 3v6l-5.5 9.5A1.7 1.7 0 006 21h12a1.7 1.7 0 001.5-2.5L14 9V3M7.5 15h9',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  clock: 'M12 7v5l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  chart: 'M4 20V4M4 20h16M8 16v-5M13 16V7M18 16v-8',
  users: 'M16 20v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 10a4 4 0 100-8 4 4 0 000 8M22 20v-2a4 4 0 00-3-3.9M16 2.1a4 4 0 010 7.8',
  shield: 'M12 3l8 3v6c0 5-3.4 8-8 9-4.6-1-8-4-8-9V6z M9 12l2 2 4-4',
  key: 'M15 7a4 4 0 11-3.4 6.1L4 21H2v-3l7.9-7.6A4 4 0 0115 7z',
  menu: 'M3 6h18M3 12h18M3 18h18',
  help: 'M12 21a9 9 0 100-18 9 9 0 000 18zM9.1 9a3 3 0 015.800 1c0 2-3 2.500-3 4.500M12 17.500h.01',
  card: 'M2 7h20M2 5h20v14H2zM6 15h4',
  external: 'M14 4h6v6M20 4l-9 9M18 14v5H5V6h5',
  coins: 'M12 2v20M17 6H9.5a3.500 3.500 0 000 7h5a3.500 3.500 0 010 7H6',
  user: 'M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8',
  close: 'M6 6l12 12M18 6L6 18',
  moon: 'M21 13A9 9 0 1111 3a7 7 0 0010 10z',
  sun: 'M12 4V2M12 22v-2M4 12H2M22 12h-2M6 6L4.5 4.5M19.5 19.5L18 18M18 6l1.5-1.5M4.5 19.5L6 18M16 12a4 4 0 11-8 0 4 4 0 018 0z',
};

export function Icon({ name }: { name: keyof typeof ICONS | string }) {
  return (
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  );
}

export function Notice({ kind = 'error', children }: { kind?: 'error' | 'success' | 'info' | 'warn'; children: ComponentChildren }) {
  if (!children) return null;
  return <div class={`notice notice-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div>;
}

export function Field({ label, hint, unit, children }: {
  label: string; hint?: string; unit?: string; children: ComponentChildren;
}) {
  return (
    <label class="field">
      <span class="field-label">{label}</span>
      <span class={unit ? 'input-wrap has-unit' : 'input-wrap'}>
        {children}
        {unit && <span class="unit">{unit}</span>}
      </span>
      {hint && <span class="hint">{hint}</span>}
    </label>
  );
}

export function PathBadge({ path }: { path: EnginePath }) {
  return path === 'rule'
    ? <span class="badge badge-exact">Exact · USP</span>
    : <span class="badge badge-ml">ML estimate</span>;
}

export function flowTone(poor: boolean | null, acceptable: boolean | null) {
  if (poor) return 'poor';
  if (acceptable) return 'good';
  return poor === false && acceptable === null ? 'good' : 'mid';
}

export function FlowBadge({ label, poor, acceptable }: { label: string; poor: boolean | null; acceptable: boolean | null }) {
  return <span class={`badge badge-${flowTone(poor, acceptable)}`}>{label}</span>;
}

export const shortClass = (name: string) => name.replace(/ \(Carr's.*\)$/, '');

export const USP_BANDS: [string, string][] = [
  ['Excellent', '≤10'], ['Good', '11–15'], ['Fair', '16–20'], ['Passable', '21–25'],
  ['Poor', '26–31'], ['Very poor', '32–37'], ['Very, very poor', '>37'],
];

export function UspScale({ active }: { active: string }) {
  return (
    <div class="scale" role="img" aria-label={`USP flow scale, this powder is ${active}`}>
      {USP_BANDS.map(([name, range], index) => (
        <div key={name} class={`scale-step step-${index} ${name === active ? 'is-active' : ''}`}>
          <span class="scale-bar" />
          <span class="scale-name">{name}</span>
          <span class="scale-range">{range}%</span>
        </div>
      ))}
    </div>
  );
}

function headline(result: ClassifyResult) {
  if (result.path === 'rule') return result.predicted_class;
  return result.poor_flow ? 'Likely poor flow' : 'Likely acceptable flow';
}

function verdict(result: ClassifyResult) {
  if (result.poor_flow && result.path === 'rule' && result.predicted_class === 'Passable') {
    return 'At the 25% poor-flow cutoff, although USP still bands it as Passable.';
  }
  if (result.poor_flow) return 'Poor flow: Carr’s index is 25% or higher.';
  if (result.path === 'ml') return 'Estimated Carr’s index below 25%. Confirm with tapped density.';
  return result.acceptable ? 'Acceptable for manufacturing.' : 'Borderline: between acceptable and poor flow.';
}

export function ResultCard({ result }: { result: ClassifyResult }) {
  const tone = flowTone(result.poor_flow, result.acceptable);
  return (
    <div class={`result tone-${tone}`} aria-live="polite">
      <div class="result-top">
        <span class="muted">Flow character</span>
        <PathBadge path={result.path} />
      </div>
      <h2 class="result-class">{headline(result)}</h2>
      <p class="result-verdict">{verdict(result)}</p>
      <div class="tiles">
        {result.path === 'rule' ? <>
          <Tile label="Carr’s index" value={`${formatNumber(result.carr_index)}%`} />
          <Tile label="Hausner ratio" value={formatNumber(result.hausner, 3)} />
          <Tile label="Hausner class" value={result.hausner_class ?? '—'} />
        </> : <>
          <Tile label="Model confidence" value={percent(result.confidence)} />
          <Tile label="Model tier" value={result.model_version?.split('/')[1] ?? '—'} />
          <Tile label="Version" value={result.model_version?.split('/')[0] ?? '—'} />
        </>}
      </div>
      {result.path === 'rule' && <UspScale active={result.predicted_class} />}
      {!!result.caveats?.length && (
        <details class="caveats" open={result.path === 'ml'}>
          <summary>{result.path === 'ml' ? 'What this estimate means' : 'Notes'} ({result.caveats.length})</summary>
          <ul>{result.caveats.map((caveat) => <li key={caveat}>{caveat}</li>)}</ul>
        </details>
      )}
      {result.basis && <p class="basis">{result.basis}</p>}
    </div>
  );
}

export function Tile({ label, value }: { label: string; value: ComponentChildren }) {
  return <div class="tile"><span class="tile-label">{label}</span><strong class="tile-value">{value}</strong></div>;
}

export function Drawer({ title, onClose, children }: { title: string; onClose: () => void; children: ComponentChildren }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); previous?.focus?.(); };
  }, []);
  return (
    <div class="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div class="drawer" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={panel}>
        <div class="drawer-head">
          <h2>{title}</h2>
          <button class="icon-btn" type="button" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Pager({ offset, limit, count, onChange }: {
  offset: number; limit: number; count: number; onChange: (offset: number) => void;
}) {
  if (offset === 0 && count < limit) return null;
  return (
    <div class="pager">
      <button class="btn btn-ghost" type="button" disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
      <span class="muted">{count ? `${offset + 1}–${offset + count}` : 'No more rows'}</span>
      <button class="btn btn-ghost" type="button" disabled={count < limit}
        onClick={() => onChange(offset + limit)}>Next</button>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ComponentChildren }) {
  return <div class="empty"><strong>{title}</strong>{children && <p>{children}</p>}</div>;
}

export function PageHead({ title, subtitle, children }: { title: string; subtitle: string; children?: ComponentChildren }) {
  return (
    <div class="page-head">
      <div><h1>{title}</h1><p>{subtitle}</p></div>
      {children && <div class="page-actions">{children}</div>}
    </div>
  );
}

export function parseOptional(value: string): number | undefined {
  const text = value.trim();
  return text === '' ? undefined : Number(text);
}
