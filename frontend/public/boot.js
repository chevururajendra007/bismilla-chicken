// Runs before the app. Kept as a file (not inline) so the Content-Security-Policy can forbid inline scripts.
(function () {
  // Owner dashboard installs as its own app ("BC Admin"); customers only ever get the shop app.
  if (location.pathname.indexOf('/admin') === 0) {
    var mf = document.getElementById('mf')
    if (mf) mf.href = '/manifest-admin.webmanifest'
    document.title = 'Bismilla Admin'
  }
  // Lite mode for budget phones: <=3 GB RAM, <=4 CPU cores, Data Saver on, or reduced motion requested.
  try {
    var n = navigator, c = n.connection || {}
    var lite = (n.deviceMemory && n.deviceMemory <= 3) || (n.hardwareConcurrency && n.hardwareConcurrency <= 4) ||
      c.saveData || /2g/.test(c.effectiveType || '') ||
      (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)
    if (lite || localStorage.getItem('bc_lite') === '1') document.documentElement.classList.add('lite')
  } catch (e) { /* ignore */ }
})()
