import { useState } from 'preact/hooks';
import { api, type Session } from '../api';
import { Field, Icon, inputValue, Notice } from '../ui';

export function Register({ onSuccess, theme, onTheme }: {
  onSuccess: (session: Session) => void; theme: string; onTheme: () => void;
}) {
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '', agree: false });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const update = (key: 'name' | 'email' | 'password' | 'confirm') => (event: Event) => {
    const value = inputValue(event);
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  async function submit(event: Event) {
    event.preventDefault();
    if (form.password !== form.confirm) { setError('The passwords do not match.'); return; }
    setBusy(true);
    setError('');
    try {
      const out = await api.register(form.email, form.name, form.password);
      onSuccess({ token: out.access_token, role: out.role, full_name: out.full_name });
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div class="login">
      <section class="login-side">
        <h1>Start free</h1>
        <p>Exact USP &lt;1174&gt; classification is free. Upgrade any time for ML screening estimates and higher limits.</p>
        <ul><li>No card needed for the Free plan</li><li>20 results every month</li><li>Your results stay private to your account</li></ul>
      </section>
      <section class="login-main">
        <button class="icon-btn login-theme" type="button" onClick={onTheme} aria-label={theme === 'dark' ? 'Use light theme' : 'Use dark theme'}>
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
        </button>
        <form class="card login-card" onSubmit={submit}>
          <h2>Create your account</h2>
          <p class="muted">Already registered? <a href="#/login">Sign in</a></p>
          <Notice>{error}</Notice>
          <Field label="Full name"><input required minLength={2} maxLength={255} autoComplete="name" value={form.name} onInput={update('name')} /></Field>
          <Field label="Email"><input required type="email" autoComplete="email" value={form.email} onInput={update('email')} /></Field>
          <Field label="Password" hint="At least 8 characters"><input required type="password" minLength={8} maxLength={256} autoComplete="new-password" value={form.password} onInput={update('password')} /></Field>
          <Field label="Confirm password"><input required type="password" minLength={8} maxLength={256} autoComplete="new-password" value={form.confirm} onInput={update('confirm')} /></Field>
          <label class="check agree">
            <input type="checkbox" required checked={form.agree} onChange={(event) => { const agree = (event.currentTarget as HTMLInputElement).checked; setForm((prev) => ({ ...prev, agree })); }} />
            <span>I agree to the <a href="#/terms">Terms</a> and <a href="#/privacy">Privacy policy</a>.</span>
          </label>
          <button class="btn btn-primary btn-block" disabled={busy}>{busy ? 'Creating account…' : 'Create free account'}</button>
          <a class="login-home" href="#/">Back to home</a>
        </form>
      </section>
    </div>
  );
}
