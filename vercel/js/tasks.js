let currentTaskFilter = 'all';

async function loadTasks() {
  const el = document.getElementById('taskList');
  if (!el) return;

  const countEl = document.getElementById('taskCount');
  const data = await api('/api/app/tasks?' + new URLSearchParams({ user_id: USER.id }).toString());
  let tasks = data.tasks || [];

  // Apply filter
  if (currentTaskFilter === 'channel') {
    tasks = tasks.filter(t => t.type === 'channel');
  } else if (currentTaskFilter === 'manual') {
    tasks = tasks.filter(t => t.type !== 'channel');
  }

  if (countEl) countEl.textContent = tasks.length + ' tasks';

  if (tasks.length === 0) {
    el.innerHTML = '<div class="empty-state">No tasks available</div>';
    return;
  }

  el.innerHTML = tasks.map((t, i) => renderTaskCard(t, i)).join('');
}

function renderTaskCard(t, index) {
  const isDone = t.is_completed;
  const hasImage = t.image && t.image.length > 5;
  const imgContent = hasImage
    ? `<img src="${t.image}" alt="${t.title}" loading="lazy">`
    : (t.icon || '📋');
  const badgeClass = t.type === 'channel' ? 'badge-channel' : 'badge-manual';
  const badgeText = t.type === 'channel' ? 'Channel' : 'Manual';

  return `
    <div class="card task-card animate-in stagger-${Math.min(index + 1, 10)}"
         onclick="showTaskDetail(${t.id})"
         style="border-left:3px solid ${t.color || (t.type === 'channel' ? '#1976d2' : '#c62828')}">
      <div class="task-img" style="background:linear-gradient(135deg,${t.color || '#7b5ef8'},${t.color2 || '#5a3fd6'})">
        ${imgContent}
      </div>
      <div class="task-info">
        <div class="tags">
          <span class="badge ${badgeClass}">${badgeText}</span>
          ${t.is_multi_reward ? '<span class="task-multi-badge">Multi Reward</span>' : ''}
        </div>
        <h3>${t.title}</h3>
        <div class="meta">
          <span>⏱ ${t.duration || '15 min'}</span>
          <span>👥 ${t.completions || 0} done</span>
        </div>
        <div class="task-actions" onclick="event.stopPropagation()">
          ${t.video_url ? `<button class="task-btn-video" onclick="event.stopPropagation();openLink('${t.video_url}')">▶ Video</button>` : ''}
          ${isDone
            ? '<span class="task-completed-badge">✓ Done</span>'
            : `<button class="task-btn-start" onclick="event.stopPropagation();showTaskDetail(${t.id})">Start Task</button>`
          }
        </div>
      </div>
      <div class="task-reward-col">
        <span class="reward">₹${t.reward}</span>
        ${isDone ? '<span style="color:var(--success);font-size:10px">✓ Completed</span>' : ''}
      </div>
    </div>`;
}

function setTaskFilter(filter) {
  currentTaskFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === filter);
  });
  loadTasks();
}

async function showTaskDetail(taskId) {
  showModal('Task Details', '<div id="taskDetailBody"><div class="loading-dots"><div></div><div></div><div></div></div></div>');
  await loadTaskDetail(taskId);
}

async function loadTaskDetail(taskId) {
  const data = await api('/api/app/task/' + taskId + '?' + new URLSearchParams({ user_id: USER.id }).toString());
  const body = document.getElementById('taskDetailBody');
  if (!data.ok || !body) { if (body) body.innerHTML = '<p class="empty-state">Failed to load</p>'; return; }

  const t = data.task;
  const isDone = t.is_completed;
  const hasImage = t.image && t.image.length > 5;
  const steps = t.steps || (t.guide ? t.guide.split('\n').filter(s => s.trim()) : []);

  const stepsHtml = steps.length > 0
    ? `<div class="task-steps"><h4>📋 Steps to Complete:</h4><ol>${steps.map(s => `<li>${s}</li>`).join('')}</ol></div>`
    : '';

  body.innerHTML = `
    <div class="task-detail-header">
      <div class="task-icon" style="background:linear-gradient(135deg,${t.color || '#7b5ef8'},${t.color2 || '#5a3fd6'})">
        ${hasImage ? `<img src="${t.image}" style="width:100%;height:100%;object-fit:cover">` : (t.icon || '📋')}
      </div>
      <h3 style="font-size:17px;font-weight:700">${t.title}</h3>
      <div style="display:flex;align-items:center;justify-content:center;gap:8px;margin-top:6px">
        <span class="badge ${t.type === 'channel' ? 'badge-channel' : 'badge-manual'}">${t.type === 'channel' ? 'Channel' : 'Manual'}</span>
        ${t.is_multi_reward ? '<span class="task-multi-badge">Multi Reward</span>' : ''}
      </div>
      <div style="color:var(--success);font-weight:800;font-size:28px;margin:8px 0">₹${t.reward}</div>
      <div style="font-size:12px;color:var(--text-secondary);display:flex;justify-content:center;gap:16px">
        <span>⏱ ${t.duration || '15 min'}</span>
        <span>👥 ${t.completions || 0} users</span>
      </div>
    </div>
    ${t.description ? `<p style="font-size:13px;color:var(--text-secondary);margin-bottom:8px">${t.description}</p>` : ''}
    ${stepsHtml}
    ${t.max_completers > 0 ? renderAffiliateSection(t) : ''}
    <div style="display:flex;gap:8px;margin-top:12px">
      ${t.video_url ? `<button class="btn btn-outline" style="flex:1;font-size:13px" onclick="openLink('${t.video_url}')">▶ Offer Video</button>` : ''}
      ${t.offer_url ? `<button class="btn btn-outline" style="flex:1;font-size:13px" onclick="openLink('${t.offer_url}')">🔗 Open Offer</button>` : ''}
    </div>
    <div style="margin-top:12px">
      ${isDone
        ? '<div style="text-align:center;padding:12px;background:rgba(0,229,160,0.1);border-radius:10px;color:var(--success);font-weight:700">✅ Task Completed</div>'
        : `<button class="btn btn-primary btn-block btn-lg" onclick="startTask(${taskId})">🚀 Start Task</button>`
      }
    </div>
  `;
}

function renderAffiliateSection(t) {
  return `
    <div class="affiliate-card">
      <div style="display:flex;justify-content:space-between;margin-bottom:6px">
        <span style="font-size:12px;color:var(--text-secondary);font-weight:600">💰 Affiliate Reward</span>
        <span style="font-size:11px;color:var(--text-secondary)">${t.current_completers}/${t.max_completers} slots</span>
      </div>
      <div style="display:flex;gap:12px;font-size:12px">
        <div style="flex:1;text-align:center;padding:8px;background:var(--card);border-radius:8px;border:1px solid var(--border)">
          <div style="color:var(--success);font-weight:800;font-size:15px">₹${t.referrer_reward}</div>
          <div style="color:var(--text-secondary);font-size:10px">You earn</div>
        </div>
        <div style="flex:1;text-align:center;padding:8px;background:var(--card);border-radius:8px;border:1px solid var(--border)">
          <div style="color:var(--primary);font-weight:800;font-size:15px">₹${t.completer_reward}</div>
          <div style="color:var(--text-secondary);font-size:10px">Completer earns</div>
        </div>
      </div>
    </div>`;
}

function startTask(taskId) {
  closeModal();
  api('/api/app/task/' + taskId + '?' + new URLSearchParams({ user_id: USER.id }).toString()).then(data => {
    if (!data.ok) return;
    const t = data.task;
    const steps = t.steps || (t.guide ? t.guide.split('\n').filter(s => s.trim()) : []);
    const stepsHtml = steps.length > 0
      ? `<div style="margin:12px 0;padding:12px 16px;background:var(--bg);border-radius:10px;border:1px solid var(--border)">
          <h4 style="font-size:13px;margin-bottom:6px;color:var(--text-secondary)">📋 Task Steps:</h4>
          <ol style="padding-left:18px;font-size:12px;line-height:1.9;margin:0">
            ${steps.map(s => `<li>${s}</li>`).join('')}
          </ol>
        </div>`
      : '';

    showModal('Submit Proof', `
      <div class="proof-submit">
        <div style="text-align:center;margin-bottom:16px">
          <div style="width:64px;height:64px;border-radius:14px;background:linear-gradient(135deg,${t.color||'#7b5ef8'},${t.color2||'#5a3fd6'});display:flex;align-items:center;justify-content:center;color:#fff;font-size:28px;margin:0 auto 8px">${t.icon||'📋'}</div>
          <h3 style="font-size:16px;font-weight:700">${t.title}</h3>
          <div style="color:var(--success);font-weight:700;font-size:20px;margin-top:4px">₹${t.reward}</div>
        </div>
        ${stepsHtml}
        <div class="proof-warning">⚠️ Complete the task above, then submit screenshot as proof. Admin will verify and credit your reward.</div>
        <div class="form-group">
          <label>📸 Screenshot Proof</label>
          <div style="display:flex;gap:8px">
            <input class="form-input" id="proofImage" placeholder="Paste image URL or screenshot link" style="flex:1">
            <button class="btn btn-sm btn-outline" onclick="document.getElementById('proofFileInput').click()" style="white-space:nowrap">📁 Upload</button>
          </div>
          <input type="file" id="proofFileInput" accept="image/*" style="display:none" onchange="handleProofFile(event)">
          <div id="proofFileName" style="font-size:11px;color:var(--text-secondary);margin-top:4px"></div>
        </div>
        <div class="form-group">
          <label>🔑 Transaction ID / Order ID</label>
          <input class="form-input" id="proofTxnId" placeholder="Enter transaction ID if applicable">
        </div>
        <div class="form-group">
          <label>💳 Your UPI ID (for payment)</label>
          <input class="form-input" id="proofUpi" placeholder="Enter your UPI ID" value="${CURRENT_USER?.upi||''}">
        </div>
        <button class="btn btn-success btn-block btn-lg" onclick="submitProof(${taskId})">📤 Submit Proof</button>
      </div>
    `);
  });
}

function handleProofFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const el = document.getElementById('proofFileName');
  if (el) el.textContent = '📎 ' + file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
  const reader = new FileReader();
  reader.onload = function(e) {
    const input = document.getElementById('proofImage');
    if (input) input.value = e.target.result;
  };
  reader.readAsDataURL(file);
}

async function submitProof(taskId) {
  const proof_image = document.getElementById('proofImage')?.value;
  const txn_id = document.getElementById('proofTxnId')?.value;
  const upi = document.getElementById('proofUpi')?.value;
  if (!proof_image && !txn_id) { toast('📸 Please provide a screenshot or transaction ID'); return; }
  if (!upi) { toast('💳 Please enter your UPI ID for payment'); return; }

  const btn = document.querySelector('.proof-submit .btn-success');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Submitting...'; }

  const data = await api('/api/app/task/' + taskId + '/submit', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, proof_image, txn_id, upi })
  });

  if (data.ok) {
    closeModal();
    toast('✅ Proof submitted! Admin will review shortly.');
    loadTasks();
  } else {
    if (btn) { btn.disabled = false; btn.textContent = '📤 Submit Proof'; }
    toast(data.error || 'Failed to submit');
  }
}

async function loadPromoted() {
  const el = document.getElementById('promotedList');
  if (!el) return;
  const data = await api('/api/app/promoted?' + new URLSearchParams({ user_id: USER.id }).toString());
  const items = data.items || [];
  if (items.length === 0) { el.innerHTML = ''; return; }

  el.innerHTML = items.map(p => `
    <div class="promoted-card" onclick="openLink('${p.url||'#'}')">
      <div class="promo-icon" style="background:linear-gradient(135deg,${p.color1||'#7b5ef8'},${p.color2||'#5a3fd6'})">${p.icon||'📢'}</div>
      <div class="promo-info">
        <span class="badge">${p.badge||'⭐ Official Partner'}</span>
        <h4>${p.title}</h4>
        <p>${p.description||''}</p>
      </div>
      <button class="promo-open" onclick="event.stopPropagation();openLink('${p.url||'#'}')">OPEN</button>
    </div>
  `).join('');
}

function showPromoteModal() {
  showModal('Promote Here',
    '<div style="text-align:center;padding:16px">' +
    '<p style="color:var(--text-secondary);margin-bottom:12px">Want to promote your brand or service? Contact our admin to get featured.</p>' +
    '<button class="btn btn-primary" onclick="closeModal()">Contact Admin</button></div>');
}

async function loadAdvertise() {
  const el = document.getElementById('advertiseSection');
  if (!el) return;
  el.innerHTML = '<div class="loading-dots"><div></div><div></div><div></div></div>';

  const [earnData, promoData] = await Promise.all([
    api('/api/app/earn?' + new URLSearchParams({ user_id: USER.id }).toString()),
    api('/api/app/promoted?' + new URLSearchParams({ user_id: USER.id }).toString())
  ]);

  const adGoal = earnData.ad_goal || { current: 0, target: 20, reward: 1, reset_in: '—' };
  const ads = earnData.ads || [];
  const pct = Math.min(100, (adGoal.current / adGoal.target) * 100);
  const items = promoData.items || [];

  const adsHtml = ads.length > 0 ? ads.map(a => `
    <div class="ad-card">
      <div class="ad-icon" style="background:linear-gradient(135deg,${a.color1||'#ff6b6b'},${a.color2||'#ee5a24'})">${a.icon||'📺'}</div>
      <div class="ad-info">
        <h4>${a.title}</h4>
        <p>${a.description||'Watch and earn'}</p>
      </div>
      <button class="btn btn-sm btn-primary" onclick="watchAd(${a.id})">▶ Watch</button>
    </div>
  `).join('') : '';

  el.innerHTML = `
    <div class="adgoal-card">
      <div class="goal-header">
        <div style="position:relative;width:110px;height:110px">
          <svg width="110" height="110" viewBox="0 0 110 110">
            <circle cx="55" cy="55" r="48" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="6"/>
            <circle cx="55" cy="55" r="48" fill="none" stroke="#00e5a0" stroke-width="6"
              stroke-dasharray="${2 * Math.PI * 48}" stroke-dashoffset="${2 * Math.PI * 48 * (1 - pct / 100)}"
              stroke-linecap="round" transform="rotate(-90 55 55)" style="transition:stroke-dashoffset 0.5s"/>
          </svg>
          <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center">
            <span style="font-size:22px;font-weight:800;color:#fff">${adGoal.current}</span>
            <span style="font-size:10px;color:rgba(255,255,255,0.5)">of ${adGoal.target}</span>
          </div>
        </div>
        <div style="text-align:left">
          <h3 style="font-size:16px;font-weight:700;color:#fff;margin-bottom:4px">Daily Ad Goal</h3>
          <div style="font-size:12px;color:rgba(255,255,255,0.6);line-height:1.8">
            <div>🎯 Target: <b style="color:#fff">${adGoal.target} Ads</b></div>
            <div>💰 Reward: <b style="color:#00e5a0">₹${adGoal.reward}</b></div>
            <div>🔄 Resets: <b style="color:#fff">${adGoal.reset_in}</b></div>
          </div>
        </div>
      </div>
      <div style="text-align:center;margin-bottom:12px;font-size:12px;color:rgba(255,255,255,0.5)">
        Complete your daily target to unlock a reward of ₹${adGoal.reward}
      </div>
      <button class="btn-watch-ad" onclick="watchAd('goal')">▶ WATCH AD TO EARN</button>
    </div>
    ${adsHtml ? `<h3 class="section-title" style="margin-top:16px">📺 Available Ads</h3>${adsHtml}` : ''}
    ${items.length > 0 ? `
      <h3 class="section-title" style="margin-top:16px">📢 Promoted</h3>
      ${items.map(p => `
        <div class="card" style="display:flex;align-items:center;gap:12px;cursor:pointer" onclick="openLink('${p.url || '#'}')">
          <div style="width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,${p.color1 || '#ff6b6b'},${p.color2 || '#ee5a24'});display:flex;align-items:center;justify-content:center;color:#fff;font-size:22px;flex-shrink:0">${p.icon || '📢'}</div>
          <div style="flex:1;min-width:0">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">
              <span style="display:inline-block;padding:1px 6px;border-radius:4px;font-size:9px;font-weight:700;background:linear-gradient(135deg,#ff6b6b,#ee5a24);color:#fff">${p.badge || '⭐ Official Partner'}</span>
            </div>
            <h4 style="font-size:13px;font-weight:600">${p.title}</h4>
            <p style="font-size:11px;color:var(--text-secondary);margin-top:2px">${p.description || ''}</p>
          </div>
          <button class="btn btn-sm btn-primary" style="flex-shrink:0">OPEN</button>
        </div>
      `).join('')}
    ` : ''}
  `;
}

async function watchAd(adId) {
  const data = await api('/api/app/ad/watch', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, ad_id: typeof adId === 'number' ? adId : 0 })
  });
  if (data.ok) {
    toast('💰 +₹' + (data.amount || '0.10') + ' earned!');
    updateBalance(data.balance || CURRENT_USER.balance);
    loadAdvertise();
  } else {
    toast(data.error || 'Failed');
  }
}
