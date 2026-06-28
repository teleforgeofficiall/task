let currentTaskFilter = 'all';
let _promoRaf = null;
let _promoResumeTimer = null;

async function loadTasks() {
  const el = document.getElementById('taskList');
  if (!el) return;

  const countEl = document.getElementById('taskCount');
  const data = await api('/api/app/tasks?' + new URLSearchParams({ user_id: USER.id }).toString());
  if (!data.ok) { el.innerHTML = '<div class="empty-state">Failed to load tasks</div>'; return; }
  let tasks = data.tasks || [];

  // Apply filter
  if (currentTaskFilter === 'channel') {
    tasks = tasks.filter(t => t.type === 'channel');
  } else if (currentTaskFilter === 'manual') {
    tasks = tasks.filter(t => t.type !== 'channel');
  } else if (currentTaskFilter === 'pending') {
    tasks = tasks.filter(t => t.has_pending_proof);
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
  const hasImage = t.task_image && t.task_image.length > 5;
  const imgContent = hasImage
    ? `<img src="${t.task_image}" alt="${t.title}" loading="lazy" onerror="this.onerror=null;var vps='http://153.75.246.79:8001${t.task_image}';var s=this;fetch(vps).then(r=>{if(!r.ok)throw 0;return r.blob()}).then(b=>{s.src=URL.createObjectURL(b)}).catch(()=>{s.style.display='none'})">`
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
            : t.has_pending_proof
              ? '<span class="task-pending-badge">⏳ Pending Review</span>'
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
  const steps = t.steps || (t.guide ? t.guide.split('\n').filter(s => s.trim()) : []);

  const stepsHtml = steps.length > 0
    ? `<div class="task-steps"><h4>📋 Steps to Complete:</h4><ol>${steps.map(s => `<li>${s}</li>`).join('')}</ol></div>`
    : '';

  body.innerHTML = `
    <div class="task-detail-header">
      <div class="task-icon" style="background:linear-gradient(135deg,${t.color || '#7b5ef8'},${t.color2 || '#5a3fd6'})">
        ${t.icon || '📋'}
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
    ${t.description ? `<p style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;white-space:pre-wrap">${escHtml(t.description)}</p>` : ''}
    ${stepsHtml}
    ${t.video_url ? `<div style="margin-top:12px"><button class="btn btn-outline btn-block" style="font-size:13px" onclick="openLink('${t.video_url}')">▶ Offer Video</button></div>` : ''}
    <div style="margin-top:12px">
      ${isDone
        ? '<div style="text-align:center;padding:12px;background:rgba(0,229,160,0.1);border-radius:10px;color:var(--success);font-weight:700">✅ Task Completed</div>'
        : t.has_pending_proof
          ? '<div style="text-align:center;padding:12px;background:rgba(255,193,7,0.1);border-radius:10px;color:#ffc107;font-weight:700">⏳ Pending Review</div>'
          : `<button class="btn btn-primary btn-block btn-lg" onclick="startTask(${taskId})">${t.type === 'channel' ? '📢' : '🚀'} Start Task</button>`
      }
    </div>
  `;
}



function startTask(taskId) {
  api('/api/app/task/' + taskId + '?' + new URLSearchParams({ user_id: USER.id }).toString()).then(data => {
    if (!data.ok) return;
    const t = data.task;

    if (t.offer_url) {
      openLink(t.offer_url);
    }

    if (t.type === 'channel') {
      let channelOpened = false;
      if (t.channel_url) {
        openLink(t.channel_url);
        channelOpened = true;
      }
      showModal('Join Channel', `
        <div class="proof-submit">
          <div style="text-align:center;margin-bottom:16px">
            <div style="width:64px;height:64px;border-radius:14px;background:linear-gradient(135deg,${t.color||'#7b5ef8'},${t.color2||'#5a3fd6'});display:flex;align-items:center;justify-content:center;color:#fff;font-size:28px;margin:0 auto 8px">${t.icon||'📋'}</div>
            <h3 style="font-size:16px;font-weight:700">${t.title}</h3>
            <div style="color:var(--success);font-weight:700;font-size:20px;margin-top:4px">₹${t.reward}</div>
          </div>
          <div class="proof-warning">⚠️ Join the channel above, then click verify to claim your reward.</div>
          ${t.channel_url ? `<button class="btn btn-outline btn-block" style="margin-bottom:8px" onclick="openLink('${t.channel_url}')">📢 Open Channel</button>` : ''}
          <button class="btn btn-primary btn-block btn-lg" onclick="verifyChannelTask(${taskId})">✅ Verify & Claim</button>
          <button class="btn btn-outline btn-block" style="margin-top:8px;font-size:12px" onclick="showProofModal(${taskId})">📤 Submit Screenshot Instead</button>
        </div>
      `);
      return;
    }

    const steps = t.steps || (t.guide ? t.guide.split('\n').filter(s => s.trim()) : []);
    const stepsHtml = steps.length > 0
      ? `<div style="margin:12px 0;padding:12px 16px;background:var(--bg);border-radius:10px;border:1px solid var(--border)">
          <h4 style="font-size:13px;margin-bottom:6px;color:var(--text-secondary)">📋 Task Steps:</h4>
          <ol style="padding-left:18px;font-size:12px;line-height:1.9;margin:0">
            ${steps.map(s => `<li>${s}</li>`).join('')}
          </ol>
        </div>`
      : '';

    showProofModal(taskId, t, stepsHtml);
  });
}

async function showProofModal(taskId, t, stepsHtml) {
  if (!t) {
    const data = await api('/api/app/task/' + taskId + '?' + new URLSearchParams({ user_id: USER.id }).toString());
    if (!data.ok) { toast('Failed to load task'); return; }
    t = data.task;
    stepsHtml = '';
  }
  const hasImage = t.image && t.image.length > 5;
  const imageUrl = '/api/app/task-image/' + taskId;
  const refHtml = hasImage
    ? `<div class="proof-side proof-ref-side">
        <div class="proof-side-label">📋 Reference</div>
        <img src="${imageUrl}" class="proof-ref-img" onerror="this.onerror=null;var vps='http://153.75.246.79:8001${imageUrl}';var s=this;fetch(vps).then(r=>{if(!r.ok)throw 0;return r.blob()}).then(b=>{s.src=URL.createObjectURL(b)}).catch(()=>{s.parentElement.innerHTML='<div class=proof-empty>No reference</div>'})">
      </div>`
    : `<div class="proof-side proof-ref-side">
        <div class="proof-empty">No reference image</div>
      </div>`;

  showModal('Submit Proof', `
    <div class="proof-submit">
      <div style="text-align:center;margin-bottom:12px">
        <h3 style="font-size:16px;font-weight:700">${t.title}</h3>
        <div style="color:var(--success);font-weight:700;font-size:20px;margin-top:4px">₹${t.reward}</div>
      </div>
      ${stepsHtml || ''}
      <div class="proof-warning">⚠️ Complete the task, then submit screenshot as proof. Admin will verify and credit your reward.</div>
      <div class="proof-layout">
        ${refHtml}
        <div class="proof-side proof-upload-side">
          <div class="proof-side-label">📸 Your Proof</div>
          <div class="proof-upload-box" onclick="document.getElementById('proofFileInput').click()">
            <div class="proof-upload-placeholder" id="proofUploadPlaceholder">
              <div style="font-size:32px;color:var(--text-secondary)">+</div>
              <div style="font-size:12px;color:var(--text-secondary)">Tap to add screenshot</div>
            </div>
            <img id="proofPreview" class="proof-preview" style="display:none">
            <input type="file" id="proofFileInput" accept="image/*" style="display:none" onchange="handleProofFile(event)">
            <input type="hidden" id="proofImage">
          </div>
          <div id="proofFileName" style="font-size:11px;color:var(--text-secondary);margin-top:4px"></div>
        </div>
      </div>
      <button class="btn btn-success btn-block btn-lg" onclick="submitProof(${taskId})">📤 Submit Proof</button>
    </div>
  `);
}

function handleProofFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const maxFileSize = 3 * 1024 * 1024;
  if (file.size > maxFileSize) { toast('File too large. Max 3MB.'); event.target.value = ''; return; }
  const el = document.getElementById('proofFileName');
  if (el) el.textContent = '📎 ' + file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
  const btn = document.querySelector('.proof-submit .btn-success');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Compressing...'; }
  const img = new Image();
  const objectUrl = URL.createObjectURL(file);
  img.onload = function() {
    const canvas = document.createElement('canvas');
    let w = img.width, h = img.height;
    const maxDim = 600;
    if (w > maxDim || h > maxDim) {
      if (w > h) { h = (h / w) * maxDim; w = maxDim; }
      else { w = (w / h) * maxDim; h = maxDim; }
    }
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, w, h);
    let quality = 0.6;
    let compressed = canvas.toDataURL('image/jpeg', quality);
    while (compressed.length > 450000 && quality > 0.2) {
      quality -= 0.1;
      compressed = canvas.toDataURL('image/jpeg', quality);
    }
    const input = document.getElementById('proofImage');
    if (input) input.value = compressed;
    if (el) el.textContent += ' (' + (compressed.length / 1024).toFixed(0) + 'KB base64)';
    if (btn) { btn.disabled = false; btn.textContent = '📤 Submit Proof'; }
    // Show preview
    const preview = document.getElementById('proofPreview');
    const placeholder = document.getElementById('proofUploadPlaceholder');
    if (preview) { preview.src = compressed; preview.style.display = 'block'; }
    if (placeholder) placeholder.style.display = 'none';
    URL.revokeObjectURL(objectUrl);
  };
  img.onerror = function() {
    toast('Failed to load image');
    if (btn) { btn.disabled = false; btn.textContent = '📤 Submit Proof'; }
    URL.revokeObjectURL(objectUrl);
  };
  img.src = objectUrl;
}

async function verifyChannelTask(taskId) {
  const btn = document.querySelector('.btn-primary.btn-lg');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Verifying...'; }
  const data = await api('/api/app/task/' + taskId + '/verify-channel', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id }),
    timeout: 15000
  });
  if (data.ok) {
    toast('✅ ' + (data.message || 'Task completed! ₹' + data.reward + ' credited!'));
    if (data.balance !== undefined) updateBalance(data.balance);
    closeModal();
    loadTasks();
  } else {
    if (data.channel_url) {
      if (confirm(data.error + '\n\nOpen channel to join?')) {
        openLink(data.channel_url);
      }
    } else {
      toast(data.error || 'Verification failed');
    }
    if (btn) { btn.disabled = false; btn.textContent = '✅ Verify & Claim'; }
  }
}

async function submitProof(taskId) {
  const proof_image = document.getElementById('proofImage')?.value;
  if (!proof_image) { toast('📸 Please provide a screenshot'); return; }

  const btn = document.querySelector('.proof-submit .btn-success');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Submitting...'; }

  const data = await api('/api/app/task/' + taskId + '/submit', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, proof_image }),
    timeout: 60000
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
  if (!data.ok) { el.innerHTML = ''; return; }
  const items = data.items || [];
  if (items.length === 0) { el.innerHTML = ''; return; }

  function renderCard(p, i) {
    return `
      <div class="promoted-card" onclick="openLink('${p.url||'#'}')">
        <div class="promo-icon" style="background:linear-gradient(135deg,${p.color1||'#7b5ef8'},${p.color2||'#5a3fd6'})">${p.icon||'📢'}</div>
        <div class="promo-info">
          <span class="badge">${p.badge||'⭐ Official Partner'}</span>
          <h4>${p.title}</h4>
          <p>${p.description||''}</p>
        </div>
        <button class="promo-open" onclick="event.stopPropagation();openLink('${p.url||'#'}')">OPEN</button>
      </div>`;
  }

  el.innerHTML = items.map((p, i) => renderCard(p, i)).join('') + items.map((p, i) => renderCard(p, i)).join('');
  el.style.scrollBehavior = 'auto';

  if (!el.scrollWidth || el.scrollWidth <= el.clientWidth) return;

  if (_promoRaf) cancelAnimationFrame(_promoRaf);
  if (_promoResumeTimer) clearTimeout(_promoResumeTimer);

  let paused = false;
  let lastTime = performance.now();
  const pxPerSecond = 80;
  const FRAME_INTERVAL = 1000 / 60;
  let resetActive = false;
  let resetStart = 0;
  let resetFrom = 0;

  function tick(time) {
    if (!paused) {
      var delta = time - lastTime;
      if (delta < FRAME_INTERVAL) {
        _promoRaf = requestAnimationFrame(tick);
        return;
      }
      if (resetActive) {
        var resetProgress = Math.min((time - resetStart) / 300, 1);
        var eased = 1 - Math.pow(1 - resetProgress, 3);
        el.scrollLeft = resetFrom - (resetFrom * eased);
        if (resetProgress >= 1) {
          el.scrollLeft = 0;
          resetActive = false;
        }
      } else {
        el.scrollLeft += pxPerSecond * (delta / 1000);
        if (el.scrollLeft >= el.scrollWidth / 2) {
          resetActive = true;
          resetStart = time;
          resetFrom = el.scrollLeft;
        }
      }
      lastTime = time;
    }
    _promoRaf = requestAnimationFrame(tick);
  }

  function doPause() {
    paused = true;
    if (_promoResumeTimer) clearTimeout(_promoResumeTimer);
  }

  function scheduleResume() {
    if (_promoResumeTimer) clearTimeout(_promoResumeTimer);
    _promoResumeTimer = setTimeout(function() {
      paused = false;
      lastTime = performance.now();
    }, 2000);
  }

  el.removeEventListener('mouseenter', doPause);
  el.removeEventListener('mouseleave', scheduleResume);
  el.removeEventListener('touchstart', doPause);
  el.removeEventListener('touchend', scheduleResume);
  el.addEventListener('mouseenter', doPause);
  el.addEventListener('mouseleave', scheduleResume);
  el.addEventListener('touchstart', doPause, { passive: true });
  el.addEventListener('touchend', scheduleResume, { passive: true });

  _promoRaf = requestAnimationFrame(tick);
}

let promoStep = 1;
let promoData = {};

function showPromoteModal() {
  promoStep = 1;
  promoData = {};
  renderPromoStep1();
}

function renderPromoStep1() {
  promoStep = 1;
  showModal('✨ Promote Here — Step 1/3', `
    <div class="admin-form">
      <div style="display:flex;gap:8px;justify-content:center;margin-bottom:16px">
        <div style="width:32px;height:4px;border-radius:2px;background:var(--primary)"></div>
        <div style="width:32px;height:4px;border-radius:2px;background:var(--border)"></div>
        <div style="width:32px;height:4px;border-radius:2px;background:var(--border)"></div>
      </div>
      <div class="form-group"><label>Type</label>
        <select id="promo_type">
          <option value="promoted">Promoted Item</option>
          <option value="task">Task/Offer</option>
          <option value="ad">Ad Campaign</option>
        </select>
      </div>
      <div class="form-group"><label>Title</label><input id="promo_title" placeholder="Your brand/task name"></div>
      <div class="form-group"><label>Description</label><textarea id="promo_desc" placeholder="Describe what you want to promote" rows="3"></textarea></div>
      <div class="form-group"><label>Accent Color</label><input id="promo_color" type="color" value="#7b5ef8" style="height:44px;padding:4px"></div>
      <div class="form-group"><label>Image URL</label><input id="promo_image" placeholder="https://..."></div>
      <div class="form-group"><label>Link URL</label><input id="promo_url" placeholder="https://..."></div>
      <div class="form-group"><label>Details / Steps</label><textarea id="promo_details" placeholder="Task steps, requirements, or additional info" rows="3"></textarea></div>
      <div id="promoPreview" style="margin:12px 0;padding:14px;border-radius:10px;border:1px solid var(--border);text-align:center">
        <div style="font-size:11px;color:var(--text-secondary);margin-bottom:6px">👁 Preview</div>
        <div id="promoPreviewCard" style="display:flex;align-items:center;gap:10px;padding:10px;background:var(--card);border-radius:8px;border:1px solid var(--border)">
          <div id="promoPreviewIcon" style="width:40px;height:40px;border-radius:8px;background:#7b5ef8;display:flex;align-items:center;justify-content:center;color:#fff;font-size:20px;flex-shrink:0">📢</div>
          <div style="flex:1;text-align:left">
            <div id="promoPreviewTitle" style="font-weight:600;font-size:13px">Your Title</div>
            <div id="promoPreviewDesc" style="font-size:11px;color:var(--text-secondary);margin-top:2px">Description will appear here</div>
          </div>
          <button class="btn btn-sm btn-primary" style="flex-shrink:0;font-size:10px">OPEN</button>
        </div>
      </div>
      <button class="btn btn-primary btn-block" onclick="promoGoStep2()">Next → Payment</button>
    </div>
  `);
  document.getElementById('promo_title')?.addEventListener('input', updatePromoPreview);
  document.getElementById('promo_desc')?.addEventListener('input', updatePromoPreview);
  document.getElementById('promo_color')?.addEventListener('input', updatePromoPreview);
  document.getElementById('promo_image')?.addEventListener('input', updatePromoPreview);
}

function updatePromoPreview() {
  const title = document.getElementById('promo_title')?.value || 'Your Title';
  const desc = document.getElementById('promo_desc')?.value || 'Description will appear here';
  const color = document.getElementById('promo_color')?.value || '#7b5ef8';
  const img = document.getElementById('promo_image')?.value || '';
  const titleEl = document.getElementById('promoPreviewTitle');
  const descEl = document.getElementById('promoPreviewDesc');
  const iconEl = document.getElementById('promoPreviewIcon');
  if (titleEl) titleEl.textContent = title.slice(0, 30);
  if (descEl) descEl.textContent = desc.slice(0, 50);
  if (iconEl) {
    iconEl.style.background = color;
    if (img && img.length > 5) iconEl.innerHTML = '<img src="' + img + '" style="width:100%;height:100%;object-fit:cover;border-radius:8px">';
    else iconEl.textContent = '📢';
  }
}

async function promoGoStep2() {
  const title = document.getElementById('promo_title')?.value?.trim();
  if (!title) { toast('Title is required'); return; }
  promoData = {
    type: document.getElementById('promo_type')?.value || 'promoted',
    title,
    description: document.getElementById('promo_desc')?.value || '',
    details: document.getElementById('promo_details')?.value || '',
    image: document.getElementById('promo_image')?.value || '',
    url: document.getElementById('promo_url')?.value || '',
    color: document.getElementById('promo_color')?.value || '#7b5ef8',
    reward: 0,
  };

  const cfg = await api('/api/app/promo-config?' + new URLSearchParams({ user_id: USER.id }).toString());
  const price = cfg?.promo_price || 50;
  const qr = cfg?.promo_qr_image || '';
  const promoDesc = cfg?.promo_description || 'One-time payment for featured promotion';

  promoStep = 2;
  const modalBody = document.getElementById('modalBody');
  if (!modalBody) return;
  modalBody.innerHTML = `
    <div class="admin-form">
      <div style="display:flex;gap:8px;justify-content:center;margin-bottom:16px">
        <div style="width:32px;height:4px;border-radius:2px;background:var(--success)"></div>
        <div style="width:32px;height:4px;border-radius:2px;background:var(--primary)"></div>
        <div style="width:32px;height:4px;border-radius:2px;background:var(--border)"></div>
      </div>
      <div style="display:flex;align-items:center;gap:10px;padding:12px;background:var(--bg);border-radius:10px;margin-bottom:12px;border:1px solid var(--border)">
        <div style="width:40px;height:40px;border-radius:8px;background:${promoData.color};display:flex;align-items:center;justify-content:center;color:#fff;font-size:20px;flex-shrink:0">📢</div>
        <div style="flex:1">
          <div style="font-weight:600;font-size:13px">${promoData.title.slice(0,30)}</div>
          <div style="font-size:11px;color:var(--text-secondary)">${promoData.description.slice(0,50) || 'No description'}</div>
        </div>
      </div>
      <div style="text-align:center;padding:16px;background:linear-gradient(135deg,#7b5ef8,#a78bfa);border-radius:12px;color:#fff;margin-bottom:12px">
        <div style="font-size:12px;opacity:0.8">${promoDesc}</div>
        <div style="font-size:36px;font-weight:800">₹${price}</div>
        <div style="font-size:11px;opacity:0.7">Price for featured promotion</div>
      </div>
      ${qr ? `<div style="text-align:center;margin-bottom:12px">
        <p style="font-size:12px;color:var(--text-secondary);margin-bottom:8px">📱 Scan QR to pay</p>
        <img src="${cfg.promo_qr_proxy_url}" style="width:180px;height:180px;border-radius:10px;border:1px solid var(--border);object-fit:contain" onerror="fetchImageAsBlob(this,'${cfg.promo_qr_proxy_url}','${qr}')">
      </div>` : `<div style="text-align:center;padding:16px;background:var(--bg);border-radius:10px;margin-bottom:12px;border:1px solid var(--border)">
        <div style="font-size:32px;margin-bottom:4px">📱</div>
        <div style="font-size:12px;color:var(--text-secondary)">QR code not set yet. Contact admin to pay.</div>
      </div>`}
      <p style="font-size:11px;color:var(--text-secondary);text-align:center">Need help? <a href="https://t.me/X_kanha_007" target="_blank" style="color:var(--primary)">Contact Admin</a></p>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="btn btn-outline" style="flex:1" onclick="renderPromoStep1()">← Back</button>
        <button class="btn btn-success" style="flex:1" onclick="promoGoStep3()">✅ I've Paid</button>
      </div>
    </div>
  `;
}

function promoGoStep3() {
  promoStep = 3;
  const modalBody = document.getElementById('modalBody');
  if (!modalBody) return;
  modalBody.innerHTML = `
    <div class="admin-form">
      <div style="display:flex;gap:8px;justify-content:center;margin-bottom:16px">
        <div style="width:32px;height:4px;border-radius:2px;background:var(--success)"></div>
        <div style="width:32px;height:4px;border-radius:2px;background:var(--success)"></div>
        <div style="width:32px;height:4px;border-radius:2px;background:var(--primary)"></div>
      </div>
      <div style="text-align:center;margin-bottom:16px">
        <div style="font-size:40px;margin-bottom:8px">📸</div>
        <h3 style="font-size:16px;font-weight:700">Submit Payment Proof</h3>
        <p style="font-size:12px;color:var(--text-secondary)">Upload your payment screenshot and transaction ID</p>
      </div>
      <div class="form-group"><label>Screenshot / Payment Proof</label>
        <div style="display:flex;gap:8px">
          <input class="form-input" id="promoProofImage" placeholder="Paste image URL or payment link" style="flex:1">
          <button class="btn btn-sm btn-outline" onclick="document.getElementById('promoProofFile').click()" style="white-space:nowrap">📁 Upload</button>
        </div>
        <input type="file" id="promoProofFile" accept="image/*" style="display:none" onchange="handlePromoProofFile(event)">
        <div id="promoProofFileName" style="font-size:11px;color:var(--text-secondary);margin-top:4px"></div>
      </div>
      <div class="form-group"><label>Transaction ID / Reference</label><input class="form-input" id="promoTxnId" placeholder="Enter transaction ID from payment app"></div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-outline" style="flex:1" onclick="promoGoStep2()">← Back</button>
        <button class="btn btn-primary btn-block" style="flex:1" onclick="submitPromotion()">📤 Submit</button>
      </div>
    </div>
  `;
}

function handlePromoProofFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const el = document.getElementById('promoProofFileName');
  if (el) el.textContent = '📎 ' + file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
  if (file.size > 500 * 1024) {
    const img = new Image();
    img.onload = function() {
      const canvas = document.createElement('canvas');
      let w = img.width, h = img.height;
      const maxDim = 800;
      if (w > maxDim || h > maxDim) {
        if (w > h) { h = (h / w) * maxDim; w = maxDim; }
        else { w = (w / h) * maxDim; h = maxDim; }
      }
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, w, h);
      const compressed = canvas.toDataURL('image/jpeg', 0.7);
      const input = document.getElementById('promoProofImage');
      if (input) input.value = compressed;
      if (el) el.textContent += ' (compressed)';
    };
    img.src = URL.createObjectURL(file);
    return;
  }
  const reader = new FileReader();
  reader.onload = function(e) {
    const input = document.getElementById('promoProofImage');
    if (input) input.value = e.target.result;
  };
  reader.readAsDataURL(file);
}

async function submitPromotion() {
  const proofImage = document.getElementById('promoProofImage')?.value || '';
  const txnId = document.getElementById('promoTxnId')?.value || '';
  if (!proofImage && !txnId) { toast('Please provide payment screenshot or transaction ID'); return; }

  const body = { ...promoData, payment_proof: proofImage, transaction_id: txnId };
  const data = await api('/api/app/promote/submit', { method: 'POST', body: JSON.stringify({ ...body, user_id: USER.id }), timeout: 60000 });
  if (data.ok) {
    showModal('✨ Submitted!', `
      <div style="text-align:center;padding:20px">
        <div style="font-size:48px;margin-bottom:12px">✅</div>
        <h3 style="font-weight:700;margin-bottom:8px">Request Sent to Admin!</h3>
        <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px">Your promotion request has been submitted. Admin will review it and once approved, your ad will appear in the Promoted section.</p>
        <div style="padding:12px;background:var(--bg);border-radius:10px;border:1px solid var(--border);margin-bottom:16px">
          <div style="font-size:11px;color:var(--text-secondary)">Need help? Contact admin directly:</div>
          <a href="https://t.me/X_kanha_007" target="_blank" style="color:var(--primary);font-weight:600;font-size:14px;text-decoration:none">@X_kanha_007</a>
        </div>
        <button class="btn btn-primary btn-block" onclick="closeModal()">Done</button>
      </div>
    `);
    loadTasks();
    loadPromoted();
  } else {
    toast(data.error || 'Failed to submit');
  }
}

async function loadAdvertise() {
  const el = document.getElementById('advertiseSection');
  if (!el) return;
  el.innerHTML = '<div class="loading-dots"><div></div><div></div><div></div></div>';

  const [earnData, promoData] = await Promise.all([
    api('/api/app/earn?' + new URLSearchParams({ user_id: USER.id }).toString()),
    api('/api/app/promoted?' + new URLSearchParams({ user_id: USER.id }).toString())
  ]);

  const adGoal = earnData.ad_goal || { current: 0, target: 20, reward: 1, reset_in: '24h', completed: false, no_ads: true };
  const ads = earnData.ads || [];
  const pct = Math.min(100, (adGoal.current / adGoal.target) * 100);
  const items = promoData.items || [];
  const isCompleted = adGoal.completed;

  const perAd = adGoal.target > 0 ? (adGoal.reward / adGoal.target).toFixed(2) : '0.05';

  let goalBody = '';
  if (isCompleted) {
    goalBody = `<div style="text-align:center;padding:16px;font-size:14px;font-weight:700;color:#00e5a0">✅ Target complete! Come back in ${adGoal.reset_in}</div>
    <div style="text-align:center;font-size:11px;color:rgba(255,255,255,0.4);margin-top:4px">Resets at midnight</div>`;
  } else if (ads.length === 0) {
    goalBody = `<div style="text-align:center;padding:16px;font-size:14px;font-weight:700;color:rgba(255,255,255,0.6)">No ads available</div>`;
  } else {
    goalBody = `<div style="text-align:center;margin-bottom:12px;font-size:12px;color:rgba(255,255,255,0.5)">
      Watch ${adGoal.target} ads at ₹${perAd} each to earn ₹${adGoal.reward}
    </div>
    <button class="btn-watch-ad" onclick="watchAdVideo()">▶ WATCH AD TO EARN</button>`;
  }

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
            <div>💰 Per Ad: <b style="color:#00e5a0">₹${perAd}</b></div>
            <div>🔄 Resets: <b style="color:#fff">${adGoal.reset_in}</b></div>
          </div>
        </div>
      </div>
      ${goalBody}
    </div>
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
    <div style="text-align:center;padding:16px;margin-top:8px">
      <button class="btn btn-outline btn-block" onclick="showPromoteModal()">📢 Promote Your Brand Here</button>
      <p style="font-size:10px;color:var(--text-secondary);margin-top:6px">Submit your ad, task, or promotion for admin review</p>
    </div>
  `;
}

async function watchAdVideo() {
  const earnData = await api('/api/app/earn?' + new URLSearchParams({ user_id: USER.id }).toString());
  const ads = earnData.ads || [];
  if (ads.length === 0) { toast('No ads available'); return; }

  const randomAd = ads[Math.floor(Math.random() * ads.length)];
  const videoUrl = randomAd.video_url || '';
  if (!videoUrl) { toast('No video ad available'); return; }

  let adCompleted = false;
  let adCancelled = false;

  try { TG?.BackButton?.hide(); } catch(e) {}

  const overlay = document.createElement('div');
  overlay.id = 'adOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:#000;display:flex;flex-direction:column;align-items:center;justify-content:center';
  overlay.innerHTML = `
    <div id="adTimer" style="position:absolute;top:12px;right:12px;background:rgba(0,0,0,0.7);color:#fff;padding:6px 14px;border-radius:20px;font-size:13px;font-weight:700;z-index:10">Loading...</div>
    <div style="width:100%;max-width:480px;aspect-ratio:16/9;background:#111;border-radius:8px;overflow:hidden;position:relative">
      <video id="adVideoPlayer" style="width:100%;height:100%;object-fit:contain" playsinline webkit-playsinline controlsList="nodownload noplaybackrate">
        <source src="${escHtml(videoUrl)}" type="video/mp4">
      </video>
      <div id="adProgressBar" style="position:absolute;bottom:0;left:0;right:0;height:4px;background:rgba(255,255,255,0.2)">
        <div id="adProgressFill" style="height:100%;background:#00e5a0;width:0%;transition:width 0.3s"></div>
      </div>
    </div>
    <div style="margin-top:16px;font-size:13px;color:rgba(255,255,255,0.7);text-align:center">Watch the full ad to earn reward</div>
  `;
  document.body.appendChild(overlay);

  const video = document.getElementById('adVideoPlayer');
  const timerEl = document.getElementById('adTimer');
  const progressFill = document.getElementById('adProgressFill');

  if (!video) { closeAdOverlay(); return; }

  video.play().catch(() => {});

  video.addEventListener('timeupdate', function onTimeUpdate() {
    if (!video.duration) return;
    const pct = Math.min(100, (video.currentTime / video.duration) * 100);
    if (progressFill) progressFill.style.width = pct + '%';
    const remaining = Math.ceil(video.duration - video.currentTime);
    if (timerEl) timerEl.textContent = remaining + 's remaining';
  });

  video.addEventListener('ended', function onEnded() {
    adCompleted = true;
    if (timerEl) timerEl.textContent = '✅ Complete!';
    if (progressFill) progressFill.style.width = '100%';

    api('/api/app/ad/watch', {
      method: 'POST',
      body: JSON.stringify({ user_id: USER.id, ad_id: randomAd.id })
    }).then(data => {
      if (data.ok) {
        toast('💰 +₹' + (data.amount || '0.10') + ' earned!');
        updateBalance(data.balance || CURRENT_USER.balance);
      }
      setTimeout(closeAdOverlay, 800);
    }).catch(() => {
      setTimeout(closeAdOverlay, 800);
    });
  });

  video.addEventListener('error', function() {
    toast('Video failed to load');
    closeAdOverlay();
  });

  function onVisibilityChange() {
    if (document.hidden && !adCompleted && !adCancelled) {
      adCancelled = true;
      try { video.pause(); } catch(e) {}
      toast('Ad closed early — no reward');
      setTimeout(closeAdOverlay, 300);
    }
  }
  document.addEventListener('visibilitychange', onVisibilityChange);

  window._adCleanup = function() {
    document.removeEventListener('visibilitychange', onVisibilityChange);
    try { TG?.BackButton?.show(); } catch(e) {}
  };
}

function closeAdOverlay() {
  const ov = document.getElementById('adOverlay');
  if (ov) ov.remove();
  if (window._adCleanup) { window._adCleanup(); window._adCleanup = null; }
  try { TG?.BackButton?.show(); } catch(e) {}
}
