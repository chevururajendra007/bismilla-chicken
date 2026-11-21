import { useEffect, useState } from 'react'
import { api, cart, enablePush, navigate, session, subscribe } from './api'
import Chat from './components/Chat'
import { clerkSignOut } from './components/clerk'
import VerifyPhone from './components/VerifyPhone'
import Admin from './pages/Admin'
import Checkout from './pages/Checkout'
import Home from './pages/Home'
import Orders from './pages/Orders'
import Track from './pages/Track'

function usePath() {
  const [p, setP] = useState(window.location.pathname + window.location.search)
  useEffect(() => {
    const f = () => setP(window.location.pathname + window.location.search)
    window.addEventListener('popstate', f)
    return () => window.removeEventListener('popstate', f)
  }, [])
  return p
}

function useStore() {
  const [, force] = useState(0)
  useEffect(() => subscribe(() => force((n) => n + 1)), [])
  return { user: session.user, items: cart.items }
}

export default function App() {
  const path = usePath()
  const { user, items } = useStore()
  const [cfg, setCfg] = useState(null)
  const [menu, setMenu] = useState(null)
  const [login, setLogin] = useState(null) // {title, then}
  const [installEvt, setInstallEvt] = useState(null)
  const [updateReady, setUpdateReady] = useState(null)
  const [pushState, setPushState] = useState(typeof Notification !== 'undefined' ? Notification.permission : 'unsupported')

  const loadMenu = () => api('/menu').then(setMenu).catch(() => {})
  useEffect(() => { api('/config').then(setCfg).catch(() => {}); loadMenu() }, [])

  // PWA: service worker, install prompt, update banner
  useEffect(() => {
    const onPrompt = (e) => { e.preventDefault(); setInstallEvt(e) }
    window.addEventListener('beforeinstallprompt', onPrompt)
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').then((reg) => {
        reg.addEventListener('updatefound', () => {
          const nw = reg.installing
          nw?.addEventListener('statechange', () => {
            if (nw.state === 'installed' && navigator.serviceWorker.controller) setUpdateReady(nw)
          })
        })
        setInterval(() => reg.update(), 30 * 60 * 1000)
      }).catch(() => {})
      let reloaded = false
      navigator.serviceWorker.addEventListener('controllerchange', () => { if (!reloaded) { reloaded = true; window.location.reload() } })
    }
    return () => window.removeEventListener('beforeinstallprompt', onPrompt)
  }, [])

  // refresh role from server (admin added/removed)
  useEffect(() => { if (session.token) api('/me').then((u) => session.save(session.token, u)).catch(() => {}) }, [])

  const requireLogin = (title, then) => {
    if (session.user) return then(session.user)
    setLogin({ title, then })
  }

  const turnOnPush = async () => setPushState(await enablePush(cfg?.vapid_public_key))

  const count = Object.keys(items).length
  const isStaff = user && ['superadmin', 'admin', 'staff'].includes(user.role)
  const route = path.split('?')[0]
  const ctx = { cfg, menu, loadMenu, user, items, requireLogin, pushState, turnOnPush }

  let page
  if (route === '/checkout') page = <Checkout {...ctx} />
  else if (route === '/orders') page = <Orders {...ctx} />
  else if (route.startsWith('/track/')) page = <Track code={route.split('/')[2]} {...ctx} />
  else if (route === '/admin') page = <Admin {...ctx} />
  else page = <Home {...ctx} />

  return (
    <div className="app">
      <header className="top">
        <a className="brand" href="/" onClick={(e) => { e.preventDefault(); navigate('/') }}>
          <img src="/icons/icon-192.png" alt="" /> <span>Bismilla <b>Chicken</b></span>
        </a>
        <nav>
          {installEvt && <button className="btn ghost sm" onClick={async () => { installEvt.prompt(); await installEvt.userChoice; setInstallEvt(null) }}>⬇ Install</button>}
          {isStaff && <button className={`btn sm ${route === '/admin' ? 'primary' : 'ghost'}`} onClick={() => navigate('/admin')}>Admin</button>}
          {user?.phone && !isStaff && <button className="btn ghost sm" onClick={() => navigate('/orders')}>My orders</button>}
        </nav>
      </header>

      {updateReady && (
        <div className="banner update">A new version of the app is ready.
          <button className="btn sm primary" onClick={() => updateReady.postMessage('SKIP_WAITING')}>Update now</button>
        </div>
      )}
      {user && pushState === 'default' && cfg?.vapid_public_key && (
        <div className="banner">🔔 Get order updates & today's rate on your phone.
          <button className="btn sm primary" onClick={turnOnPush}>Turn on</button>
        </div>
      )}

      <main>{page}</main>

      {count > 0 && route !== '/checkout' && route !== '/admin' && (
        <button className="cart-bar" onClick={() => navigate('/checkout')}>
          <span>🛒 {count} item{count > 1 ? 's' : ''}</span><b>View cart →</b>
        </button>
      )}

      {route !== '/admin' && <Chat />}

      <footer className="foot">
        <p>Bismilla Chicken · Opp. Extra Mart, Kota & Vidyanagar · 📞 <a href={`tel:${cfg?.shop_phone || '7904711708'}`}>{cfg?.shop_phone || '7904711708'}</a></p>
        <p className="muted">v{cfg?.version || '1.1.0'} · {user
          ? <>{user.phone || user.email} ({user.role}) · <button className="link" onClick={async () => { await clerkSignOut(); session.logout(); navigate('/') }}>Logout</button></>
          : <button className="link" onClick={() => navigate('/admin')}>Shop login</button>}</p>
      </footer>

      {login && (
        <div className="modal-bg" onClick={() => setLogin(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="x" onClick={() => setLogin(null)} aria-label="Close">×</button>
            <h3>{login.title}</h3>
            <VerifyPhone compact askEmail={false} askName={false}
              onVerified={(u) => { setLogin(null); login.then?.(u); if (cfg?.vapid_public_key && window.Notification?.permission === 'default') turnOnPush() }} />
          </div>
        </div>
      )}
    </div>
  )
}
