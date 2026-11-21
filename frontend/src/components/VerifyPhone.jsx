import { useState } from 'react'
import { api, session } from '../api'

// Customer details + one-time mobile OTP. No password, no account. Once verified, this phone stays verified.
// Used inline at checkout and as a modal to view orders on a new device.
export default function VerifyPhone({ onVerified, compact = false, askEmail = true, askName = true }) {
  const u = session.user
  const [name, setName] = useState(u?.name || '')
  const [phone, setPhone] = useState(u?.phone || '')
  const [email, setEmail] = useState(u?.email || '')
  const [code, setCode] = useState('')
  const [sent, setSent] = useState(false)
  const [devCode, setDevCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function send() {
    setErr(''); setBusy(true)
    try {
      const r = await api('/auth/otp/request', { method: 'POST', body: { phone } })
      setSent(true); setDevCode(r.dev_code || '')
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  async function verify() {
    setErr(''); setBusy(true)
    try {
      const r = await api('/auth/otp/verify', { method: 'POST', body: { phone, code, name: name || null, email: email || null } })
      session.save(r.token, r.user)
      onVerified?.(r.user)
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  return (
    <div className={compact ? '' : 'panel'}>
      {!compact && <h3>Your details</h3>}
      {askName && <><label>Name *</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoComplete="name" /></>}
      <label>Mobile number *</label>
      <div className="phone-in"><span>+91</span>
        <input inputMode="numeric" maxLength={10} value={phone} disabled={sent} autoComplete="tel-national"
          onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))} placeholder="10-digit mobile" />
      </div>
      {askEmail && <><label>Email (optional)</label>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Leave empty if you don't have one" autoComplete="email" /></>}

      {!sent ? (
        <button className="btn primary block" disabled={busy || phone.length !== 10 || (askName && name.trim().length < 2)} onClick={send}>
          {busy ? 'Sending…' : '📩 Send OTP to verify mobile'}
        </button>
      ) : (
        <div className="otp-box">
          <p className="small">Enter the 6-digit OTP sent to +91 {phone} · <button className="link" onClick={() => { setSent(false); setCode('') }}>change number</button></p>
          {devCode && <p className="dev">Demo mode – SMS not connected yet. OTP: <b>{devCode}</b></p>}
          <input className="otp" inputMode="numeric" autoComplete="one-time-code" maxLength={6} autoFocus
            value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} placeholder="• • • • • •" />
          <button className="btn primary block" disabled={busy || code.length !== 6} onClick={verify}>{busy ? 'Checking…' : '✅ Verify'}</button>
          <button className="link" onClick={send} disabled={busy}>Resend OTP</button>
        </div>
      )}
      {err && <p className="err small">{err}</p>}
      <p className="muted small">We verify your number once so the shop knows the order is genuine. No password needed.</p>
    </div>
  )
}
