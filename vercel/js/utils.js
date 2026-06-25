function showModal(title, bodyHtml) {
  const titleEl = document.getElementById('modalTitle');
  const bodyEl = document.getElementById('modalBody');
  const overlay = document.getElementById('modalOverlay');
  if (titleEl) titleEl.textContent = title;
  if (bodyEl) bodyEl.innerHTML = bodyHtml;
  if (overlay) overlay.classList.add('open');
}

function closeModal() {
  const overlay = document.getElementById('modalOverlay');
  if (overlay) overlay.classList.remove('open');
}

function openLink(url) {
  if (url && url !== '#') {
    if (TG) { TG.openLink(url); }
    else { window.open(url, '_blank'); }
  }
}

function formatCurrency(amount) {
  return '₹' + (amount || 0).toFixed(2);
}

function copyToClipboard(text, msg) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => {
      toast(msg || '✅ Copied!');
    }).catch(() => {
      fallbackCopy(text, msg);
    });
  } else {
    fallbackCopy(text, msg);
  }
}

function fallbackCopy(text, msg) {
  const el = document.createElement('textarea');
  el.value = text;
  el.style.position = 'fixed';
  el.style.opacity = '0';
  document.body.appendChild(el);
  el.select();
  document.execCommand('copy');
  document.body.removeChild(el);
  toast(msg || '✅ Copied!');
}

function showError(msg, detail, buttons) {
  const screen = document.getElementById('loadingScreen');
  if (!screen) return;
  switchScreen('loadingScreen');
  let html = '<div style="text-align:center;padding:40px">' +
    '<div style="font-size:48px;margin-bottom:12px">❌</div>' +
    '<h3>' + msg + '</h3>';
  if (detail) html += '<p style="font-size:12px;color:var(--text-secondary);word-break:break-word;margin-top:8px">' + detail + '</p>';
  if (buttons && buttons.length) {
    html += '<div style="display:flex;flex-direction:column;gap:8px;margin-top:16px">';
    buttons.forEach(b => {
      html += '<button class="btn ' + (b.cls || 'btn-primary') + '" onclick="' + b.onclick + '">' + b.text + '</button>';
    });
    html += '</div>';
  } else {
    html += '<button class="btn btn-primary" style="margin-top:16px" onclick="location.reload()">Retry</button>';
  }
  html += '</div>';
  screen.innerHTML = html;
}

function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function getInitials(name) {
  if (!name) return 'U';
  return name.charAt(0).toUpperCase();
}

function getAvatarSvg(name) {
  const initial = getInitials(name);
  const colors = ['7b5ef8', '00e5a0', 'ffab00', 'ff4f5e', '1976d2', '388e3c', 'f57c00', 'c62828'];
  const colorIndex = initial.charCodeAt(0) % colors.length;
  return `data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"%3E%3Ccircle cx="50" cy="50" r="50" fill="%23${colors[colorIndex]}"/%3E%3Ctext x="50" y="68" text-anchor="middle" fill="%23fff" font-size="44" font-weight="700"%3E${initial}%3C/text%3E%3C/svg%3E`;
}
