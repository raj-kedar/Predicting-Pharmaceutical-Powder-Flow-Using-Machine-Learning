import { useState } from 'preact/hooks';
import { api, type ClassifyResult, type Sample } from '../api';
import { Drawer, Empty, Field, formatDate, formatNumber, inputValue, Notice, PageHead, Pager, parseOptional, ResultCard, useLoad } from '../ui';

const LIMIT = 25;
const BLANK = { material_name: '', material_type: '', batch_no: '', replicate_no: '1', bulk: '', tapped: '', angle: '', size: '', moisture: '', flow: '', method_ref: '', notes: '' };
type Form = typeof BLANK;

function NewSample({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<Form>(BLANK);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const { data: materials } = useLoad(() => api.materials(), []);
  const text = (key: keyof Form) => ({
    value: form[key],
    onInput: (event: Event) => { const value = inputValue(event); setForm((prev) => ({ ...prev, [key]: value })); },
  });

  async function submit(event: Event) {
    event.preventDefault();
    const numbers = {
      bulk_density: parseOptional(form.bulk), tapped_density: parseOptional(form.tapped),
      angle_of_repose: parseOptional(form.angle), particle_size_um: parseOptional(form.size),
      moisture_percent: parseOptional(form.moisture), flow_rate_g_s: parseOptional(form.flow),
    };
    const replicate = Number(form.replicate_no);
    if (!Number.isInteger(replicate) || Object.values(numbers).some((v) => v !== undefined && !Number.isFinite(v))) {
      setError('Measurements must be numbers and the replicate must be a whole number.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await api.createSample({
        ...numbers, bulk_density: numbers.bulk_density!, material_name: form.material_name,
        material_type: form.material_type || undefined, batch_no: form.batch_no, replicate_no: replicate,
        method_ref: form.method_ref || undefined, notes: form.notes || undefined,
      });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <Drawer title="Record a sample" onClose={onClose}>
      <form onSubmit={submit}>
        <Notice>{error}</Notice>
        <Notice kind="info">Measurements are permanent once saved. A wrong entry can be voided with a reason.</Notice>
        <Field label="Material"><input required maxLength={255} list="materials" {...text('material_name')} /></Field>
        <datalist id="materials">{materials?.map((item) => <option key={item.id} value={item.name} />)}</datalist>
        <div class="form-grid">
          <Field label="Material type">
            <select {...text('material_type')}>
              <option value="">Not specified</option><option>Excipient</option><option>API</option>
              <option>API Granule</option><option>Blend</option>
            </select>
          </Field>
          <Field label="Batch number"><input required maxLength={64} {...text('batch_no')} /></Field>
          <Field label="Replicate"><input required inputMode="numeric" {...text('replicate_no')} /></Field>
          <Field label="Bulk density" unit="g/mL"><input required inputMode="decimal" {...text('bulk')} /></Field>
          <Field label="Tapped density" unit="g/mL"><input inputMode="decimal" {...text('tapped')} /></Field>
          <Field label="Angle of repose" unit="deg"><input inputMode="decimal" {...text('angle')} /></Field>
          <Field label="Particle size" unit="µm"><input inputMode="decimal" {...text('size')} /></Field>
          <Field label="Moisture" unit="%"><input inputMode="decimal" {...text('moisture')} /></Field>
          <Field label="Flow rate" unit="g/s"><input inputMode="decimal" {...text('flow')} /></Field>
        </div>
        <Field label="Method reference"><input maxLength={255} placeholder="e.g. USP <616> Method I" {...text('method_ref')} /></Field>
        <Field label="Notes"><textarea rows={2} maxLength={5000} {...text('notes')} /></Field>
        <button class="btn btn-primary btn-block" disabled={busy}>{busy ? 'Saving…' : 'Save sample'}</button>
      </form>
    </Drawer>
  );
}

function VoidSample({ sample, onClose, onDone }: { sample: Sample; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: Event) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.voidSample(sample.id, reason);
      onDone();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <Drawer title={`Void sample #${sample.id}`} onClose={onClose}>
      <form onSubmit={submit}>
        <Notice>{error}</Notice>
        <Notice kind="warn">This cannot be undone. The sample stays on record, marked as void, and can no longer be classified or reviewed.</Notice>
        <Field label="Reason"><textarea required minLength={3} maxLength={1000} rows={3} value={reason}
          onInput={(event) => setReason(inputValue(event))} /></Field>
        <button class="btn btn-danger btn-block" disabled={busy}>{busy ? 'Voiding…' : 'Void sample'}</button>
      </form>
    </Drawer>
  );
}

export function Samples() {
  const [offset, setOffset] = useState(0);
  const [voided, setVoided] = useState(false);
  const [adding, setAdding] = useState(false);
  const [voiding, setVoiding] = useState<Sample | null>(null);
  const [result, setResult] = useState<ClassifyResult | null>(null);
  const [actionError, setActionError] = useState('');
  const [message, setMessage] = useState('');
  const { data, error, loading, reload } = useLoad(() => api.samples(LIMIT, offset, voided), [offset, voided]);
  const rows = data ?? [];

  async function classify(sample: Sample) {
    setActionError('');
    setMessage('');
    try {
      setResult(await api.classifySample(sample.id));
    } catch (err) {
      setActionError((err as Error).message);
    }
  }

  return (
    <>
      <PageHead title="Samples" subtitle="Recorded measurements by material, batch and replicate.">
        <button class="btn btn-primary" type="button" onClick={() => setAdding(true)}>Record sample</button>
      </PageHead>
      <Notice>{error || actionError}</Notice>
      <Notice kind="success">{message}</Notice>
      <section class="card">
        <label class="check">
          <input type="checkbox" checked={voided} onChange={(event) => { setVoided((event.currentTarget as HTMLInputElement).checked); setOffset(0); }} />
          Include voided samples
        </label>
        {rows.length === 0 && !loading ? <Empty title="No samples recorded">Record your first measurement to get started.</Empty> : (
          <div class="table-wrap">
            <table>
              <thead><tr><th>ID</th><th>Material</th><th>Batch</th><th>Rep</th><th class="num">Bulk</th><th class="num">Tapped</th><th>Measured</th><th>Status</th><th><span class="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} class={row.is_voided ? 'is-void' : ''}>
                    <td>{row.id}</td><td class="strong">{row.material_name}</td><td>{row.batch_no}</td><td>{row.replicate_no}</td>
                    <td class="num">{formatNumber(row.bulk_density, 3)}</td><td class="num">{formatNumber(row.tapped_density, 3)}</td>
                    <td class="nowrap">{formatDate(row.measured_at)}</td>
                    <td>{row.is_voided ? <span class="badge badge-poor" title={row.void_reason ?? ''}>Void</span> : <span class="badge badge-good">Active</span>}</td>
                    <td class="row-actions">
                      {!row.is_voided && <>
                        <button class="btn btn-small" type="button" onClick={() => classify(row)}>Classify</button>
                        <button class="btn btn-small btn-ghost" type="button" onClick={() => setVoiding(row)}>Void</button>
                      </>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager offset={offset} limit={LIMIT} count={rows.length} onChange={setOffset} />
      </section>
      {adding && <NewSample onClose={() => setAdding(false)} onSaved={() => { setAdding(false); setMessage('Sample saved.'); setOffset(0); void reload(); }} />}
      {voiding && <VoidSample sample={voiding} onClose={() => setVoiding(null)} onDone={() => { setVoiding(null); setMessage('Sample voided.'); void reload(); }} />}
      {result && <Drawer title="Classification result" onClose={() => setResult(null)}><ResultCard result={result} /></Drawer>}
    </>
  );
}
