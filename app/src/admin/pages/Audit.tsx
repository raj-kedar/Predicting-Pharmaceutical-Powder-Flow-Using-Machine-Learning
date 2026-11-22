import { useState } from 'preact/hooks';
import { api } from '../../api';
import { Empty, Field, formatDate, inputValue, Notice, PageHead, Pager, useLoad } from '../../ui';

const LIMIT = 50;
const ACTIONS = ['login', 'login_failed', 'register', 'change_password', 'create', 'update', 'classify',
  'review', 'void', 'order', 'payment', 'payment_rejected', 'set_plan'];

export function AdminAudit() {
  const [offset, setOffset] = useState(0);
  const [action, setAction] = useState('');
  const { data, error, loading } = useLoad(() => api.audit(LIMIT, offset, action || undefined), [offset, action]);
  const rows = data ?? [];

  return (
    <>
      <PageHead title="Audit trail" subtitle="Append-only record of who did what, and when. Entries cannot be edited or deleted." />
      <Notice>{error}</Notice>
      <section class="card">
        <div class="filters">
          <Field label="Action">
            <select value={action} onChange={(event) => { setAction(inputValue(event)); setOffset(0); }}>
              <option value="">All actions</option>
              {ACTIONS.map((item) => <option key={item} value={item}>{item.replace('_', ' ')}</option>)}
            </select>
          </Field>
        </div>
        {rows.length === 0 && !loading ? <Empty title="No audit entries" /> : (
          <div class="table-wrap">
            <table>
              <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Record</th><th>Detail</th><th>IP</th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td class="nowrap">{formatDate(row.at)}</td><td>{row.actor ?? 'unknown'}</td>
                    <td><span class="chip">{row.action}</span></td>
                    <td class="nowrap">{row.entity ? `${row.entity} #${row.entity_id ?? '—'}` : '—'}</td>
                    <td class="detail-cell">{row.detail ? JSON.stringify(row.detail) : '—'}</td>
                    <td>{row.ip_address ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager offset={offset} limit={LIMIT} count={rows.length} onChange={setOffset} />
      </section>
    </>
  );
}
