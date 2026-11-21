import { useState } from 'react'
import { api, session } from '../api'

// Mobile OTP login. The shop owner's number (7904711708) is automatically recognised as ADMIN by the server.
export default function Login({ onDone, onClose, title = 'Login with mobile OTP' }) {
  const [phone, setPhone] = useState('')
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [step, setStep] = useState(1)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [devCode, setDevCode] = useState('')

  async function send(e) {
    e?.preventDefault(); setErr(''); setBusy(true)
    try {
      const r = await api('/auth/otp/request', { method: 'POST', body: { phone } })
      setStep(2); setDevCode(r.dev_code || '')
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  async function verify(e) {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      const r = await api('/auth/otp/verify', { method: 'POST', body: { phone, code, name } })
      session.save(r.token, r.user)
      onDone?.(r.user)
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="x" onClick={onClose} aria-label="Close">×</button>
        <h3>{title}</h3>
        {step === 1 ? (
          <form onSubmit={send}>
            <label>Mobile number</label>
            <div className="phone-in"><span>+91</span>
              <input inputMode="numeric" autoFocus maxLength={10} value={phone}
                onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))} placeholder="10-digit mobile" />
            </div>
            <label>Your name (optional)</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name for delivery" />
            <button className="btn primary block" disabled={busy || phone.length !== 10}>{busy ? 'Sending…' : 'Send OTP'}</button>
          </form>
        ) : (
          <form onSubmit={verify}>
            <p className="muted">OTP sent to +91 {phone} <button type="button" className="link" onClick={() => setStep(1)}>change</button></p>
            {devCode && <p className="dev">Demo mode – SMS not connected yet. Your OTP: <b>{devCode}</b></p>}
            <input className="otp" inputMode="numeric" autoComplete="one-time-code" autoFocus maxLength={6}
              value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} placeholder="• • • • • •" />
            <button className="btn primary block" disabled={busy || code.length !== 6}>{busy ? 'Verifying…' : 'Verify & continue'}</button>
            <button type="button" className="link" onClick={send}>Resend OTP</button>
          </form>
        )}
        {err && <p className="err">{err}</p>}
      </div>
    </div>
  )
}
