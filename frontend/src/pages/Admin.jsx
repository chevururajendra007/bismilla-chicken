import { useEffect, useRef, useState } from 'react'
import { api, navigate, qtyLabel, rupee, session } from '../api'
import { clerkSignOut, loadClerk } from '../components/clerk'
import MapView from '../components/MapView'
import VerifyPhone from '../components/VerifyPhone'

const NEXT = {
  placed: [['accepted', '✅ Accept'], ['cancelled', '✕ Reject']],
  accepted: [['preparing', '🔪 Start cutting']],
  preparing: [['ready', '📦 Ready / Send out']],
  ready: [['picked_up', '🤝 Picked up']],
  out_for_delivery: [['delivered', '🏁 Delivered']],
}

const STAFF = ['superadmin', 'admin', 'staff']

export default function Admin({ user, cfg, loadMenu, pushState, turnOnPush }) {
  const [tab, setTab] = useState('orders')
  const [billing, setBilling] = useState(null)
  const isStaff = user && STAFF.includes(user.role)
  const isAdmin = user && ['superadmin', 'admin'].includes(user.role)
  useEffect(() => { if (isAdmin) api('/admin/settings').then((r) => setBilling(r.billing)).catch(() => {}) }, [isAdmin])

  if (!isStaff) return <AdminLogin cfg={cfg} user={user} />
  const tabs = [['orders', '📋 Orders'], ...(isAdmin ? [['history', '📊 History'], ['rates', '💹 Rates'], ['settings', '⚙️ Settings'], ['notify', '🔔 Notify']] : []),
    ...(user.role === 'superadmin' ? [['platform', '🛠 Platform']] : [])]
  return (
    <div className="admin">
      <div className="admin-who">
        <span>👤 {user.name || user.email || user.phone} · <b>{user.role}</b></span>
        <button className="link small" onClick={async () => { await clerkSignOut(); session.logout(); navigate('/') }}>Sign out</button>
      </div>
      {billing && ['due_soon', 'overdue'].includes(billing.state) && (
        <div className={`banner ${billing.state === 'overdue' ? 'warn' : ''}`}>
          🧾 App maintenance {billing.state === 'overdue' ? `overdue since ${billing.paid_until}` : `due on ${billing.paid_until}`} · ₹{billing.monthly_fee}/month.
          Contact {billing.provider}{billing.provider_phone ? ` (${billing.provider_phone})` : ''}.
        </div>
      )}
      <div className="tabs">
        {tabs.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {pushState !== 'granted' && cfg?.vapid_public_key && (
        <div className="banner">🔔 Turn on notifications to hear about new orders instantly. <button className="btn sm primary" onClick={turnOnPush}>Turn on</button></div>
      )}
      {tab === 'orders' && <OrdersTab cfg={cfg} />}
      {tab === 'rates' && <RatesTab loadMenu={loadMenu} />}
      {tab === 'settings' && <SettingsTab cfg={cfg} />}
      {tab === 'notify' && <NotifyTab />}
      {tab === 'history' && <HistoryTab />}
      {tab === 'platform' && <PlatformTab />}
    </div>
  )
}

// Owner signs in with Clerk (Google / email) once; the app then keeps this phone logged in.
function AdminLogin({ cfg, user }) {
  const el = useRef(null)
  const [state, setState] = useState('loading')
  const [err, setErr] = useState('')
  const [otp, setOtp] = useState(false)
  const hasClerk = !!(cfg?.clerk_publishable_key && cfg?.clerk_frontend_api)

  useEffect(() => {
    if (!cfg) return
    if (!hasClerk) { setState('noclerk'); return }
    let alive = true
    loadClerk(cfg.clerk_publishable_key, cfg.clerk_frontend_api).then(async (clerk) => {
      if (!alive || !clerk) return
      const exchange = async () => {
        try {
          setState('checking')
          const token = await clerk.session.getToken()
          const r = await api('/auth/clerk', { method: 'POST', body: { token } })
          session.save(r.token, r.user)
        } catch (e) { setErr(e.message); setState('denied') }
      }
      if (clerk.user) return exchange()
      setState('signin')
      clerk.mountSignIn(el.current, { forceRedirectUrl: '/admin', signUpForceRedirectUrl: '/admin' })
      clerk.addListener(({ user: u }) => { if (u && alive) exchange() })
    }).catch((e) => { setErr(e.message); setState('noclerk') })
    return () => { alive = false; try { window.Clerk?.unmountSignIn(el.current) } catch { /* ignore */ } }
  }, [cfg]) // eslint-disable-line

  return (
    <div className="admin-login">
      <h2>Shop admin</h2>
      {user && !STAFF.includes(user.role) && <p className="muted small">You're verified as a customer ({user.phone}). Sign in with the shop account below.</p>}
      {hasClerk && <>
        <p className="muted">Sign in once with the shop's Google / email account – this phone stays signed in.</p>
        {state === 'checking' && <p>Checking access…</p>}
        {state === 'denied' && <div className="banner warn">{err} <button className="btn sm" onClick={async () => { await clerkSignOut(); window.location.reload() }}>Use another account</button></div>}
        <div ref={el} className="clerk-box" />
      </>}
      {!hasClerk && state !== 'loading' && <p className="muted small">Google / email sign-in (Clerk) is not set up yet{err ? ` (${err})` : ''}.</p>}
      {cfg?.admin_otp_login && (
        <div className="panel">
          {!otp && <button className="btn ghost block" onClick={() => setOtp(true)}>📱 {hasClerk ? 'Staff / delivery boy?' : 'Owner & staff'} – sign in with mobile OTP</button>}
          {otp && <VerifyPhone compact askEmail={false} askName={false} onVerified={(u) => { if (!STAFF.includes(u.role)) setErr(`${u.phone} is not on the shop team.`) }} />}
          {otp && err && !hasClerk && <p className="err small">{err}</p>}
          <p className="muted small">One-time login. You stay signed in on this phone.</p>
        </div>
      )}
    </div>
  )
}

function HistoryTab() {
  const today = new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10)
  const monthStart = today.slice(0, 8) + '01'
  const [from, setFrom] = useState(monthStart)
  const [to, setTo] = useState(today)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [data, setData] = useState(null)
  const [audit, setAudit] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    setBusy(true)
    try { setData(await api(`/admin/history?date_from=${from}&date_to=${to}&q=${encodeURIComponent(q)}&status=${status}`)) } finally { setBusy(false) }
  }
  useEffect(() => { load() }, []) // eslint-disable-line

  function csv() {
    const head = ['Order', 'Date', 'Customer', 'Mobile', 'Email', 'Type', 'Kg', 'Subtotal', 'Delivery', 'Total', 'Payment', 'Pay status', 'UTR', 'Status', 'Paper rate', 'Address']
    const rows = data.orders.map((o) => [o.code, new Date(o.created * 1000).toLocaleString('en-IN'), o.name, o.phone, o.email || '', o.fulfilment,
      o.weight_kg, o.subtotal, o.delivery_fee, o.total, o.payment_label, o.payment_status, o.utr || '', o.status, o.paper_rate, o.address || ''])
    const text = [head, ...rows].map((r) => r.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob(['\ufeff' + text], { type: 'text/csv' }))
    a.download = `bismilla-orders-${from}-to-${to}.csv`
    a.click()
  }

  const s = data?.summary
  return (
    <>
      <div className="panel filters">
        <label>From<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label>To<input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <label>Search<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Mobile / name / order no" /></label>
        <label>Status<select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>{['placed', 'accepted', 'preparing', 'out_for_delivery', 'delivered', 'picked_up', 'cancelled'].map((x) => <option key={x}>{x}</option>)}
        </select></label>
        <div className="row"><button className="btn primary" onClick={load} disabled={busy}>{busy ? 'Loading…' : 'Show'}</button>
          {data?.orders?.length > 0 && <button className="btn ghost" onClick={csv}>⬇ Excel (CSV)</button>}</div>
      </div>
      {s && <div className="stats">
        <div><b>{s.orders}</b><small>orders</small></div>
        <div><b>{s.kg}</b><small>kg sold</small></div>
        <div><b>{rupee(s.revenue)}</b><small>sales</small></div>
        <div><b>{rupee(s.collected)}</b><small>collected · {rupee(s.pending_payments)} pending</small></div>
      </div>}
      {s && Object.keys(s.by_payment).length > 0 && <p className="small muted">{Object.entries(s.by_payment).map(([k, v]) => `${k}: ${rupee(v)}`).join(' · ')} · {s.customers} customers · {s.cancelled} cancelled</p>}
      {data && (
        <div className="table-wrap">
          <table className="htable">
            <thead><tr><th>Order</th><th>Date</th><th>Customer</th><th>Kg</th><th>Total</th><th>Payment</th><th>Status</th></tr></thead>
            <tbody>
              {data.orders.map((o) => (
                <tr key={o.code}>
                  <td>{o.code}</td>
                  <td>{new Date(o.created * 1000).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                  <td>{o.name}<br /><a href={`tel:${o.phone}`}>{o.phone}</a></td>
                  <td>{o.weight_kg}</td>
                  <td>{rupee(o.total)}</td>
                  <td>{o.payment_label}<br /><small className={o.payment_status === 'paid' ? 'ok' : 'warn-t'}>{o.payment_status}{o.utr ? ` · ${o.utr}` : ''}</small></td>
                  <td><span className={`st st-${o.status}`}>{o.status_label}</span></td>
                </tr>
              ))}
              {!data.orders.length && <tr><td colSpan={7} className="center muted">No orders in this period.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {data?.top_customers?.length > 0 && (
        <div className="panel">
          <h3>Top customers</h3>
          {data.top_customers.map((c) => <p key={c.phone} className="cline2"><span>{c.name} · <a href={`tel:${c.phone}`}>{c.phone}</a></span><span>{c.orders} orders · {c.kg} kg · <b>{rupee(c.total)}</b></span></p>)}
        </div>
      )}
      <div className="panel">
        <h3>Activity log</h3>
        {!audit ? <button className="btn sm ghost" onClick={() => api('/admin/audit').then(setAudit)}>Show who changed what</button>
          : audit.map((a, i) => <p key={i} className="small cline2"><span>{new Date(a.ts * 1000).toLocaleString('en-IN')} · {a.actor}</span><span>{a.action} {a.detail?.to ? `→ ₹${a.detail.to}` : a.detail?.code || ''}</span></p>)}
      </div>
    </>
  )
}

// Only for the platform provider (you): health, usage and the monthly maintenance plan.
function PlatformTab() {
  const [p, setP] = useState(null)
  const [sub, setSub] = useState(null)
  const [msg, setMsg] = useState('')
  const load = () => api('/platform').then((r) => { setP(r); setSub(r.billing) })
  useEffect(() => { load() }, [])
  if (!p) return <div className="loading">Loading…</div>
  async function save() {
    try {
      const { plan, monthly_fee, paid_until, provider, provider_phone, notes } = sub
      await api('/platform/subscription', { method: 'PUT', body: { plan, monthly_fee: Number(monthly_fee), paid_until: paid_until || null, provider, provider_phone, notes } })
      setMsg('✅ Saved'); load()
    } catch (e) { setMsg('❌ ' + e.message) }
  }
  const extend = (months) => {
    const base = sub.paid_until && sub.paid_until > new Date().toISOString().slice(0, 10) ? new Date(sub.paid_until) : new Date()
    base.setMonth(base.getMonth() + months)
    setSub({ ...sub, paid_until: base.toISOString().slice(0, 10) })
  }
  const u = p.usage
  return (
    <>
      <div className="panel">
        <h3>System health · v{p.version}</h3>
        <ul className="health">
          <li className={p.storage === 'postgres' ? 'ok' : 'warn-t'}>Database: {p.storage}</li>
          <li className={p.clerk ? 'ok' : 'warn-t'}>Admin sign-in (Clerk): {p.clerk ? 'on' : 'not set'}</li>
          <li className={p.sms ? 'ok' : 'warn-t'}>SMS OTP: {p.sms || 'not set'}{p.otp_dev_mode ? ' · demo OTP on screen' : ''}</li>
          <li className={p.push ? 'ok' : 'warn-t'}>Push notifications: {p.push ? 'on' : 'off'}</li>
          <li className={p.llm.reachable ? 'ok' : 'muted'}>AI model: {p.llm.reachable ? p.llm.model : 'offline – rule answers'}</li>
        </ul>
      </div>
      <div className="stats">
        <div><b>{u.this_month.orders}</b><small>orders this month</small></div>
        <div><b>{rupee(u.this_month.revenue)}</b><small>sales this month</small></div>
        <div><b>{u.last_month.orders}</b><small>orders last month</small></div>
        <div><b>{rupee(u.last_month.revenue)}</b><small>sales last month</small></div>
      </div>
      <div className="panel">
        <h3>Maintenance plan <span className={`st st-${sub.state === 'active' ? 'delivered' : sub.state === 'overdue' ? 'placed' : 'ready'}`}>{sub.state}{sub.days_left != null ? ` · ${sub.days_left} days` : ''}</span></h3>
        <div className="grid2">
          <label>Plan<input value={sub.plan} onChange={(e) => setSub({ ...sub, plan: e.target.value })} /></label>
          <label>Monthly fee (₹)<input type="number" value={sub.monthly_fee} onChange={(e) => setSub({ ...sub, monthly_fee: e.target.value })} /></label>
          <label>Paid until<input type="date" value={sub.paid_until || ''} onChange={(e) => setSub({ ...sub, paid_until: e.target.value })} /></label>
          <label>Your phone (shown to owner)<input value={sub.provider_phone || ''} onChange={(e) => setSub({ ...sub, provider_phone: e.target.value })} /></label>
        </div>
        <label>Notes<input value={sub.notes || ''} onChange={(e) => setSub({ ...sub, notes: e.target.value })} placeholder="e.g. Paid ₹1,497 for Dec–Feb via PhonePe" /></label>
        <div className="row wrap">
          <button className="btn sm ghost" onClick={() => extend(1)}>+1 month</button>
          <button className="btn sm ghost" onClick={() => extend(3)}>+3 months</button>
          <button className="btn sm ghost" onClick={() => extend(12)}>+1 year</button>
          <button className="btn primary" onClick={save}>Save plan</button>
        </div>
        {msg && <p>{msg}</p>}
        <p className="muted small">The owner sees a reminder 5 days before the due date. Ordering never stops automatically.</p>
      </div>
      <div className="panel">
        <h3>Shop admins</h3>
        <p className="small">Emails: {p.admins.emails.join(', ') || '—'}</p>
        <p className="small">Phones: {p.admins.phones.join(', ') || '—'}</p>
      </div>
    </>
  )
}

function OrdersTab({ cfg }) {
  const [data, setData] = useState(null)
  const [active, setActive] = useState(true)
  const [sharing, setSharing] = useState(null) // order code being tracked
  const seen = useRef(new Set())
  const watch = useRef(null)

  const load = () => api(`/admin/orders?active=${active}`).then((d) => {
    const fresh = d.orders.filter((o) => o.status === 'placed' && !seen.current.has(o.code))
    if (seen.current.size && fresh.length) beep()
    d.orders.forEach((o) => seen.current.add(o.code))
    setData(d)
  }).catch(() => {})

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t) }, [active]) // eslint-disable-line
  useEffect(() => () => watch.current != null && navigator.geolocation.clearWatch(watch.current), [])

  async function act(code, status) {
    await api(`/admin/orders/${code}/status`, { method: 'POST', body: { status } })
    if (status === 'ready' && data.orders.find((o) => o.code === code)?.fulfilment === 'delivery') startSharing(code)
    if (['delivered', 'cancelled'].includes(status) && sharing === code) stopSharing()
    load()
  }
  async function paid(code, v) { await api(`/admin/orders/${code}/paid`, { method: 'POST', body: { paid: v } }); load() }

  function startSharing(code) {
    if (!navigator.geolocation) return alert('Location not available on this device')
    stopSharing()
    let last = 0
    watch.current = navigator.geolocation.watchPosition((p) => {
      if (Date.now() - last < 12000) return
      last = Date.now()
      api(`/admin/orders/${code}/location`, { method: 'POST', body: { lat: p.coords.latitude, lng: p.coords.longitude } }).catch(() => {})
    }, () => {}, { enableHighAccuracy: true })
    setSharing(code)
  }
  function stopSharing() { if (watch.current != null) navigator.geolocation.clearWatch(watch.current); watch.current = null; setSharing(null) }

  if (!data) return <div className="loading">Loading orders…</div>
  const s = data.stats
  return (
    <>
      <div className="stats">
        <div><b>{s.orders_today}</b><small>orders today</small></div>
        <div><b>{s.kg_today}</b><small>kg sold</small></div>
        <div><b>{rupee(s.revenue_today)}</b><small>revenue</small></div>
        <div><b>{rupee(s.pending_payments)}</b><small>to collect</small></div>
      </div>
      <div className="seg small">
        <button className={active ? 'on' : ''} onClick={() => setActive(true)}>Active</button>
        <button className={!active ? 'on' : ''} onClick={() => setActive(false)}>All</button>
      </div>
      {sharing && <div className="banner ok">🛵 Sharing your live location for {sharing}. <button className="btn sm" onClick={stopSharing}>Stop</button></div>}
      {!data.orders.length && <p className="empty">No {active ? 'active ' : ''}orders right now.</p>}
      {data.orders.map((o) => (
        <div key={o.code} className={`aorder st-${o.status}`}>
          <div className="ao-h">
            <b>{o.code}</b>
            <span className={`st st-${o.status}`}>{o.status_label}</span>
          </div>
          {o.awaiting_payment && <p className="small warn-t">⏳ Prepaid – waiting for payment. Don't start cutting yet.</p>}
          <p className="small">{new Date(o.created * 1000).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })} · {o.name || 'Customer'} · <a href={`tel:${o.phone}`}>{o.phone}</a></p>
          <ul className="ao-items">{o.items.map((l) => <li key={l.product_id}>{l.name} — <b>{qtyLabel(l.qty, l.unit)}</b>{l.note && ` (${l.note})`}</li>)}</ul>
          {o.notes && <p className="small">📝 {o.notes}</p>}
          <p className="small">
            {o.fulfilment === 'delivery'
              ? <>🛵 {o.distance_km} km · {o.address} · <a target="_blank" rel="noreferrer" href={`https://www.google.com/maps/dir/?api=1&destination=${o.lat},${o.lng}`}>Navigate</a></>
              : <>🏪 Pickup at {o.branch?.name}</>}
          </p>
          <p className="small">
            <b>{rupee(o.total)}</b> · {o.payment_label} ·
            <span className={o.payment_status === 'paid' ? 'ok' : o.payment_status === 'claimed' ? 'warn-t' : 'muted'}> {o.payment_status}{o.utr ? ` (UTR ${o.utr})` : ''}</span>
          </p>
          <div className="row wrap">
            {(NEXT[o.status] || []).map(([st, label]) => <button key={st} className={`btn sm ${st === 'cancelled' ? 'ghost' : 'primary'}`} disabled={o.awaiting_payment && st === 'accepted'} onClick={() => act(o.code, st).catch((e) => alert(e.message))}>{label}</button>)}
            {o.payment_status !== 'paid' && o.status !== 'cancelled' && <button className="btn sm ghost" onClick={() => paid(o.code, true)}>💰 Mark paid</button>}
            {o.status === 'out_for_delivery' && sharing !== o.code && <button className="btn sm ghost" onClick={() => startSharing(o.code)}>📡 Share my location</button>}
          </div>
        </div>
      ))}
      <p className="muted small">Auto-refreshes every 15 s · {cfg?.shop_name}</p>
    </>
  )
}

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    ;[0, 0.25, 0.5].forEach((t) => { const o = ctx.createOscillator(); o.frequency.value = 880; o.connect(ctx.destination); o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.15) })
  } catch { /* no audio */ }
}

// Resize a phone photo to <= 800px JPEG before upload (keeps the database small and pages fast on 3G).
function resizePhoto(file) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const k = Math.min(1, 800 / Math.max(img.width, img.height))
      const c = document.createElement('canvas')
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k)
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height)
      resolve(c.toDataURL('image/jpeg', 0.8))
    }
    img.onerror = reject
    img.src = URL.createObjectURL(file)
  })
}

function RatesTab({ loadMenu }) {
  const [menu, setMenu] = useState(null)
  const [live, setLive] = useState('')
  const [broiler, setBroiler] = useState('')
  const [notify, setNotify] = useState(true)
  const [products, setProducts] = useState([])
  const [hist, setHist] = useState([])
  const [msg, setMsg] = useState('')
  const [mode, setMode] = useState('paper')
  const [uploading, setUploading] = useState('')

  const load = () => Promise.all([api('/menu'), api('/admin/rate/history'), api('/admin/settings')]).then(([m, h, s]) => {
    setMenu(m); setLive(m.rates.live); setBroiler(m.rates.broiler); setProducts(m.products); setHist(h); setMode(s.settings.rate_mode)
  })
  useEffect(() => { load() }, [])

  async function saveRate(e) {
    e.preventDefault(); setMsg('')
    try {
      const r = await api('/admin/rate', { method: 'POST', body: { live_rate: Number(live), broiler_rate: Number(broiler), notify } })
      setMsg(`✅ Rates updated – Live ₹${live} · Broiler ₹${broiler}${notify ? ` · notified ${r.notified} customers` : ''}`); load(); loadMenu()
    } catch (x) { setMsg('❌ ' + x.message) }
  }
  async function saveMode(m) { setMode(m); await api('/admin/settings', { method: 'PUT', body: { rate_mode: m } }); load(); loadMenu() }
  async function saveProducts() {
    try { await api('/admin/products', { method: 'PUT', body: products.map(({ price, ...p }) => p) }); setMsg('✅ Products saved'); load(); loadMenu() }
    catch (x) { setMsg('❌ ' + x.message) }
  }
  async function upload(pid, file) {
    if (!file) return
    setUploading(pid)
    try {
      const data_url = await resizePhoto(file)
      await api(`/admin/products/${pid}/image`, { method: 'POST', body: { data_url } })
      setMsg('✅ Photo updated'); await load(); loadMenu()
    } catch (x) { setMsg('❌ ' + x.message) } finally { setUploading('') }
  }
  const upd = (i, k, v) => setProducts((ps) => ps.map((p, j) => (j === i ? { ...p, [k]: v } : p)))
  const preview = (p) => {
    if (mode === 'manual' || p.pricing === 'manual') return Number(p.manual_price)
    const base = Number(p.basis === 'live' ? live : broiler)
    return Math.round(base * Number(p.multiplier) + Number(p.offset))
  }

  if (!menu) return <div className="loading">Loading…</div>
  return (
    <>
      <form className="panel rate-form" onSubmit={saveRate}>
        <h3>📰 Today's paper rates (Nellore)</h3>
        <p className="muted small">Type the two broiler rates printed in today's paper. All prices update instantly.</p>
        <div className="rate-inputs">
          <label className="rate-in live"><span>🐔 Live / లైవ్</span><div>₹<input type="number" step="1" value={live} onChange={(e) => setLive(e.target.value)} /></div><small>per kg live bird</small></label>
          <label className="rate-in broiler"><span>🥩 Broiler / స్కిన్‌లెస్</span><div>₹<input type="number" step="1" value={broiler} onChange={(e) => setBroiler(e.target.value)} /></div><small>per kg dressed chicken</small></label>
        </div>
        <label className="check"><input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} /> Send today's rate to customers' phones</label>
        <button className="btn primary block big">Update today's rates</button>
        <p className="muted small">Last set: {menu.paper_rate_date} {menu.rate_is_today ? '(today)' : '⚠️ not updated today'}</p>
        {msg && <p>{msg}</p>}
      </form>

      <div className="panel">
        <h3>Pricing mode</h3>
        <div className="seg">
          <button className={mode === 'paper' ? 'on' : ''} onClick={() => saveMode('paper')}>📰 Auto from paper rates</button>
          <button className={mode === 'manual' ? 'on' : ''} onClick={() => saveMode('manual')}>✍️ Manual prices for all</button>
        </div>
        <p className="muted small">Auto: price = linked rate × multiplier + offset. Example: With-skin = Broiler − ₹20. Any product can still be Manual.</p>
      </div>

      <div className="panel">
        <h3>Products & photos</h3>
        <div className="ptable">
          {products.map((p, i) => (
            <div key={p.id} className="prow2">
              <label className="pthumb" title="Change photo">
                {p.image ? <img src={p.image} alt="" /> : <span>{p.emoji}</span>}
                <em>{uploading === p.id ? '…' : '📷'}</em>
                <input type="file" accept="image/*" capture="environment" hidden onChange={(e) => upload(p.id, e.target.files?.[0])} />
              </label>
              <div className="pmain">
                <b>{p.name}</b>
                <div className="pcontrols">
                  <label className="check"><input type="checkbox" checked={p.available} onChange={(e) => upd(i, 'available', e.target.checked)} /> In stock</label>
                  <select value={p.pricing === 'manual' ? 'manual' : p.basis} onChange={(e) => {
                    const v = e.target.value
                    setProducts((ps) => ps.map((x, j) => (j === i ? { ...x, pricing: v === 'manual' ? 'manual' : 'paper', basis: v === 'manual' ? x.basis : v } : x)))
                  }}>
                    <option value="live">Live rate</option><option value="broiler">Broiler rate</option><option value="manual">Manual price</option>
                  </select>
                  {p.pricing !== 'manual' && mode === 'paper' ? (
                    <>
                      <label>× <input type="number" step="0.05" value={p.multiplier} onChange={(e) => upd(i, 'multiplier', e.target.value)} /></label>
                      <label>+₹ <input type="number" step="1" value={p.offset} onChange={(e) => upd(i, 'offset', e.target.value)} /></label>
                    </>
                  ) : (
                    <label>₹ <input type="number" step="1" value={p.manual_price} onChange={(e) => upd(i, 'manual_price', e.target.value)} /> /{p.unit}</label>
                  )}
                  <b className="pprice">= {rupee(preview(p))}/{p.unit}</b>
                </div>
              </div>
            </div>
          ))}
        </div>
        <p className="muted small">Tap a photo to take or choose a picture of your own chicken – real shop photos sell best.</p>
        <button className="btn primary" onClick={saveProducts}>Save products</button>
      </div>

      <div className="panel">
        <h3>Rate history</h3>
        {hist.length ? hist.map((h) => <p key={h.ts} className="cline2"><span>{h.date}</span><span>Live ₹{h.live}{h.broiler ? ` · Broiler ₹${h.broiler}` : ''}</span></p>) : <p className="muted">No history yet.</p>}
      </div>
    </>
  )
}

function SettingsTab({ cfg }) {
  const [s, setS] = useState(null)
  const [branches, setBranches] = useState([])
  const [envAdmins, setEnvAdmins] = useState([])
  const [envEmails, setEnvEmails] = useState([])
  const [msg, setMsg] = useState('')
  const [pickFor, setPickFor] = useState(null)

  useEffect(() => { api('/admin/settings').then((r) => { setS(r.settings); setBranches(r.branches); setEnvAdmins(r.env_admins); setEnvEmails(r.env_admin_emails || []) }) }, [])
  if (!s) return <div className="loading">Loading…</div>

  const d = s.delivery
  const setD = (k, v) => setS({ ...s, delivery: { ...d, [k]: v } })
  const setB = (i, k, v) => setBranches((bs) => bs.map((b, j) => (j === i ? { ...b, [k]: v } : b)))
  const phones = (v) => v.split(/[,\s]+/).filter(Boolean)

  async function save() {
    setMsg('')
    try {
      const r = await api('/admin/settings', { method: 'PUT', body: { ...s, branches } })
      setS(r.settings); setBranches(r.branches); setMsg('✅ Saved')
    } catch (x) { setMsg('❌ ' + x.message) }
  }

  return (
    <>
      <div className="panel">
        <h3>Shop</h3>
        <label className="check"><input type="checkbox" checked={s.shop_open} onChange={(e) => setS({ ...s, shop_open: e.target.checked })} /> Accepting orders (shop open)</label>
        <h3>Payments</h3>
        <label className="check"><input type="checkbox" checked={s.accept_cod} onChange={(e) => setS({ ...s, accept_cod: e.target.checked })} /> 💵 Cash on delivery / at shop</label>
        <label className="check"><input type="checkbox" checked={s.accept_upi_delivery} onChange={(e) => setS({ ...s, accept_upi_delivery: e.target.checked })} /> 📱 PhonePe / UPI at delivery</label>
        <label className="check"><input type="checkbox" checked={s.accept_prepaid} onChange={(e) => setS({ ...s, accept_prepaid: e.target.checked })} /> ✅ Prepaid – pay before cutting ({cfg?.upi_id})</label>
        <label>Orders above this amount must be prepaid (₹, 0 = no limit)<input type="number" value={s.cod_max_amount || 0} onChange={(e) => setS({ ...s, cod_max_amount: e.target.value })} /></label>
        <label>Announcement on home page</label>
        <input value={s.announcement} onChange={(e) => setS({ ...s, announcement: e.target.value })} />
      </div>

      <div className="panel">
        <h3>Delivery rules</h3>
        <div className="grid2">
          {[['free_radius_km', 'Free delivery radius (km)'], ['max_radius_km', 'Max delivery radius (km)'], ['min_kg_outer', 'Min kg beyond free radius'],
            ['fee_outer', 'Fee beyond free radius (₹)'], ['min_kg_inner', 'Min kg inside free radius'], ['prep_minutes', 'Prep time (min)'],
            ['speed_kmph', 'Rider speed (km/h)'], ['road_factor', 'Road distance factor']].map(([k, l]) => (
            <label key={k}>{l}<input type="number" step="0.1" value={d[k]} onChange={(e) => setD(k, e.target.value)} /></label>
          ))}
        </div>
      </div>

      <div className="panel">
        <h3>Branches</h3>
        <p className="muted small">⚠️ Set the exact shop location – delivery distance is measured from here.</p>
        {branches.map((b, i) => (
          <div key={b.id} className="branch-edit">
            <label>Name<input value={b.name} onChange={(e) => setB(i, 'name', e.target.value)} /></label>
            <label>Address<input value={b.address} onChange={(e) => setB(i, 'address', e.target.value)} /></label>
            <div className="grid2">
              <label>Hours<input value={b.hours} onChange={(e) => setB(i, 'hours', e.target.value)} /></label>
              <label>Phone<input value={b.phone} onChange={(e) => setB(i, 'phone', e.target.value)} /></label>
              <label>Latitude<input type="number" step="0.0001" value={b.lat} onChange={(e) => setB(i, 'lat', e.target.value)} /></label>
              <label>Longitude<input type="number" step="0.0001" value={b.lng} onChange={(e) => setB(i, 'lng', e.target.value)} /></label>
            </div>
            <label className="check"><input type="checkbox" checked={b.open} onChange={(e) => setB(i, 'open', e.target.checked)} /> Open</label>
            <div className="row">
              <button className="btn sm ghost" onClick={() => setPickFor(pickFor === i ? null : i)}>🗺 Pick on map</button>
              <button className="btn sm ghost" onClick={() => navigator.geolocation?.getCurrentPosition((p) => { setB(i, 'lat', +p.coords.latitude.toFixed(6)); setB(i, 'lng', +p.coords.longitude.toFixed(6)) })}>📍 I'm at this shop now</button>
            </div>
            {pickFor === i && <MapView googleKey={cfg?.google_maps_key} center={{ lat: +b.lat, lng: +b.lng }} onPick={(la, ln) => { setB(i, 'lat', +la.toFixed(6)); setB(i, 'lng', +ln.toFixed(6)) }} height={240} zoom={16} />}
          </div>
        ))}
      </div>

      <div className="panel">
        <h3>Team</h3>
        <p className="muted small">Permanent admins (server): {[...envAdmins, ...envEmails].join(', ')}</p>
        <label>Admin emails – sign in with Google / email (comma separated)</label>
        <input value={(s.admin_emails || []).join(', ')} onChange={(e) => setS({ ...s, admin_emails: phones(e.target.value) })} placeholder="owner@gmail.com" />
        <label>Staff emails</label>
        <input value={(s.staff_emails || []).join(', ')} onChange={(e) => setS({ ...s, staff_emails: phones(e.target.value) })} />
        <label>Admin mobiles (OTP login)</label>
        <input value={(s.admin_phones || []).join(', ')} onChange={(e) => setS({ ...s, admin_phones: phones(e.target.value) })} />
        <label>Delivery boys / staff mobiles (OTP login – see & update orders, share location)</label>
        <input value={(s.staff_phones || []).join(', ')} onChange={(e) => setS({ ...s, staff_phones: phones(e.target.value) })} />
      </div>

      <button className="btn primary block big" onClick={save}>Save settings</button>
      {msg && <p className="center">{msg}</p>}
    </>
  )
}

function NotifyTab() {
  const [title, setTitle] = useState('🐔 Fresh stock arrived!')
  const [body, setBody] = useState('Natu Kodi available today. Order now – free delivery within 3 km.')
  const [msg, setMsg] = useState('')
  async function send(e) {
    e.preventDefault()
    try { const r = await api('/admin/broadcast', { method: 'POST', body: { title, body } }); setMsg(`✅ Sent to ${r.sent} devices`) } catch (x) { setMsg('❌ ' + x.message) }
  }
  return (
    <form className="panel" onSubmit={send}>
      <h3>Send a notification to all customers</h3>
      <label>Title</label><input value={title} maxLength={60} onChange={(e) => setTitle(e.target.value)} />
      <label>Message</label><textarea rows={3} value={body} maxLength={160} onChange={(e) => setBody(e.target.value)} />
      <button className="btn primary">Send</button>
      {msg && <p>{msg}</p>}
      <p className="muted small">Only customers who allowed notifications receive this. Use it for rate drops, Sunday specials, festival offers.</p>
    </form>
  )
}
