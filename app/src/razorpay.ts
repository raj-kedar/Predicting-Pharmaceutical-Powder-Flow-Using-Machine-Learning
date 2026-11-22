import { api, type OrderOut } from './api';

declare global {
  interface Window { Razorpay?: new (options: Record<string, unknown>) => { open: () => void; on: (event: string, cb: (r: unknown) => void) => void } }
}

let loading: Promise<void> | null = null;

function loadCheckout(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  loading ??= new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => { loading = null; reject(new Error('Could not load Razorpay Checkout. Check your connection.')); };
    document.head.appendChild(script);
  });
  return loading;
}

export type CheckoutOutcome = { status: 'paid'; planName: string } | { status: 'dismissed' };

/** Create a server-priced order, open Razorpay Checkout, then verify on the server. */
export async function checkout(plan: 'pro' | 'lab'): Promise<CheckoutOutcome> {
  const order: OrderOut = await api.createOrder(plan);
  await loadCheckout();
  return new Promise((resolve, reject) => {
    const razorpay = new window.Razorpay!({
      key: order.key_id,
      amount: order.amount,
      currency: order.currency,
      order_id: order.order_id,
      name: 'FlowLytix',
      description: `${order.plan_name} plan · 30 days`,
      prefill: { name: order.name, email: order.email },
      theme: { color: '#a9552f' },
      handler: (response: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) => {
        api.verifyPayment(response)
          .then((result) => resolve({ status: 'paid', planName: result.plan_name }))
          .catch(reject);
      },
      modal: { ondismiss: () => resolve({ status: 'dismissed' }) },
    });
    razorpay.on('payment.failed', () => undefined); // Checkout shows the failure and lets the user retry
    razorpay.open();
  });
}
