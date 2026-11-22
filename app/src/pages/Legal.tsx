import type { ComponentChildren } from 'preact';
import { useSiteContent } from '../photos';
import { BrandMark } from '../brand';

export const LEGAL_PAGES = ['/terms', '/privacy', '/refunds', '/contact'];

function Contact() {
  const { business } = useSiteContent();
  return (
    <dl class="facts">
      <div><dt>Business</dt><dd>{business.name}</dd></div>
      <div><dt>Email</dt><dd>{business.email}</dd></div>
      <div><dt>Phone</dt><dd>{business.phone}</dd></div>
      <div><dt>Address</dt><dd>{business.address}</dd></div>
    </dl>
  );
}

function LastUpdated() {
  const { business } = useSiteContent();
  return <p class="muted">Last updated: {business.last_updated}</p>;
}

const PAGES: Record<string, { title: string; body: ComponentChildren }> = {
  '/terms': {
    title: 'Terms of use',
    body: <>
      <h2>The service</h2>
      <p>FlowLytix classifies pharmaceutical powder flow from measurements you enter. Exact results apply the USP &lt;1174&gt; compressibility scale. Estimates come from statistical models and are labelled as estimates.</p>
      <h2>Not for regulated decisions</h2>
      <p>FlowLytix is a screening and decision-support tool. It is not a validated computerised system under GMP or 21 CFR Part 11. Do not rely on it alone for quality control, batch release, regulatory submissions or any decision affecting patient safety; confirm with your own validated test methods.</p>
      <h2>Accounts</h2>
      <p>Keep your password private. You are responsible for activity under your account and for the accuracy of data you enter.</p>
      <h2>Paid plans</h2>
      <p>A paid plan gives the listed features for 30 days from payment and does not renew automatically. Payments are processed by Razorpay. See the Refund &amp; cancellation policy.</p>
      <h2>Liability</h2>
      <p>The service is provided as is, without warranties, to the extent permitted by law.</p>
    </>,
  },
  '/privacy': {
    title: 'Privacy policy',
    body: <>
      <h2>What we collect</h2>
      <p>Your name, email address, password (stored only as a secure hash), the measurements and results you save, and records of actions for the audit trail, including the network address used.</p>
      <h2>Payments</h2>
      <p>Payments are handled by Razorpay. FlowLytix receives order and payment references and the amount paid. We never receive or store card, UPI or bank details.</p>
      <h2>How we use it</h2>
      <p>Only to provide the service, secure accounts, keep an audit trail and process payments. We do not sell personal data.</p>
      <h2>Storage and retention</h2>
      <p>Data is stored on Amazon Web Services. Audit and payment records are kept as permanent records. Contact us to ask about or close your account.</p>
    </>,
  },
  '/refunds': {
    title: 'Refund & cancellation policy',
    body: <>
      <h2>Cancellation</h2>
      <p>Plans do not renew automatically, so there is nothing to cancel. Your plan simply ends 30 days after payment.</p>
      <h2>Refunds</h2>
      <p>If you were charged twice or charged without the plan activating, contact us within 7 days with the payment ID. Approved refunds are returned to the original payment method through Razorpay, usually within 5–7 working days.</p>
      <h2>Delivery</h2>
      <p>FlowLytix is an online service with no physical delivery. Plan access starts immediately after successful payment.</p>
    </>,
  },
  '/contact': { title: 'Contact us', body: <><p>For support, billing or refund requests:</p><Contact /></> },
};

export function Legal({ path }: { path: string }) {
  const page = PAGES[path] ?? PAGES['/terms'];
  return (
    <div class="legal">
      <header class="lp-nav">
        <a class="lp-brand" href="#/">
          <BrandMark />
          FlowLytix
        </a>
        <div class="lp-nav-right"><a class="btn btn-outline" href="#/">Home</a></div>
      </header>
      <main class="legal-body">
        <div class="notice notice-warn">Draft for review. The site owner must complete the bracketed details and check this policy before accepting live payments.</div>
        <h1>{page.title}</h1>
        <LastUpdated />
        {page.body}
        {path !== '/contact' && <><h2>Contact</h2><Contact /></>}
        <nav class="legal-links" aria-label="Policies">
          <a href="#/terms">Terms</a><a href="#/privacy">Privacy</a><a href="#/refunds">Refunds &amp; cancellation</a><a href="#/contact">Contact</a>
        </nav>
      </main>
    </div>
  );
}
