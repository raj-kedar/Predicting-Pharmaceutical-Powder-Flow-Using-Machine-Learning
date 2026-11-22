import { api, rupees } from '../../api';
import { Notice, PageHead, Tile, useLoad } from '../../ui';

export function Overview() {
  const { data, error } = useLoad(() => api.adminOverview(), []);
  const plans = useLoad(() => api.plans(), []);
  const mode = plans.data?.mode;
  return (
    <>
      <PageHead title="Overview" subtitle="Accounts, subscriptions and payments at a glance." />
      <Notice>{error}</Notice>
      {mode === 'live' && <Notice kind="success">Razorpay is in LIVE mode. Real payments are being accepted.</Notice>}
      {mode === 'test' && <Notice kind="warn">Razorpay is in TEST mode. No real money is charged.</Notice>}
      {mode === 'disabled' && <Notice kind="info">Payments are not configured. Set the Razorpay keys on the server.</Notice>}
      {data && <>
        <div class="stat-grid">
          <Tile label="Analysts" value={data.users.analyst} />
          <Tile label="Reviewers" value={data.users.reviewer} />
          <Tile label="Admins" value={data.users.admin + (data.users.superadmin ?? 0)} />
          <Tile label="Active Pro" value={data.active_subscriptions.pro} />
          <Tile label="Active Lab" value={data.active_subscriptions.lab} />
        </div>
        <div class="stat-grid three">
          <Tile label="Revenue (live)" value={<span class="money">{rupees(data.revenue_paise.live)}</span>} />
          <Tile label="Paid orders" value={data.payments_paid} />
          <Tile label="Results this month" value={data.results_this_month} />
        </div>
        {data.revenue_paise.test > 0 && <p class="muted small">Test-mode payments total {rupees(data.revenue_paise.test)} and are not counted as revenue.</p>}
      </>}
    </>
  );
}
