import { useEffect, useState } from 'react'
import { api, navigate, rupee, session } from '../api'

export default function Orders({ requireLogin }) {
  const [list, setList] = useState(null)
  const load = () => api('/orders').then(setList).catch(() => setList([]))
  useEffect(() => { session.token ? load() : requireLogin('Login to see your orders', load) }, []) // eslint-disable-line

  if (!list) return <div className="loading">Loading…</div>
  if (!list.length) return <div className="empty"><p>No orders yet.</p><button className="btn primary" onClick={() => navigate('/')}>Order now</button></div>
  return (
    <div>
      <h2>My orders</h2>
      {list.map((o) => (
        <button key={o.code} className="order-row" onClick={() => navigate(`/track/${o.code}`)}>
          <span><b>{o.code}</b><br /><small className="muted">{new Date(o.created * 1000).toLocaleString('en-IN')} · {o.weight_kg} kg · {o.fulfilment}</small></span>
          <span className="right"><b>{rupee(o.total)}</b><br /><small className={`st st-${o.status}`}>{o.status_label}</small></span>
        </button>
      ))}
    </div>
  )
}
