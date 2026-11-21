import { useState } from 'react'
import { cart, navigate, qtyLabel, rupee } from '../api'

const STEP = { kg: 0.5, tray: 1, piece: 1 }
const HERO_IMG = 'https://images.unsplash.com/photo-1672787153720-e85fe802fd9f?auto=format&fit=crop&w=900&q=70'

function Photo({ src, emoji, alt }) {
  const [bad, setBad] = useState(false)
  if (!src || bad) return <div className="ph-fallback"><span>{emoji || '🍗'}</span><small>Shop photo coming soon</small></div>
  return <img src={src} alt={alt} loading="lazy" onError={() => setBad(true)} />
}

function HeroImg() {
  const [bad, setBad] = useState(false)
  return bad ? <div className="hero-fallback">🍗</div> : <img src={HERO_IMG} alt="Fresh chicken" onError={() => setBad(true)} />
}

export default function Home({ menu, cfg, items }) {
  const [cat, setCat] = useState('All')
  if (!menu) return <div className="loading light">Loading today's rates…</div>
  const cats = ['All', ...new Set(menu.products.map((p) => p.category))]
  const list = menu.products.filter((p) => cat === 'All' || p.category === cat)
  const d = cfg?.delivery
  const phone = cfg?.shop_phone || '7904711708'
  const rates = menu.rates || { live: menu.paper_rate, broiler: menu.paper_rate }
  const date = new Date(menu.paper_rate_date + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })

  return (
    <>
      <section className="hero2">
        <div className="hero-copy">
          <span className="pill">📍 Kota (opp. Extra Mart) · Vidyanagar</span>
          <h1>Fresh chicken.<br /><span className="grad-text">Paper rate.</span><br />At your door.</h1>
          <p className="te hero-te">తాజా చికెన్ – రోజు పేపర్ రేటుకే, మీ ఇంటికే</p>

          <div className="rate-duo">
            <div className="rate-glass">
              <small>🐔 LIVE · లైవ్</small>
              <strong>{rupee(rates.live)}<em>/kg</em></strong>
            </div>
            <div className="rate-glass gold">
              <small>🥩 BROILER · స్కిన్‌లెస్</small>
              <strong>{rupee(rates.broiler)}<em>/kg</em></strong>
            </div>
          </div>
          <p className={`rate-note ${menu.rate_is_today ? 'ok' : 'stale'}`}>
            {menu.rate_is_today ? `● Today's Nellore paper rate · ${date}` : `● Last updated ${date}`}
          </p>

          <div className="hero-cta">
            <a href="#menu" className="btn shine big">🛒 Order now</a>
            <a href={`https://wa.me/91${phone}?text=${encodeURIComponent('Hi Bismilla Chicken, I want to order')}`} className="btn glass big" target="_blank" rel="noreferrer">WhatsApp</a>
          </div>
        </div>
        <div className="hero-art">
          <div className="halo" />
          <HeroImg />
          <div className="float-badge b1">🛵 FREE<br /><b>within {d?.free_radius_km ?? 3} km</b></div>
          <div className="float-badge b2">🔪 Cut fresh<br /><b>in front of you</b></div>
        </div>
      </section>

      <div className="marquee"><div>
        {Array(2).fill(0).map((_, i) => (
          <span key={i}>✦ FREE door delivery within {d?.free_radius_km ?? 3} km ✦ Up to {d?.max_radius_km ?? 5} km on {d?.min_kg_outer ?? 2} kg+ ✦ Cash on delivery ✦ PhonePe / UPI ✦ Daily paper rate ✦ Hygienic packing ✦ Pickup at 2 branches </span>
        ))}
      </div></div>

      {!menu.shop_open && <div className="banner warn">Shop is closed right now – you can browse, ordering opens soon.</div>}

      <section className="steps3">
        <div><b>1</b><span>Choose chicken<br /><small>కోడి / కట్ ఎంచుకోండి</small></span></div>
        <div><b>2</b><span>Verify mobile once<br /><small>ఒక్కసారి OTP</small></span></div>
        <div><b>3</b><span>Fresh at your door<br /><small>ఇంటికే డెలివరీ</small></span></div>
      </section>

      <section id="menu" className="menu-head">
        <h2>Today's fresh menu</h2>
        <div className="tabs glass-tabs">{cats.map((c) => <button key={c} className={c === cat ? 'on' : ''} onClick={() => setCat(c)}>{c}</button>)}</div>
      </section>

      <section className="grid">
        {list.map((p) => {
          const q = items[p.id] || 0
          const step = STEP[p.unit] || 1
          return (
            <article key={p.id} className={`card2 ${p.available ? '' : 'off'} ${q ? 'in' : ''}`}>
              <div className="card-img">
                <Photo src={p.image} emoji={p.emoji} alt={p.name} />
                {p.badge && <span className="badge">{p.badge}</span>}
                {p.pricing !== 'manual' && <span className="basis">{p.basis === 'live' ? 'Live rate' : 'Broiler rate'}</span>}
              </div>
              <div className="card-body">
                <h3>{p.name}</h3>
                <p className="te small">{p.name_te}</p>
                <p className="muted small desc">{p.desc}</p>
                <div className="price-row">
                  <b>{rupee(p.price)}<small>/{p.unit}</small></b>
                  {!p.available ? <span className="tag">Sold out</span> : q === 0 ? (
                    <button className="btn primary sm add" onClick={() => cart.set(p.id, 1)}>ADD +</button>
                  ) : (
                    <div className="stepper">
                      <button onClick={() => cart.set(p.id, q - step)}>−</button>
                      <span>{qtyLabel(q, p.unit)}</span>
                      <button onClick={() => cart.set(p.id, q + step)}>+</button>
                    </div>
                  )}
                </div>
                {q > 0 && <p className="line-total">{rupee(p.price * q)}</p>}
              </div>
            </article>
          )
        })}
      </section>

      <section className="trust">
        <div>🧼<b>Hygienic</b><small>Cleaned & packed fresh</small></div>
        <div>⚖️<b>Honest weight</b><small>Weighed in front of you</small></div>
        <div>📰<b>Paper rate</b><small>No hidden markup</small></div>
        <div>🔔<b>Live tracking</b><small>Know when it arrives</small></div>
      </section>

      <section className="owner2">
        <div className="owner-photo"><img src="/owner.jpg" alt="Owner of Bismilla Chicken" /></div>
        <div>
          <span className="pill">Meet the owner</span>
          <h2>Bismilla Chicken, Kota</h2>
          <p>Every bird is chosen live, weighed in front of you and cut fresh. Our prices follow the daily Nellore
            paper rate, so you always pay the fair price of the day.</p>
          <p className="te">మీ నమ్మకమే మా బలం. తాజా చికెన్ – నిజాయితీ ధర.</p>
          <div className="row wrap">
            <a className="btn shine" href={`tel:${phone}`}>📞 Call {phone}</a>
            <a className="btn glass" href={`https://wa.me/91${phone}`} target="_blank" rel="noreferrer">WhatsApp</a>
          </div>
        </div>
      </section>

      <section className="branches">
        {(cfg?.branches || []).map((b) => (
          <div key={b.id} className="branch2">
            <h3>🏪 {b.name}</h3>
            <p>{b.address}</p>
            <p className="small">{b.hours} · {b.open ? <span className="open">● Open</span> : <span className="closed">● Closed</span>}</p>
            <a className="link" target="_blank" rel="noreferrer" href={`https://www.google.com/maps/dir/?api=1&destination=${b.lat},${b.lng}`}>Get directions →</a>
          </div>
        ))}
      </section>

      {Object.keys(items).length > 0 && <div style={{ height: 70 }} />}
      <p className="center"><button className="link light" onClick={() => navigate('/orders')}>Track my orders</button></p>
    </>
  )
}
