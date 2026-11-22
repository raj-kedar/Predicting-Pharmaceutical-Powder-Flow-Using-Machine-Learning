import { useRef, useState } from 'preact/hooks';
import { api, type ProfileInfo } from '../api';
import { Avatar } from '../photos';
import { Field, inputValue, Notice, PageHead, useAuth, useLoad } from '../ui';

export const PROFILE_CHANGED = 'flowlytix:profile-changed';

function ProfilePhoto() {
  const { user } = useAuth();
  const { data, error, reload } = useLoad(() => api.myProfile(), []);
  const [problem, setProblem] = useState('');
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  async function run(action: () => Promise<ProfileInfo>) {
    setBusy(true);
    setProblem('');
    try {
      await action();
      await reload();
      window.dispatchEvent(new Event(PROFILE_CHANGED));
    } catch (err) {
      setProblem((err as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  }

  const locked = data?.photo_locked ?? true;
  return (
    <section class="card">
      <h2>Profile photo</h2>
      <Notice>{error || problem}</Notice>
      <div class="photo-row">
        <Avatar url={data?.photo_url ?? null} name={user.full_name} locked={locked && !!data?.has_photo} size={96} />
        <div class="photo-actions">
          <input ref={input} id="photo-input" class="sr-only" type="file" accept="image/jpeg,image/png,image/webp"
            onChange={(event) => { const file = (event.currentTarget as HTMLInputElement).files?.[0]; if (file) void run(() => api.uploadPhoto(file)); }} />
          <label class={`btn btn-primary ${busy ? 'is-busy' : ''}`} for="photo-input">{busy ? 'Working…' : data?.has_photo ? 'Change photo' : 'Upload photo'}</label>
          {data?.has_photo && <button class="btn btn-ghost" type="button" disabled={busy} onClick={() => run(() => api.deletePhoto())}>Remove</button>}
          <p class="hint">JPEG, PNG or WebP, up to 5 MB. It is cropped square, and location and camera details are removed.</p>
        </div>
      </div>
      <label class="lock-toggle">
        <input type="checkbox" checked={locked} disabled={busy || !data}
          onChange={(event) => { const value = (event.currentTarget as HTMLInputElement).checked; void run(() => api.setPhotoLock(value)); }} />
        <span><strong>🔒 Lock my profile photo</strong>
          {locked ? 'Only you and administrators can see it.' : 'Anyone signed in to FlowLytix can see it.'}</span>
      </label>
    </section>
  );
}

export function Account() {
  const { user, updateSession } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: Event) {
    event.preventDefault();
    setError('');
    setMessage('');
    if (next !== confirm) { setError('The new passwords do not match.'); return; }
    setBusy(true);
    try {
      const out = await api.changePassword(current, next);
      updateSession({ token: out.access_token, role: out.role, full_name: out.full_name });
      setCurrent(''); setNext(''); setConfirm('');
      setMessage('Password changed. Your other sessions have been signed out.');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead title="My account" subtitle="Your profile and password." />
      <div class="grid-2">
        <section class="card">
          <h2>Profile</h2>
          <dl class="facts">
            <div><dt>Name</dt><dd>{user.full_name}</dd></div>
            <div><dt>Email</dt><dd>{user.email}</dd></div>
            <div><dt>Role</dt><dd>{user.role}</dd></div>
          </dl>
        </section>
        <ProfilePhoto />
        <form class="card" onSubmit={submit}>
          <h2>Change password</h2>
          <Notice>{error}</Notice>
          <Notice kind="success">{message}</Notice>
          <Field label="Current password"><input required type="password" autoComplete="current-password" value={current} onInput={(e) => setCurrent(inputValue(e))} /></Field>
          <Field label="New password" hint="At least 8 characters"><input required type="password" minLength={8} maxLength={256} autoComplete="new-password" value={next} onInput={(e) => setNext(inputValue(e))} /></Field>
          <Field label="Confirm new password"><input required type="password" minLength={8} maxLength={256} autoComplete="new-password" value={confirm} onInput={(e) => setConfirm(inputValue(e))} /></Field>
          <button class="btn btn-primary btn-block" disabled={busy}>{busy ? 'Saving…' : 'Change password'}</button>
        </form>
      </div>
    </>
  );
}
