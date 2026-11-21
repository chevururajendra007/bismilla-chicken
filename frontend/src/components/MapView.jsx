import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Google Maps when GOOGLE_MAPS_API_KEY is configured on the server; otherwise OpenStreetMap (Leaflet),
// so the app works on day one without billing set up.
// props: center {lat,lng}, markers [{lat,lng,label,kind:'shop'|'home'|'rider'}], onPick(lat,lng) -> pin is draggable
let gmapsPromise = null
function loadGoogle(key) {
  if (window.google?.maps) return Promise.resolve(window.google.maps)
  if (!gmapsPromise) {
    gmapsPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script')
      s.src = `https://maps.googleapis.com/maps/api/js?key=${key}&libraries=places`
      s.async = true
      s.onload = () => resolve(window.google.maps)
      s.onerror = reject
      document.head.appendChild(s)
    })
  }
  return gmapsPromise
}

const EMOJI = { shop: '🏪', home: '🏠', rider: '🛵', pick: '📍' }

export default function MapView({ googleKey, center, markers = [], onPick, height = 260, zoom = 15 }) {
  const el = useRef(null)
  const state = useRef({})

  // init once
  useEffect(() => {
    let cancelled = false
    const st = state.current
    const c = center || markers[0] || { lat: 14.0386, lng: 80.0467 }
    if (googleKey) {
      loadGoogle(googleKey).then((gm) => {
        if (cancelled) return
        st.kind = 'g'
        st.map = new gm.Map(el.current, { center: c, zoom, disableDefaultUI: true, zoomControl: true, gestureHandling: 'greedy' })
        st.markers = []
        if (onPick) {
          st.pin = new gm.Marker({ position: c, map: st.map, draggable: true, label: '📍', zIndex: 1000 })
          st.pin.addListener('dragend', (e) => onPick(e.latLng.lat(), e.latLng.lng()))
          st.map.addListener('click', (e) => { st.pin.setPosition(e.latLng); onPick(e.latLng.lat(), e.latLng.lng()) })
        }
        draw()
      }).catch(() => initLeaflet(c))
    } else initLeaflet(c)

    function initLeaflet(c0) {
      if (cancelled || st.map) return
      st.kind = 'l'
      st.map = L.map(el.current, { zoomControl: true, attributionControl: true }).setView([c0.lat, c0.lng], zoom)
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(st.map)
      st.layer = L.layerGroup().addTo(st.map)
      if (onPick) {
        st.pin = L.marker([c0.lat, c0.lng], { draggable: true, icon: icon('pick'), zIndexOffset: 1000 }).addTo(st.map)
        st.pin.on('dragend', () => { const p = st.pin.getLatLng(); onPick(p.lat, p.lng) })
        st.map.on('click', (e) => { st.pin.setLatLng(e.latlng); onPick(e.latlng.lat, e.latlng.lng) })
      }
      draw()
    }
    return () => { cancelled = true; if (st.kind === 'l' && st.map) st.map.remove(); state.current = {} }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [googleKey])

  function icon(kind) {
    return L.divIcon({ className: 'map-emoji', html: `<span>${EMOJI[kind] || '📍'}</span>`, iconSize: [34, 34], iconAnchor: [17, 30] })
  }

  function draw() {
    const st = state.current
    if (!st.map) return
    const pts = markers.filter((m) => m && m.lat != null && m.lng != null)
    if (st.kind === 'l') {
      st.layer.clearLayers()
      pts.forEach((m) => L.marker([m.lat, m.lng], { icon: icon(m.kind) }).bindTooltip(m.label || '').addTo(st.layer))
      if (pts.length >= 2 && !onPick) L.polyline(pts.map((m) => [m.lat, m.lng]), { color: '#B91C1C', dashArray: '6 6', weight: 3 }).addTo(st.layer)
      if (pts.length >= 2 && !onPick) st.map.fitBounds(L.latLngBounds(pts.map((m) => [m.lat, m.lng])).pad(0.3))
    } else if (st.kind === 'g') {
      const gm = window.google.maps
      ;(st.markers || []).forEach((m) => m.setMap(null))
      st.markers = pts.map((m) => new gm.Marker({ position: m, map: st.map, label: EMOJI[m.kind], title: m.label }))
      if (st.line) st.line.setMap(null)
      if (pts.length >= 2 && !onPick) {
        st.line = new gm.Polyline({ path: pts, map: st.map, strokeColor: '#B91C1C', strokeOpacity: 0.8, strokeWeight: 3 })
        if (!onPick) { const b = new gm.LatLngBounds(); pts.forEach((p) => b.extend(p)); st.map.fitBounds(b, 60) }
      }
    }
  }

  useEffect(draw, [JSON.stringify(markers)]) // eslint-disable-line react-hooks/exhaustive-deps

  // move pin when center changes from outside (e.g. "use my location")
  useEffect(() => {
    const st = state.current
    if (!st.map || !center || !onPick) return
    if (st.kind === 'l') { st.pin?.setLatLng([center.lat, center.lng]); st.map.setView([center.lat, center.lng], 16) }
    else { st.pin?.setPosition(center); st.map.setCenter(center); st.map.setZoom(16) }
  }, [center?.lat, center?.lng]) // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={el} className="map" style={{ height }} />
}
