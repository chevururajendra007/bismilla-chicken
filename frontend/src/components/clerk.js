// Loads Clerk's browser SDK straight from the shop's Clerk Frontend API – no build-time key needed,
// so the owner can switch Clerk apps by changing one Vercel env var.
let loading = null

export function loadClerk(publishableKey, frontendApi) {
  if (!publishableKey || !frontendApi) return Promise.resolve(null)
  if (window.Clerk?.loaded) return Promise.resolve(window.Clerk)
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const s = document.createElement('script')
      s.src = `https://${frontendApi}/npm/@clerk/clerk-js@5/dist/clerk.browser.js`
      s.async = true
      s.crossOrigin = 'anonymous'
      s.setAttribute('data-clerk-publishable-key', publishableKey)
      s.onload = async () => {
        try { await window.Clerk.load(); resolve(window.Clerk) } catch (e) { reject(e) }
      }
      s.onerror = () => reject(new Error('Could not load Clerk sign-in'))
      document.head.appendChild(s)
    })
  }
  return loading
}

export async function clerkSignOut() {
  try { if (window.Clerk?.user) await window.Clerk.signOut() } catch { /* ignore */ }
}
