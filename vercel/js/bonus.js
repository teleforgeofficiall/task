let _spinSegmentsData = [];

async function loadBonus() {
  const el = document.getElementById('dailyBonusSection');
  const spinSection = document.querySelector('.spin-section');
  if (!el) return;

  const [bonusData, spinData] = await Promise.all([
    api('/api/app/bonus?' + new URLSearchParams({ user_id: USER.id }).toString()),
    api('/api/app/spin-config?' + new URLSearchParams({ user_id: USER.id }).toString())
  ]);

  const canClaim = bonusData.can_claim;
  const day = bonusData.day || 1;
  const amount = bonusData.amount || 1;
  const streak = bonusData.streak || 0;
  const nextIn = bonusData.next_in || '';

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

  if (spinSection) {
    if (spinData.ok && spinData.enabled) {
      spinSection.style.display = '';
      _spinSegmentsData = spinData.segments || [];
      renderSpinWheel();
    } else {
      spinSection.style.display = 'none';
    }
  }
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

const SPIN_COLORS = ['#7b5ef8','#00e5a0','#ffab00','#ff4f5e','#a78bfa','#6b6b80','#34d399','#f87171','#60a5fa','#fbbf24'];

function renderSpinWheel() {
  const container = document.getElementById('spinSegments');
  if (!container || !_spinSegmentsData.length) return;

  const segmentAngle = 360 / _spinSegmentsData.length;
  container.innerHTML = _spinSegmentsData.map((amount, i) => `
    <div class="spin-segment"
      style="background:${SPIN_COLORS[i % SPIN_COLORS.length]}; transform: rotate(${i * segmentAngle}deg);
      clip-path: polygon(50% 50%, 50% 0%, ${50 + 50 * Math.tan((segmentAngle / 2) * Math.PI / 180)}% 0%);">
    </div>
  `).join('');
}

async function startSpin() {
  const btn = document.getElementById('spinBtn');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = 'Spinning...';

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

    if (wheel) {
      setTimeout(() => {
        wheel.style.transition = 'none';
        wheel.style.transform = 'rotate(0deg)';
      }, 500);
    }
  }, 3000);
}
