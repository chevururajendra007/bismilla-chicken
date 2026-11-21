import { useEffect, useMemo, useState } from 'react'
import { api, cart, navigate, qtyLabel, rupee } from '../api'
import MapView from '../components/MapView'

export default function Checkout({ cfg, menu, items, user, requireLogin }) {
  const [mode, setMode] = useState('delivery')
  const [pay, setPay] = useState('cod')
  const [branch, setBranch] = useState('kota')
  const [loc, setLoc] = useState(null)
  const [center, setCenter] = useState(null)
  const [quote, setQuote] = useState(null)
  const [address, setAddress] = useState('')
  const [name, setName] = useState(user?.name || '')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [locErr, setLocErr] = useState('')

  const products = useMemo(() => Object.fromEntries((menu?.products || []).map((p) => [p.id, p])), [menu])
  const lines = Object.entries(items).map(([id, qty]) => ({ p: products[id], qty })).filter((l) => l.p)
  const subtotal = lines.reduce((s, l) => s + Math.round(l.p.price * l.qty), 0)
  const weight = lines.reduce((s, l) => s + (l.p.unit === 'kg' ? l.qty : 0), 0)
  const fee = mode === 'delivery' && quote?.deliverable ? quote.fee : 0
  const saved = user?.addresses || []

  useEffect(() => {
    if (mode !== 'delivery' || !loc) return
    api('/delivery/quote', { method: 'POST', body: { lat: loc.lat, lng: loc.lng, weight_kg: weight } }).then(setQuote).catch(() => {})
  }, [loc?.lat, loc?.lng, weight, mode])

  function useMyLocation() {
    setLocErr('')
    if (!navigator.geolocation) return setLocErr('Location not supported on this device.')
    navigator.geolocation.getCurrentPosition(
      (p) => { const c = { lat: p.coords.latitude, lng: p.coords.longitude }; setLoc(c); setCenter(c) },
      () => setLocErr('Could not get location – allow location access or drag the pin on the map.'),
      { enableHighAccuracy: true, timeout: 10000 })
  }

  async function place() {
    setErr('')
    requireLogin('Login to place your order', async (u) => {
      setBusy(true)
      try {
        const o = await api('/orders', {
          method: 'POST', body: {
            items: lines.map((l) => ({ product_id: l.p.id, qty: l.qty })), fulfilment: mode, payment_method: pay,
            branch_id: mode === 'pickup' ? branch : quote?.branch_id, location: loc, address, name: name || u.name, notes,
          },
        })
        cart.clear()
        navigate(`/track/${o.code}`)
      } catch (e) { setErr(e.message) } finally { setBusy(false) }
    })
  }

  if (!menu) return <div className="loading">Loading…</div>
  if (!lines.length) return (
    <div className="empty"><p>🛒 Your cart is empty.</p><button className="btn primary" onClick={() => navigate('/')}>Browse today's chicken</button></div>
  )

  const canPlace = mode === 'pickup' || (loc && quote?.deliverable && address.trim().length >= 5)

  return (
    <div className="checkout">
      <h2>Your order</h2>
      <div className="panel">
        {lines.map(({ p, qty }) => (
          <div className="cline" key={p.id}>
            <span>{p.emoji} {p.name}<br /><small className="muted">{rupee(p.price)}/{p.unit}</small></span>
            <div className="stepper">
              <button onClick={() => cart.set(p.id, qty - (p.unit === 'kg' ? 0.5 : 1))}>−</button>
              <span>{qtyLabel(qty, p.unit)}</span>
              <button onClick={() => cart.set(p.id, qty + (p.unit === 'kg' ? 0.5 : 1))}>+</button>
            </div>
            <b>{rupee(p.price * qty)}</b>
          </div>
        ))}
      </div>

      <h3>How do you want it?</h3>
      <div className="seg">
        <button className={mode === 'delivery' ? 'on' : ''} onClick={() => setMode('delivery')}>🛵 Door delivery</button>
        <button className={mode === 'pickup' ? 'on' : ''} onClick={() => setMode('pickup')}>🏪 Pickup</button>
      </div>

      {mode === 'pickup' ? (
        <div className="panel">
          {(cfg?.branches || []).map((b) => (
            <label key={b.id} className="radio">
              <input type="radio" checked={branch === b.id} onChange={() => setBranch(b.id)} disabled={!b.open} />
              <span><b>{b.name}</b><br /><small className="muted">{b.address} · {b.hours}</small></span>
            </label>
          ))}
          <p className="muted small">Ready in about {cfg?.delivery?.prep_minutes || 15} minutes. We'll notify you.</p>
        </div>
      ) : (
        <div className="panel">
          {saved.length > 0 && (
            <div className="saved">{saved.map((a, i) => (
              <button key={i} className="chip" onClick={() => { setLoc({ lat: a.lat, lng: a.lng }); setCenter({ lat: a.lat, lng: a.lng }); setAddress(a.address) }}>🏠 {a.address.slice(0, 32)}</button>
            ))}</div>
          )}
          <button className="btn ghost block" onClick={useMyLocation}>📍 Use my current location</button>
          {locErr && <p className="err small">{locErr}</p>}
          <p className="muted small">Or tap / drag the pin to your house on the map.</p>
          <MapView googleKey={cfg?.google_maps_key} center={center || (cfg?.branches?.[0])}
            markers={(cfg?.branches || []).map((b) => ({ ...b, kind: 'shop', label: b.name }))}
            onPick={(lat, lng) => setLoc({ lat, lng })} height={280} zoom={14} />
          {quote && (
            <div className={`quote ${quote.deliverable ? 'ok' : 'no'}`}>
              <b>{quote.deliverable ? '✅' : '⚠️'} {quote.distance_km} km from {quote.branch_name}</b>
              <p>{quote.reason}</p>
              {quote.deliverable && <p>Estimated delivery: <b>~{quote.eta_minutes} min</b></p>}
              {!quote.deliverable && <button className="btn sm ghost" onClick={() => setMode('pickup')}>Switch to pickup</button>}
            </div>
          )}
          <label>House no, street, landmark</label>
          <textarea rows={2} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="e.g. 4-12, Gandhi street, near Ramalayam" />
        </div>
      )}

      <label>Name</label>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
      <label>Cutting instructions (optional)</label>
      <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Small pieces / biryani cut / keep liver" />

      <h3>Payment</h3>
      <div className="seg">
        {cfg?.accept_cod !== false && <button className={pay === 'cod' ? 'on' : ''} onClick={() => setPay('cod')}>💵 Cash {mode === 'pickup' ? 'at shop' : 'on delivery'}</button>}
        {cfg?.accept_phonepe !== false && <button className={pay === 'phonepe' ? 'on' : ''} onClick={() => setPay('phonepe')}>📱 PhonePe / UPI</button>}
      </div>

      <div className="panel totals">
        <p><span>Items ({weight} kg)</span><span>{rupee(subtotal)}</span></p>
        {mode === 'delivery' && <p><span>Delivery</span><span>{fee ? rupee(fee) : 'FREE'}</span></p>}
        <p className="grand"><span>Total</span><span>{rupee(subtotal + fee)}</span></p>
        <p className="muted small">Final price is by actual weight at today's rate (₹{menu.paper_rate}/kg paper rate).</p>
      </div>

      {err && <p className="err">{err}</p>}
      <button className="btn primary block big" disabled={busy || !canPlace} onClick={place}>
        {busy ? 'Placing order…' : `Place order · ${rupee(subtotal + fee)}`}
      </button>
      {!canPlace && mode === 'delivery' && <p className="muted small center">Pick your location and enter your address to continue.</p>}
    </div>
  )
}
