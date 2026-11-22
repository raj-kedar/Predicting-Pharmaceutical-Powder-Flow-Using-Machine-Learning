import { api } from '../api';
import { UsageMeter } from './Billing';
import { Empty, FlowBadge, formatDate, Notice, PageHead, PathBadge, shortClass, Tile, USP_BANDS, useAuth, useLoad } from '../ui';

const WINDOW = 200;

export function Dashboard() {
  const { user } = useAuth();
  const { data, error, loading } = useLoad(() => api.predictions({ limit: WINDOW, offset: 0 }), []);
  const plan = useLoad(() => api.myPlan(), []);
  const rows = data ?? [];
  const exact = rows.filter((row) => row.path === 'rule');
  const poor = rows.filter((row) => row.poor_flow).length;
  const pending = rows.filter((row) => !row.reviewed && !row.sample_voided).length;
  const counts = USP_BANDS.map(([name]) => ({ name, count: exact.filter((row) => row.predicted_class === name).length }));
  const largest = Math.max(1, ...counts.map((item) => item.count));

  return (
    <>
      <PageHead title={`Welcome, ${user.full_name}`}
        subtitle={user.role === 'analyst' ? 'A summary of your classification results.' : 'A summary of classification results across the lab.'}>
        <a class="btn btn-primary" href="#/classify">Classify a powder</a>
      </PageHead>
      <Notice>{error}</Notice>
      {plan.data && !plan.data.staff && (
        <section class="card plan-strip">
          <div><span class="muted">Your plan</span><strong>{plan.data.plan_name}</strong></div>
          <UsageMeter used={plan.data.used_this_month} limit={plan.data.monthly_limit} />
          <a class="btn btn-ghost" href="#/billing">{plan.data.plan === 'free' ? 'Upgrade' : 'Manage plan'}</a>
        </section>
      )}
      <div class="stat-grid">
        <Tile label="Total results" value={loading ? '…' : rows.length} />
        <Tile label="Exact (USP)" value={loading ? '…' : exact.length} />
        <Tile label="ML estimates" value={loading ? '…' : rows.length - exact.length} />
        <Tile label="Poor flow" value={loading ? '…' : poor} />
        <Tile label="Awaiting review" value={loading ? '…' : pending} />
      </div>
      {rows.length === WINDOW && <p class="muted small">Showing the latest {WINDOW} results.</p>}
      <div class="grid-2">
        <section class="card">
          <h2>Exact results by USP class</h2>
          {exact.length === 0 ? <Empty title="No exact results yet">Enter bulk and tapped density to get one.</Empty> : (
            <div class="bars">
              {counts.map((item, index) => (
                <div class="bar-row" key={item.name}>
                  <span>{item.name}</span>
                  <span class="bar-track"><span class={`bar-fill step-${index}`} style={{ width: `${(item.count / largest) * 100}%` }} /></span>
                  <strong>{item.count}</strong>
                </div>
              ))}
            </div>
          )}
        </section>
        <section class="card">
          <div class="card-head"><h2>Recent results</h2><a href="#/history">View all</a></div>
          {rows.length === 0 && !loading ? <Empty title="No results yet" /> : (
            <ul class="recent">
              {rows.slice(0, 6).map((row) => (
                <li key={row.id}>
                  <div><FlowBadge label={shortClass(row.predicted_class)} poor={row.poor_flow} acceptable={row.acceptable} />
                    <small>{formatDate(row.created_at)}</small></div>
                  <PathBadge path={row.path} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
