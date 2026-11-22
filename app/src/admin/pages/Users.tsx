import { useState } from 'preact/hooks';
import { api, type AdminSubscription, type Role, type User } from '../../api';
import { Avatar } from '../../photos';
import { Drawer, Field, formatDate, inputValue, Notice, PageHead, useAuth, useLoad } from '../../ui';

function SetPlan({ user, current, onClose, onDone }: {
  user: User; current?: AdminSubscription; onClose: () => void; onDone: (text: string) => void;
}) {
  const [plan, setPlan] = useState(current?.active ? current.plan : 'pro');
  const [days, setDays] = useState('30');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: Event) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.setPlan(user.id, plan, Number(days));
      onDone(plan === 'free' ? `${user.full_name} moved to Free.` : `${user.full_name} granted ${plan} for ${days} days.`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <Drawer title={`Plan: ${user.full_name}`} onClose={onClose}>
      <form onSubmit={submit}>
        <Notice>{error}</Notice>
        {current?.active && <Notice kind="info">Currently {current.plan} until {formatDate(current.current_period_end)}. Granting the same plan adds days to it.</Notice>}
        <Field label="Plan">
          <select value={plan} onChange={(e) => setPlan(inputValue(e))}>
            <option value="pro">Pro</option><option value="lab">Lab</option><option value="free">Free (end current plan now)</option>
          </select>
        </Field>
        {plan !== 'free' && <Field label="Days" hint="1 to 366"><input required inputMode="numeric" value={days} onInput={(e) => setDays(inputValue(e))} /></Field>}
        <button class="btn btn-primary btn-block" disabled={busy}>{busy ? 'Saving…' : 'Apply'}</button>
        <p class="fineprint">Complimentary grants are recorded in the audit trail and are not payments.</p>
      </form>
    </Drawer>
  );
}

const BASE_ROLES: Role[] = ['analyst', 'reviewer', 'admin'];
const rolesFor = (me: User): Role[] => (me.role === 'superadmin' ? [...BASE_ROLES, 'superadmin'] : BASE_ROLES);

function ViewPhoto({ user, onClose, onRemoved }: { user: User; onClose: () => void; onRemoved: () => void }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function remove() {
    setBusy(true);
    try {
      await api.removeUserPhoto(user.id);
      onRemoved();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <Drawer title={`Profile photo: ${user.full_name}`} onClose={onClose}>
      <Notice>{error}</Notice>
      <div class="photo-review"><Avatar url={`/profile/${user.id}/photo`} name={user.full_name} size={220} /></div>
      <p class="hint">Shown to you because you are an administrator, even if the user has locked it. Initials mean there is no photo.</p>
      <button class="btn btn-danger btn-block" type="button" disabled={busy} onClick={remove}>{busy ? 'Removing…' : 'Remove photo'}</button>
      <p class="fineprint">Removal is permanent and recorded in the audit trail.</p>
    </Drawer>
  );
}

function NewUser({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { user: me } = useAuth();
  const ROLES = rolesFor(me);
  const [form, setForm] = useState({ email: '', full_name: '', password: '', role: 'analyst' as Role });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const update = (key: keyof typeof form) => (event: Event) => {
    const value = inputValue(event);
    setForm((prev) => ({ ...prev, [key]: value }));
  };
  async function submit(event: Event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.createUser(form);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <Drawer title="Add user" onClose={onClose}>
      <form onSubmit={submit}>
        <Notice>{error}</Notice>
        <Field label="Full name"><input required minLength={2} maxLength={255} value={form.full_name} onInput={update('full_name')} /></Field>
        <Field label="Email"><input required type="email" autoComplete="off" value={form.email} onInput={update('email')} /></Field>
        <Field label="Temporary password" hint="At least 8 characters"><input required type="password" minLength={8} maxLength={256} autoComplete="new-password" value={form.password} onInput={update('password')} /></Field>
        <Field label="Role">
          <select value={form.role} onChange={update('role')}>
            {ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
          </select>
        </Field>
        <button class="btn btn-primary btn-block" disabled={busy}>{busy ? 'Adding…' : 'Add user'}</button>
      </form>
    </Drawer>
  );
}

function ResetPassword({ user, onClose, onDone }: { user: User; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: Event) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.updateUser(user.id, { password });
      onDone();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <Drawer title={`Reset password: ${user.full_name}`} onClose={onClose}>
      <form onSubmit={submit}>
        <Notice>{error}</Notice>
        <Notice kind="warn">This signs the user out of all their sessions.</Notice>
        <Field label="New password" hint="At least 8 characters"><input required type="password" minLength={8} maxLength={256} autoComplete="new-password" value={password} onInput={(e) => setPassword(inputValue(e))} /></Field>
        <button class="btn btn-primary btn-block" disabled={busy}>{busy ? 'Saving…' : 'Reset password'}</button>
      </form>
    </Drawer>
  );
}

export function AdminUsers() {
  const { user: me } = useAuth();
  const { data, error, reload } = useLoad(() => api.users(), []);
  const subs = useLoad(() => api.adminSubscriptions(), []);
  const subByUser = new Map((subs.data ?? []).map((row) => [row.user_id, row]));
  const [adding, setAdding] = useState(false);
  const [resetting, setResetting] = useState<User | null>(null);
  const [planFor, setPlanFor] = useState<User | null>(null);
  const [photoFor, setPhotoFor] = useState<User | null>(null);
  const ROLES = rolesFor(me);
  const canManage = (target: User) => me.role === 'superadmin' || target.role !== 'superadmin';
  const [actionError, setActionError] = useState('');
  const [message, setMessage] = useState('');

  async function change(user: User, patch: { role?: Role; is_active?: boolean }, text: string) {
    setActionError('');
    setMessage('');
    try {
      await api.updateUser(user.id, patch);
      setMessage(text);
    } catch (err) {
      setActionError((err as Error).message);
    }
    await reload();
  }

  return (
    <>
      <PageHead title="Users" subtitle="Accounts are deactivated rather than deleted, so results stay attributable.">
        <button class="btn btn-primary" type="button" onClick={() => setAdding(true)}>Add user</button>
      </PageHead>
      <Notice>{error || actionError}</Notice>
      <Notice kind="success">{message}</Notice>
      <section class="card">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Plan</th><th>Status</th><th><span class="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {data?.map((user) => (
                <tr key={user.id} class={user.is_active ? '' : 'is-void'}>
                  <td class="strong">{user.full_name}{user.id === me.id && <span class="chip">you</span>}</td>
                  <td>{user.email}</td>
                  <td>
                    {canManage(user) ? (
                      <select class="select-small" aria-label={`Role for ${user.full_name}`} value={user.role}
                        onChange={(e) => change(user, { role: inputValue(e) as Role }, `${user.full_name} is now ${inputValue(e)}.`)}>
                        {ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
                      </select>
                    ) : <span class="chip">superadmin</span>}
                  </td>
                  <td>{user.role !== 'analyst' ? <span class="chip">staff</span>
                    : <span class="chip plan-pill">{subByUser.get(user.id)?.active ? subByUser.get(user.id)!.plan : 'free'}</span>}</td>
                  <td>{user.is_active ? <span class="badge badge-good">Active</span> : <span class="badge badge-poor">Inactive</span>}</td>
                  <td class="row-actions">
                    {canManage(user) ? <>
                      <button class="btn btn-small btn-ghost" type="button" onClick={() => setPhotoFor(user)}>Photo</button>
                      {user.role === 'analyst' && <button class="btn btn-small btn-ghost" type="button" onClick={() => setPlanFor(user)}>Set plan</button>}
                      <button class="btn btn-small btn-ghost" type="button" onClick={() => setResetting(user)}>Reset password</button>
                      <button class="btn btn-small btn-ghost" type="button"
                        onClick={() => change(user, { is_active: !user.is_active }, `${user.full_name} ${user.is_active ? 'deactivated' : 'reactivated'}.`)}>
                        {user.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    </> : <span class="muted small">Managed by superadmins</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {adding && <NewUser onClose={() => setAdding(false)} onSaved={() => { setAdding(false); setMessage('User added.'); void reload(); }} />}
      {planFor && <SetPlan user={planFor} current={subByUser.get(planFor.id)} onClose={() => setPlanFor(null)}
        onDone={(text) => { setPlanFor(null); setMessage(text); void subs.reload(); }} />}
      {photoFor && <ViewPhoto user={photoFor} onClose={() => setPhotoFor(null)}
        onRemoved={() => { setPhotoFor(null); setMessage('Photo removed.'); }} />}
      {resetting && <ResetPassword user={resetting} onClose={() => setResetting(null)} onDone={() => { setResetting(null); setMessage('Password reset.'); void reload(); }} />}
    </>
  );
}
