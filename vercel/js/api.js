let API_BASE = window.location.origin;
let TG = window.Telegram?.WebApp;

function toast(msg) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

async function api(path, opts = {}) {
  const timeout = opts.timeout || 10000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetch(API_BASE + path, {
      headers: { 'Content-Type': 'application/json', ...opts.headers },
      ...opts,
      signal: controller.signal
    });
    clearTimeout(timer);
    return await res.json();
  } catch(e) {
    clearTimeout(timer);
    if (e.name === 'AbortError') return { ok: false, error: 'Timed out after 10s' };
    return { ok: false, error: 'Network error: ' + e.message };
  }
}

function setLoadingStatus(msg) {
  const el = document.getElementById('loadingStatus');
  if (el) el.textContent = msg;
}
