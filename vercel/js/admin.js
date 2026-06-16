function loadAdmin() {
  const el = document.getElementById('adminSection');
  if (!el) return;
  el.innerHTML = `
    <h3 class="section-title" style="color:var(--primary);padding:0 16px 12px">🛠 Admin Panel</h3>
    <div class="admin-menu" id="adminMenu">
      <div class="admin-item" onclick="adminDashboard()">
        <svg viewBox="0 0 24 24"><path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 4-6"/></svg>
        <div class="info"><h4>Dashboard</h4><p>Analytics and stats overview</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item" onclick="adminUsers()">
        <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        <div class="info"><h4>Users</h4><p>Manage users, bans, balance</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item" onclick="adminTasks()">
        <svg viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 14l2 2 4-4"/></svg>
        <div class="info"><h4>Tasks</h4><p>Add/edit tasks, manage proofs</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item" onclick="adminWithdrawals()">
        <svg viewBox="0 0 24 24"><rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/></svg>
        <div class="info"><h4>Withdrawals</h4><p>Approve/reject withdrawals</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item" onclick="adminPromoted()">
        <svg viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        <div class="info"><h4>Promoted</h4><p>Manage promoted tasks</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item" onclick="adminAds()">
        <svg viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/></svg>
        <div class="info"><h4>Ads</h4><p>Manage ad campaigns</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item" onclick="adminSubmissions()">
        <svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
        <div class="info"><h4>Submissions</h4><p>Review user-submitted content</p></div>
        <span class="arrow">›</span>
      </div>
      <div class="admin-item" onclick="adminSettings()">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        <div class="info"><h4>Settings</h4><p>Bot settings, payouts</p></div>
        <span class="arrow">›</span>
      </div>
    </div>
  `;
}

function adminGoBack() {
  loadAdmin();
  closeModal();
}

function showAdminLoading() {
  return '<div class="loading-dots"><div></div><div></div><div></div></div>';
}

async function adminApi(path, method, body) {
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify({ ...body, user_id: TG_USER_ID });
    else if (method === 'GET') path += (path.includes('?') ? '&' : '?') + 'user_id=' + TG_USER_ID;
    const res = await fetch('/api/admin' + path, opts);
    return await res.json();
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

// ─── Dashboard ───────────────────────────────────────────────────────────

async function adminDashboard() {
  const el = document.getElementById('adminSection');
  el.innerHTML = '<div class="admin-dashboard"><div class="admin-back" onclick="adminGoBack()">← Back</div>' + showAdminLoading() + '</div>';
  const data = await adminApi('/dashboard', 'GET');
  if (!data.ok) { el.innerHTML = '<div class="admin-dashboard"><div class="admin-back" onclick="adminGoBack()">← Back</div><div class="empty-state">Failed to load</div></div>'; return; }
  el.innerHTML = `
    <div class="admin-dashboard">
      <div class="admin-back" onclick="adminGoBack()">← Back to Menu</div>
      <div class="admin-stats-grid">
        <div class="stat-card"><div class="stat-value">${data.total_users}</div><div class="stat-label">Total Users</div></div>
        <div class="stat-card"><div class="stat-value">${data.active_users_7d}</div><div class="stat-label">Active (7d)</div></div>
        <div class="stat-card"><div class="stat-value">${data.today_joins}</div><div class="stat-label">Today Joins</div></div>
        <div class="stat-card"><div class="stat-value">${data.banned}</div><div class="stat-label">Banned</div></div>
        <div class="stat-card"><div class="stat-value">${data.flagged}</div><div class="stat-label">Flagged</div></div>
        <div class="stat-card"><div class="stat-value">${data.pending_proofs}</div><div class="stat-label">Pending Proofs</div></div>
        <div class="stat-card"><div class="stat-value">${data.pending_withdrawals}</div><div class="stat-label">Pending Wds</div></div>
        <div class="stat-card"><div class="stat-value">₹${data.total_earnings.toFixed(1)}</div><div class="stat-label">Total Earnings</div></div>
        <div class="stat-card"><div class="stat-value">₹${data.total_withdrawn.toFixed(1)}</div><div class="stat-label">Total Withdrawn</div></div>
      </div>
    </div>
  `;
}

// ─── Users ────────────────────────────────────────────────────────────────

async function adminUsers() {
  const el = document.getElementById('adminSection');
  el.innerHTML = `
    <div style="padding:0 16px"><div class="admin-back" onclick="adminGoBack()">← Back to Menu</div></div>
    <div class="admin-search"><input id="userSearch" placeholder="Search by ID, name, or @username..." onkeydown="if(event.key==='Enter')adminSearchUsers()"><button class="btn btn-sm" onclick="adminSearchUsers()">Search</button></div>
    <div id="userList" class="admin-list">${showAdminLoading()}</div>
  `;
  adminSearchUsers();
}

async function adminSearchUsers() {
  const q = document.getElementById('userSearch')?.value || '';
  const list = document.getElementById('userList');
  if (!list) return;
  list.innerHTML = showAdminLoading();
  const data = await adminApi('/users/search?q=' + encodeURIComponent(q), 'GET');
  if (!data.ok) { list.innerHTML = '<div class="empty-state">Failed to load users</div>'; return; }
  if (!data.users.length) { list.innerHTML = '<div class="empty-state">No users found</div>'; return; }
  list.innerHTML = data.users.map(u => `
    <div class="admin-list-item" onclick="adminUserDetail(${u.id})">
      <div class="info">
        <div class="title">${u.name} ${u.banned ? '<span class="badge badge-danger">BANNED</span>' : ''} ${u.is_flagged ? '<span class="badge badge-pending">FLAGGED</span>' : ''}</div>
        <div class="subtitle">ID: ${u.id} ${u.username ? '@' + u.username : ''} · ₹${u.balance}</div>
      </div>
      <span class="arrow">›</span>
    </div>
  `).join('');
}

async function adminUserDetail(uid) {
  const el = document.getElementById('adminSection');
  el.innerHTML = '<div style="padding:0 16px"><div class="admin-back" onclick="adminUsers()">← Back to Users</div></div><div class="admin-detail">' + showAdminLoading() + '</div>';
  const data = await adminApi('/users/' + uid, 'GET');
  if (!data.ok) { el.innerHTML = '<div style="padding:16px"><div class="admin-back" onclick="adminUsers()">← Back</div><div class="empty-state">User not found</div></div>'; return; }
  const u = data.user;
  el.innerHTML = `
    <div style="padding:0 16px"><div class="admin-back" onclick="adminUsers()">← Back to Users</div></div>
    <div class="admin-detail">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
        <div style="width:48px;height:48px;border-radius:50%;background:var(--primary-gradient);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:20px">${u.name.charAt(0)}</div>
        <div><div style="font-weight:700;font-size:16px">${u.name}</div><div style="font-size:12px;color:var(--text-secondary)">ID: ${u.id} ${u.username ? '· @' + u.username : ''}</div></div>
      </div>
      <div class="detail-row"><span class="label">Balance</span><span class="value" style="color:var(--success)">₹${u.balance}</span></div>
      <div class="detail-row"><span class="label">Lifetime Earnings</span><span class="value" style="color:var(--primary)">₹${u.lifetime_earnings}</span></div>
      <div class="detail-row"><span class="label">Referral Earnings</span><span class="value">₹${u.referral_earnings}</span></div>
      <div class="detail-row"><span class="label">Completed Tasks</span><span class="value">${u.completed_tasks.length}</span></div>
      <div class="detail-row"><span class="label">Referrals</span><span class="value">${u.referrals}</span></div>
      <div class="detail-row"><span class="label">Warnings</span><span class="value" style="color:${u.warnings >= 3 ? 'var(--danger)' : 'inherit'}">${u.warnings}/3</span></div>
      <div class="detail-row"><span class="label">Joined</span><span class="value">${u.joined_at?.slice(0,10) || 'N/A'}</span></div>
      <div class="detail-row"><span class="label">Last Active</span><span class="value">${u.last_active?.slice(0,10) || 'N/A'}</span></div>
      <div class="detail-row"><span class="label">UPI</span><span class="value">${u.upi || 'N/A'}</span></div>
      <div class="detail-row"><span class="label">Phone</span><span class="value">${u.phone || 'N/A'}</span></div>
      <div class="detail-row"><span class="label">Fraud Score</span><span class="value" style="color:${u.fraud_score > 50 ? 'var(--danger)' : 'inherit'}">${u.fraud_score}</span></div>
      <div class="detail-row"><span class="label">Device Verified</span><span class="value">${u.device_verified ? '✅' : '❌'}</span></div>
      <div class="detail-row"><span class="label">Withdraw Locked</span><span class="value">${u.withdraw_locked ? '🔒 Yes' : '🔓 No'}</span></div>
      ${u.ban_reason ? `<div class="detail-row"><span class="label">Ban Reason</span><span class="value" style="color:var(--danger)">${u.ban_reason}</span></div>` : ''}
      <div class="admin-actions">
        ${u.banned
          ? `<button class="btn btn-sm btn-primary" onclick="adminAction('unban', ${u.id})">✅ Unban</button>`
          : `<button class="btn btn-sm btn-danger" onclick="adminAction('ban', ${u.id})">🚫 Ban</button>`}
        <button class="btn btn-sm btn-primary" onclick="adminAdjustBalance(${u.id})">💵 Balance</button>
        <button class="btn btn-sm btn-warning" onclick="adminAction('warn', ${u.id})">⚠️ Warn</button>
        <button class="btn btn-sm btn-ghost" onclick="adminAction('unwarn', ${u.id})">🩹 Remove Warn</button>
        ${u.withdraw_locked
          ? `<button class="btn btn-sm btn-success" onclick="adminAction('unlock', ${u.id})">🔓 Unlock</button>`
          : `<button class="btn btn-sm btn-danger" onclick="adminAction('lock', ${u.id})">🔒 Lock</button>`}
      </div>
    </div>
  `;
}

async function adminAction(action, uid) {
  if (action === 'ban' && !confirm('Ban user ' + uid + '?')) return;
  if (action === 'warn' && !confirm('Add warning to user ' + uid + '?')) return;
  const data = await adminApi('/users/' + uid + '/' + action, 'POST');
  if (data.ok) { toast('Action completed'); adminUserDetail(uid); }
  else { toast('Failed: ' + data.error); }
}

async function adminAdjustBalance(uid) {
  const amount = prompt('Enter amount (+ to add, - to deduct):', '0');
  if (amount === null) return;
  const reason = prompt('Reason:', '');
  const data = await adminApi('/users/' + uid + '/balance', 'POST', { amount: parseFloat(amount) || 0, reason });
  if (data.ok) { toast('Balance updated to ₹' + data.new_balance); adminUserDetail(uid); }
  else { toast('Failed: ' + data.error); }
}

// ─── Tasks ────────────────────────────────────────────────────────────────

async function adminTasks() {
  const el = document.getElementById('adminSection');
  el.innerHTML = '<div style="padding:0 16px"><div class="admin-back" onclick="adminGoBack()">← Back to Menu</div><button class="btn btn-primary btn-block" style="margin-bottom:12px" onclick="adminCreateTask()">➕ Add New Task</button></div><div id="adminTaskList" class="admin-list">' + showAdminLoading() + '</div>';
  const data = await adminApi('/tasks', 'GET');
  if (!data.ok) { document.getElementById('adminTaskList').innerHTML = '<div class="empty-state">Failed to load</div>'; return; }
  const list = document.getElementById('adminTaskList');
  if (!data.tasks.length) { list.innerHTML = '<div class="empty-state">No tasks yet</div>'; return; }
  list.innerHTML = data.tasks.map(t => `
    <div class="admin-list-item" onclick="adminEditTask(${t.id})">
      <div class="info">
        <div class="title">${t.description?.slice(0, 50) || 'Task'} ${t.is_active === false ? '<span class="badge badge-rejected">PAUSED</span>' : ''} <span class="badge badge-pending">${t.task_type}</span></div>
        <div class="subtitle">₹${t.reward} · ${t.completion_count} completions</div>
      </div>
      <span class="arrow">›</span>
    </div>
  `).join('');
}

function adminCreateTask() {
  showModal('Admin › Create Task', `
    <div class="admin-form">
      <div class="form-group"><label>Type</label><select id="f_task_type"><option value="manual">Manual</option><option value="channel">Channel</option></select></div>
      <div class="form-group"><label>Description</label><textarea id="f_description" placeholder="Task description"></textarea></div>
      <div class="form-group"><label>Guide</label><textarea id="f_guide" placeholder="How to complete this task"></textarea></div>
      <div class="form-group"><label>Reward (₹)</label><input id="f_reward" type="number" step="0.01" value="1"></div>
      <div class="form-group"><label>Image URL</label><input id="f_image" placeholder="https://..."></div>
      <div class="form-group"><label>Video URL</label><input id="f_video_url" placeholder="https://..."></div>
      <div class="form-group"><label>Color</label><input id="f_color" type="color" value="#7b5ef8"></div>
      <div class="form-group"><label>Duration Text</label><input id="f_duration" value="15 min"></div>
      <div class="form-group"><label>Offer URL</label><input id="f_offer_url" placeholder="https://..."></div>
      <div class="form-group"><label>Max Completers (0 = unlimited)</label><input id="f_max_completers" type="number" value="0"></div>
      <button class="btn btn-primary btn-block" onclick="adminSaveTask(0)">Create Task</button>
    </div>
  `);
}

async function adminEditTask(tid) {
  const data = await adminApi('/tasks', 'GET');
  const task = data.tasks?.find(t => t.id === tid);
  if (!task) { toast('Task not found'); return; }
  showModal('Admin › Edit Task', `
    <div class="admin-form">
      <div class="form-group"><label>Description</label><textarea id="f_description">${task.description || ''}</textarea></div>
      <div class="form-group"><label>Guide</label><textarea id="f_guide">${task.guide || ''}</textarea></div>
      <div class="form-group"><label>Reward (₹)</label><input id="f_reward" type="number" step="0.01" value="${task.reward}"></div>
      <div class="form-group"><label>Image URL</label><input id="f_image" value="${task.image || ''}"></div>
      <div class="form-group"><label>Video URL</label><input id="f_video_url" value="${task.video_url || ''}"></div>
      <div class="form-group"><label>Color</label><input id="f_color" type="color" value="${task.color || '#7b5ef8'}"></div>
      <div class="form-group"><label>Duration Text</label><input id="f_duration" value="${task.duration_text || '15 min'}"></div>
      <div class="form-group"><label>Offer URL</label><input id="f_offer_url" value="${task.offer_url || ''}"></div>
      <div class="form-group"><label>Max Completers</label><input id="f_max_completers" type="number" value="${task.max_completers || 0}"></div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" onclick="adminSaveTask(${tid})">Save</button>
        <button class="btn btn-warning" onclick="adminToggleTask(${tid})">${task.is_active ? '⏸️ Pause' : '▶️ Resume'}</button>
        <button class="btn btn-danger" onclick="adminDeleteTask(${tid})">🗑️ Delete</button>
      </div>
    </div>
  `);
}

async function adminSaveTask(tid) {
  const body = {
    task_type: document.getElementById('f_task_type')?.value || 'manual',
    description: document.getElementById('f_description')?.value || '',
    guide: document.getElementById('f_guide')?.value || '',
    reward: parseFloat(document.getElementById('f_reward')?.value || 0),
    image: document.getElementById('f_image')?.value || '',
    video_url: document.getElementById('f_video_url')?.value || '',
    color: document.getElementById('f_color')?.value || '#7b5ef8',
    duration_text: document.getElementById('f_duration')?.value || '15 min',
    offer_url: document.getElementById('f_offer_url')?.value || '',
    max_completers: parseInt(document.getElementById('f_max_completers')?.value || 0),
  };
  const data = tid
    ? await adminApi('/tasks/' + tid, 'PUT', body)
    : await adminApi('/tasks', 'POST', body);
  if (data.ok) { toast(tid ? 'Task updated!' : 'Task created!'); closeModal(); adminTasks(); }
  else { toast('Failed: ' + data.error); }
}

async function adminToggleTask(tid) {
  const data = await adminApi('/tasks/' + tid + '/toggle', 'POST');
  if (data.ok) { toast('Task ' + (data.is_active ? 'resumed' : 'paused')); closeModal(); adminTasks(); }
  else { toast('Failed: ' + data.error); }
}

async function adminDeleteTask(tid) {
  if (!confirm('Delete task #' + tid + '?')) return;
  const data = await adminApi('/tasks/' + tid, 'DELETE');
  if (data.ok) { toast('Task deleted'); closeModal(); adminTasks(); }
  else { toast('Failed: ' + data.error); }
}

// ─── Withdrawals + Proofs ────────────────────────────────────────────────

async function adminWithdrawals() {
  const el = document.getElementById('adminSection');
  el.innerHTML = '<div style="padding:0 16px"><div class="admin-back" onclick="adminGoBack()">← Back to Menu</div></div><div style="padding:0 16px"><button class="btn btn-sm btn-primary" onclick="adminProofs()" style="margin-bottom:12px">📝 View Pending Proofs</button></div><div id="adminWdList" class="admin-list">' + showAdminLoading() + '</div>';
  const data = await adminApi('/withdrawals/pending', 'GET');
  if (!data.ok) { document.getElementById('adminWdList').innerHTML = '<div class="empty-state">Failed to load</div>'; return; }
  const list = document.getElementById('adminWdList');
  if (!data.withdrawals.length) { list.innerHTML = '<div class="empty-state">No pending withdrawals</div>'; return; }
  list.innerHTML = data.withdrawals.map(w => `
    <div class="admin-list-item">
      <div class="info">
        <div class="title">${w.user_name} <span class="badge badge-pending">${w.method}</span></div>
        <div class="subtitle">₹${w.amount} · ${w.upi_id || 'N/A'} · ${w.date?.slice(0,10) || ''}</div>
      </div>
      <div style="display:flex;gap:4px">
        <button class="btn btn-sm btn-success" onclick="event.stopPropagation();adminApproveWd(${w.id})">✅</button>
        <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();adminRejectWd(${w.id})">❌</button>
      </div>
    </div>
  `).join('');
}

async function adminApproveWd(wid) {
  if (!confirm('Approve withdrawal #' + wid + '?')) return;
  const data = await adminApi('/withdrawals/' + wid + '/approve', 'POST', {});
  if (data.ok) { toast('Withdrawal approved'); adminWithdrawals(); }
  else { toast('Failed'); }
}

async function adminRejectWd(wid) {
  const reason = prompt('Rejection reason:', '');
  if (reason === null) return;
  const data = await adminApi('/withdrawals/' + wid + '/reject', 'POST', { reason });
  if (data.ok) { toast('Withdrawal rejected'); adminWithdrawals(); }
  else { toast('Failed'); }
}

async function adminProofs() {
  const el = document.getElementById('adminSection');
  el.innerHTML = '<div style="padding:0 16px"><div class="admin-back" onclick="adminWithdrawals()">← Back to Withdrawals</div></div><div id="adminProofList" class="admin-list">' + showAdminLoading() + '</div>';
  const data = await adminApi('/proofs/pending', 'GET');
  if (!data.ok) { document.getElementById('adminProofList').innerHTML = '<div class="empty-state">Failed to load</div>'; return; }
  const list = document.getElementById('adminProofList');
  if (!data.proofs.length) { list.innerHTML = '<div class="empty-state">No pending proofs</div>'; return; }
  list.innerHTML = data.proofs.map(p => `
    <div class="admin-list-item">
      <div class="info">
        <div class="title">${p.user_name} · Task #${p.task_id}</div>
        <div class="subtitle">${p.date?.slice(0,10) || ''} · ${p.file_type}</div>
      </div>
      <div style="display:flex;gap:4px">
        <button class="btn btn-sm btn-success" onclick="event.stopPropagation();adminApproveProof(${p.id})">✅</button>
        <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();adminRejectProof(${p.id})">❌</button>
      </div>
    </div>
  `).join('');
}

async function adminApproveProof(pid) {
  if (!confirm('Approve proof #' + pid + '?')) return;
  const data = await adminApi('/proofs/' + pid + '/approve', 'POST', {});
  if (data.ok) { toast('Proof approved! Reward credited.'); adminProofs(); }
  else { toast('Failed'); }
}

async function adminRejectProof(pid) {
  const reason = prompt('Rejection reason:', 'Incorrect proof');
  if (reason === null) return;
  const data = await adminApi('/proofs/' + pid + '/reject', 'POST', { reason });
  if (data.ok) { toast('Proof rejected'); adminProofs(); }
  else { toast('Failed'); }
}

// ─── Promoted ─────────────────────────────────────────────────────────────

async function adminPromoted() {
  const el = document.getElementById('adminSection');
  el.innerHTML = '<div style="padding:0 16px"><div class="admin-back" onclick="adminGoBack()">← Back to Menu</div><button class="btn btn-primary btn-block" style="margin-bottom:12px" onclick="adminAddPromoted()">➕ Add Promoted Item</button></div><div id="adminPromotedList" class="admin-list">' + showAdminLoading() + '</div>';
  const data = await adminApi('/promoted', 'GET');
  if (!data.ok) { document.getElementById('adminPromotedList').innerHTML = '<div class="empty-state">Failed to load</div>'; return; }
  const list = document.getElementById('adminPromotedList');
  if (!data.items.length) { list.innerHTML = '<div class="empty-state">No promoted items</div>'; return; }
  list.innerHTML = data.items.map(i => `
    <div class="admin-list-item">
      <div class="info">
        <div class="title">${i.title || 'Untitled'} ${i.active === false ? '<span class="badge badge-rejected">INACTIVE</span>' : ''}</div>
        <div class="subtitle">${i.description?.slice(0, 50) || ''}${i.url ? ' · ' + i.url : ''}</div>
      </div>
      <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();adminDeletePromoted(${i.id})">🗑️</button>
    </div>
  `).join('');
}

function adminAddPromoted() {
  showModal('Admin › Add Promoted', `
    <div class="admin-form">
      <div class="form-group"><label>Title</label><input id="f_p_title"></div>
      <div class="form-group"><label>Description</label><textarea id="f_p_desc"></textarea></div>
      <div class="form-group"><label>Image URL</label><input id="f_p_image" placeholder="https://..."></div>
      <div class="form-group"><label>Link URL</label><input id="f_p_url" placeholder="https://..."></div>
      <div class="form-group"><label>Badge Text</label><input id="f_p_badge" placeholder="AD, PROMO, etc."></div>
      <button class="btn btn-primary btn-block" onclick="adminSavePromoted()">Add</button>
    </div>
  `);
}

async function adminSavePromoted() {
  const body = {
    title: document.getElementById('f_p_title')?.value || '',
    description: document.getElementById('f_p_desc')?.value || '',
    image: document.getElementById('f_p_image')?.value || '',
    url: document.getElementById('f_p_url')?.value || '',
    badge: document.getElementById('f_p_badge')?.value || '',
  };
  const data = await adminApi('/promoted', 'POST', body);
  if (data.ok) { toast('Promoted item added!'); closeModal(); adminPromoted(); }
  else { toast('Failed'); }
}

async function adminDeletePromoted(id) {
  if (!confirm('Delete promoted item #' + id + '?')) return;
  const data = await adminApi('/promoted/' + id, 'DELETE');
  if (data.ok) { toast('Deleted'); adminPromoted(); }
}

// ─── Ads ──────────────────────────────────────────────────────────────────

async function adminAds() {
  const el = document.getElementById('adminSection');
  el.innerHTML = '<div style="padding:0 16px"><div class="admin-back" onclick="adminGoBack()">← Back to Menu</div><button class="btn btn-primary btn-block" style="margin-bottom:12px" onclick="adminAddAd()">➕ Add Ad Campaign</button></div><div id="adminAdList" class="admin-list">' + showAdminLoading() + '</div>';
  const data = await adminApi('/ads', 'GET');
  if (!data.ok) { document.getElementById('adminAdList').innerHTML = '<div class="empty-state">Failed to load</div>'; return; }
  const list = document.getElementById('adminAdList');
  if (!data.ads.length) { list.innerHTML = '<div class="empty-state">No ad campaigns</div>'; return; }
  list.innerHTML = data.ads.map(a => `
    <div class="admin-list-item">
      <div class="info">
        <div class="title">${a.title || 'Untitled'} ${a.active === false ? '<span class="badge badge-rejected">INACTIVE</span>' : ''}</div>
        <div class="subtitle">₹${a.reward || 0} per view · ${a.description?.slice(0, 50) || ''}</div>
      </div>
      <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();adminDeleteAd(${a.id})">🗑️</button>
    </div>
  `).join('');
}

function adminAddAd() {
  showModal('Admin › Add Ad Campaign', `
    <div class="admin-form">
      <div class="form-group"><label>Title</label><input id="f_a_title"></div>
      <div class="form-group"><label>Description</label><textarea id="f_a_desc"></textarea></div>
      <div class="form-group"><label>Image URL</label><input id="f_a_image" placeholder="https://..."></div>
      <div class="form-group"><label>Link URL</label><input id="f_a_url" placeholder="https://..."></div>
      <div class="form-group"><label>Reward per View (₹)</label><input id="f_a_reward" type="number" step="0.01" value="0.05"></div>
      <button class="btn btn-primary btn-block" onclick="adminSaveAd()">Add</button>
    </div>
  `);
}

async function adminSaveAd() {
  const body = {
    title: document.getElementById('f_a_title')?.value || '',
    description: document.getElementById('f_a_desc')?.value || '',
    image: document.getElementById('f_a_image')?.value || '',
    url: document.getElementById('f_a_url')?.value || '',
    reward: parseFloat(document.getElementById('f_a_reward')?.value || 0),
  };
  const data = await adminApi('/ads', 'POST', body);
  if (data.ok) { toast('Ad campaign added!'); closeModal(); adminAds(); }
  else { toast('Failed'); }
}

async function adminDeleteAd(id) {
  if (!confirm('Delete ad campaign #' + id + '?')) return;
  const data = await adminApi('/ads/' + id, 'DELETE');
  if (data.ok) { toast('Deleted'); adminAds(); }
}

// ─── User Submissions ─────────────────────────────────────────────────────

async function adminSubmissions() {
  const el = document.getElementById('adminSection');
  el.innerHTML = '<div style="padding:0 16px"><div class="admin-back" onclick="adminGoBack()">← Back to Menu</div></div><div id="adminSubList" class="admin-list">' + showAdminLoading() + '</div>';
  const data = await adminApi('/user-submissions', 'GET');
  if (!data.ok) { document.getElementById('adminSubList').innerHTML = '<div class="empty-state">Failed to load</div>'; return; }
  const list = document.getElementById('adminSubList');
  const pending = (data.submissions || []).filter(s => s.status === 'pending');
  if (!pending.length) { list.innerHTML = '<div class="empty-state">No pending submissions</div>'; return; }
  list.innerHTML = pending.map(s => `
    <div class="admin-list-item">
      <div class="info">
        <div class="title">${s.title || 'Untitled'} <span class="badge badge-pending">${s.type}</span></div>
        <div class="subtitle">User: ${s.user_id} · ${s.date?.slice(0,10) || ''}${s.reward ? ' · ₹' + s.reward : ''}</div>
        ${s.description ? `<div class="subtitle" style="margin-top:4px;font-size:11px">${s.description.slice(0,100)}</div>` : ''}
      </div>
      <div style="display:flex;gap:4px">
        <button class="btn btn-sm btn-success" onclick="event.stopPropagation();adminApproveSubmission(${s.id})">✅</button>
        <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();adminRejectSubmission(${s.id})">❌</button>
      </div>
    </div>
  `).join('');
}

async function adminApproveSubmission(sid) {
  if (!confirm('Approve submission #' + sid + '? It will be published.')) return;
  const data = await adminApi('/user-submissions/' + sid + '/approve', 'POST', {});
  if (data.ok) { toast('Approved! Published.'); adminSubmissions(); }
  else { toast('Failed'); }
}

async function adminRejectSubmission(sid) {
  const reason = prompt('Rejection reason:', '');
  if (reason === null) return;
  const data = await adminApi('/user-submissions/' + sid + '/reject', 'POST', { reason });
  if (data.ok) { toast('Rejected'); adminSubmissions(); }
  else { toast('Failed'); }
}

// ─── Settings ─────────────────────────────────────────────────────────────

async function adminSettings() {
  const el = document.getElementById('adminSection');
  el.innerHTML = '<div style="padding:0 16px"><div class="admin-back" onclick="adminGoBack()">← Back to Menu</div></div><div id="adminSettingsList" class="admin-settings">' + showAdminLoading() + '</div>';
  const data = await adminApi('/settings', 'GET');
  if (!data.ok) { document.getElementById('adminSettingsList').innerHTML = '<div class="empty-state">Failed to load</div>'; return; }
  const s = data.settings || {};
  const list = document.getElementById('adminSettingsList');
  const settingsToShow = [
    { key: 'maintenance_mode', label: 'Maintenance Mode', type: 'bool' },
    { key: 'referral_paused', label: 'Referral Paused', type: 'bool' },
    { key: 'contact_mandatory', label: 'Contact Mandatory', type: 'bool' },
    { key: 'device_verification_enabled', label: 'Device Verification', type: 'bool' },
    { key: 'welcome_bonus_amount', label: 'Welcome Bonus (₹)', type: 'float' },
    { key: 'min_withdraw_upi', label: 'Min UPI Withdraw (₹)', type: 'float' },
    { key: 'max_withdraw_upi', label: 'Max UPI Withdraw (₹)', type: 'float' },
    { key: 'daily_withdraw_limit', label: 'Daily Withdraw Limit (₹)', type: 'float' },
    { key: 'ad_goal_target', label: 'Ad Goal Target', type: 'int' },
    { key: 'ad_goal_reward', label: 'Ad Goal Reward (₹)', type: 'float' },
    { key: 'referral_fixed_reward', label: 'Referral Fixed Reward (₹)', type: 'float' },
    { key: 'referral_min_reward', label: 'Referral Min Reward (₹)', type: 'float' },
    { key: 'referral_max_reward', label: 'Referral Max Reward (₹)', type: 'float' },
  ];
  list.innerHTML = settingsToShow.map(st => {
    const val = s[st.key];
    const displayVal = st.type === 'bool' ? (val ? 'ON' : 'OFF') : (val ?? 'N/A');
    return `
      <div class="setting-item" onclick="adminEditSetting('${st.key}', '${st.label}', '${st.type}', ${JSON.stringify(val ?? '')})">
        <div>
          <div class="label">${st.label}</div>
          <div class="value">${st.type === 'bool' ? `<div class="toggle-switch ${val ? 'on' : ''}"></div>` : displayVal}</div>
        </div>
      </div>
    `;
  }).join('');
}

function adminEditSetting(key, label, type, currentVal) {
  if (type === 'bool') {
    const newVal = !(currentVal === true || currentVal === 'true');
    adminSaveSetting(key, newVal);
    return;
  }
  const newVal = prompt('Enter new value for ' + label + ':', currentVal);
  if (newVal === null) return;
  adminSaveSetting(key, newVal);
}

async function adminSaveSetting(key, val) {
  const body = {};
  body[key] = val;
  const data = await adminApi('/settings', 'PUT', body);
  if (data.ok) { toast('Setting updated!'); adminSettings(); }
  else { toast('Failed'); }
}
