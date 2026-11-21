import { useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'
import { api, navigate, qtyLabel, rupee, session } from '../api'
import MapView from '../components/MapView'

const FLOW_D = ['placed', 'accepted', 'preparing', 'out_for_delivery', 'delivered']
const FLOW_P = ['placed', 'accepted', 'preparing', 'ready', 'picked_up']
const NAMES = { placed: 'Placed', accepted: 'Accepted', preparing: 'Cutting', ready: 'Ready', out_for_delivery: 'On the way', delivered: 'Delivered', picked_up: 'Picked up' }

export default function Track({ code, cfg, requireLogin }) {
  const [o, setO] = useState(null)
  const [err, setErr] = useState('')
  const [utr, setUtr] = useState('')
  const [qr, setQr] = useState('')
  const timer = useRef(null)

  const load = () => api(`/orders/${code}`).then((x) => { setO(x); setErr('') }).catch((e) => setErr(e.message))

  useEffect(() => {
    if (!session.token) { requireLogin('Verify your mobile to see this order', load); return }
    load()
    timer.current = setInterval(load, 10000) // live tracking: poll every 10 s
    return () => clearInterval(timer.current)
  }, [code]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (o?.upi_link) QRCode.toDataURL(o.upi_link, { width: 220, margin: 1 }).then(setQr) }, [o?.upi_link])

  if (err) return <div className="empty"><p className="err">{err}</p><button className="btn" onClick={() => navigate('/orders')}>My orders</button></div>
  if (!o) return <div className="loading">Loading order…</div>

  const flow = o.fulfilment === 'delivery' ? FLOW_D : FLOW_P
  const idx = flow.indexOf(o.status)
  const done = ['delivered', 'picked_up', 'cancelled'].includes(o.status)
  const markers = [
    o.branch && { ...o.branch, kind: 'shop', label: o.branch.name },
    o.lat != null && { lat: o.lat, lng: o.lng, kind: 'home', label: 'You' },
    o.rider?.lat != null && { lat: o.rider.lat, lng: o.rider.lng, kind: 'rider', label: o.rider.name },
  ].filter(Boolean)

  async function submitUtr(e) {
    e.preventDefault()
    try { setO(await api(`/orders/${code}/utr`, { method: 'POST', body: { utr } })) } catch (x) { alert(x.message) }
  }
  async function cancel() {
    if (!confirm('Cancel this order?')) return
    try { setO(await api(`/orders/${code}/cancel`, { method: 'POST' })) } catch (x) { alert(x.message) }
  }

  return (
    <div className="track">
      <div className="track-head">
        <div><p className="kicker">Order {o.code}</p><h2>{o.status_label}</h2></div>
        {!done && o.live_eta_minutes != null && <div className="eta"><b>{o.live_eta_minutes}</b><small>min</small></div>}
      </div>

      {o.status === 'cancelled' ? <p className="banner warn">This order was cancelled.</p> : (
        <ol className="steps">{flow.map((s, i) => <li key={s} className={i <= idx ? 'done' : ''}><span>{i < idx ? '✓' : i + 1}</span>{NAMES[s]}</li>)}</ol>
      )}

      {o.fulfilment === 'delivery' && (
        <>
          <MapView googleKey={cfg?.google_maps_key} markers={markers} height={260} zoom={14} />
          <p className="muted small">
            {o.rider?.lat != null ? `🛵 ${o.rider.name} is ${o.rider_distance_km} km away · live` : `${o.distance_km} km from ${o.branch?.name}`}
          </p>
        </>
      )}
      {o.fulfilment === 'pickup' && o.branch && (
        <div className="panel"><b>Pickup at {o.branch.name}</b><p>{o.branch.address}</p>
          <a className="link" target="_blank" rel="noreferrer" href={`https://www.google.com/maps/dir/?api=1&destination=${o.branch.lat},${o.branch.lng}`}>Directions →</a></div>
      )}

      {o.awaiting_payment && <p className="banner warn">⏳ Prepaid order – please pay {rupee(o.total)} below. The shop starts cutting as soon as payment is received.</p>}
      {['prepaid', 'upi_delivery'].includes(o.payment_method) && o.payment_status !== 'paid' && o.status !== 'cancelled' && (
        <div className="panel pay">
          <h3>{o.payment_method === 'prepaid' ? `Pay ${rupee(o.total)} now` : `Pay ${rupee(o.total)} by PhonePe at delivery`}</h3>
          {o.payment_status === 'claimed' ? (
            <p className="ok">✅ We received your transaction ID ({o.utr}). The shop will confirm shortly.</p>
          ) : (
            <>
              {o.payment_method === 'upi_delivery' && <p className="muted small">You can pay now or when the chicken arrives – same QR.</p>}
              <div className="row">
                <a className="btn primary" href={o.phonepe_link}>Open PhonePe</a>
                <a className="btn ghost" href={o.upi_link}>Other UPI app</a>
              </div>
              {qr && <img className="qr" src={qr} alt="UPI QR" />}
              <p className="muted small">UPI ID: <b>{o.upi_id}</b> · Bismilla Chicken. On a computer? Scan the QR with your phone.</p>
              <form onSubmit={submitUtr} className="row">
                <input value={utr} onChange={(e) => setUtr(e.target.value)} placeholder="UPI transaction ID / UTR (12 digits)" />
                <button className="btn primary">I've paid</button>
              </form>
            </>
          )}
        </div>
      )}
      {o.payment_status === 'paid' && <p className="banner ok">✅ Payment received</p>}

      <div className="panel">
        {o.items.map((l) => <p key={l.product_id} className="cline2"><span>{l.name} × {qtyLabel(l.qty, l.unit)}</span><span>{rupee(l.amount)}</span></p>)}
        {o.delivery_fee > 0 && <p className="cline2"><span>Delivery</span><span>{rupee(o.delivery_fee)}</span></p>}
        <p className="cline2 grand"><span>Total · {o.payment_label}</span><span>{rupee(o.total)}</span></p>
        {o.address && <p className="muted small">📍 {o.address}</p>}
      </div>

      <div className="row">
        <a className="btn ghost" href={`tel:${o.branch?.phone || cfg?.shop_phone}`}>📞 Call shop</a>
        {o.status === 'placed' && <button className="btn ghost" onClick={cancel}>Cancel order</button>}
      </div>
    </div>
  )
}
