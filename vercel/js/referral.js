let BOT_USERNAME = '';

async function loadReferral() {
  const el = document.getElementById('inviteSection');
  if (!el) return;

  const [refData, taskData] = await Promise.all([
    api('/api/app/refer?' + new URLSearchParams({ user_id: USER.id }).toString()),
    api('/api/app/tasks?' + new URLSearchParams({ user_id: USER.id }).toString())
  ]);

  const ref = refData.referral || { code: '—', total: 0, active: 0, earned: 0, referrals: [] };
  const tasks = (taskData.tasks || []).filter(t => t.max_completers > 0);

  // Extract bot username from initData or use fallback
  BOT_USERNAME = refData.bot_username || TG?.initDataUnsafe?.bot_username || 'taskhubpocketbot';
  const referralLink = `https://t.me/${BOT_USERNAME}?start=${USER.id}`;

  el.innerHTML = `
    <!-- Hero Card with Link -->
    <div class="ref-hero">
      <h2>🚀 Invite & Earn</h2>
      <p>Share your link with friends. Earn commission when they complete tasks!</p>

      <div class="ref-link-box">
        <div class="link-label">Your Invite Link</div>
        <div class="link-text" id="refLinkText">${referralLink}</div>
      </div>

      <div class="ref-actions">
        <button class="ref-btn ref-btn-copy" onclick="copyReferralLink('${referralLink}')">📋 Copy Link</button>
        <button class="ref-btn ref-btn-share" onclick="shareReferralLink('${referralLink}')">📤 Share</button>
      </div>
    </div>

    <!-- Stats Grid -->
    <div class="ref-stats-grid">
      <div class="ref-stat-card animate-in fade stagger-1">
        <div class="stat-icon">👥</div>
        <div class="stat-value" id="refTotalCount">${ref.total}</div>
        <div class="stat-label">Total Referrals</div>
      </div>
      <div class="ref-stat-card animate-in fade stagger-2">
        <div class="stat-icon">✅</div>
        <div class="stat-value" id="refActiveCount">${ref.active}</div>
        <div class="stat-label">Active Referrals</div>
      </div>
      <div class="ref-stat-card animate-in fade stagger-3">
        <div class="stat-icon">💰</div>
        <div class="stat-value">${formatCurrency(ref.earned || 0)}</div>
        <div class="stat-label">Total Earned</div>
      </div>
      <div class="ref-stat-card animate-in fade stagger-4">
        <div class="stat-icon">📊</div>
        <div class="stat-value" id="refRateCount">${ref.total > 0 ? Math.round((ref.active / ref.total) * 100) : 0}%</div>
        <div class="stat-label">Conversion Rate</div>
      </div>
    </div>

    <!-- Reward Tiers -->
    <h3 class="section-title">🏆 Reward Tiers</h3>
    <div class="ref-tiers">
      ${renderTier('🥉', 'Bronze', '0-5', '1x', ref.total >= 0 && ref.total < 6)}
      ${renderTier('🥈', 'Silver', '6-15', '1.5x', ref.total >= 6 && ref.total < 16)}
      ${renderTier('🥇', 'Gold', '16-30', '2x', ref.total >= 16 && ref.total < 31)}
      ${renderTier('💎', 'Diamond', '30+', '3x', ref.total >= 31)}
    </div>

    <!-- Referral List -->
    <h3 class="section-title">👥 Your Friends (${ref.total})</h3>
    <div class="ref-list" id="refList">
      ${(ref.referrals || []).length > 0
        ? ref.referrals.slice(0, 10).map(r => renderReferralItem(r)).join('')
        : '<div class="empty-state">No friends yet. Share your invite link!</div>'
      }
    </div>

    ${renderAffiliateTasks(tasks)}
  `;
}

function renderTier(icon, name, range, reward, isActive) {
  return `
    <div class="tier-card ${isActive ? 'tier-active' : ''}">
      <div class="tier-icon">${icon}</div>
      <div class="tier-name">${name}</div>
      <div class="tier-range">${range} referrals</div>
      <div class="tier-reward">${reward}</div>
    </div>
  `;
}

function renderReferralItem(r) {
  const name = r.name || 'User ' + r.id;
  return `
    <div class="ref-list-item animate-in fade">
      <div class="ref-list-pfp">${getInitials(name)}</div>
      <div class="ref-list-info">
        <div class="name">${name}</div>
        <div class="status ${r.active ? 'active' : 'inactive'}">${r.active ? '✅ Active' : '⏳ Pending'}</div>
      </div>
      <div class="ref-list-earnings">+${formatCurrency(r.earned || 0)}</div>
    </div>
  `;
}

function renderAffiliateTasks(tasks) {
  if (tasks.length === 0) return '';
  return `
    <div class="affiliate-section">
      <h3 class="section-title">🤝 Affiliate Tasks</h3>
      <p style="font-size:11px;color:var(--text-secondary);margin-bottom:8px">Share these tasks — earn referrer reward when someone completes!</p>
      ${tasks.map(t => `
        <div class="card affiliate-task-card animate-in fade">
          <div class="task-row">
            <div class="task-title">${t.title}</div>
            <div class="task-progress">${t.current_completers || 0}/${t.max_completers}</div>
          </div>
          <div class="task-rewards">
            <span class="referrer-reward">You earn: ₹${t.referrer_reward}</span>
            <span style="color:var(--text-secondary)">|</span>
            <span class="completer-reward">Completer: ₹${t.completer_reward}</span>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function copyReferralLink(link) {
  copyToClipboard(link, '✅ Invite link copied!');
}

function shareReferralLink(link) {
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent('🚀 Join me on TaskHub and start earning! Complete tasks and get rewards.')}`;
  if (TG?.openTelegramLink) {
    TG.openTelegramLink(shareUrl);
  } else if (TG?.openLink) {
    TG.openLink(shareUrl);
  } else {
    window.open(shareUrl, '_blank');
  }
}
