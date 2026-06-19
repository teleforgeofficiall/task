var GAME_BETS = [5, 10, 25, 50, 100];
var _gameBet = 10;
var _minesGameId = null;
var _crashGameId = null;
var _crashInterval = null;
var _crashPoint = 0;
var _crashMult = 1.0;
var _crashActive = false;

function loadGames() {
  var el = document.getElementById('gamesSection');
  if (!el) return;
  el.innerHTML = `
    <h3 class="section-title">Games</h3>
    <div class="game-grid" id="gameGrid">
      <div class="game-card" onclick="showGame('dice')">
        <div class="game-icon">🎲</div>
        <h4>Dice</h4>
        <p>Bet & roll</p>
      </div>
      <div class="game-card" onclick="showGame('slots')">
        <div class="game-icon">🎰</div>
        <h4>Slots</h4>
        <p>Spin & match</p>
      </div>
      <div class="game-card" onclick="showGame('mines')">
        <div class="game-icon">💣</div>
        <h4>Mines</h4>
        <p>3x3 grid</p>
      </div>
      <div class="game-card" onclick="showGame('crash')">
        <div class="game-icon">📈</div>
        <h4>Crash</h4>
        <p>Cash out timing</p>
      </div>
    </div>
    <div id="gamePlayArea" style="display:none"></div>
  `;
}

function showGame(game) {
  document.getElementById('gameGrid').style.display = 'none';
  var el = document.getElementById('gamePlayArea');
  el.style.display = 'block';
  _gameBet = 10;
  if (game === 'dice') renderDice(el);
  else if (game === 'slots') renderSlots(el);
  else if (game === 'mines') renderMines(el);
  else if (game === 'crash') renderCrash(el);
}

function backToGames() {
  stopCrash();
  _minesGameId = null;
  _crashGameId = null;
  document.getElementById('gameGrid').style.display = '';
  var el = document.getElementById('gamePlayArea');
  el.style.display = 'none';
  el.innerHTML = '';
}

function betSelector() {
  return '<div class="bet-selector">' + GAME_BETS.map(function (b) {
    var sel = b === _gameBet ? ' selected' : '';
    return '<button class="bet-btn' + sel + '" onclick="selectBet(' + b + ', this)">₹' + b + '</button>';
  }).join('') + '</div>';
}

function selectBet(amount, btn) {
  _gameBet = amount;
  var parent = btn.parentElement;
  if (parent) {
    var btns = parent.querySelectorAll('.bet-btn');
    for (var i = 0; i < btns.length; i++) btns[i].classList.remove('selected');
  }
  btn.classList.add('selected');
}

function gameBackBtn() {
  return '<button class="btn btn-secondary btn-block" onclick="backToGames()" style="margin-top:12px">Back</button>';
}

function showGameResult(content) {
  var el = document.getElementById('gameResult');
  if (el) el.innerHTML = content;
}

// ─── DICE ────────────────────────────────────────────────────────────────────
function renderDice(el) {
  el.innerHTML = `
    <h3 class="section-title">🎲 Dice</h3>
    <p class="game-desc">Roll the dice. Win if 4-6!</p>
    <div class="game-play">
      <div class="dice-display" id="diceDisplay">
        <div class="dice-face" id="diceFace">🎲</div>
        <div class="dice-result" id="diceResult"></div>
      </div>
      <div class="game-bets" id="gameBets">${betSelector()}</div>
      <button class="btn btn-primary btn-block" id="diceRollBtn" onclick="rollDice()">Roll 🎲</button>
      <div id="gameResult" class="game-result"></div>
      ${gameBackBtn()}
    </div>
  `;
}

async function rollDice() {
  var btn = document.getElementById('diceRollBtn');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = 'Rolling...';
  var face = document.getElementById('diceFace');
  if (face) face.textContent = '🎲';
  showGameResult('');
  var res = await api('/api/app/game/dice', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, bet: _gameBet })
  });
  btn.disabled = false;
  btn.textContent = 'Roll 🎲';
  if (!res.ok) { toast(res.error || 'Failed'); return; }
  var roll = res.roll;
  var diceEmojis = ['', '⚀', '⚁', '⚂', '⚃', '⚄', '⚅'];
  if (face) {
    face.textContent = diceEmojis[roll] || '🎲';
    face.className = 'dice-face roll-anim';
    setTimeout(function () { if (face) face.className = 'dice-face'; }, 600);
  }
  var resultEl = document.getElementById('diceResult');
  if (resultEl) {
    if (res.win) {
      resultEl.innerHTML = '<span class="win-text">Win! ₹' + res.payout + ' (x' + res.multiplier + ')</span>';
    } else {
      resultEl.innerHTML = '<span class="lose-text">Lost! Try again.</span>';
    }
  }
  if (res.balance !== undefined) updateBalance(res.balance);
}

// ─── SLOTS ────────────────────────────────────────────────────────────────────
var SLOTS_EMOJI = { 'common': '🍒', 'rare': '🔔', 'epic': '⭐', 'legendary': '👑' };

function renderSlots(el) {
  el.innerHTML = `
    <h3 class="section-title">🎰 Slots</h3>
    <p class="game-desc">Match 3 symbols to win!</p>
    <div class="game-play">
      <div class="slots-display" id="slotsDisplay">
        <div class="slot-reels" id="slotReels">
          <span class="slot-sym">🍒</span>
          <span class="slot-sym">🍒</span>
          <span class="slot-sym">🍒</span>
        </div>
      </div>
      <div class="game-bets">${betSelector()}</div>
      <button class="btn btn-primary btn-block" id="slotsSpinBtn" onclick="spinSlots()">Spin 🎰</button>
      <div id="gameResult" class="game-result"></div>
      ${gameBackBtn()}
    </div>
  `;
}

async function spinSlots() {
  var btn = document.getElementById('slotsSpinBtn');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = 'Spinning...';
  showGameResult('');
  var reelsEl = document.getElementById('slotReels');
  if (reelsEl) {
    reelsEl.innerHTML = '<span class="slot-sym spin-anim">🍒</span><span class="slot-sym spin-anim">🔔</span><span class="slot-sym spin-anim">⭐</span>';
  }
  var res = await api('/api/app/game/slots', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, bet: _gameBet })
  });
  btn.disabled = false;
  btn.textContent = 'Spin 🎰';
  if (!res.ok) { toast(res.error || 'Failed'); return; }
  if (reelsEl && res.reels) {
    var display = res.reels.map(function (s) { return '<span class="slot-sym">' + (SLOTS_EMOJI[s] || s) + '</span>'; }).join('');
    reelsEl.innerHTML = display;
  }
  if (res.win) {
    var msg = 'Win! ₹' + res.payout;
    if (res.jackpot) msg += ' JACKPOT!';
    showGameResult('<span class="win-text">' + msg + ' (x' + res.multiplier + ')</span>');
  } else if (res.near_miss) {
    showGameResult('<span class="near-text">So close! Try again.</span>');
  } else {
    showGameResult('<span class="lose-text">No luck this time.</span>');
  }
  if (res.balance !== undefined) updateBalance(res.balance);
}

// ─── MINES ────────────────────────────────────────────────────────────────────
var _minesRevealed = [];

function renderMines(el) {
  el.innerHTML = `
    <h3 class="section-title">💣 Mines</h3>
    <p class="game-desc">Reveal gems, avoid bombs!</p>
    <div class="game-play">
      <div class="mines-info" id="minesInfo">
        <span>Bet: ₹<span id="minesBetDisplay">${_gameBet}</span></span>
        <span>Gems: <span id="minesGems">0</span></span>
        <span>Multiplier: <span id="minesMult">1.00</span>x</span>
      </div>
      <div class="game-bets" id="minesBets">${betSelector()}</div>
      <div class="mines-grid" id="minesGrid"></div>
      <div class="mines-actions">
        <button class="btn btn-primary" id="minesStartBtn" onclick="minesStart()">Start ▶</button>
        <button class="btn btn-success" id="minesCashoutBtn" onclick="minesCashout()" style="display:none">Cash Out 💰</button>
      </div>
      <div id="gameResult" class="game-result"></div>
      ${gameBackBtn()}
    </div>
  `;
  buildMinesGrid();
}

function buildMinesGrid() {
  var grid = document.getElementById('minesGrid');
  if (!grid) return;
  grid.innerHTML = '';
  for (var i = 0; i < 9; i++) {
    var cell = document.createElement('div');
    cell.className = 'mine-cell';
    cell.dataset.index = i;
    cell.textContent = '?';
    cell.onclick = function () { minesReveal(parseInt(this.dataset.index)); };
    grid.appendChild(cell);
  }
}

function resetMinesGrid() {
  var cells = document.querySelectorAll('.mine-cell');
  for (var i = 0; i < cells.length; i++) {
    cells[i].textContent = '?';
    cells[i].className = 'mine-cell';
  }
  _minesRevealed = [];
  document.getElementById('minesGems').textContent = '0';
  document.getElementById('minesMult').textContent = '1.00';
  document.getElementById('minesCashoutBtn').style.display = 'none';
  document.getElementById('minesStartBtn').style.display = '';
  document.getElementById('minesStartBtn').disabled = false;
  document.getElementById('minesStartBtn').textContent = 'Start ▶';
  var bets = document.getElementById('minesBets');
  if (bets) bets.style.display = '';
  showGameResult('');
}

async function minesStart() {
  var btn = document.getElementById('minesStartBtn');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = 'Starting...';
  var res = await api('/api/app/game/mines/start', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, bet: _gameBet })
  });
  if (!res.ok) { btn.disabled = false; btn.textContent = 'Start ▶'; toast(res.error || 'Failed'); return; }
  _minesGameId = res.game_id;
  var betDisplay = document.getElementById('minesBetDisplay');
  if (betDisplay) betDisplay.textContent = _gameBet;
  document.getElementById('minesBets').style.display = 'none';
  btn.style.display = 'none';
  document.getElementById('minesCashoutBtn').style.display = 'none';
  if (res.balance !== undefined) updateBalance(res.balance);
}

async function minesReveal(index) {
  if (!_minesGameId) { toast('Start a game first!'); return; }
  var cell = document.querySelector('.mine-cell[data-index="' + index + '"]');
  if (!cell || cell.classList.contains('revealed')) return;
  cell.classList.add('revealing');
  var res = await api('/api/app/game/mines/reveal', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, game_id: _minesGameId, cell_index: index })
  });
  if (!res.ok) { cell.classList.remove('revealing'); toast(res.error || 'Failed'); return; }
  if (res.hit) {
    cell.textContent = '💣';
    cell.classList.add('mine');
    cell.classList.remove('revealing');
    showGameResult('<span class="lose-text">💥 Hit a mine! Lost.</span>');
    _minesGameId = null;
    setTimeout(resetMinesGrid, 1500);
  } else {
    cell.textContent = '💎';
    cell.classList.add('gem');
    cell.classList.remove('revealing');
    _minesRevealed.push(index);
    document.getElementById('minesGems').textContent = res.gems_found;
    document.getElementById('minesMult').textContent = res.multiplier.toFixed(2);
    document.getElementById('minesCashoutBtn').style.display = '';
    if (res.balance !== undefined) updateBalance(res.balance);
  }
}

async function minesCashout() {
  if (!_minesGameId) return;
  var btn = document.getElementById('minesCashoutBtn');
  if (btn) btn.disabled = true;
  var res = await api('/api/app/game/mines/cashout', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, game_id: _minesGameId })
  });
  if (!res.ok) { if (btn) btn.disabled = false; toast(res.error || 'Failed'); return; }
  showGameResult('<span class="win-text">Cashed out! ₹' + res.payout + ' (x' + res.multiplier + ')</span>');
  _minesGameId = null;
  if (res.balance !== undefined) updateBalance(res.balance);
  setTimeout(resetMinesGrid, 2000);
}

// ─── CRASH ────────────────────────────────────────────────────────────────────
function renderCrash(el) {
  el.innerHTML = `
    <h3 class="section-title">📈 Crash</h3>
    <p class="game-desc">Cash out before it crashes!</p>
    <div class="game-play">
      <div class="crash-display" id="crashDisplay">
        <div class="crash-mult" id="crashMult">1.00x</div>
        <div class="crash-status" id="crashStatus">Place your bet</div>
      </div>
      <div class="game-bets" id="crashBets">${betSelector()}</div>
      <div class="crash-actions">
        <button class="btn btn-primary" id="crashStartBtn" onclick="crashStart()">Bet & Start ▶</button>
        <button class="btn btn-success" id="crashCashoutBtn" onclick="crashCashout()" style="display:none">Cash Out 💰</button>
      </div>
      <div id="gameResult" class="game-result"></div>
      ${gameBackBtn()}
    </div>
  `;
}

function stopCrash() {
  if (_crashInterval) { clearInterval(_crashInterval); _crashInterval = null; }
  _crashActive = false;
  _crashGameId = null;
}

async function crashStart() {
  var startBtn = document.getElementById('crashStartBtn');
  if (!startBtn) return;
  startBtn.disabled = true;
  startBtn.textContent = 'Starting...';
  stopCrash();
  showGameResult('');
  var res = await api('/api/app/game/crash/start', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, bet: _gameBet })
  });
  if (!res.ok) { startBtn.disabled = false; startBtn.textContent = 'Bet & Start ▶'; toast(res.error || 'Failed'); return; }
  _crashGameId = res.game_id;
  _crashMult = 1.0;
  _crashActive = true;
  document.getElementById('crashBets').style.display = 'none';
  startBtn.style.display = 'none';
  document.getElementById('crashCashoutBtn').style.display = '';
  document.getElementById('crashStatus').textContent = 'Waiting...';
  document.getElementById('crashMult').textContent = '1.00x';
  document.getElementById('crashMult').className = 'crash-mult';
  if (res.balance !== undefined) updateBalance(res.balance);
  setTimeout(function () {
    if (_crashActive) crashFetchResult();
  }, 800);
}

async function crashFetchResult() {
  if (!_crashGameId || !_crashActive) return;
  var res = await api('/api/app/game/crash/result', {
    method: 'POST',
    body: JSON.stringify({ game_id: _crashGameId, user_id: USER.id })
  });
  if (!res.ok || !res.crash_point) { crashBust(); return; }
  _crashPoint = res.crash_point;
  document.getElementById('crashStatus').textContent = 'Running...';
  _crashInterval = setInterval(function () {
    if (!_crashActive) return;
    _crashMult += 0.01 + (_crashMult * 0.003);
    if (_crashMult >= _crashPoint) {
      crashBust();
      return;
    }
    var el = document.getElementById('crashMult');
    if (el) el.textContent = _crashMult.toFixed(2) + 'x';
  }, 50);
}

function crashBust() {
  _crashActive = false;
  if (_crashInterval) { clearInterval(_crashInterval); _crashInterval = null; }
  var el = document.getElementById('crashMult');
  if (el) {
    el.textContent = _crashPoint.toFixed(2) + 'x';
    el.className = 'crash-mult busted';
  }
  document.getElementById('crashStatus').textContent = 'Crashed! 💥';
  document.getElementById('crashCashoutBtn').style.display = 'none';
  showGameResult('<span class="lose-text">Busted at ' + _crashPoint.toFixed(2) + 'x</span>');
  _crashGameId = null;
  setTimeout(resetCrash, 2000);
}

async function crashCashout() {
  if (!_crashGameId || !_crashActive) return;
  _crashActive = false;
  if (_crashInterval) { clearInterval(_crashInterval); _crashInterval = null; }
  var btn = document.getElementById('crashCashoutBtn');
  if (btn) btn.disabled = true;
  var mult = _crashMult;
  var res = await api('/api/app/game/crash/cashout', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, game_id: _crashGameId, cashout_mult: mult })
  });
  if (!res.ok) {
    if (res.crash_point) {
      var el = document.getElementById('crashMult');
      if (el) {
        el.textContent = res.crash_point.toFixed(2) + 'x';
        el.className = 'crash-mult busted';
      }
      document.getElementById('crashStatus').textContent = 'Crashed! 💥';
      showGameResult('<span class="lose-text">Already crashed at ' + res.crash_point.toFixed(2) + 'x</span>');
    } else {
      toast(res.error || 'Failed');
    }
    _crashGameId = null;
    setTimeout(resetCrash, 2000);
    return;
  }
  var el = document.getElementById('crashMult');
  if (el) {
    el.textContent = mult.toFixed(2) + 'x';
    el.className = 'crash-mult won';
  }
  document.getElementById('crashStatus').textContent = 'Cashed out!';
  document.getElementById('crashCashoutBtn').style.display = 'none';
  showGameResult('<span class="win-text">Cashed out at ' + mult.toFixed(2) + 'x! ₹' + res.payout + '</span>');
  _crashGameId = null;
  if (res.balance !== undefined) updateBalance(res.balance);
  setTimeout(resetCrash, 2000);
}

function resetCrash() {
  stopCrash();
  document.getElementById('crashBets').style.display = '';
  var startBtn = document.getElementById('crashStartBtn');
  if (startBtn) { startBtn.style.display = ''; startBtn.disabled = false; startBtn.textContent = 'Bet & Start ▶'; }
  var cashoutBtn = document.getElementById('crashCashoutBtn');
  if (cashoutBtn) cashoutBtn.style.display = 'none';
  var multEl = document.getElementById('crashMult');
  if (multEl) { multEl.textContent = '1.00x'; multEl.className = 'crash-mult'; }
  var statusEl = document.getElementById('crashStatus');
  if (statusEl) statusEl.textContent = 'Place your bet';
  showGameResult('');
}
