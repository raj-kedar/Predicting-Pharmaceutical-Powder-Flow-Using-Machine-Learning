import { useCallback, useEffect, useMemo, useState } from 'preact/hooks';
import { api, getSession, isAdminRole, setSession, setUnauthorizedHandler, type ProfileInfo, type Role, type Session, type User } from './api';
import { Avatar } from './photos';
import { AuthContext, Icon } from './ui';
import { Account, PROFILE_CHANGED } from './pages/Account';
import { Billing } from './pages/Billing';
import { ClassifyPage } from './pages/Classify';
import { Dashboard } from './pages/Dashboard';
import { History } from './pages/History';
import { ForcePassword } from './pages/ForcePassword';
import { HelpPage } from './pages/Guide';
import { Landing } from './pages/Landing';
import { Legal, LEGAL_PAGES } from './pages/Legal';
import { Login } from './pages/Login';
import { Models } from './pages/Models';
import { Register } from './pages/Register';
import { Samples } from './pages/Samples';
import { BrandMark } from './brand';

interface Route { path: string; label: string; icon: string; group: string; roles?: Role[]; view: () => preact.JSX.Element }

const ROUTES: Route[] = [
  { path: '/', label: 'Dashboard', icon: 'home', group: 'Overview', view: () => <Dashboard /> },
  { path: '/help', label: 'How to use', icon: 'help', group: 'Overview', view: () => <HelpPage /> },
  { path: '/welcome', label: 'About flowability', icon: 'book', group: 'Overview', view: () => <Dashboard /> },
  { path: '/classify', label: 'Classify powder', icon: 'flask', group: 'Analysis', view: () => <ClassifyPage /> },
  { path: '/samples', label: 'Samples', icon: 'list', group: 'Analysis', view: () => <Samples /> },
  { path: '/history', label: 'Results & review', icon: 'clock', group: 'Analysis', view: () => <History /> },
  { path: '/models', label: 'Model performance', icon: 'chart', group: 'Model', view: () => <Models /> },
  { path: '/billing', label: 'Plans & billing', icon: 'card', group: 'Account', view: () => <Billing /> },
  { path: '/account', label: 'My account', icon: 'key', group: 'Account', view: () => <Account /> },
];

const currentPath = () => window.location.hash.replace(/^#/, '').split('?')[0] || '/';

function initialTheme(): 'light' | 'dark' {
  try {
    const saved = localStorage.getItem('powderflow.theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* storage may be blocked */ }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function App() {
  const [session, updateSessionState] = useState<Session | null>(getSession());
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(!!getSession());
  const [path, setPath] = useState(currentPath());
  const [menuOpen, setMenuOpen] = useState(false);
  const [theme, setTheme] = useState(initialTheme);

  const signOut = useCallback(() => {
    setSession(null);
    updateSessionState(null);
    setUser(null);
    setBooting(false);
  }, []);

  const updateSession = useCallback((next: Session) => {
    setSession(next);
    updateSessionState(next);
  }, []);

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

  const [photo, setPhoto] = useState<ProfileInfo | null>(null);
  useEffect(() => {
    if (!user) { setPhoto(null); return; }
    const load = () => { api.myProfile().then(setPhoto).catch(() => setPhoto(null)); };
    load();
    window.addEventListener(PROFILE_CHANGED, load);
    return () => window.removeEventListener(PROFILE_CHANGED, load);
  }, [user?.id]);

  const auth = useMemo(() => (user && session ? { user, session, updateSession, signOut } : null),
    [user, session, updateSession, signOut]);

  const visible = ROUTES.filter((route) => !route.roles || (user && route.roles.includes(user.role)));
  const route = visible.find((item) => item.path === path) ?? visible[0];

  useEffect(() => {
    const landing = path === '/welcome' || (!user && path === '/');
    if (landing) document.title = 'FlowLytix · Pharmaceutical powder flowability';
    else if (user) document.title = `${route.label} · FlowLytix`;
    else document.title = path === '/register' ? 'Create account · FlowLytix' : 'Sign in · FlowLytix';
  }, [route.label, user, path]);

  const toggleTheme = () => setTheme(theme === 'dark' ? 'light' : 'dark');

  if (LEGAL_PAGES.includes(path)) return <Legal path={path} />;
  if (booting) return <div class="boot" role="status">Loading FlowLytix…</div>;
  if (!session || !auth) {
    const enter = (next: Session) => {
      setBooting(true);
      updateSession(next);
      if (['/login', '/register'].includes(currentPath())) window.location.hash = '#/';
    };
    if (path === '/' || path === '/welcome') return <Landing signedIn={false} theme={theme} onTheme={toggleTheme} />;
    if (path === '/register') return <Register onSuccess={enter} theme={theme} onTheme={toggleTheme} />;
    return <Login onSuccess={enter} theme={theme} onTheme={toggleTheme} />;
  }
  if (auth.user.must_change_password) {
    return <ForcePassword name={auth.user.full_name} onChanged={updateSession}
      onSignOut={() => { signOut(); window.location.hash = '#/'; }} />;
  }
  if (path === '/welcome') return <Landing signedIn theme={theme} onTheme={toggleTheme} />;

  const groups = [...new Set(visible.map((item) => item.group))];
  return (
    <AuthContext.Provider value={auth}>
      <div class="shell">
        {menuOpen && <div class="nav-scrim" onClick={() => setMenuOpen(false)} />}
        <aside class={menuOpen ? 'sidebar open' : 'sidebar'}>
          <a class="brand" href="#/">
            <BrandMark />
            <span><strong>FlowLytix</strong><small>Measure. Classify. Review.</small></span>
          </a>
          <nav aria-label="Main">
            {groups.map((group) => (
              <div key={group} class="nav-group">
                <span class="nav-title">{group}</span>
                {visible.filter((item) => item.group === group).map((item) => (
                  <a key={item.path} href={`#${item.path}`} class={item === route ? 'nav-link active' : 'nav-link'}
                    aria-current={item === route ? 'page' : undefined}>
                    <Icon name={item.icon} /><span>{item.label}</span>
                  </a>
                ))}
              </div>
            ))}
            {isAdminRole(user!.role) && (
              <div class="nav-group">
                <span class="nav-title">Administration</span>
                <a class="nav-link" href="/admin"><Icon name="shield" /><span>Admin panel</span></a>
              </div>
            )}
          </nav>
        </aside>
        <div class="main">
          <header class="topbar">
            <button class="icon-btn menu-btn" type="button" onClick={() => setMenuOpen(true)} aria-label="Open menu">
              <Icon name="menu" />
            </button>
            <span class="topbar-title">{route.label}</span>
            <div class="topbar-right">
              <a class="who-link" href="#/account" aria-label="My account">
                <Avatar url={photo?.photo_url ?? null} name={user!.full_name} locked={!!photo?.has_photo && photo.photo_locked} size={38} />
                <span class="who"><strong>{user!.full_name}</strong><small>{user!.role}</small></span>
              </a>
              <button class="btn btn-outline" type="button" onClick={() => { signOut(); window.location.hash = '#/'; }}>Sign out</button>
              <button class="icon-btn" type="button" onClick={toggleTheme}
                aria-label={theme === 'dark' ? 'Use light theme' : 'Use dark theme'}>
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
