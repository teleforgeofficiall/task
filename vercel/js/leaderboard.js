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

  // Load real profile photos in background (only if pfp URL exists and image loads)
  setTimeout(function() {
    document.querySelectorAll('[data-pfp]').forEach(function(el) {
      var url = el.getAttribute('data-pfp');
      if (!url) return;
      var img = new Image();
      img.onload = function() {
        if (img.naturalWidth > 10 && img.naturalHeight > 10) { el.src = url; }
      };
      img.src = url;
    });
  }, 100);
}

function renderPodiumItem(user, rank, color, className) {
  if (!user) return `<div class="podium-item ${className}" style="opacity:0.3"><div class="podium-rank" style="background:${color}">${rank}</div><div class="podium-name">—</div></div>`;

  const name = user.name || 'User';
  const earnings = user.earnings || 0;
  const fallback = getAvatarSvg(name);
  const pfpUrl = user.pfp || '';

  return `
    <div class="podium-item ${className} animate-in scale stagger-${rank}">
      ${rank === 1 ? '<div class="podium-crown">👑</div>' : ''}
      <img class="podium-pfp" src="${fallback}" data-pfp="${escHtml(pfpUrl)}" alt="${name}">
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
  const fallback = getAvatarSvg(name);
  const pfpUrl = user.pfp || '';
  const rankClass = rank <= 3 ? ['rank-gold', 'rank-silver', 'rank-bronze'][rank - 1] : 'rank-default';

  return `
    <div class="top10-item animate-in fade stagger-${rank}">
      <div class="top10-rank ${rankClass}">${rank}</div>
      <img class="top10-pfp" src="${fallback}" data-pfp="${escHtml(pfpUrl)}" alt="${name}">
      <div class="top10-name">${name}</div>
      <div class="top10-earnings">${formatCurrency(earnings)}</div>
    </div>
  `;
}
