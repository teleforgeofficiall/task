async function loadWallet() {
  const el = document.getElementById('walletSection');
  if (!el) return;
  el.innerHTML = '<div class="loading-dots"><div></div><div></div><div></div></div>';

  const data = await api('/api/app/wallet?' + new URLSearchParams({ user_id: USER.id }).toString());
  const w = data.wallet || { balance: 0, pending: 0, withdrawn: 0, upi: '' };
  const min_withdraw = data.min_withdraw || 10;
  const can_withdraw = w.balance >= min_withdraw;

  el.innerHTML = `
    <div class="wallet-hero animate-in">
      <div class="label">Total Balance</div>
      <div class="balance">${formatCurrency(w.balance || 0)}</div>
      <div class="stats-row">
        <span>Pending: <b>${formatCurrency(w.pending || 0)}</b></span>
        <span>Withdrawn: <b>${formatCurrency(w.withdrawn || 0)}</b></span>
      </div>
    </div>

    <h3 class="section-title">Withdraw</h3>
    <div class="withdraw-grid">
      <div class="withdraw-opt animate-in fade stagger-1" onclick="startWithdraw('upi')">
        <svg viewBox="0 0 24 24"><rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/></svg>
        <h4>UPI</h4>
        <p>Min ₹${min_withdraw}</p>
      </div>
      <div class="withdraw-opt animate-in fade stagger-2" onclick="startWithdraw('stars')">
        <svg viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
        <h4>Stars</h4>
        <p>Instant</p>
      </div>
      <div class="withdraw-opt animate-in fade stagger-3" onclick="startWithdraw('redeem')">
        <svg viewBox="0 0 24 24"><rect x="2" y="8" width="20" height="14" rx="2"/><path d="M12 2v6"/><path d="M8 2l4 6 4-6"/></svg>
        <h4>Redeem</h4>
        <p>Min ₹50</p>
      </div>
    </div>

    <h3 class="section-title">Recent Transactions</h3>
    <div class="txn-list">
      ${(data.transactions || []).length > 0
        ? data.transactions.slice(0, 10).map(t => `
          <div class="txn-item animate-in fade">
            <div>
              <div class="txn-desc">${t.description || t.type}</div>
              <div class="txn-date">${t.date || ''}</div>
            </div>
            <div class="txn-amount ${(t.amount || 0) > 0 ? 'positive' : 'negative'}">
              ${(t.amount || 0) > 0 ? '+' : ''}${formatCurrency(t.amount || 0)}
            </div>
          </div>
        `).join('')
        : '<div class="empty-state">No transactions yet</div>'
      }
    </div>
  `;
}

function startWithdraw(method) {
  const methods = { upi: 'UPI', stars: 'Telegram Stars', redeem: 'Redeem Code' };
  let html = '';
  if (method === 'upi') {
    html = `
      <div class="form-group"><label>UPI ID</label><input class="form-input" id="wUpi" placeholder="example@upi" value="${CURRENT_USER?.upi||''}"></div>
      <div class="form-group"><label>Amount (₹)</label><input class="form-input" id="wAmount" type="number" placeholder="Min ₹10"></div>
      <button class="btn btn-success btn-block" onclick="submitWithdraw('upi')">Withdraw via UPI</button>
    `;
  } else if (method === 'stars') {
    html = `
      <div class="form-group"><label>Amount (Stars)</label><input class="form-input" id="wStarsAmount" type="number" placeholder="Min 5 Stars"></div>
      <button class="btn btn-success btn-block" onclick="submitWithdraw('stars')">Withdraw via Stars</button>
    `;
  } else if (method === 'redeem') {
    html = `
      <div class="form-group"><label>Amount (₹)</label><input class="form-input" id="wRedeemAmount" type="number" placeholder="Min ₹50"></div>
      <button class="btn btn-success btn-block" onclick="submitWithdraw('redeem')">Request Redeem Code</button>
    `;
  }
  showModal('Withdraw - ' + methods[method], html);
}

async function submitWithdraw(method) {
  let body = { user_id: USER.id, method };
  if (method === 'upi') {
    body.upi = document.getElementById('wUpi')?.value;
    body.amount = parseFloat(document.getElementById('wAmount')?.value);
  } else if (method === 'stars') {
    body.amount = parseFloat(document.getElementById('wStarsAmount')?.value);
  } else if (method === 'redeem') {
    body.amount = parseFloat(document.getElementById('wRedeemAmount')?.value);
  }
  if (!body.amount || body.amount <= 0) { toast('Enter valid amount'); return; }

  const data = await api('/api/app/withdraw', { method: 'POST', body: JSON.stringify(body) });
  if (data.ok) {
    toast('✅ Withdrawal requested!');
    closeModal();
    loadWallet();
  } else {
    toast(data.error || 'Failed');
  }
}
