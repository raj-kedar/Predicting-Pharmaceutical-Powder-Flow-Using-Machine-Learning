import { useState } from 'preact/hooks';
import { api, type Session } from '../api';
import { Field, Icon, inputValue, Notice } from '../ui';
import { BrandMark } from '../brand';

export function Login({ onSuccess, theme, onTheme, admin = false }: {
  onSuccess: (session: Session) => void; theme: string; onTheme: () => void; admin?: boolean;
}) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: Event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const out = await api.login(email, password);
      onSuccess({ token: out.access_token, role: out.role, full_name: out.full_name });
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div class="login">
      <section class="login-side">
        <BrandMark size={72} />
        <h1>FlowLytix</h1>
        <p>Pharmaceutical powder flowability, classified from your lab measurements.</p>
        <ul>
          <li>Exact USP &lt;1174&gt; class from bulk and tapped density</li>
          <li>Screening estimates validated on unseen materials</li>
          <li>Attributable results with independent review</li>
        </ul>
      </section>
      <section class="login-main">
        <button class="icon-btn login-theme" type="button" onClick={onTheme}
          aria-label={theme === 'dark' ? 'Use light theme' : 'Use dark theme'}>
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
        </button>
        <form class="card login-card" onSubmit={submit}>
          <h2>{admin ? 'Admin sign in' : 'Sign in'}</h2>
          <p class="muted">{admin ? 'Restricted to FlowLytix administrators.' : 'Welcome back to FlowLytix.'}</p>
          <Notice>{error}</Notice>
          <Field label="Email">
            <input type="email" required autoComplete="username" value={email}
              onInput={(event) => setEmail(inputValue(event))} />
          </Field>
          <Field label="Password">
            <input type="password" required autoComplete="current-password" value={password}
              onInput={(event) => setPassword(inputValue(event))} />
          </Field>
          <button class="btn btn-primary btn-block" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          {!admin && <p class="login-alt">New to FlowLytix? <a href="#/register">Create a free account</a></p>}
          <a class="login-home" href={admin ? '/' : '#/'}>{admin ? 'Back to FlowLytix' : 'Back to home'}</a>
          <p class="fineprint">Screening and decision support. Not a GMP-validated system; confirm QC and regulatory decisions with validated methods.</p>
        </form>
      </section>
    </div>
  );
}
