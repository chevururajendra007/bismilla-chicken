import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import MapView from './MapView'

// Village-friendly address entry:
//  1. pick town  2. door no (or "no door number")  3. street / colony / area -> map jumps there automatically
//  4. landmark (required when there is no door number)  5. drag the pin onto the house to be exact
export default function AddressPicker({ cfg, value, onChange, loc, onLoc, jump }) {
  const branches = cfg?.branches || []
  const towns = ['Kota', 'Vidyanagar']
  const v = value
  const set = (k, val) => onChange({ ...v, [k]: val })
  const [center, setCenter] = useState(null)
  const [sugs, setSugs] = useState([])
  const [searching, setSearching] = useState(false)
  const [msg, setMsg] = useState('')
  const timer = useRef(null)
  const otherTown = v.town && !towns.includes(v.town)

  // center on the chosen town until we know better
  useEffect(() => {
    if (loc) return
    const b = branches.find((x) => x.name.toLowerCase().includes((v.town || 'kota').toLowerCase())) || branches[0]
    if (b) setCenter({ lat: b.lat, lng: b.lng })
  }, [v.town, branches.length]) // eslint-disable-line

  useEffect(() => { if (jump) setCenter({ lat: jump.lat, lng: jump.lng }) }, [jump])

  // search as they type the area (debounced)
  useEffect(() => {
    clearTimeout(timer.current)
    const q = (v.street || '').trim()
    if (q.length < 3) { setSugs([]); return }
    timer.current = setTimeout(async () => {
      setSearching(true); setMsg('')
      try {
        const r = await api(`/geocode?q=${encodeURIComponent(q)}&town=${encodeURIComponent(v.town || 'Kota')}`)
        setSugs(r.results || [])
        if (r.results?.length) pick(r.results[0], false)
        else setMsg(`Couldn't find "${q}" on the map – drag the pin to your house, the shop will call to confirm.`)
      } catch { setMsg('Map search is busy – please drag the pin to your house.') } finally { setSearching(false) }
    }, 700)
    return () => clearTimeout(timer.current)
  }, [v.street, v.town]) // eslint-disable-line

  function pick(s, close = true) {
    const c = { lat: s.lat, lng: s.lng }
    setCenter(c); onLoc(c)
    if (close) setSugs([])
  }

  function myLocation() {
    setMsg('')
    if (!navigator.geolocation) return setMsg('Location not supported on this phone.')
    navigator.geolocation.getCurrentPosition(async (p) => {
      const c = { lat: p.coords.latitude, lng: p.coords.longitude }
      setCenter(c); onLoc(c); setSugs([])
      try {
        const r = await api(`/geocode/reverse?lat=${c.lat}&lng=${c.lng}`)
        if (r.area && !v.street) onChange({ ...v, street: r.area })
        setMsg(r.label ? `📍 ${r.label}` : '')
      } catch { /* ignore */ }
    }, () => setMsg('Allow location access, or type your area below.'), { enableHighAccuracy: true, timeout: 10000 })
  }

  return (
    <div className="addr">
      <label>Town / village</label>
      <div className="chips-row">
        {towns.map((t) => <button key={t} type="button" className={`chip ${v.town === t ? 'on' : ''}`} onClick={() => set('town', t)}>{t}</button>)}
        <button type="button" className={`chip ${otherTown ? 'on' : ''}`} onClick={() => set('town', otherTown ? v.town : ' ')}>Other village</button>
      </div>
      {otherTown && <input value={v.town.trim()} onChange={(e) => set('town', e.target.value || ' ')} placeholder="Village name" />}

      <div className="addr-grid">
        <div>
          <label>Door / House no.</label>
          <input value={v.door_no} disabled={v.no_door} onChange={(e) => set('door_no', e.target.value)} placeholder="e.g. 4-12" inputMode="text" />
          <label className="check small"><input type="checkbox" checked={!!v.no_door} onChange={(e) => onChange({ ...v, no_door: e.target.checked, door_no: '' })} /> No door number</label>
        </div>
        <div className="sugg-wrap">
          <label>Street / colony / area *</label>
          <input value={v.street} onChange={(e) => set('street', e.target.value)} placeholder="e.g. Gandhi Nagar, NCR Nagar" autoComplete="off" />
          {searching && <span className="searching">🔎</span>}
          {sugs.length > 0 && (
            <ul className="suggs">
              {sugs.map((s, i) => <li key={i}><button type="button" onClick={() => pick(s)}>📍 {s.label}</button></li>)}
            </ul>
          )}
        </div>
      </div>

      <label>Landmark {v.no_door ? '*' : '(optional)'}</label>
      <input value={v.landmark} onChange={(e) => set('landmark', e.target.value)}
        placeholder={v.no_door ? 'Required – e.g. near Ramalayam / school / ration shop' : 'e.g. near Ramalayam'} />

      <button type="button" className="btn ghost block" onClick={myLocation}>📍 I'm at home – use my current location</button>
      {msg && <p className="small muted">{msg}</p>}

      <MapView googleKey={cfg?.google_maps_key} center={center}
        markers={branches.map((b) => ({ ...b, kind: 'shop', label: b.name }))}
        onPick={(lat, lng) => onLoc({ lat, lng })} height={280} zoom={15} />
      <p className="pin-hint">👆 Drag the 📍 pin onto your house roof for exact delivery</p>
    </div>
  )
}

export const emptyAddress = { town: 'Kota', door_no: '', no_door: false, street: '', landmark: '' }
export const addressOk = (a) => a.street.trim().length >= 3 && (a.door_no.trim() || a.landmark.trim().length >= 3)
