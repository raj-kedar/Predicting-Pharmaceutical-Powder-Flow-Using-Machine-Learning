import { useState } from 'preact/hooks';
import { api } from '../api';
import { Drawer, Empty, Field, FlowBadge, formatDate, formatNumber, inputValue, Notice, PageHead, Pager, PathBadge, percent, ResultCard, shortClass, useAuth, useLoad } from '../ui';

const LIMIT = 25;
const INPUT_LABELS: Record<string, string> = {
  bulk_density: 'Bulk density (g/mL)', tapped_density: 'Tapped density (g/mL)', angle_of_repose: 'Angle of repose (deg)',
  particle_size_um: 'Particle size (µm)', moisture_percent: 'Moisture (%)', flow_rate_g_s: 'Flow rate (g/s)',
};

function Detail({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const { user } = useAuth();
  const { data, error, reload } = useLoad(() => api.prediction(id), [id]);
  const [comment, setComment] = useState('');
  const [reviewError, setReviewError] = useState('');
  const [busy, setBusy] = useState(false);
  const canReview = !!data && user.role !== 'analyst' && data.user_id !== user.id && !data.reviewed && !data.sample_voided;

  async function review(event: Event) {
    event.preventDefault();
    setBusy(true);
    setReviewError('');
    try {
      await api.review(id, comment);
      await reload();
      onChanged();
    } catch (err) {
      setReviewError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer title={`Result #${id}`} onClose={onClose}>
      <Notice>{error}</Notice>
      {data && <>
        {data.sample_voided && <Notice kind="warn">The sample behind this result has been voided.</Notice>}
        <ResultCard result={data} />
        <h3>Inputs</h3>
        <dl class="facts">
          {Object.entries(INPUT_LABELS).filter(([key]) => data.inputs[key] != null).map(([key, label]) => (
            <div key={key}><dt>{label}</dt><dd>{data.inputs[key]}</dd></div>
          ))}
          <div><dt>Created</dt><dd>{formatDate(data.created_at)}</dd></div>
          {data.sample_id && <div><dt>Sample</dt><dd>#{data.sample_id}</dd></div>}
        </dl>
        <h3>Review</h3>
        {data.reviewed ? (
          <Notice kind="success">Reviewed {formatDate(data.reviewed_at)}{data.review_comment ? `: ${data.review_comment}` : ''}</Notice>
        ) : canReview ? (
          <form onSubmit={review}>
            <Notice>{reviewError}</Notice>
            <Field label="Comment (optional)"><textarea rows={2} maxLength={2000} value={comment} onInput={(event) => setComment(inputValue(event))} /></Field>
            <button class="btn btn-primary btn-block" disabled={busy}>{busy ? 'Saving…' : 'Approve result'}</button>
            <p class="fineprint">A review is final and is recorded in the audit trail.</p>
          </form>
        ) : (
          <p class="muted">{data.sample_voided ? 'Voided results cannot be reviewed.' : data.user_id === user.id && user.role !== 'analyst'
            ? 'You produced this result, so someone else must review it.' : 'Awaiting review by a reviewer.'}</p>
        )}
      </>}
    </Drawer>
  );
}

export function History() {
  const [offset, setOffset] = useState(0);
  const [path, setPath] = useState('');
  const [reviewed, setReviewed] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const { data, error, loading, reload } = useLoad(
    () => api.predictions({ limit: LIMIT, offset, path: path || undefined, reviewed: reviewed || undefined }),
    [offset, path, reviewed],
  );
  const rows = data ?? [];

  return (
    <>
      <PageHead title="Results & review" subtitle="Every result, with its method, inputs and review status." />
      <Notice>{error}</Notice>
      <section class="card">
        <div class="filters">
          <Field label="Method">
            <select value={path} onChange={(event) => { setPath(inputValue(event)); setOffset(0); }}>
              <option value="">All methods</option><option value="rule">Exact (USP)</option><option value="ml">ML estimate</option>
            </select>
          </Field>
          <Field label="Review status">
            <select value={reviewed} onChange={(event) => { setReviewed(inputValue(event)); setOffset(0); }}>
              <option value="">All</option><option value="false">Awaiting review</option><option value="true">Reviewed</option>
            </select>
          </Field>
        </div>
        {rows.length === 0 && !loading ? <Empty title="No matching results" /> : (
          <div class="table-wrap">
            <table>
              <thead><tr><th>ID</th><th>Class</th><th>Method</th><th class="num">Carr’s</th><th class="num">Hausner</th><th class="num">Confidence</th><th>Created</th><th>Review</th><th><span class="sr-only">Open</span></th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} class={row.sample_voided ? 'is-void' : ''}>
                    <td>{row.id}</td>
                    <td><FlowBadge label={shortClass(row.predicted_class)} poor={row.poor_flow} acceptable={row.acceptable} /></td>
                    <td><PathBadge path={row.path} /></td>
                    <td class="num">{formatNumber(row.carr_index)}</td><td class="num">{formatNumber(row.hausner, 3)}</td>
                    <td class="num">{row.path === 'ml' ? percent(row.confidence) : '—'}</td>
                    <td class="nowrap">{formatDate(row.created_at)}</td>
                    <td>{row.sample_voided ? <span class="badge badge-poor">Void</span> : row.reviewed ? <span class="badge badge-good">Reviewed</span> : <span class="badge badge-mid">Pending</span>}</td>
                    <td><button class="btn btn-small btn-ghost" type="button" onClick={() => setSelected(row.id)}>Open</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager offset={offset} limit={LIMIT} count={rows.length} onChange={setOffset} />
      </section>
      {selected !== null && <Detail id={selected} onClose={() => setSelected(null)} onChanged={() => void reload()} />}
    </>
  );
}
