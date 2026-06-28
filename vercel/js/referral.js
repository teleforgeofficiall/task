let BOT_USERNAME = '';

async function loadReferral() {
  const el = document.getElementById('inviteSection');
  if (!el) return;

  const refData = await api('/api/app/refer?' + new URLSearchParams({ user_id: USER.id }).toString());

  const ref = refData.referral || { code: '—', total: 0, active: 0, earned: 0, referrals: [] };
  const perReferReward = refData.per_refer_reward || 0;
  const isPaused = refData.referral_paused || false;

  BOT_USERNAME = refData.bot_username || TG?.initDataUnsafe?.bot_username || 'taskhubpocketbot';
  const referralLink = `https://t.me/${BOT_USERNAME}?start=${USER.id}`;

  el.innerHTML = `
    <div class="ref-hero">
      <h2>🚀 Invite & Earn</h2>
      <p>Share your link with friends. Earn rewards when they complete tasks!</p>

      ${isPaused ? '<div class="ref-paused-banner">⚠️ Referral program is currently paused</div>' : ''}

      <div class="ref-link-box">
        <div class="link-label">Your Invite Link</div>
        <div class="link-text" id="refLinkText">${referralLink}</div>
      </div>

      <div class="ref-actions">
        <button class="ref-btn ref-btn-copy" onclick="copyReferralLink('${referralLink}')">📋 Copy Link</button>
        <button class="ref-btn ref-btn-share" onclick="shareReferralLink('${referralLink}')">📤 Share</button>
      </div>
    </div>

    <div class="ref-per-refer">
      <span class="per-refer-label">Per Referral Reward:</span>
      <span class="per-refer-amount">${formatCurrency(perReferReward)}</span>
    </div>

    <blockquote class="ref-note">Note: Your referred user must complete at least <b>1 task</b> before you receive the referral reward.</blockquote>

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

    <h3 class="section-title">👥 Your Friends (${ref.total})</h3>
    <div class="ref-list" id="refList">
      ${(ref.referrals || []).length > 0
        ? ref.referrals.slice(0, 10).map(r => renderReferralItem(r)).join('')
        : '<div class="empty-state">No friends yet. Share your invite link!</div>'
      }
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
