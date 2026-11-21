import { useState } from 'react'
import { cart, navigate, qtyLabel, rupee } from '../api'

const STEP = { kg: 0.5, tray: 1, piece: 1 }

export default function Home({ menu, cfg, items }) {
  const [cat, setCat] = useState('All')
  if (!menu) return <div className="loading">Loading today's rates…</div>
  const cats = ['All', ...new Set(menu.products.map((p) => p.category))]
  const list = menu.products.filter((p) => cat === 'All' || p.category === cat)
  const d = cfg?.delivery

  return (
    <>
      <section className="hero">
        <div>
          <p className="kicker">Kota · Vidyanagar</p>
          <h1>Fresh chicken,<br />cut in front of you.</h1>
          <p className="te">తాజా చికెన్ – రోజు పేపర్ రేటుకే</p>
          <div className="rate-card">
            <span>Today's paper rate</span>
            <strong>{rupee(menu.paper_rate)}<small>/kg</small></strong>
            <em className={menu.rate_is_today ? 'ok' : 'stale'}>{menu.rate_is_today ? `Updated ${menu.paper_rate_date}` : `Last updated ${menu.paper_rate_date}`}</em>
          </div>
        </div>
        <ul className="perks">
          <li>🛵 <b>Free delivery</b> within {d?.free_radius_km ?? 3} km</li>
          <li>📦 Up to {d?.max_radius_km ?? 5} km on {d?.min_kg_outer ?? 2} kg+ orders</li>
          <li>💵 Cash on delivery · 📱 PhonePe</li>
          <li>🏪 Or pick up at either branch</li>
        </ul>
      </section>

      {!menu.shop_open && <div className="banner warn">Shop is closed right now – you can browse, ordering opens soon.</div>}
      {menu.announcement && <p className="announce">📣 {menu.announcement}</p>}

      <div className="tabs">{cats.map((c) => <button key={c} className={c === cat ? 'on' : ''} onClick={() => setCat(c)}>{c}</button>)}</div>

      <section className="grid">
        {list.map((p) => {
          const q = items[p.id] || 0
          const step = STEP[p.unit] || 1
          return (
            <article key={p.id} className={`card ${p.available ? '' : 'off'}`}>
              <div className="emoji">{p.emoji}</div>
              <h3>{p.name}</h3>
              <p className="te small">{p.name_te}</p>
              <p className="muted small">{p.desc}</p>
              <div className="price-row">
                <b>{rupee(p.price)}<small>/{p.unit}</small></b>
                {!p.available ? <span className="tag">Sold out</span> : q === 0 ? (
                  <button className="btn primary sm" onClick={() => cart.set(p.id, p.unit === 'kg' ? 1 : 1)}>ADD</button>
                ) : (
                  <div className="stepper">
                    <button onClick={() => cart.set(p.id, q - step)}>−</button>
                    <span>{qtyLabel(q, p.unit)}</span>
                    <button onClick={() => cart.set(p.id, q + step)}>+</button>
                  </div>
                )}
              </div>
              {q > 0 && <p className="line-total">{rupee(p.price * q)}</p>}
            </article>
          )
        })}
      </section>

      <section className="owner">
        <img src="/owner.jpg" alt="Owner of Bismilla Chicken" />
        <div>
          <p className="kicker">Meet the owner</p>
          <h2>Bismilla Chicken, Kota</h2>
          <p>Every bird is chosen live, weighed in front of you and cut fresh – the same way we have served Kota for years.
            Prices follow the daily newspaper rate, so you always pay the fair price of the day.</p>
          <p className="te">మీ నమ్మకమే మా బలం. తాజా చికెన్ – నిజాయితీ ధర.</p>
          <div className="row">
            <a className="btn primary" href={`tel:${cfg?.shop_phone || '7904711708'}`}>📞 Call {cfg?.shop_phone || '7904711708'}</a>
            <a className="btn ghost" href={`https://wa.me/91${cfg?.shop_phone || '7904711708'}`} target="_blank" rel="noreferrer">WhatsApp</a>
          </div>
        </div>
      </section>

      <section className="branches">
        {(cfg?.branches || []).map((b) => (
          <div key={b.id} className="branch">
            <h3>🏪 {b.name}</h3>
            <p>{b.address}</p>
            <p className="muted small">{b.hours} · {b.open ? <span className="ok">Open</span> : <span className="err">Closed</span>}</p>
            <a className="link" target="_blank" rel="noreferrer" href={`https://www.google.com/maps/dir/?api=1&destination=${b.lat},${b.lng}`}>Directions →</a>
          </div>
        ))}
      </section>

      {Object.keys(items).length > 0 && <div style={{ height: 70 }} />}
      <p className="center"><button className="link" onClick={() => navigate('/orders')}>Track my orders</button></p>
    </>
  )
}
