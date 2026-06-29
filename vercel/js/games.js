var _gameBet = 10;
var _minesGameId = null;

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
      <div class="game-card" onclick="showGame('mines')">
        <div class="game-icon">💣</div>
        <h4>Mines</h4>
        <p>3x3 grid</p>
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
  else if (game === 'mines') renderMines(el);
}

function backToGames() {
  _minesGameId = null;
  document.getElementById('gameGrid').style.display = '';
  var el = document.getElementById('gamePlayArea');
  el.style.display = 'none';
  el.innerHTML = '';
}

function betSelector() {
  return '<div class="bet-selector"><input type="number" class="bet-input" id="betInput" min="2" max="50" step="1" value="' + _gameBet + '" oninput="updateBet(this)"><span class="bet-label">Min ₹2 · Max ₹50</span></div>';
}

function updateBet(el) {
  var v = parseInt(el.value) || 2;
  if (v < 2) v = 2;
  if (v > 50) v = 50;
  el.value = v;
  _gameBet = v;
}

function syncBet() {
  var el = document.getElementById('betInput');
  if (el) updateBet(el);
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
  syncBet();
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
  syncBet();
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

