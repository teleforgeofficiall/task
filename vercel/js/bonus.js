async function loadBonus() {
  const el = document.getElementById('dailyBonusSection');
  if (!el) return;

  const bonusData = await api('/api/app/bonus?' + new URLSearchParams({ user_id: USER.id }).toString());

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


