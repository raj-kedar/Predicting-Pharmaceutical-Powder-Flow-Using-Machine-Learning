import { useState } from 'preact/hooks';
import { api, type Session } from '../api';
import { Field, inputValue, Notice } from '../ui';

/** Shown instead of the app until a temporary password has been replaced. */
export function ForcePassword({ name, onChanged, onSignOut }: {
  name: string; onChanged: (session: Session) => void; onSignOut: () => void;
}) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: Event) {
    event.preventDefault();
    setError('');
    if (next !== confirm) { setError('The new passwords do not match.'); return; }
    if (next === current) { setError('Choose a password different from the temporary one.'); return; }
    setBusy(true);
    try {
      const out = await api.changePassword(current, next);
      onChanged({ token: out.access_token, role: out.role, full_name: out.full_name });
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div class="admin-gate">
      <form class="card force-card" onSubmit={submit}>
        <h1>Set your own password</h1>
        <p class="muted">Welcome, {name}. You signed in with a temporary password. Choose a new one to continue.</p>
        <Notice>{error}</Notice>
        <Field label="Temporary password"><input required type="password" autoComplete="current-password" value={current} onInput={(e) => setCurrent(inputValue(e))} /></Field>
        <Field label="New password" hint="At least 8 characters. Use something only you know."><input required type="password" minLength={8} maxLength={256} autoComplete="new-password" value={next} onInput={(e) => setNext(inputValue(e))} /></Field>
        <Field label="Confirm new password"><input required type="password" minLength={8} maxLength={256} autoComplete="new-password" value={confirm} onInput={(e) => setConfirm(inputValue(e))} /></Field>
        <button class="btn btn-primary btn-block" disabled={busy}>{busy ? 'Saving…' : 'Save and continue'}</button>
        <button class="btn btn-ghost btn-block force-signout" type="button" onClick={onSignOut}>Sign out</button>
      </form>
    </div>
  );
}
