async function loadBonus() {
  const el = document.getElementById('dailyBonusSection');
  if (!el) return;

  const data = await api('/api/app/bonus?' + new URLSearchParams({ user_id: USER.id }).toString());
  const canClaim = data.can_claim;
  const day = data.day || 1;
  const amount = data.amount || 1;
  const streak = data.streak || 0;
  const nextIn = data.next_in || '';

  el.innerHTML = `
    <div class="bonus-hero animate-in">
      <h2>🎁 Daily Bonus</h2>
      <div class="bonus-amount" id="dailyBonusAmount">₹${amount}</div>
      <div class="bonus-sub">Day ${day}${streak > 0 ? ` • ${streak} day streak 🔥` : ''}</div>
      ${canClaim
        ? `<button class="bonus-claim-btn" onclick="claimDailyBonus()">🎁 Claim ${amount > 5 ? '🎉' : ''}</button>`
        : `<div class="bonus-next">Next bonus in ${nextIn}</div>`
      }
    </div>
    <div class="streak-info">Come back daily for bigger rewards! <strong>Day 7 = ₹10 bonus 🎉</strong></div>
  `;
}

async function claimDailyBonus() {
  const data = await api('/api/app/bonus/claim', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, type: 'daily' })
  });
  if (data.ok) {
    toast('🎉 Daily bonus claimed! ₹' + data.amount);
    updateBalance(data.balance || CURRENT_USER.balance);
    loadBonus();
  } else {
    toast(data.error || 'Already claimed');
  }
}

const SPIN_SEGMENTS = [
  { label: '₹0.5', color: '#7b5ef8', amount: 0.5 },
  { label: '₹1', color: '#00e5a0', amount: 1 },
  { label: '₹2', color: '#ffab00', amount: 2 },
  { label: '₹3', color: '#ff4f5e', amount: 3 },
  { label: '₹5', color: '#a78bfa', amount: 5 },
  { label: '₹0', color: '#6b6b80', amount: 0 },
  { label: '₹1.5', color: '#34d399', amount: 1.5 },
  { label: '₹0.75', color: '#f87171', amount: 0.75 },
];

function renderSpinWheel() {
  const container = document.getElementById('spinSegments');
  if (!container) return;

  const segmentAngle = 360 / SPIN_SEGMENTS.length;
  container.innerHTML = SPIN_SEGMENTS.map((seg, i) => `
    <div class="spin-segment"
      style="background:${seg.color}; transform: rotate(${i * segmentAngle}deg);
      clip-path: polygon(50% 50%, 50% 0%, ${50 + 50 * Math.tan((segmentAngle / 2) * Math.PI / 180)}% 0%);">
    </div>
  `).join('');
}

async function startSpin() {
  const btn = document.getElementById('spinBtn');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = 'Spinning...';

  // Spin animation
  const wheel = document.querySelector('.spin-wheel');
  if (wheel) {
    const spinDeg = 1800 + Math.floor(Math.random() * 360);
    wheel.style.transition = 'transform 3s cubic-bezier(0.17,0.67,0.12,0.99)';
    wheel.style.transform = 'rotate(' + spinDeg + 'deg)';
  }

  setTimeout(async () => {
    const data = await api('/api/app/spin', {
      method: 'POST',
      body: JSON.stringify({ user_id: USER.id })
    });
    btn.disabled = false;
    btn.textContent = '🎡 Spin Now';

    if (data.ok) {
      toast('🎉 You won ₹' + data.amount + '!');
      updateBalance(data.balance || CURRENT_USER.balance);
    } else {
      toast(data.error || 'Try again tomorrow');
    }

    // Reset wheel
    if (wheel) {
      setTimeout(() => {
        wheel.style.transition = 'none';
        wheel.style.transform = 'rotate(0deg)';
      }, 500);
    }
  }, 3000);
}
