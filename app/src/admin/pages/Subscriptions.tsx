import { api } from '../../api';
import { Empty, formatDate, Notice, PageHead, useLoad } from '../../ui';

export function Subscriptions() {
  const { data, error, loading } = useLoad(() => api.adminSubscriptions(), []);
  const rows = data ?? [];
  return (
    <>
      <PageHead title="Subscriptions" subtitle="Paid and complimentary plans. Users without a row are on the Free plan." />
      <Notice>{error}</Notice>
      <section class="card">
        {rows.length === 0 && !loading ? <Empty title="No subscriptions yet" /> : (
          <div class="table-wrap">
            <table>
              <thead><tr><th>User</th><th>Email</th><th>Plan</th><th>Ends</th><th>Source</th><th>Status</th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.user_id} class={row.active ? '' : 'is-void'}>
                    <td class="strong">{row.full_name}</td><td>{row.email}</td>
                    <td><span class="chip plan-pill">{row.plan}</span></td>
                    <td class="nowrap">{formatDate(row.current_period_end)}</td>
                    <td>{row.source === 'admin' ? 'Granted by admin' : 'Razorpay'}</td>
                    <td>{row.active ? <span class="badge badge-good">Active</span> : <span class="badge badge-mid">Expired</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
