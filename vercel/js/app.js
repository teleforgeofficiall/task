let USER = null;
let CURRENT_USER = null;
let NAV_ITEMS = [];
let _initDone = false;
let _leaderboardInterval = null;

try { TG?.ready(); } catch(e) {}
try { TG?.expand(); } catch(e) {}

let _init5sTimer = setTimeout(() => {
  if (document.getElementById('loadingScreen')?.classList.contains('active')) {
    showError('Taking longer than expected...', 'Will retry automatically. Check your connection.');
  }
}, 10000);

function switchScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}

async function init() {
  if (_initDone) return;
  _initDone = true;
  clearTimeout(_init5sTimer);
  const MIN_LOAD = 1500;
  const loadStart = Date.now();

  setLoadingStatus('Checking Telegram...');
  let initData = TG?.initData || '';
  let user = TG?.initDataUnsafe?.user;

  if (!user) {
    try {
      let p = new URLSearchParams(window.location.search);
      let raw = p.get('tgWebAppData');
      if (!raw && window.location.hash) {
        raw = new URLSearchParams(window.location.hash.slice(1)).get('tgWebAppData');
      }
      if (raw) {
        let dp = new URLSearchParams(raw);
        let userStr = dp.get('user');
        if (userStr) {
          user = JSON.parse(userStr);
          initData = raw;
          if (!window.TG) window.TG = {};
          window.TG.initData = initData;
          window.TG.initDataUnsafe = { user: user };
        }
      }
    } catch(e) {}

    if (!user) {
      try {
        let p = new URLSearchParams(window.location.search);
        let uid = p.get('user_id');
        if (uid) {
          user = { id: parseInt(uid) };
          initData = '';
        }
      } catch(e) {}
    }

    if (!user) {
      showError('Not in Telegram', 'This Mini App only works inside Telegram.\n\nOpen the bot and tap "Open MiniApp".', [
        { text: '📱 Open Bot', cls: 'btn-primary', onclick: 'openLink(\'https://t.me/Taskhubpocketbot\')' }
      ]);
      return;
    }
  }
  USER = user;

  setLoadingStatus('Testing connection...');
  const health = await api('/api/health');
  if (!health.ok || health.status !== 'healthy') {
    showError('Backend offline', 'Server not responding. Try again later.');
    return;
  }

  setLoadingStatus('Loading your data...');
  const startParam = TG?.initDataUnsafe?.start_param || '';
  const urlParams = new URLSearchParams(window.location.search);
  const startFromUrl = urlParams.get('start') || '';
  const startapp = startParam || startFromUrl;
  const params = new URLSearchParams({ user_id: user.id, init_data: initData, hash: '' });
  if (startapp) params.set('startapp', startapp);
  const data = await api('/api/app/init?' + params.toString());

  if (!data.ok) {
    showError('Init failed', data.error || 'Unknown server error');
    return;
  }
  CURRENT_USER = data.user;

  const elapsed = Date.now() - loadStart;
  const remaining = Math.max(0, MIN_LOAD - elapsed);

  if (data.channels_unjoined?.length > 0) {
    setTimeout(() => { switchScreen('channelScreen'); renderChannels(data.channels_unjoined); }, remaining);
    return;
  }
  if (!data.welcome_bonus_claimed) {
    setTimeout(() => {
      switchScreen('bonusScreen');
      document.getElementById('bonusAmount').textContent = '₹' + (data.welcome_bonus || 5);
    }, remaining);
    return;
  }

  setTimeout(() => enterApp(data), remaining);
}

function renderChannels(channels) {
  const el = document.getElementById('channelList');
  if (!el) return;
  el.innerHTML = channels.map(c => `
    <div class="channel-item" data-id="${c.id}">
      <div class="channel-icon">📢</div>
      <div class="channel-info">
        <h4>${c.title || 'Channel ' + c.id}</h4>
        <p>Join and come back to verify</p>
      </div>
      <div class="channel-check" id="chk_${c.id}">✓</div>
    </div>
  `).join('');
}

async function checkChannels() {
  const data = await api('/api/app/check-channels?' + new URLSearchParams({ user_id: USER.id }).toString());
  if (data.ok && data.all_joined) {
    init();
  } else if (data.joined) {
    data.joined.forEach(id => {
      const chk = document.getElementById('chk_' + id);
      if (chk) { chk.classList.add('checked'); document.querySelector(`.channel-item[data-id="${id}"]`)?.classList.add('verified'); }
    });
    toast('Join all channels to continue');
  } else {
    toast('Please join all channels first');
  }
}

async function claimWelcomeBonus() {
  const btn = document.querySelector('#bonusScreen .btn-success');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Claiming...'; }
  const data = await api('/api/app/claim-bonus', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, type: 'welcome' })
  });
  if (data.ok) {
    toast('🎁 Welcome bonus claimed! ₹' + data.amount);
    if (CURRENT_USER) CURRENT_USER.balance = (CURRENT_USER.balance || 0) + data.amount;
    setTimeout(() => {
      const params = new URLSearchParams({ user_id: USER.id, init_data: TG?.initData || '', hash: '' });
      api('/api/app/init?' + params.toString()).then(d => {
        if (d.ok) enterApp(d);
        else init();
      });
    }, 300);
  } else {
    toast(data.error || 'Failed to claim');
    if (btn) { btn.disabled = false; btn.textContent = '🎁 Claim Bonus'; }
  }
}

function enterApp(data) {
  CURRENT_USER = data.user;
  const pfp = document.getElementById('headerPfp');
  const nameEl = document.getElementById('headerName');
  const idEl = document.getElementById('headerId');

  if (pfp) {
    var fallback = getAvatarSvg(data.user.first_name || 'U');
    pfp.src = data.user.pfp || fallback;
    pfp.dataset.fallback = fallback;
  }
  if (nameEl) nameEl.textContent = data.user.first_name || 'User';
  if (idEl) idEl.textContent = 'ID: ' + data.user.id;
  updateBalance(data.user.balance || 0);

  const isAdmin = data.is_admin || false;
  NAV_ITEMS = [
    { id: 'Tasks', icon: '<svg viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 14l2 2 4-4"/></svg>', label: 'Tasks' },
    { id: 'Top', icon: '<svg viewBox="0 0 24 24"><path d="M6 20V4"/><path d="M12 20V10"/><path d="M18 20V6"/></svg>', label: 'Top' },
    { id: 'Invite', icon: '<svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>', label: 'Invite' },
    { id: 'Wallet', icon: '<svg viewBox="0 0 24 24"><rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/><circle cx="18" cy="12" r="2"/></svg>', label: 'Wallet' },
    { id: 'Advertise', icon: '<svg viewBox="0 0 24 24"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>', label: 'Earn' },
    { id: 'Bonus', icon: '<svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>', label: 'Bonus' },
    { id: 'Games', icon: '<svg viewBox="0 0 24 24"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 12h4M8 10v4"/><circle cx="16" cy="10" r="1"/><circle cx="16" cy="14" r="1"/><circle cx="20" cy="10" r="1"/><circle cx="20" cy="14" r="1"/></svg>', label: 'Games' },
  ];

  if (isAdmin) {
    NAV_ITEMS.push({ id: 'Admin', icon: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>', label: 'Admin' });
  }

  renderNav();
  switchScreen('mainScreen');
  navigateTab('Tasks');

  // Auto-navigate to referred task if coming from referral link
  const _urlParams = new URLSearchParams(window.location.search);
  const _startParam = TG?.initDataUnsafe?.start_param || '';
  const autoTask = _startParam || _urlParams.get('start') || '';
  if (autoTask.startsWith('ref_')) {
    const parts = autoTask.split('_');
    if (parts.length >= 4 && parts[2] === 'task') {
      const taskId = parseInt(parts[3]);
      if (taskId > 0) {
        setTimeout(() => showTaskDetail(taskId), 800);
      }
    }
  }
}

function updateBalance(bal) {
  const el = document.getElementById('headerBalance');
  if (el) el.textContent = formatCurrency(bal || 0);
}

function renderNav() {
  const el = document.getElementById('bottomNav');
  if (!el) return;
  el.innerHTML = NAV_ITEMS.map(item => `
    <button class="nav-item" data-tab="${item.id.toLowerCase()}" onclick="navigateTab('${item.id}')">
      ${item.icon}
      <span>${item.label}</span>
    </button>
  `).join('');
}

function navigateTab(name) {
  const tabId = name.toLowerCase();
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelector(`.nav-item[data-tab="${tabId}"]`)?.classList.add('active');
  document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));

  const tabNames = { tasks: 'Tasks', top: 'Top', advertise: 'Advertise', wallet: 'Wallet', invite: 'Invite', bonus: 'Bonus', games: 'Games', admin: 'Admin' };
  const tabName = tabNames[tabId] || name;
  const tab = document.getElementById('tab' + tabName);

  if (tab) {
    tab.classList.add('active');
    loadTab(tabName);
  }
}

function loadTab(name) {
  switch(name) {
    case 'Tasks': loadTasks(); loadPromoted(); loadTasksAds(); break;
    case 'Top': loadLeaderboard(); break;
    case 'Invite': loadReferral(); break;
    case 'Wallet': loadWallet(); break;
    case 'Advertise': loadAdvertise(); break;
    case 'Bonus': loadBonus(); break;
    case 'Games': loadGames(); break;
    case 'Admin': loadAdmin(); break;
  }
}
