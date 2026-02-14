/* ========================================================
   Kakeibo - Household Budget App (Frontend Logic)
   ======================================================== */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let categories = [];
let accounts = [];
let currentTxType = "expense";
let editTxType = "expense";

// Month trackers
const today = new Date();
let listYear = today.getFullYear();
let listMonth = today.getMonth() + 1;
let summaryYear = today.getFullYear();
let summaryMonth = today.getMonth() + 1;
let budgetYear = today.getFullYear();
let budgetMonth = today.getMonth() + 1;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function ym(y, m) {
  return `${y}-${String(m).padStart(2, "0")}`;
}

function ymLabel(y, m) {
  return `${y}年${m}月`;
}

function formatMoney(n) {
  if (n == null) return "-";
  return Number(n).toLocaleString("ja-JP");
}

async function api(url, opts = {}) {
  if (opts.body && typeof opts.body === "object") {
    opts.headers = { "Content-Type": "application/json", ...opts.headers };
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(url, opts);
  return res.json();
}

function cmpArrow(current, prev) {
  if (prev === 0 && current === 0) return '<span class="cmp neutral">-</span>';
  if (current > prev) return `<span class="cmp up">+${formatMoney(current - prev)}</span>`;
  if (current < prev) return `<span class="cmp down">${formatMoney(current - prev)}</span>`;
  return '<span class="cmp neutral">±0</span>';
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
document.querySelectorAll(".nav-links button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-links button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const page = btn.dataset.page;
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
    document.getElementById("page-" + page).classList.add("active");

    if (page === "list") loadList();
    if (page === "summary") loadSummary();
    if (page === "balance") loadBalances();
    if (page === "budget") loadBudgetForm();
    if (page === "input") loadRecent();
  });
});

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------
async function loadMasterData() {
  [categories, accounts] = await Promise.all([api("/api/categories"), api("/api/accounts")]);
  populateCategorySelect("tx-category", currentTxType);
  populateAccountSelect("tx-account");
  populateAccountSelect("tx-to-account");
  populateCategorySelect("edit-tx-category", editTxType);
  populateAccountSelect("edit-tx-account");
  populateAccountSelect("edit-tx-to-account");
}

function populateCategorySelect(selectId, type) {
  const sel = document.getElementById(selectId);
  sel.innerHTML = "";
  categories
    .filter((c) => c.type === type)
    .forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      sel.appendChild(opt);
    });
}

function populateAccountSelect(selectId) {
  const sel = document.getElementById(selectId);
  sel.innerHTML = "";
  accounts.forEach((a) => {
    const opt = document.createElement("option");
    opt.value = a.id;
    opt.textContent = a.name;
    sel.appendChild(opt);
  });
}

// ---------------------------------------------------------------------------
// Transaction type toggle (shared logic)
// ---------------------------------------------------------------------------
function updateTypeToggleUI(prefix, type) {
  const be = document.getElementById(prefix + "btn-expense");
  const bi = document.getElementById(prefix + "btn-income");
  const bt = document.getElementById(prefix + "btn-transfer");
  be.className = type === "expense" ? "active-expense" : "";
  bi.className = type === "income" ? "active-income" : "";
  bt.className = type === "transfer" ? "active-transfer" : "";

  // Show/hide category and to-account fields
  const catGroup = document.getElementById(prefix + "tx-category-group");
  const toAccGroup = document.getElementById(prefix + "tx-to-account-group");
  const accLabel = document.getElementById(prefix + "tx-account-label");
  const catSelect = document.getElementById(prefix + "tx-category");

  if (type === "transfer") {
    catGroup.style.display = "none";
    catSelect.removeAttribute("required");
    toAccGroup.style.display = "";
    accLabel.textContent = "振替元";
  } else {
    catGroup.style.display = "";
    catSelect.setAttribute("required", "");
    toAccGroup.style.display = "none";
    accLabel.textContent = "支払元";
  }
}

function setTxType(type) {
  currentTxType = type;
  updateTypeToggleUI("", type);
  if (type !== "transfer") {
    populateCategorySelect("tx-category", type);
  }
}

function setEditTxType(type) {
  editTxType = type;
  updateTypeToggleUI("edit-", type);
  if (type !== "transfer") {
    populateCategorySelect("edit-tx-category", type);
  }
}

// ---------------------------------------------------------------------------
// Transaction form (Add)
// ---------------------------------------------------------------------------
document.getElementById("tx-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = {
    date: document.getElementById("tx-date").value,
    type: currentTxType,
    amount: document.getElementById("tx-amount").value,
    memo: document.getElementById("tx-memo").value,
  };

  if (currentTxType === "transfer") {
    data.account_id = document.getElementById("tx-account").value;
    data.to_account_id = document.getElementById("tx-to-account").value;
    if (data.account_id === data.to_account_id) {
      alert("振替元と振替先が同じです");
      return;
    }
  } else {
    data.category_id = document.getElementById("tx-category").value;
    data.account_id = document.getElementById("tx-account").value;
  }

  await api("/api/transactions", { method: "POST", body: data });
  // Reset form but keep date
  document.getElementById("tx-amount").value = "";
  document.getElementById("tx-memo").value = "";
  loadRecent();
});

// ---------------------------------------------------------------------------
// Transaction list rendering (shared)
// ---------------------------------------------------------------------------
function renderTxItem(tx) {
  let categoryDisplay, accountDisplay, amountPrefix, amountClass;

  if (tx.type === "transfer") {
    categoryDisplay = "振替";
    accountDisplay = `${tx.account_name} → ${tx.to_account_name || "?"}`;
    amountPrefix = "";
    amountClass = "transfer";
  } else {
    categoryDisplay = tx.category_name || "";
    accountDisplay = tx.account_name;
    amountPrefix = tx.type === "expense" ? "-" : "+";
    amountClass = tx.type;
  }

  return `
    <li class="tx-item">
      <span class="tx-date">${tx.date}</span>
      <span class="tx-info">
        <span class="tx-category">${categoryDisplay}</span>
        <span class="tx-account-memo">${accountDisplay}${tx.memo ? " / " + escapeHtml(tx.memo) : ""}</span>
      </span>
      <span class="tx-amount ${amountClass}">${amountPrefix}${formatMoney(tx.amount)}</span>
      <span class="tx-actions">
        <button onclick="openEditModal(${tx.id})">編集</button>
      </span>
    </li>`;
}

// ---------------------------------------------------------------------------
// Recent transactions (input page)
// ---------------------------------------------------------------------------
async function loadRecent() {
  const currentYm = ym(today.getFullYear(), today.getMonth() + 1);
  const txs = await api(`/api/transactions?year_month=${currentYm}`);
  const list = document.getElementById("recent-tx-list");
  if (txs.length === 0) {
    list.innerHTML = '<li class="empty-state">今月の記録はまだありません</li>';
    return;
  }
  list.innerHTML = txs.slice(0, 20).map(renderTxItem).join("");
}

// ---------------------------------------------------------------------------
// Transaction list page
// ---------------------------------------------------------------------------
function changeListMonth(delta) {
  listMonth += delta;
  if (listMonth > 12) { listMonth = 1; listYear++; }
  if (listMonth < 1) { listMonth = 12; listYear--; }
  loadList();
}

async function loadList() {
  document.getElementById("list-month-label").textContent = ymLabel(listYear, listMonth);
  const currentYm = ym(listYear, listMonth);
  const [txs, summary] = await Promise.all([
    api(`/api/transactions?year_month=${currentYm}`),
    api(`/api/summary?year_month=${currentYm}`),
  ]);

  // Summary row
  document.getElementById("list-summary-row").innerHTML = `
    <div class="summary-card"><div class="label">収入</div><div class="value income">+${formatMoney(summary.total_income)}</div></div>
    <div class="summary-card"><div class="label">支出</div><div class="value expense">-${formatMoney(summary.total_expense)}</div></div>
    <div class="summary-card"><div class="label">収支</div><div class="value balance">${summary.balance >= 0 ? "+" : ""}${formatMoney(summary.balance)}</div></div>
  `;

  const list = document.getElementById("full-tx-list");
  if (txs.length === 0) {
    list.innerHTML = '<li class="empty-state">この月の記録はありません</li>';
    return;
  }
  list.innerHTML = txs.map(renderTxItem).join("");
}

// ---------------------------------------------------------------------------
// Summary page
// ---------------------------------------------------------------------------
function changeSummaryMonth(delta) {
  summaryMonth += delta;
  if (summaryMonth > 12) { summaryMonth = 1; summaryYear++; }
  if (summaryMonth < 1) { summaryMonth = 12; summaryYear--; }
  loadSummary();
}

async function loadSummary() {
  const currentYm = ym(summaryYear, summaryMonth);
  document.getElementById("summary-month-label").textContent = ymLabel(summaryYear, summaryMonth);

  const data = await api(`/api/summary?year_month=${currentYm}`);

  // Summary row
  document.getElementById("summary-row").innerHTML = `
    <div class="summary-card"><div class="label">収入合計</div><div class="value income">+${formatMoney(data.total_income)}</div></div>
    <div class="summary-card"><div class="label">支出合計</div><div class="value expense">-${formatMoney(data.total_expense)}</div></div>
    <div class="summary-card"><div class="label">収支</div><div class="value balance">${data.balance >= 0 ? "+" : ""}${formatMoney(data.balance)}</div></div>
  `;

  // Expense table
  const expenseRows = data.categories.filter((c) => c.type === "expense" && (c.total > 0 || c.budget || c.prev_month_total > 0 || c.prev_year_total > 0));
  const expenseTbody = document.querySelector("#expense-summary-table tbody");
  if (expenseRows.length === 0) {
    expenseTbody.innerHTML = '<tr><td colspan="5" class="empty-state">データなし</td></tr>';
  } else {
    expenseTbody.innerHTML = expenseRows
      .map((c) => {
        let budgetCell = "-";
        if (c.budget != null && c.budget > 0) {
          const pct = Math.round((c.total / c.budget) * 100);
          const cls = pct > 100 ? "over" : pct > 80 ? "warn" : "ok";
          budgetCell = `${formatMoney(c.budget)}<div class="progress-bar"><div class="fill ${cls}" style="width:${Math.min(pct, 100)}%"></div></div><span class="cmp ${pct > 100 ? "up" : "down"}">${pct}%</span>`;
        }
        return `<tr>
          <td>${c.category_name}</td>
          <td>${formatMoney(c.total)}</td>
          <td>${budgetCell}</td>
          <td>${formatMoney(c.prev_month_total)} ${cmpArrow(c.total, c.prev_month_total)}</td>
          <td>${formatMoney(c.prev_year_total)} ${cmpArrow(c.total, c.prev_year_total)}</td>
        </tr>`;
      })
      .join("");

    // Totals row
    const totalExpense = expenseRows.reduce((s, c) => s + c.total, 0);
    const totalPrev = expenseRows.reduce((s, c) => s + c.prev_month_total, 0);
    const totalPrevYear = expenseRows.reduce((s, c) => s + c.prev_year_total, 0);
    const totalBudget = expenseRows.reduce((s, c) => s + (c.budget || 0), 0);
    expenseTbody.innerHTML += `<tr style="font-weight:700;border-top:2px solid var(--gray-300)">
      <td>合計</td>
      <td>${formatMoney(totalExpense)}</td>
      <td>${totalBudget > 0 ? formatMoney(totalBudget) : "-"}</td>
      <td>${formatMoney(totalPrev)} ${cmpArrow(totalExpense, totalPrev)}</td>
      <td>${formatMoney(totalPrevYear)} ${cmpArrow(totalExpense, totalPrevYear)}</td>
    </tr>`;
  }

  // Income table
  const incomeRows = data.categories.filter((c) => c.type === "income" && (c.total > 0 || c.prev_month_total > 0 || c.prev_year_total > 0));
  const incomeTbody = document.querySelector("#income-summary-table tbody");
  if (incomeRows.length === 0) {
    incomeTbody.innerHTML = '<tr><td colspan="4" class="empty-state">データなし</td></tr>';
  } else {
    incomeTbody.innerHTML = incomeRows
      .map(
        (c) => `<tr>
        <td>${c.category_name}</td>
        <td>${formatMoney(c.total)}</td>
        <td>${formatMoney(c.prev_month_total)} ${cmpArrow(c.total, c.prev_month_total)}</td>
        <td>${formatMoney(c.prev_year_total)} ${cmpArrow(c.total, c.prev_year_total)}</td>
      </tr>`
      )
      .join("");
  }
}

// ---------------------------------------------------------------------------
// Balance page
// ---------------------------------------------------------------------------
async function loadBalances() {
  const data = await api("/api/balances");
  document.getElementById("grand-total-value").textContent = `¥${formatMoney(data.grand_total)}`;

  const typeLabels = { cash: "現金", bank: "銀行口座", credit_card: "クレジットカード", e_money: "電子マネー", other: "その他" };
  document.getElementById("balance-grid").innerHTML = data.accounts
    .map(
      (a) => `
    <div class="balance-card" onclick="openBalanceModal(${a.id}, '${escapeHtml(a.name)}', ${a.current_balance})" style="cursor:pointer">
      <div class="account-name">${a.name}</div>
      <div class="account-type">${typeLabels[a.type] || a.type}</div>
      <div class="account-balance" style="color:${a.current_balance >= 0 ? "var(--primary)" : "var(--danger)"}">
        ¥${formatMoney(a.current_balance)}
      </div>
      <div class="balance-adjust-hint">クリックで残高調整</div>
    </div>`
    )
    .join("");
}

// ---------------------------------------------------------------------------
// Balance adjustment modal
// ---------------------------------------------------------------------------
function openBalanceModal(accountId, accountName, currentBalance) {
  document.getElementById("balance-account-id").value = accountId;
  document.getElementById("balance-account-name").textContent = accountName;
  document.getElementById("balance-current").textContent = `¥${formatMoney(currentBalance)}`;
  document.getElementById("balance-new").value = currentBalance;
  document.getElementById("balance-modal").classList.add("show");
}

function closeBalanceModal() {
  document.getElementById("balance-modal").classList.remove("show");
}

document.getElementById("balance-adjust-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const accountId = document.getElementById("balance-account-id").value;
  const newBalance = document.getElementById("balance-new").value;
  await api(`/api/accounts/${accountId}/adjust_balance`, {
    method: "PUT",
    body: { balance: parseInt(newBalance) },
  });
  closeBalanceModal();
  loadBalances();
});

document.getElementById("balance-modal").addEventListener("click", (e) => {
  if (e.target === document.getElementById("balance-modal")) closeBalanceModal();
});

// ---------------------------------------------------------------------------
// Budget page
// ---------------------------------------------------------------------------
function changeBudgetMonth(delta) {
  budgetMonth += delta;
  if (budgetMonth > 12) { budgetMonth = 1; budgetYear++; }
  if (budgetMonth < 1) { budgetMonth = 12; budgetYear--; }
  loadBudgetForm();
}

async function loadBudgetForm() {
  const currentYm = ym(budgetYear, budgetMonth);
  document.getElementById("budget-month-label").textContent = ymLabel(budgetYear, budgetMonth);

  const budgets = await api(`/api/budgets?year_month=${currentYm}`);
  const budgetMap = {};
  budgets.forEach((b) => (budgetMap[b.category_id] = b.amount));

  const expCats = categories.filter((c) => c.type === "expense");
  const tbody = document.querySelector("#budget-table tbody");
  tbody.innerHTML = expCats
    .map(
      (c) => `<tr>
      <td>${c.name}</td>
      <td><input type="number" min="0" data-cat-id="${c.id}" value="${budgetMap[c.id] || ""}"></td>
    </tr>`
    )
    .join("");
}

document.getElementById("budget-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const inputs = document.querySelectorAll("#budget-table input[data-cat-id]");
  const budgets = [];
  inputs.forEach((inp) => {
    if (inp.value) {
      budgets.push({ category_id: inp.dataset.catId, amount: parseInt(inp.value) });
    }
  });
  await api("/api/budgets", {
    method: "POST",
    body: { year_month: ym(budgetYear, budgetMonth), budgets },
  });
  alert("予算を保存しました");
});

async function copyPrevBudget() {
  let pm = budgetMonth - 1;
  let py = budgetYear;
  if (pm < 1) { pm = 12; py--; }
  const prevBudgets = await api(`/api/budgets?year_month=${ym(py, pm)}`);
  if (prevBudgets.length === 0) {
    alert("前月の予算データがありません");
    return;
  }
  const inputs = document.querySelectorAll("#budget-table input[data-cat-id]");
  const prevMap = {};
  prevBudgets.forEach((b) => (prevMap[b.category_id] = b.amount));
  inputs.forEach((inp) => {
    if (prevMap[inp.dataset.catId] != null) {
      inp.value = prevMap[inp.dataset.catId];
    }
  });
}

// ---------------------------------------------------------------------------
// Edit modal
// ---------------------------------------------------------------------------
async function openEditModal(txId) {
  const txs = await api("/api/transactions");
  const tx = txs.find((t) => t.id === txId);
  if (!tx) return;

  setEditTxType(tx.type);
  document.getElementById("edit-tx-id").value = tx.id;
  document.getElementById("edit-tx-date").value = tx.date;
  document.getElementById("edit-tx-amount").value = tx.amount;
  document.getElementById("edit-tx-memo").value = tx.memo || "";

  if (tx.type === "transfer") {
    document.getElementById("edit-tx-account").value = tx.account_id;
    document.getElementById("edit-tx-to-account").value = tx.to_account_id;
  } else {
    populateCategorySelect("edit-tx-category", tx.type);
    document.getElementById("edit-tx-category").value = tx.category_id;
    document.getElementById("edit-tx-account").value = tx.account_id;
  }

  document.getElementById("edit-modal").classList.add("show");
}

function closeEditModal() {
  document.getElementById("edit-modal").classList.remove("show");
}

document.getElementById("edit-tx-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("edit-tx-id").value;
  const data = {
    date: document.getElementById("edit-tx-date").value,
    type: editTxType,
    amount: document.getElementById("edit-tx-amount").value,
    memo: document.getElementById("edit-tx-memo").value,
  };

  if (editTxType === "transfer") {
    data.account_id = document.getElementById("edit-tx-account").value;
    data.to_account_id = document.getElementById("edit-tx-to-account").value;
    if (data.account_id === data.to_account_id) {
      alert("振替元と振替先が同じです");
      return;
    }
  } else {
    data.category_id = document.getElementById("edit-tx-category").value;
    data.account_id = document.getElementById("edit-tx-account").value;
  }

  await api(`/api/transactions/${id}`, { method: "PUT", body: data });
  closeEditModal();
  loadRecent();
  loadList();
});

document.getElementById("edit-delete-btn").addEventListener("click", async () => {
  if (!confirm("この取引を削除しますか？")) return;
  const id = document.getElementById("edit-tx-id").value;
  await api(`/api/transactions/${id}`, { method: "DELETE" });
  closeEditModal();
  loadRecent();
  loadList();
});

// Close modal on overlay click
document.getElementById("edit-modal").addEventListener("click", (e) => {
  if (e.target === document.getElementById("edit-modal")) closeEditModal();
});

// ---------------------------------------------------------------------------
// Settings: Add category / account
// ---------------------------------------------------------------------------
document.getElementById("category-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("/api/categories", {
    method: "POST",
    body: {
      name: document.getElementById("cat-name").value,
      type: document.getElementById("cat-type").value,
    },
  });
  document.getElementById("cat-name").value = "";
  await loadMasterData();
  alert("カテゴリを追加しました");
});

document.getElementById("account-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("/api/accounts", {
    method: "POST",
    body: {
      name: document.getElementById("acc-name").value,
      type: document.getElementById("acc-type").value,
      initial_balance: parseInt(document.getElementById("acc-balance").value) || 0,
    },
  });
  document.getElementById("acc-name").value = "";
  document.getElementById("acc-balance").value = "0";
  await loadMasterData();
  alert("口座を追加しました");
});

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
(async function init() {
  // Set today as default date
  document.getElementById("tx-date").value = today.toISOString().slice(0, 10);
  await loadMasterData();
  loadRecent();
})();
