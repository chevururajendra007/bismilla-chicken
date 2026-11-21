// API client + tiny global store (session, cart) + router helpers.
const TOKEN_KEY = 'bc_token'
const USER_KEY = 'bc_user'
const CART_KEY = 'bc_cart'

const safe = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d } catch { return d } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* private mode */ } },
  del(k) { try { localStorage.removeItem(k) } catch { /* ignore */ } },
}

export const session = {
  get token() { return safe.get(TOKEN_KEY, null) },
  get user() { return safe.get(USER_KEY, null) },
  save(token, user) { safe.set(TOKEN_KEY, token); safe.set(USER_KEY, user); emit() },
  logout() { safe.del(TOKEN_KEY); safe.del(USER_KEY); emit() },
}

export const cart = {
  get items() { return safe.get(CART_KEY, {}) },
  set(id, qty) {
    const c = { ...cart.items }
    if (qty <= 0) delete c[id]; else c[id] = Math.round(qty * 100) / 100
    safe.set(CART_KEY, c); emit()
  },
  clear() { safe.set(CART_KEY, {}); emit() },
}

const listeners = new Set()
export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn) }
function emit() { listeners.forEach((f) => f()) }

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (session.token) headers.Authorization = `Bearer ${session.token}`
  const res = await fetch(`/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  let data = null
  try { data = await res.json() } catch { /* empty */ }
  if (res.status === 401 && session.token) session.logout()
  if (!res.ok) throw new Error((data && (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))) || `Error ${res.status}`)
  return data
}

// --- router ---------------------------------------------------------------
export function navigate(to) {
  window.history.pushState({}, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
  window.scrollTo(0, 0)
}

export const rupee = (n) => `₹${Math.round(Number(n) || 0).toLocaleString('en-IN')}`
export const qtyLabel = (q, unit) => unit === 'kg'
  ? (q < 1 ? `${Math.round(q * 1000)} g` : `${q} kg`)
  : `${q} ${unit}${q > 1 ? 's' : ''}`

// --- push -----------------------------------------------------------------
function b64ToUint8(b64) {
  const pad = '='.repeat((4 - (b64.length % 4)) % 4)
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)))
}

export async function enablePush(vapidKey) {
  if (!vapidKey || !('serviceWorker' in navigator) || !('PushManager' in window) || !session.token) return 'unsupported'
  const perm = await Notification.requestPermission()
  if (perm !== 'granted') return perm
  const reg = await navigator.serviceWorker.ready
  let sub = await reg.pushManager.getSubscription()
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(vapidKey) })
  await api('/push/subscribe', { method: 'POST', body: sub.toJSON() })
  return 'granted'
}
