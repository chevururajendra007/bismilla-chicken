import { useEffect, useRef, useState } from 'react'
import { api, navigate, qtyLabel, rupee } from '../api'
import MapView from '../components/MapView'

const NEXT = {
  placed: [['accepted', '✅ Accept'], ['cancelled', '✕ Reject']],
  accepted: [['preparing', '🔪 Start cutting']],
  preparing: [['ready', '📦 Ready / Send out']],
  ready: [['picked_up', '🤝 Picked up']],
  out_for_delivery: [['delivered', '🏁 Delivered']],
}

export default function Admin({ user, requireLogin, cfg, loadMenu, pushState, turnOnPush }) {
  const [tab, setTab] = useState('orders')
  useEffect(() => { if (!user) requireLogin('Admin login (mobile OTP)', () => {}) }, [user]) // eslint-disable-line
  if (!user) return <div className="empty"><p>Admin login required.</p></div>
  if (!['admin', 'staff'].includes(user.role)) return (
    <div className="empty"><p>This number ({user.phone}) is not an admin.</p><button className="btn" onClick={() => navigate('/')}>Home</button></div>
  )
  const isAdmin = user.role === 'admin'
  return (
    <div className="admin">
      <div className="tabs">
        {[['orders', '📋 Orders'], ...(isAdmin ? [['rates', '💹 Rates'], ['settings', '⚙️ Settings'], ['notify', '🔔 Notify']] : [])]
          .map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {pushState !== 'granted' && cfg?.vapid_public_key && (
        <div className="banner">🔔 Turn on notifications to hear about new orders instantly. <button className="btn sm primary" onClick={turnOnPush}>Turn on</button></div>
      )}
      {tab === 'orders' && <OrdersTab cfg={cfg} />}
      {tab === 'rates' && <RatesTab loadMenu={loadMenu} />}
      {tab === 'settings' && <SettingsTab cfg={cfg} />}
      {tab === 'notify' && <NotifyTab />}
    </div>
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
          <p className="small">{new Date(o.created * 1000).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })} · {o.name || 'Customer'} · <a href={`tel:${o.phone}`}>{o.phone}</a></p>
          <ul className="ao-items">{o.items.map((l) => <li key={l.product_id}>{l.name} — <b>{qtyLabel(l.qty, l.unit)}</b>{l.note && ` (${l.note})`}</li>)}</ul>
          {o.notes && <p className="small">📝 {o.notes}</p>}
          <p className="small">
            {o.fulfilment === 'delivery'
              ? <>🛵 {o.distance_km} km · {o.address} · <a target="_blank" rel="noreferrer" href={`https://www.google.com/maps/dir/?api=1&destination=${o.lat},${o.lng}`}>Navigate</a></>
              : <>🏪 Pickup at {o.branch?.name}</>}
          </p>
          <p className="small">
            <b>{rupee(o.total)}</b> · {o.payment_method === 'cod' ? 'Cash' : 'PhonePe'} ·
            <span className={o.payment_status === 'paid' ? 'ok' : o.payment_status === 'claimed' ? 'warn-t' : 'muted'}> {o.payment_status}{o.utr ? ` (UTR ${o.utr})` : ''}</span>
          </p>
          <div className="row wrap">
            {(NEXT[o.status] || []).map(([st, label]) => <button key={st} className={`btn sm ${st === 'cancelled' ? 'ghost' : 'primary'}`} onClick={() => act(o.code, st)}>{label}</button>)}
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

function RatesTab({ loadMenu }) {
  const [menu, setMenu] = useState(null)
  const [rate, setRate] = useState('')
  const [notify, setNotify] = useState(true)
  const [products, setProducts] = useState([])
  const [hist, setHist] = useState([])
  const [msg, setMsg] = useState('')
  const [mode, setMode] = useState('paper')

  const load = () => Promise.all([api('/menu'), api('/admin/rate/history'), api('/admin/settings')]).then(([m, h, s]) => {
    setMenu(m); setRate(m.paper_rate); setProducts(m.products); setHist(h); setMode(s.settings.rate_mode)
  })
  useEffect(() => { load() }, [])

  async function saveRate(e) {
    e.preventDefault(); setMsg('')
    try {
      const r = await api('/admin/rate', { method: 'POST', body: { paper_rate: Number(rate), notify } })
      setMsg(`✅ Rate updated to ₹${rate}/kg${notify ? ` · notified ${r.notified} customers` : ''}`); load(); loadMenu()
    } catch (x) { setMsg('❌ ' + x.message) }
  }
  async function saveMode(m) { setMode(m); await api('/admin/settings', { method: 'PUT', body: { rate_mode: m } }); load(); loadMenu() }
  async function saveProducts() {
    try { await api('/admin/products', { method: 'PUT', body: products.map(({ price, ...p }) => p) }); setMsg('✅ Products saved'); load(); loadMenu() }
    catch (x) { setMsg('❌ ' + x.message) }
  }
  const upd = (i, k, v) => setProducts((ps) => ps.map((p, j) => (j === i ? { ...p, [k]: v } : p)))
  const preview = (p) => (mode === 'manual' || p.pricing === 'manual') ? Number(p.manual_price) : Math.round(Number(rate) * Number(p.multiplier) + Number(p.offset))

  if (!menu) return <div className="loading">Loading…</div>
  return (
    <>
      <form className="panel rate-form" onSubmit={saveRate}>
        <h3>Today's paper rate (₹/kg, live broiler)</h3>
        <div className="row">
          <input type="number" step="0.5" value={rate} onChange={(e) => setRate(e.target.value)} className="big-in" />
          <button className="btn primary">Update rate</button>
        </div>
        <label className="check"><input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} /> Send push notification to customers</label>
        <p className="muted small">Last set: {menu.paper_rate_date} {menu.rate_is_today ? '(today)' : '⚠️ not updated today'}</p>
        {msg && <p>{msg}</p>}
      </form>

      <div className="panel">
        <h3>Pricing mode</h3>
        <div className="seg">
          <button className={mode === 'paper' ? 'on' : ''} onClick={() => saveMode('paper')}>📰 Auto from paper rate</button>
          <button className={mode === 'manual' ? 'on' : ''} onClick={() => saveMode('manual')}>✍️ Manual prices for all</button>
        </div>
        <p className="muted small">Auto: price = paper rate × multiplier + offset. Any product can still be set to Manual individually.</p>
      </div>

      <div className="panel">
        <h3>Products</h3>
        <div className="ptable">
          {products.map((p, i) => (
            <div key={p.id} className="prow">
              <div className="pname"><b>{p.emoji} {p.name}</b><span className="muted small">{p.id}</span></div>
              <label className="check"><input type="checkbox" checked={p.available} onChange={(e) => upd(i, 'available', e.target.checked)} /> In stock</label>
              <select value={p.pricing} onChange={(e) => upd(i, 'pricing', e.target.value)}>
                <option value="paper">Paper rate</option><option value="manual">Manual</option>
              </select>
              {p.pricing === 'paper' && mode === 'paper' ? (
                <>
                  <label>× <input type="number" step="0.05" value={p.multiplier} onChange={(e) => upd(i, 'multiplier', e.target.value)} /></label>
                  <label>+ ₹<input type="number" step="1" value={p.offset} onChange={(e) => upd(i, 'offset', e.target.value)} /></label>
                </>
              ) : (
                <label>₹<input type="number" step="1" value={p.manual_price} onChange={(e) => upd(i, 'manual_price', e.target.value)} />/{p.unit}</label>
              )}
              <b className="pprice">= {rupee(preview(p))}/{p.unit}</b>
            </div>
          ))}
        </div>
        <button className="btn primary" onClick={saveProducts}>Save products</button>
      </div>

      <div className="panel">
        <h3>Rate history</h3>
        {hist.length ? hist.map((h) => <p key={h.ts} className="cline2"><span>{h.date}</span><span>₹{h.rate}/kg</span></p>) : <p className="muted">No history yet.</p>}
      </div>
    </>
  )
}

function SettingsTab({ cfg }) {
  const [s, setS] = useState(null)
  const [branches, setBranches] = useState([])
  const [envAdmins, setEnvAdmins] = useState([])
  const [msg, setMsg] = useState('')
  const [pickFor, setPickFor] = useState(null)

  useEffect(() => { api('/admin/settings').then((r) => { setS(r.settings); setBranches(r.branches); setEnvAdmins(r.env_admins) }) }, [])
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
        <label className="check"><input type="checkbox" checked={s.accept_cod} onChange={(e) => setS({ ...s, accept_cod: e.target.checked })} /> Cash on delivery</label>
        <label className="check"><input type="checkbox" checked={s.accept_phonepe} onChange={(e) => setS({ ...s, accept_phonepe: e.target.checked })} /> PhonePe / UPI ({cfg?.upi_id})</label>
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
        <h3>Team (mobile OTP access)</h3>
        <p className="muted small">Permanent admins (server): {envAdmins.join(', ')}</p>
        <label>Extra admins (comma separated)</label>
        <input value={(s.admin_phones || []).join(', ')} onChange={(e) => setS({ ...s, admin_phones: phones(e.target.value) })} />
        <label>Staff / delivery boys (see & update orders, share location)</label>
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
