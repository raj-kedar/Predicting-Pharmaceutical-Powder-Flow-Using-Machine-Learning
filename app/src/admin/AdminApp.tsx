import { useCallback, useEffect, useMemo, useState } from 'preact/hooks';
import { api, getSession, isAdminRole, setSession, setUnauthorizedHandler, type Session, type User } from '../api';
import { ForcePassword } from '../pages/ForcePassword';
import { Login } from '../pages/Login';
import { AuthContext, Icon } from '../ui';
import { AdminAudit } from './pages/Audit';
import { Overview } from './pages/Overview';
import { Payments } from './pages/Payments';
import { SiteEditor } from './pages/SiteContent';
import { Subscriptions } from './pages/Subscriptions';
import { AdminUsers } from './pages/Users';
import { BrandMark } from '../brand';

const ALL_ROUTES = [
  { path: '/', label: 'Overview', icon: 'chart', superOnly: false, view: () => <Overview /> },
  { path: '/users', label: 'Users', icon: 'users', superOnly: false, view: () => <AdminUsers /> },
  { path: '/subscriptions', label: 'Subscriptions', icon: 'card', superOnly: false, view: () => <Subscriptions /> },
  { path: '/payments', label: 'Payments', icon: 'coins', superOnly: false, view: () => <Payments /> },
  { path: '/audit', label: 'Audit trail', icon: 'shield', superOnly: false, view: () => <AdminAudit /> },
  { path: '/site', label: 'Site content', icon: 'book', superOnly: true, view: () => <SiteEditor /> },
];

const currentPath = () => window.location.hash.replace(/^#/, '').split('?')[0] || '/';

export function AdminApp() {
  const [session, setSessionState] = useState<Session | null>(getSession());
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(!!getSession());
  const [path, setPath] = useState(currentPath());
  const [menuOpen, setMenuOpen] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try { return localStorage.getItem('powderflow.theme') === 'dark' ? 'dark' : 'light'; } catch { return 'light'; }
  });

  const signOut = useCallback(() => { setSession(null); setSessionState(null); setUser(null); setBooting(false); }, []);
  const updateSession = useCallback((next: Session) => { setSession(next); setSessionState(next); }, []);
  useEffect(() => { setUnauthorizedHandler(signOut); }, [signOut]);
  useEffect(() => {
    const onHash = () => { setPath(currentPath()); setMenuOpen(false); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('powderflow.theme', theme); } catch { /* optional */ }
  }, [theme]);
  useEffect(() => {
    if (!session) return;
    let active = true;
    api.me().then((me) => { if (active) { setUser(me); setBooting(false); } })
      .catch(() => { if (active) setBooting(false); });
    return () => { active = false; };
  }, [session?.token]);

  const auth = useMemo(() => (user && session ? { user, session, updateSession, signOut } : null),
    [user, session, updateSession, signOut]);
  const ROUTES = ALL_ROUTES.filter((item) => !item.superOnly || user?.role === 'superadmin');
  const route = ROUTES.find((item) => item.path === path) ?? ROUTES[0];
  useEffect(() => { document.title = `${user ? route.label : 'Sign in'} · FlowLytix Admin`; }, [route.label, user]);
  const toggleTheme = () => setTheme(theme === 'dark' ? 'light' : 'dark');

  if (booting) return <div class="boot" role="status">Loading admin panel…</div>;
  if (!session || !auth) {
    return <Login admin onSuccess={(next) => { setBooting(true); updateSession(next); }} theme={theme} onTheme={toggleTheme} />;
  }
  if (auth.user.must_change_password) {
    return <ForcePassword name={auth.user.full_name} onChanged={updateSession} onSignOut={signOut} />;
  }
  if (!isAdminRole(auth.user.role)) {
    return (
      <div class="admin-gate">
        <div class="card">
          <h1>Admin access only</h1>
          <p class="muted">You are signed in as {auth.user.email}, which is not an admin account.</p>
          <a class="btn btn-primary" href="/">Go to FlowLytix</a>{' '}
          <button class="btn btn-ghost" type="button" onClick={signOut}>Sign out</button>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={auth}>
      <div class="shell admin-shell">
        {menuOpen && <div class="nav-scrim" onClick={() => setMenuOpen(false)} />}
        <aside class={menuOpen ? 'sidebar open' : 'sidebar'}>
          <a class="brand" href="#/">
            <BrandMark />
            <span><strong>FlowLytix<span class="admin-badge">ADMIN</span></strong><small>Operations console</small></span>
          </a>
          <nav aria-label="Admin">
            <div class="nav-group">
              <span class="nav-title">Manage</span>
              {ROUTES.map((item) => (
                <a key={item.path} href={`#${item.path}`} class={item === route ? 'nav-link active' : 'nav-link'}
                  aria-current={item === route ? 'page' : undefined}><Icon name={item.icon} /><span>{item.label}</span></a>
              ))}
            </div>
            <div class="nav-group">
              <span class="nav-title">Leave</span>
              <a class="nav-link" href="/"><Icon name="external" /><span>Open lab workspace</span></a>
            </div>
          </nav>
        </aside>
        <div class="main">
          <header class="topbar">
            <button class="icon-btn menu-btn" type="button" onClick={() => setMenuOpen(true)} aria-label="Open menu"><Icon name="menu" /></button>
            <span class="topbar-title">{route.label}</span>
            <div class="topbar-right">
              <span class="who"><strong>{auth.user.full_name}</strong><small>{auth.user.role}</small></span>
              <button class="btn btn-outline" type="button" onClick={signOut}>Sign out</button>
              <button class="icon-btn" type="button" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Use light theme' : 'Use dark theme'}>
                <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
              </button>
            </div>
          </header>
          <main class="content" key={route.path}>{route.view()}</main>
        </div>
      </div>
    </AuthContext.Provider>
  );
}
