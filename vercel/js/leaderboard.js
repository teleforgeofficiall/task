async function loadLeaderboard() {
  const el = document.getElementById('topSection');
  if (!el) return;
  el.innerHTML = '<div class="loading-dots"><div></div><div></div><div></div></div>';

  const data = await api('/api/app/leaderboard?' + new URLSearchParams({ user_id: USER.id }).toString());
  const leaders = data.leaders || [];
  const myRank = data.my_rank || '-';
  const myEarnings = data.my_earnings || 0;

  if (leaders.length === 0) {
    el.innerHTML = '<div class="empty-state">No leaderboard data yet</div>';
    return;
  }

  const top3 = leaders.slice(0, 3);
  const rest = leaders.slice(3, 10);

  el.innerHTML = `
    <div class="card leaderboard-header" style="background:var(--primary-gradient);color:#fff;border:none">
      <h3 style="margin-bottom:4px">🏆 Top Earners</h3>
      <p style="opacity:0.7;font-size:12px">Top 10 users by earnings</p>
    </div>

    <div class="podium-container">
      ${renderPodiumItem(top3[1], 2, '#C0C0C0', 'podium-2')}  <!-- #2 Left -->
      ${renderPodiumItem(top3[0], 1, '#FFD700', 'podium-1')}  <!-- #1 Center -->
      ${renderPodiumItem(top3[2], 3, '#CD7F32', 'podium-3')}  <!-- #3 Right -->
    </div>

    <div class="top10-list">
      ${rest.map((l, i) => renderTop10Item(l, i + 4)).join('')}
    </div>

    <div class="my-rank-card animate-in">
      <div class="rank-label">Your Rank</div>
      <div class="rank-value">#${myRank}</div>
      <div class="earnings-value" id="myEarningsCounter">${formatCurrency(myEarnings)}</div>
      <div class="rank-label">Lifetime Earnings</div>
    </div>

    <div class="leaderboard-refresh">🔄 Updates every 30 seconds</div>
  `;

  // Start auto-refresh
  if (_leaderboardInterval) clearInterval(_leaderboardInterval);
  _leaderboardInterval = setInterval(() => {
    loadLeaderboard();
  }, 30000);

}

function renderPodiumItem(user, rank, color, className) {
  if (!user) return `<div class="podium-item ${className}" style="opacity:0.3"><div class="podium-rank" style="background:${color}">${rank}</div><div class="podium-name">—</div></div>`;

  const name = user.name || 'User';
  const earnings = user.earnings || 0;
  const initial = getInitials(name);
  const avColors = ['#7b5ef8','#00e5a0','#ffab00','#ff4f5e','#1976d2','#388e3c','#f57c00','#c62828'];
  const bgColor = avColors[initial.charCodeAt(0) % avColors.length];
  const pfpUrl = user.pfp || '';
  const sz = rank === 1 ? 64 : 56;
  const bColors = {1:'#FFD700',2:'#A8A8A8',3:'#CD7F32'};
  const bColor = bColors[rank] || '#A8A8A8';

  return `
    <div class="podium-item ${className} animate-in scale stagger-${rank}">
      ${rank === 1 ? '<div class="podium-crown">👑</div>' : ''}
      <div style="position:relative;width:${sz}px;height:${sz}px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:${bgColor};flex-shrink:0;margin-bottom:8px;border:3px solid ${bColor}">
        <span style="color:#fff;font-weight:700;font-size:${Math.round(sz*0.35)}px;line-height:1;pointer-events:none">${initial}</span>
        ${pfpUrl ? `<img src="${escHtml(pfpUrl)}" alt="${name}" style="position:absolute;inset:0;width:100%;height:100%;border-radius:50%;object-fit:cover" onerror="this.style.display='none'">` : ''}
      </div>
      <div class="podium-rank" style="background:${color}">${rank}</div>
      <div class="podium-name">${name}</div>
      <div class="podium-earnings" data-target="${earnings}">${formatCurrency(earnings)}</div>
      <div class="podium-label">${rank === 1 ? '🥇 Gold' : rank === 2 ? '🥈 Silver' : '🥉 Bronze'}</div>
    </div>
  `;
}

function renderTop10Item(user, rank) {
  if (!user) return '';
  const name = user.name || 'User';
  const earnings = user.earnings || 0;
  const initial = getInitials(name);
  const avColors = ['#7b5ef8','#00e5a0','#ffab00','#ff4f5e','#1976d2','#388e3c','#f57c00','#c62828'];
  const bgColor = avColors[initial.charCodeAt(0) % avColors.length];
  const pfpUrl = user.pfp || '';
  const rankClass = rank <= 3 ? ['rank-gold', 'rank-silver', 'rank-bronze'][rank - 1] : 'rank-default';

  return `
    <div class="top10-item animate-in fade stagger-${rank}">
      <div class="top10-rank ${rankClass}">${rank}</div>
      <div style="position:relative;width:36px;height:36px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:${bgColor};flex-shrink:0;overflow:hidden">
        <span style="color:#fff;font-weight:700;font-size:13px;line-height:1;pointer-events:none">${initial}</span>
        ${pfpUrl ? `<img src="${escHtml(pfpUrl)}" alt="${name}" style="position:absolute;inset:0;width:100%;height:100%;border-radius:50%;object-fit:cover" onerror="this.style.display='none'">` : ''}
      </div>
      <div class="top10-name">${name}</div>
      <div class="top10-earnings">${formatCurrency(earnings)}</div>
    </div>
  `;
}
