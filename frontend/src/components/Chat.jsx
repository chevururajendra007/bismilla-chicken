import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

// Floating assistant – talks to /api/chat (agent.py: tools + local LLM + loop).
export default function Chat({ startOpen = false }) {
  const [open, setOpen] = useState(startOpen)
  const [msgs, setMsgs] = useState([{ role: 'assistant', content: 'Namaste 🙏 I can tell you today\'s rate, delivery charges, how much to buy, or your order status.' }])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef(null)
  useEffect(() => end.current?.scrollIntoView({ behavior: 'smooth' }), [msgs, open])

  async function send(q) {
    const message = (q ?? text).trim()
    if (!message || busy) return
    const history = msgs.slice(1)
    setMsgs((m) => [...m, { role: 'user', content: message }]); setText(''); setBusy(true)
    try {
      const r = await api('/chat', { method: 'POST', body: { message, history } })
      setMsgs((m) => [...m, { role: 'assistant', content: r.reply }])
    } catch (e) {
      setMsgs((m) => [...m, { role: 'assistant', content: 'Sorry, something went wrong. ' + e.message }])
    } finally { setBusy(false) }
  }

  if (!open) return <button className="chat-fab" onClick={() => setOpen(true)} aria-label="Chat">💬</button>
  return (
    <div className="chat">
      <div className="chat-h"><b>Bismilla Helper</b><button className="x" onClick={() => setOpen(false)}>×</button></div>
      <div className="chat-b">
        {msgs.map((m, i) => <div key={i} className={`bubble ${m.role}`}>{m.content}</div>)}
        {busy && <div className="bubble assistant">…</div>}
        <div ref={end} />
      </div>
      <div className="chips">
        {["Today's rate?", 'Delivery charges?', 'Chicken for 6 people biryani'].map((q) => <button key={q} onClick={() => send(q)}>{q}</button>)}
      </div>
      <form className="chat-f" onSubmit={(e) => { e.preventDefault(); send() }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask in Telugu or English…" />
        <button className="btn primary" disabled={busy}>Send</button>
      </form>
    </div>
  )
}
