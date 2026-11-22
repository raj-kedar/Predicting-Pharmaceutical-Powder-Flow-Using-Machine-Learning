import { useState } from 'preact/hooks';
import { api, rupees } from '../../api';
import { Empty, formatDate, Notice, PageHead, Pager, useLoad } from '../../ui';

const LIMIT = 50;

export function Payments() {
  const [offset, setOffset] = useState(0);
  const { data, error, loading } = useLoad(() => api.adminPayments(LIMIT, offset), [offset]);
  const rows = data ?? [];
  return (
    <>
      <PageHead title="Payments" subtitle="Every Razorpay order. Created orders that were never paid stay as 'created'." />
      <Notice>{error}</Notice>
      <section class="card">
        {rows.length === 0 && !loading ? <Empty title="No payments yet" /> : (
          <div class="table-wrap">
            <table>
              <thead><tr><th>ID</th><th>User</th><th>Plan</th><th class="num">Amount</th><th>Mode</th><th>Status</th><th>Order</th><th>Payment</th><th>Created</th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.id}</td><td>{row.email}</td><td><span class="chip plan-pill">{row.plan}</span></td>
                    <td class="num money">{rupees(row.amount_paise)}</td>
                    <td>{row.mode === 'live' ? <span class="badge badge-good">Live</span> : <span class="badge badge-mid">Test</span>}</td>
                    <td>{row.status === 'paid' ? <span class="badge badge-good">Paid</span> : <span class="badge badge-mid">Created</span>}</td>
                    <td class="detail-cell">{row.razorpay_order_id}</td>
                    <td class="detail-cell">{row.razorpay_payment_id ?? '—'}</td>
                    <td class="nowrap">{formatDate(row.created_at)}</td>
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
