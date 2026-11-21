import { useEffect, useMemo, useState } from 'react'
import { api, cart, navigate, qtyLabel, rupee, session } from '../api'
import AddressPicker, { addressOk, emptyAddress } from '../components/AddressPicker'
import VerifyPhone from '../components/VerifyPhone'

const PAY = [
  { id: 'cod', flag: 'accept_cod', icon: '💵', title: (m) => (m === 'pickup' ? 'Cash at shop' : 'Cash on delivery'), sub: 'Pay cash when you get it' },
  { id: 'upi_delivery', flag: 'accept_upi_delivery', icon: '📱', title: (m) => (m === 'pickup' ? 'PhonePe at shop' : 'PhonePe / UPI at delivery'), sub: 'Scan & pay when you get it' },
  { id: 'prepaid', flag: 'accept_prepaid', icon: '✅', title: () => 'Pay now (prepaid)', sub: 'PhonePe / UPI now – we start cutting right away' },
]

export default function Checkout({ cfg, menu, items, user }) {
  const [mode, setMode] = useState('delivery')
  const [pay, setPay] = useState('cod')
  const [branch, setBranch] = useState('kota')
  const [loc, setLoc] = useState(null)
  const [quote, setQuote] = useState(null)
  const [addr, setAddr] = useState(emptyAddress)
  const [jump, setJump] = useState(null)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [changing, setChanging] = useState(false)

  const verified = user && user.phone && !changing
  const products = useMemo(() => Object.fromEntries((menu?.products || []).map((p) => [p.id, p])), [menu])
  const lines = Object.entries(items).map(([id, qty]) => ({ p: products[id], qty })).filter((l) => l.p)
  const subtotal = lines.reduce((s, l) => s + Math.round(l.p.price * l.qty), 0)
  const weight = lines.reduce((s, l) => s + (l.p.unit === 'kg' ? l.qty : 0), 0)
  const fee = mode === 'delivery' && quote?.deliverable ? quote.fee : 0
  const total = subtotal + fee
  const saved = user?.addresses || []
  const codCap = Number(cfg?.cod_max_amount || 0)
  const payOptions = PAY.filter((p) => cfg?.[p.flag] !== false)
  const mustPrepay = codCap > 0 && total > codCap

  useEffect(() => { if (mustPrepay && pay !== 'prepaid') setPay('prepaid') }, [mustPrepay]) // eslint-disable-line
  useEffect(() => { if (payOptions.length && !payOptions.find((p) => p.id === pay)) setPay(payOptions[0].id) }, [cfg]) // eslint-disable-line

  useEffect(() => {
    if (mode !== 'delivery' || !loc) return
    api('/delivery/quote', { method: 'POST', body: { lat: loc.lat, lng: loc.lng, weight_kg: weight } }).then(setQuote).catch(() => {})
  }, [loc?.lat, loc?.lng, weight, mode])

  async function place() {
    setErr(''); setBusy(true)
    try {
      const u = session.user
      const o = await api('/orders', {
        method: 'POST', body: {
          items: lines.map((l) => ({ product_id: l.p.id, qty: l.qty })), fulfilment: mode, payment_method: pay,
          branch_id: mode === 'pickup' ? branch : quote?.branch_id, location: loc,
          address_parts: mode === 'delivery' ? { door_no: addr.no_door ? '' : addr.door_no.trim(), street: addr.street.trim(), landmark: addr.landmark.trim(), town: addr.town.trim() } : null,
          name: u?.name, email: u?.email || null, notes,
        },
      })
      cart.clear()
      navigate(`/track/${o.code}`)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (!menu) return <div className="loading">Loading…</div>
  if (!lines.length) return (
    <div className="empty"><p>🛒 Your cart is empty.</p><button className="btn primary" onClick={() => navigate('/')}>Browse today's chicken</button></div>
  )

  const locationOk = mode === 'pickup' || (loc && quote?.deliverable && addressOk(addr))
  const canPlace = verified && locationOk

  return (
    <div className="checkout">
      <h2>Your order</h2>
      <div className="panel">
        {lines.map(({ p, qty }) => (
          <div className="cline" key={p.id}>
            <span className="cl-name">{p.image ? <img className="thumb" src={p.image} alt="" /> : p.emoji} <span>{p.name}<br /><small className="muted">{rupee(p.price)}/{p.unit}</small></span></span>
            <div className="stepper">
              <button onClick={() => cart.set(p.id, qty - (p.unit === 'kg' ? 0.5 : 1))}>−</button>
              <span>{qtyLabel(qty, p.unit)}</span>
              <button onClick={() => cart.set(p.id, qty + (p.unit === 'kg' ? 0.5 : 1))}>+</button>
            </div>
            <b>{rupee(p.price * qty)}</b>
          </div>
        ))}
      </div>

      <h3>1 · How do you want it?</h3>
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
          <p className="muted small">Ready in about {cfg?.delivery?.prep_minutes || 15} minutes.</p>
        </div>
      ) : (
        <div className="panel">
          {saved.length > 0 && (
            <div className="saved">{saved.map((a, i) => (
              <button key={i} className="chip" onClick={() => { setLoc({ lat: a.lat, lng: a.lng }); setJump({ lat: a.lat, lng: a.lng, t: Date.now() }); if (a.parts) setAddr({ ...emptyAddress, ...a.parts, no_door: !a.parts.door_no }) }}>🏠 {a.address.slice(0, 34)}</button>
            ))}</div>
          )}
          <AddressPicker cfg={cfg} value={addr} onChange={setAddr} loc={loc} onLoc={setLoc} jump={jump} />
          {quote && (
            <div className={`quote ${quote.deliverable ? 'ok' : 'no'}`}>
              <b>{quote.deliverable ? '✅' : '⚠️'} {quote.distance_km} km from {quote.branch_name}</b>
              <p>{quote.reason}</p>
              {quote.deliverable && <p>Estimated delivery: <b>~{quote.eta_minutes} min</b></p>}
              {!quote.deliverable && <button className="btn sm ghost" onClick={() => setMode('pickup')}>Switch to pickup</button>}
            </div>
          )}
        </div>
      )}
      <label>Cutting instructions (optional)</label>
      <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Small pieces / biryani cut / keep liver" />

      <h3>2 · Your details</h3>
      {verified ? (
        <div className="panel verified">
          <p>✅ <b>{user.name || 'Customer'}</b> · +91 {user.phone}{user.email ? ` · ${user.email}` : ''}</p>
          <button className="link small" onClick={() => setChanging(true)}>Not you? Use another number</button>
        </div>
      ) : (
        <VerifyPhone onVerified={() => setChanging(false)} />
      )}

      <h3>3 · Payment</h3>
      <div className="paylist">
        {payOptions.map((p) => {
          const disabled = mustPrepay && p.id !== 'prepaid'
          return (
            <label key={p.id} className={`payopt ${pay === p.id ? 'on' : ''} ${disabled ? 'off' : ''}`}>
              <input type="radio" name="pay" checked={pay === p.id} disabled={disabled} onChange={() => setPay(p.id)} />
              <span className="pi">{p.icon}</span>
              <span><b>{p.title(mode)}</b><br /><small className="muted">{p.sub}</small></span>
            </label>
          )
        })}
      </div>
      {mustPrepay && <p className="small warn-t">Orders above {rupee(codCap)} must be paid in advance.</p>}

      <div className="panel totals">
        <p><span>Items ({weight} kg)</span><span>{rupee(subtotal)}</span></p>
        {mode === 'delivery' && <p><span>Delivery</span><span>{fee ? rupee(fee) : 'FREE'}</span></p>}
        <p className="grand"><span>Total</span><span>{rupee(total)}</span></p>
        <p className="muted small">Today's paper rate: Live ₹{menu.rates?.live}/kg · Broiler ₹{menu.rates?.broiler}/kg. Final amount is by actual weight.</p>
      </div>

      {err && <p className="err">{err}</p>}
      <button className="btn primary block big" disabled={busy || !canPlace} onClick={place}>
        {busy ? 'Placing order…' : pay === 'prepaid' ? `Place order & pay ${rupee(total)}` : `Place order · ${rupee(total)}`}
      </button>
      {!verified && <p className="muted small center">Verify your mobile number above to place the order.</p>}
      {verified && !locationOk && mode === 'delivery' && <p className="muted small center">{!addressOk(addr) ? 'Enter your area and door number (or a landmark).' : 'Place the pin on your house to see delivery charges.'}</p>}
    </div>
  )
}
