var REDEEM_AMOUNTS = [10, 25, 50, 100, 250, 500];

async function loadWallet() {
  var el = document.getElementById('walletSection');
  if (!el) return;
  el.innerHTML = '<div class="loading-dots"><div></div><div></div><div></div></div>';

  var data = await api('/api/app/wallet?' + new URLSearchParams({ user_id: USER.id }).toString());
  var w = data.wallet || { balance: 0, pending: 0, withdrawn: 0, upi: '' };
  var min_withdraw = data.min_withdraw || 10;
  var can_withdraw = w.balance >= min_withdraw;

  var redeemData = await api('/api/app/redeem-codes?' + new URLSearchParams({ user_id: USER.id }).toString());
  var redeemCodes = (redeemData.ok && redeemData.codes) || [];

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
        <p>Instant</p>
      </div>
    </div>

    <h3 class="section-title">My Redeem Codes</h3>
    <div class="txn-list" id="redeemCodesList">
      ${redeemCodes.length > 0
        ? redeemCodes.map(function(c) { return `
          <div class="txn-item animate-in fade">
            <div style="flex:1;min-width:0">
              <div class="txn-desc" style="font-size:12px;font-family:monospace;word-break:break-all">${c.code}</div>
              <div class="txn-date">₹${c.amount} &middot; ${c.used_at || ''}</div>
            </div>
          </div>
        `; }).join('')
        : '<div class="empty-state">No redeem codes yet</div>'
      }
    </div>

    <h3 class="section-title">Recent Transactions</h3>
    <div class="txn-list">
      ${(data.transactions || []).length > 0
        ? data.transactions.slice(0, 10).map(function(t) { return `
          <div class="txn-item animate-in fade">
            <div>
              <div class="txn-desc">${t.description || t.type}</div>
              <div class="txn-date">${t.date || ''}</div>
            </div>
            <div class="txn-amount ${(t.amount || 0) > 0 ? 'positive' : 'negative'}">
              ${(t.amount || 0) > 0 ? '+' : ''}${formatCurrency(t.amount || 0)}
            </div>
          </div>
        `; }).join('')
        : '<div class="empty-state">No transactions yet</div>'
      }
    </div>
  `;
}

function startWithdraw(method) {
  var methods = { upi: 'UPI', stars: 'Telegram Stars', redeem: 'Redeem Code' };
  var html = '';
  if (method === 'upi') {
    html = `
      <div class="form-group"><label>UPI ID</label><input class="form-input" id="wUpi" placeholder="example@upi" value="${CURRENT_USER?.upi || ''}"></div>
      <div class="form-group"><label>Amount (₹)</label><input class="form-input" id="wAmount" type="number" placeholder="Min ₹10"></div>
      <button class="btn btn-success btn-block" onclick="submitWithdraw('upi')">Withdraw via UPI</button>
    `;
  } else if (method === 'stars') {
    html = `
      <div class="form-group"><label>Amount (Stars)</label><input class="form-input" id="wStarsAmount" type="number" placeholder="Min 5 Stars"></div>
      <button class="btn btn-success btn-block" onclick="submitWithdraw('stars')">Withdraw via Stars</button>
    `;
  } else if (method === 'redeem') {
    html = '<div class="form-group"><label>Select Amount</label></div><div class="bet-selector">' +
      REDEEM_AMOUNTS.map(function(a) { return '<button class="bet-btn" onclick="submitRedeem(' + a + ')">₹' + a + '</button>'; }).join('') +
      '</div>';
  }
  showModal('Withdraw - ' + methods[method], html);
}

async function submitRedeem(amount) {
  closeModal();
  var data = await api('/api/app/withdraw', {
    method: 'POST',
    body: JSON.stringify({ user_id: USER.id, method: 'redeem', amount: amount })
  });
  if (data.ok) {
    showModal('Redeem Code Issued!',
      '<div style="text-align:center;padding:16px 0">' +
      '<div style="font-size:48px;margin-bottom:12px">🎫</div>' +
      '<div style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">Your Google Redeem Code:</div>' +
      '<div style="font-size:18px;font-weight:800;font-family:monospace;background:var(--bg);padding:12px 16px;border-radius:10px;word-break:break-all;margin-bottom:16px">' + data.code + '</div>' +
      '<div style="font-size:12px;color:var(--text-secondary)">Redeem on Google Play Store</div>' +
      '</div>'
    );
    if (data.balance !== undefined) updateBalance(data.balance);
    loadWallet();
  } else {
    toast(data.error || 'Failed');
  }
}

async function submitWithdraw(method) {
  var body = { user_id: USER.id, method: method };
  if (method === 'upi') {
    body.upi = document.getElementById('wUpi')?.value;
    body.amount = parseFloat(document.getElementById('wAmount')?.value);
  } else if (method === 'stars') {
    body.amount = parseFloat(document.getElementById('wStarsAmount')?.value);
  } else if (method === 'redeem') {
    return;
  }
  if (!body.amount || body.amount <= 0) { toast('Enter valid amount'); return; }

  var data = await api('/api/app/withdraw', { method: 'POST', body: JSON.stringify(body) });
  if (data.ok) {
    toast('Withdrawal requested!');
    closeModal();
    if (data.balance !== undefined) updateBalance(data.balance);
    loadWallet();
  } else {
    toast(data.error || 'Failed');
  }
}
