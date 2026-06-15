function loadAdmin() {
  const el = document.getElementById('adminSection');
  if (!el) return;
  el.innerHTML = `
    <h3 class="section-title" style="color:var(--primary)">🛠 Admin Panel</h3>
    <div class="admin-menu">
      <div class="admin-item animate-in fade stagger-1" onclick="adminPage('users')">
        <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        <div class="info"><h4>Users</h4><p>Manage users, bans, balance</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item animate-in fade stagger-2" onclick="adminPage('tasks')">
        <svg viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 14l2 2 4-4"/></svg>
        <div class="info"><h4>Tasks</h4><p>Add/edit tasks, manage proofs</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item animate-in fade stagger-3" onclick="adminPage('withdrawals')">
        <svg viewBox="0 0 24 24"><rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/></svg>
        <div class="info"><h4>Withdrawals</h4><p>Approve/reject withdrawals</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item animate-in fade stagger-4" onclick="adminPage('promoted')">
        <svg viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        <div class="info"><h4>Promoted</h4><p>Manage promoted tasks</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item animate-in fade stagger-5" onclick="adminPage('ads')">
        <svg viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/></svg>
        <div class="info"><h4>Ads</h4><p>Manage ad campaigns</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item animate-in fade stagger-6" onclick="adminPage('settings')">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        <div class="info"><h4>Settings</h4><p>Bot settings, payouts</p></div>
        <span class="arrow">›</span>
      </div>
    </div>
  `;
}

function adminPage(page) {
  showModal('Admin › ' + page.charAt(0).toUpperCase() + page.slice(1),
    '<div id="adminPageBody"><div class="loading-dots"><div></div><div></div><div></div></div></div>');
  setTimeout(() => {
    const body = document.getElementById('adminPageBody');
    if (body) body.innerHTML = '<div class="empty-state">Coming soon in update</div>';
  }, 500);
}
