function loadGames() {
  const el = document.getElementById('gamesSection');
  if (!el) return;
  el.innerHTML = `
    <h3 class="section-title">🎮 Games</h3>
    <div class="game-grid">
      <div class="game-card coming-soon animate-in fade stagger-1" onclick="toast('Coming soon!')">
        <div class="game-icon">🎲</div>
        <h4>Dice</h4>
        <p>Heads or Tails</p>
      </div>
      <div class="game-card coming-soon animate-in fade stagger-2" onclick="toast('Coming soon!')">
        <div class="game-icon">🎰</div>
        <h4>Slots</h4>
        <p>Spin to win</p>
      </div>
      <div class="game-card coming-soon animate-in fade stagger-3" onclick="toast('Coming soon!')">
        <div class="game-icon">💣</div>
        <h4>Mines</h4>
        <p>Click to reveal</p>
      </div>
      <div class="game-card coming-soon animate-in fade stagger-4" onclick="toast('Coming soon!')">
        <div class="game-icon">📈</div>
        <h4>Crash</h4>
        <p>Cash out timing</p>
      </div>
    </div>
  `;
}
