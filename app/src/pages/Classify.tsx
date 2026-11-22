import { useState } from 'preact/hooks';
import { api, ApiError, type ClassifyResult, type ModelCard } from '../api';
import { Field, inputValue, Notice, PageHead, parseOptional, percent, ResultCard, useLoad } from '../ui';

const EMPTY = { bulk: '', tapped: '', angle: '', size: '', moisture: '', flow: '' };
type Form = typeof EMPTY;
const EXAMPLE: Form = { bulk: '0.45', tapped: '0.58', angle: '36', size: '110', moisture: '3.2', flow: '4.1' };

function method(form: Form, card: ModelCard | null) {
  const has = (key: keyof Form) => form[key].trim() !== '';
  const accuracy = (tier: string) => {
    const value = card?.ml_tiers[tier]?.lomo_accuracy;
    return value === undefined ? '' : ` · ${percent(value)} validated accuracy`;
  };
  if (!has('bulk')) return { tone: 'idle', text: 'Enter bulk density to begin' };
  if (has('tapped')) return { tone: 'exact', text: 'Exact USP <1174> classification' };
  if (!has('angle')) return { tone: 'idle', text: 'Add tapped density (exact) or angle of repose (estimate)' };
  if (has('size') && has('moisture') && has('flow')) return { tone: 'ml', text: `ML estimate, full tier${accuracy('full')}` };
  if (has('size') && has('moisture')) return { tone: 'ml', text: `ML estimate, mid tier${accuracy('mid')}` };
  return { tone: 'ml', text: `ML estimate, basic tier${accuracy('basic')}` };
}

export function ClassifyPage() {
  const [form, setForm] = useState<Form>(EMPTY);
  const [result, setResult] = useState<ClassifyResult | null>(null);
  const [error, setError] = useState('');
  const [needsUpgrade, setNeedsUpgrade] = useState(false);
  const [busy, setBusy] = useState(false);
  const { data: card } = useLoad(() => api.modelCard(), []);
  const current = method(form, card);

  const input = (key: keyof Form, label: string, unit: string, hint?: string, required = false) => (
    <Field label={label} unit={unit} hint={hint}>
      <input inputMode="decimal" autoComplete="off" required={required} value={form[key]}
        onInput={(event) => { const value = inputValue(event); setForm((prev) => ({ ...prev, [key]: value })); }} />
    </Field>
  );

  async function submit(event: Event) {
    event.preventDefault();
    const values = {
      bulk_density: parseOptional(form.bulk), tapped_density: parseOptional(form.tapped),
      angle_of_repose: parseOptional(form.angle), particle_size_um: parseOptional(form.size),
      moisture_percent: parseOptional(form.moisture), flow_rate_g_s: parseOptional(form.flow),
    };
    if (Object.values(values).some((value) => value !== undefined && !Number.isFinite(value))) {
      setError('Every measurement must be a number.');
      return;
    }
    setBusy(true);
    setError('');
    setNeedsUpgrade(false);
    try {
      setResult(await api.classify({ ...values, bulk_density: values.bulk_density! }));
    } catch (err) {
      setResult(null);
      setError((err as Error).message);
      setNeedsUpgrade(err instanceof ApiError && err.status === 402);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead title="Classify powder"
        subtitle="Tapped density gives the exact pharmacopoeial class. Without it, a validated model gives a screening estimate." />
      <div class="split">
        <form class="card" onSubmit={submit}>
          <div class={`method method-${current.tone}`} role="status">{current.text}</div>
          <Notice>{error}</Notice>
          {needsUpgrade && <p class="upgrade-link"><a class="btn btn-primary" href="#/billing">See plans</a></p>}
          <div class="form-grid">
            {input('bulk', 'Bulk density', 'g/mL', undefined, true)}
            {input('tapped', 'Tapped density', 'g/mL', 'Gives an exact class')}
            {input('angle', 'Angle of repose', 'deg')}
            {input('size', 'Particle size', 'µm')}
            {input('moisture', 'Moisture', '%')}
            {input('flow', 'Flow rate', 'g/s', 'Most useful ML input')}
          </div>
          <div class="form-actions">
            <button class="btn btn-primary btn-grow" disabled={busy}>{busy ? 'Classifying…' : 'Classify'}</button>
            <button class="btn btn-ghost" type="button" onClick={() => { setForm(EXAMPLE); setResult(null); setError(''); }}>Example</button>
            <button class="btn btn-ghost" type="button" onClick={() => { setForm(EMPTY); setResult(null); setError(''); }}>Clear</button>
          </div>
        </form>
        <section class="card card-accent">
          {result ? <ResultCard result={result} /> : (
            <div class="placeholder">
              <h2>Your result appears here</h2>
              <p>It will always say whether it is an exact calculation or a model estimate. Each result is saved to your history.</p>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
