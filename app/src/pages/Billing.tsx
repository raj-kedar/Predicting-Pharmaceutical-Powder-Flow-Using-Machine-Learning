import { useState } from 'preact/hooks';
import { api, rupees, type PlanInfo } from '../api';
import { checkout } from '../razorpay';
import { formatDate, Notice, PageHead, useLoad } from '../ui';

export function UsageMeter({ used, limit }: { used: number; limit: number | null }) {
  const share = limit ? Math.min(1, used / limit) : 0;
  return (
    <div class="usage">
      <div class="usage-text"><strong>{used}</strong> {limit ? `of ${limit} results used this month` : 'results this month · unlimited'}</div>
      {limit !== null && <div class="meter"><span class={share >= 0.9 ? 'meter-fill warn' : 'meter-fill'} style={{ width: `${share * 100}%` }} /></div>}
    </div>
  );
}

export function PlanCard({ plan, current, action }: { plan: PlanInfo; current?: boolean; action?: preact.ComponentChildren }) {
  return (
    <article class={`plan-card ${plan.code === 'pro' ? 'featured' : ''}`}>
      {plan.code === 'pro' && <span class="plan-flag">Most popular</span>}
      <h3>{plan.name}</h3>
      <div class="plan-price">{plan.price_paise ? <><strong>{rupees(plan.price_paise)}</strong><span>/ 30 days</span></> : <strong>Free</strong>}</div>
      <ul>{plan.features.map((feature) => <li key={feature}>{feature}</li>)}</ul>
      {current ? <span class="btn btn-ghost btn-block is-current">Current plan</span> : action}
    </article>
  );
}

export function Billing() {
  const plans = useLoad(() => api.plans(), []);
  const mine = useLoad(() => api.myPlan(), []);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const mode = plans.data?.mode;

  async function buy(code: 'pro' | 'lab') {
    setBusy(code);
    setError('');
    setMessage('');
    try {
      const outcome = await checkout(code);
      if (outcome.status === 'paid') {
        setMessage(`Payment received. Your ${outcome.planName} plan is active.`);
        await mine.reload();
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('');
    }
  }

  return (
    <>
      <PageHead title="Plans & billing" subtitle="Each payment buys 30 days. Paying again before it ends adds another 30 days." />
      <Notice>{error || plans.error || mine.error}</Notice>
      <Notice kind="success">{message}</Notice>
      {mode === 'test' && <Notice kind="warn">Razorpay is in test mode. Use Razorpay test cards; no real money is charged.</Notice>}
      {mode === 'disabled' && <Notice kind="info">Online payments are not configured on this server yet.</Notice>}
      {mine.data && (
        <section class="card">
          <div class="card-head">
            <div><span class="muted">Current plan</span><h2>{mine.data.plan_name}{mine.data.staff ? ' (staff access)' : ''}</h2></div>
            {mine.data.current_period_end && <span class="muted">Active until {formatDate(mine.data.current_period_end)}</span>}
          </div>
          <UsageMeter used={mine.data.used_this_month} limit={mine.data.monthly_limit} />
        </section>
      )}
      {plans.data && (
        <div class="plan-grid">
          {plans.data.plans.map((plan) => (
            <PlanCard key={plan.code} plan={plan} current={!mine.data?.staff && mine.data?.plan === plan.code}
              action={plan.code === 'free' || mine.data?.staff ? null : (
                <button class="btn btn-primary btn-block" type="button" disabled={!!busy || mode === 'disabled'}
                  onClick={() => buy(plan.code as 'pro' | 'lab')}>
                  {busy === plan.code ? 'Opening checkout…' : mine.data?.plan === plan.code ? `Add 30 days` : `Get ${plan.name}`}
                </button>
              )} />
          ))}
        </div>
      )}
      <p class="fineprint">Prices include applicable taxes unless stated otherwise. Payments are processed by Razorpay; FlowLytix never sees your card or bank details.
        By paying you agree to the <a href="#/terms">Terms</a> and <a href="#/refunds">Refund &amp; cancellation policy</a>.</p>
    </>
  );
}
