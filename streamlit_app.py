import streamlit as st
import sqlite3
import os
from datetime import datetime, date

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="家計簿アプリ", page_icon="📒", layout="centered")

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kakeibo.db")

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL CHECK(type IN ('cash', 'bank', 'credit_card', 'e_money', 'other')),
            initial_balance INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            sort_order INTEGER NOT NULL DEFAULT 0,
            UNIQUE(name, type)
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            amount INTEGER NOT NULL CHECK(amount > 0),
            category_id INTEGER NOT NULL REFERENCES categories(id),
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            memo TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL REFERENCES categories(id),
            year_month TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK(amount >= 0),
            UNIQUE(category_id, year_month)
        );
        CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
        CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
        CREATE INDEX IF NOT EXISTS idx_budgets_year_month ON budgets(year_month);
    """
    )
    cursor = db.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        expense_categories = [
            "食費", "日用品", "住居費", "水道光熱費", "通信費", "交通費",
            "衣服・美容", "医療・健康", "教育・教養", "趣味・娯楽",
            "交際費", "保険", "税金・社会保険", "その他支出",
        ]
        income_categories = ["給与", "賞与", "副業", "投資収益", "その他収入"]
        for i, name in enumerate(expense_categories):
            db.execute(
                "INSERT INTO categories (name, type, sort_order) VALUES (?, 'expense', ?)",
                (name, i),
            )
        for i, name in enumerate(income_categories):
            db.execute(
                "INSERT INTO categories (name, type, sort_order) VALUES (?, 'income', ?)",
                (name, i),
            )
    cursor = db.execute("SELECT COUNT(*) FROM accounts")
    if cursor.fetchone()[0] == 0:
        defaults = [
            ("現金", "cash", 0),
            ("銀行口座", "bank", 1),
            ("クレジットカード", "credit_card", 2),
        ]
        for name, atype, order in defaults:
            db.execute(
                "INSERT INTO accounts (name, type, sort_order) VALUES (?, ?, ?)",
                (name, atype, order),
            )
    db.commit()
    db.close()


init_db()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
TYPE_LABELS = {
    "cash": "現金",
    "bank": "銀行口座",
    "credit_card": "クレジットカード",
    "e_money": "電子マネー",
    "other": "その他",
}


def fetch_categories(tx_type=None):
    db = get_db()
    if tx_type:
        rows = db.execute(
            "SELECT * FROM categories WHERE type=? ORDER BY sort_order", (tx_type,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM categories ORDER BY type, sort_order"
        ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def fetch_accounts():
    db = get_db()
    rows = db.execute("SELECT * FROM accounts ORDER BY sort_order").fetchall()
    db.close()
    return [dict(r) for r in rows]


def format_money(n):
    if n is None:
        return "-"
    return f"{int(n):,}"


def ym_str(y, m):
    return f"{y}-{m:02d}"


# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
if "list_year" not in st.session_state:
    st.session_state.list_year = date.today().year
if "list_month" not in st.session_state:
    st.session_state.list_month = date.today().month
if "summary_year" not in st.session_state:
    st.session_state.summary_year = date.today().year
if "summary_month" not in st.session_state:
    st.session_state.summary_month = date.today().month
if "budget_year" not in st.session_state:
    st.session_state.budget_year = date.today().year
if "budget_month" not in st.session_state:
    st.session_state.budget_month = date.today().month


def change_month(key_prefix, delta):
    y = st.session_state[f"{key_prefix}_year"]
    m = st.session_state[f"{key_prefix}_month"] + delta
    if m > 12:
        m = 1
        y += 1
    elif m < 1:
        m = 12
        y -= 1
    st.session_state[f"{key_prefix}_year"] = y
    st.session_state[f"{key_prefix}_month"] = m


# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        font-weight: 600;
    }
    div[data-testid="stMetric"] {
        background: #ffffff;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
st.title("家計簿")

tabs = st.tabs(["入力", "明細", "集計", "残高", "予算", "設定"])

# ===== Tab: 入力 =====
with tabs[0]:
    st.subheader("収支を記録")

    tx_type = st.radio(
        "種別", ["支出", "収入"], horizontal=True, key="input_tx_type"
    )
    tx_type_val = "expense" if tx_type == "支出" else "income"

    categories = fetch_categories(tx_type_val)
    accounts = fetch_accounts()

    if not categories:
        st.warning("カテゴリが登録されていません。設定タブから追加してください。")
    elif not accounts:
        st.warning("口座が登録されていません。設定タブから追加してください。")
    else:
        col1, col2 = st.columns(2)
        with col1:
            tx_date = st.date_input("日付", value=date.today(), key="input_date")
            cat_options = {c["name"]: c["id"] for c in categories}
            tx_cat = st.selectbox(
                "カテゴリ", options=list(cat_options.keys()), key="input_cat"
            )
        with col2:
            tx_amount = st.number_input(
                "金額 (円)", min_value=1, step=100, key="input_amount"
            )
            acc_options = {a["name"]: a["id"] for a in accounts}
            tx_acc = st.selectbox(
                "支払元", options=list(acc_options.keys()), key="input_acc"
            )
        tx_memo = st.text_input("メモ（任意）", key="input_memo")

        if st.button("記録する", type="primary", key="btn_add_tx"):
            db = get_db()
            db.execute(
                "INSERT INTO transactions (date, type, amount, category_id, account_id, memo) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    tx_date.isoformat(),
                    tx_type_val,
                    int(tx_amount),
                    cat_options[tx_cat],
                    acc_options[tx_acc],
                    tx_memo,
                ),
            )
            db.commit()
            db.close()
            st.success("記録しました")
            st.rerun()

    # Recent transactions
    st.markdown("---")
    st.subheader("最近の記録")
    current_ym = ym_str(date.today().year, date.today().month)
    db = get_db()
    recent = db.execute(
        """SELECT t.*, c.name AS category_name, c.type AS category_type,
                  a.name AS account_name
           FROM transactions t
           JOIN categories c ON t.category_id = c.id
           JOIN accounts a ON t.account_id = a.id
           WHERE strftime('%Y-%m', t.date) = ?
           ORDER BY t.date DESC, t.id DESC
           LIMIT 20""",
        (current_ym,),
    ).fetchall()
    db.close()

    if not recent:
        st.info("今月の記録はまだありません")
    else:
        for tx in recent:
            tx = dict(tx)
            sign = "-" if tx["type"] == "expense" else "+"
            color = "red" if tx["type"] == "expense" else "green"
            memo_part = f" / {tx['memo']}" if tx["memo"] else ""
            col_a, col_b, col_c = st.columns([2, 4, 3])
            with col_a:
                st.caption(tx["date"])
            with col_b:
                st.markdown(
                    f"**{tx['category_name']}**  \n"
                    f"<small style='color:#6b7280'>{tx['account_name']}{memo_part}</small>",
                    unsafe_allow_html=True,
                )
            with col_c:
                st.markdown(
                    f"<div style='text-align:right;font-weight:700;color:{color}'>{sign}{format_money(tx['amount'])}円</div>",
                    unsafe_allow_html=True,
                )

# ===== Tab: 明細 =====
with tabs[1]:
    col_prev, col_label, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("← 前月", key="list_prev"):
            change_month("list", -1)
            st.rerun()
    with col_label:
        st.markdown(
            f"<h3 style='text-align:center'>{st.session_state.list_year}年{st.session_state.list_month}月</h3>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("翌月 →", key="list_next"):
            change_month("list", 1)
            st.rerun()

    list_ym = ym_str(st.session_state.list_year, st.session_state.list_month)
    db = get_db()

    # Summary row
    summary_row = db.execute(
        """SELECT
            COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE 0 END), 0) AS total_income,
            COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS total_expense
           FROM transactions WHERE strftime('%Y-%m', date) = ?""",
        (list_ym,),
    ).fetchone()
    total_income = summary_row["total_income"]
    total_expense = summary_row["total_expense"]
    balance = total_income - total_expense

    m1, m2, m3 = st.columns(3)
    m1.metric("収入", f"+{format_money(total_income)}円")
    m2.metric("支出", f"-{format_money(total_expense)}円")
    m3.metric("収支", f"{'+' if balance >= 0 else ''}{format_money(balance)}円")

    txs = db.execute(
        """SELECT t.*, c.name AS category_name, c.type AS category_type,
                  a.name AS account_name
           FROM transactions t
           JOIN categories c ON t.category_id = c.id
           JOIN accounts a ON t.account_id = a.id
           WHERE strftime('%Y-%m', t.date) = ?
           ORDER BY t.date DESC, t.id DESC""",
        (list_ym,),
    ).fetchall()
    db.close()

    if not txs:
        st.info("この月の記録はありません")
    else:
        for tx in txs:
            tx = dict(tx)
            sign = "-" if tx["type"] == "expense" else "+"
            color = "red" if tx["type"] == "expense" else "green"
            memo_part = f" / {tx['memo']}" if tx["memo"] else ""

            col_a, col_b, col_c, col_d = st.columns([2, 4, 3, 1])
            with col_a:
                st.caption(tx["date"])
            with col_b:
                st.markdown(
                    f"**{tx['category_name']}**  \n"
                    f"<small style='color:#6b7280'>{tx['account_name']}{memo_part}</small>",
                    unsafe_allow_html=True,
                )
            with col_c:
                st.markdown(
                    f"<div style='text-align:right;font-weight:700;color:{color}'>{sign}{format_money(tx['amount'])}円</div>",
                    unsafe_allow_html=True,
                )
            with col_d:
                if st.button("削除", key=f"del_{tx['id']}"):
                    db = get_db()
                    db.execute(
                        "DELETE FROM transactions WHERE id=?", (tx["id"],)
                    )
                    db.commit()
                    db.close()
                    st.rerun()


# ===== Tab: 集計 =====
with tabs[2]:
    col_prev, col_label, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("← 前月", key="sum_prev"):
            change_month("summary", -1)
            st.rerun()
    with col_label:
        st.markdown(
            f"<h3 style='text-align:center'>{st.session_state.summary_year}年{st.session_state.summary_month}月</h3>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("翌月 →", key="sum_next"):
            change_month("summary", 1)
            st.rerun()

    s_year = st.session_state.summary_year
    s_month = st.session_state.summary_month
    s_ym = ym_str(s_year, s_month)

    # Previous month
    if s_month == 1:
        prev_ym = f"{s_year - 1}-12"
    else:
        prev_ym = f"{s_year}-{s_month - 1:02d}"
    # Previous year same month
    prev_year_ym = f"{s_year - 1}-{s_month:02d}"

    db = get_db()

    rows = db.execute(
        """SELECT c.id AS category_id, c.name AS category_name, c.type,
                  COALESCE(SUM(t.amount), 0) AS total
           FROM categories c
           LEFT JOIN transactions t ON t.category_id = c.id AND strftime('%Y-%m', t.date) = ?
           GROUP BY c.id ORDER BY c.type, c.sort_order""",
        (s_ym,),
    ).fetchall()

    prev_rows = db.execute(
        """SELECT c.id AS category_id, COALESCE(SUM(t.amount), 0) AS total
           FROM categories c
           LEFT JOIN transactions t ON t.category_id = c.id AND strftime('%Y-%m', t.date) = ?
           GROUP BY c.id""",
        (prev_ym,),
    ).fetchall()
    prev_map = {r["category_id"]: r["total"] for r in prev_rows}

    prev_year_rows = db.execute(
        """SELECT c.id AS category_id, COALESCE(SUM(t.amount), 0) AS total
           FROM categories c
           LEFT JOIN transactions t ON t.category_id = c.id AND strftime('%Y-%m', t.date) = ?
           GROUP BY c.id""",
        (prev_year_ym,),
    ).fetchall()
    prev_year_map = {r["category_id"]: r["total"] for r in prev_year_rows}

    budget_rows = db.execute(
        "SELECT category_id, amount FROM budgets WHERE year_month = ?", (s_ym,)
    ).fetchall()
    budget_map = {r["category_id"]: r["amount"] for r in budget_rows}
    db.close()

    total_income = sum(dict(r)["total"] for r in rows if r["type"] == "income")
    total_expense = sum(dict(r)["total"] for r in rows if r["type"] == "expense")
    s_balance = total_income - total_expense

    m1, m2, m3 = st.columns(3)
    m1.metric("収入合計", f"+{format_money(total_income)}円")
    m2.metric("支出合計", f"-{format_money(total_expense)}円")
    m3.metric("収支", f"{'+' if s_balance >= 0 else ''}{format_money(s_balance)}円")

    # Expense table
    st.subheader("支出カテゴリ別")
    expense_rows = [
        dict(r)
        for r in rows
        if r["type"] == "expense"
        and (
            r["total"] > 0
            or budget_map.get(r["category_id"])
            or prev_map.get(r["category_id"], 0) > 0
            or prev_year_map.get(r["category_id"], 0) > 0
        )
    ]
    if not expense_rows:
        st.info("データなし")
    else:
        header_cols = st.columns([3, 2, 2, 2, 2])
        header_cols[0].markdown("**カテゴリ**")
        header_cols[1].markdown("**今月**")
        header_cols[2].markdown("**予算**")
        header_cols[3].markdown("**前月**")
        header_cols[4].markdown("**前年同月**")
        st.markdown("---")

        for r in expense_rows:
            cid = r["category_id"]
            cols = st.columns([3, 2, 2, 2, 2])
            cols[0].write(r["category_name"])
            cols[1].write(f"{format_money(r['total'])}円")

            budget_val = budget_map.get(cid)
            if budget_val and budget_val > 0:
                pct = round(r["total"] / budget_val * 100)
                cols[2].write(f"{format_money(budget_val)}円 ({pct}%)")
            else:
                cols[2].write("-")

            pm_total = prev_map.get(cid, 0)
            diff_pm = r["total"] - pm_total
            diff_pm_str = f"({'+' if diff_pm >= 0 else ''}{format_money(diff_pm)})" if pm_total > 0 or r["total"] > 0 else ""
            cols[3].write(f"{format_money(pm_total)}円 {diff_pm_str}")

            py_total = prev_year_map.get(cid, 0)
            diff_py = r["total"] - py_total
            diff_py_str = f"({'+' if diff_py >= 0 else ''}{format_money(diff_py)})" if py_total > 0 or r["total"] > 0 else ""
            cols[4].write(f"{format_money(py_total)}円 {diff_py_str}")

    # Income table
    st.subheader("収入カテゴリ別")
    income_rows = [
        dict(r)
        for r in rows
        if r["type"] == "income"
        and (
            r["total"] > 0
            or prev_map.get(r["category_id"], 0) > 0
            or prev_year_map.get(r["category_id"], 0) > 0
        )
    ]
    if not income_rows:
        st.info("データなし")
    else:
        header_cols = st.columns([3, 2, 2, 2])
        header_cols[0].markdown("**カテゴリ**")
        header_cols[1].markdown("**今月**")
        header_cols[2].markdown("**前月**")
        header_cols[3].markdown("**前年同月**")
        st.markdown("---")

        for r in income_rows:
            cid = r["category_id"]
            cols = st.columns([3, 2, 2, 2])
            cols[0].write(r["category_name"])
            cols[1].write(f"{format_money(r['total'])}円")

            pm_total = prev_map.get(cid, 0)
            diff_pm = r["total"] - pm_total
            diff_pm_str = f"({'+' if diff_pm >= 0 else ''}{format_money(diff_pm)})" if pm_total > 0 or r["total"] > 0 else ""
            cols[2].write(f"{format_money(pm_total)}円 {diff_pm_str}")

            py_total = prev_year_map.get(cid, 0)
            diff_py = r["total"] - py_total
            diff_py_str = f"({'+' if diff_py >= 0 else ''}{format_money(diff_py)})" if py_total > 0 or r["total"] > 0 else ""
            cols[3].write(f"{format_money(py_total)}円 {diff_py_str}")


# ===== Tab: 残高 =====
with tabs[3]:
    db = get_db()
    bal_rows = db.execute(
        """SELECT a.id, a.name, a.type, a.initial_balance,
                  COALESCE(SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE 0 END), 0) AS total_income,
                  COALESCE(SUM(CASE WHEN t.type = 'expense' THEN t.amount ELSE 0 END), 0) AS total_expense
           FROM accounts a
           LEFT JOIN transactions t ON t.account_id = a.id
           GROUP BY a.id ORDER BY a.sort_order"""
    ).fetchall()
    db.close()

    grand_total = 0
    account_data = []
    for r in bal_rows:
        d = dict(r)
        bal = d["initial_balance"] + d["total_income"] - d["total_expense"]
        d["current_balance"] = bal
        grand_total += bal
        account_data.append(d)

    st.markdown(
        f"<div style='text-align:center;margin-bottom:1.5rem'>"
        f"<div style='color:#6b7280;font-size:0.9rem'>総資産</div>"
        f"<div style='font-size:2rem;font-weight:700;color:#2563eb'>¥{format_money(grand_total)}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    cols = st.columns(min(len(account_data), 3) if account_data else 1)
    for i, acc in enumerate(account_data):
        with cols[i % len(cols)]:
            color = "#2563eb" if acc["current_balance"] >= 0 else "#dc2626"
            st.markdown(
                f"<div style='background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1);padding:1rem;text-align:center;margin-bottom:1rem'>"
                f"<div style='font-size:0.85rem;color:#6b7280'>{acc['name']}</div>"
                f"<div style='font-size:0.7rem;color:#9ca3af'>{TYPE_LABELS.get(acc['type'], acc['type'])}</div>"
                f"<div style='font-size:1.3rem;font-weight:700;color:{color}'>¥{format_money(acc['current_balance'])}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ===== Tab: 予算 =====
with tabs[4]:
    col_prev, col_label, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("← 前月", key="bud_prev"):
            change_month("budget", -1)
            st.rerun()
    with col_label:
        st.markdown(
            f"<h3 style='text-align:center'>{st.session_state.budget_year}年{st.session_state.budget_month}月</h3>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("翌月 →", key="bud_next"):
            change_month("budget", 1)
            st.rerun()

    b_ym = ym_str(st.session_state.budget_year, st.session_state.budget_month)
    expense_cats = fetch_categories("expense")

    db = get_db()
    existing_budgets = db.execute(
        "SELECT category_id, amount FROM budgets WHERE year_month = ?", (b_ym,)
    ).fetchall()
    db.close()
    existing_map = {r["category_id"]: r["amount"] for r in existing_budgets}

    st.subheader("月間予算設定（支出カテゴリ）")

    with st.form("budget_form"):
        budget_inputs = {}
        for cat in expense_cats:
            default_val = existing_map.get(cat["id"], 0)
            budget_inputs[cat["id"]] = st.number_input(
                cat["name"],
                min_value=0,
                step=1000,
                value=default_val,
                key=f"budget_{cat['id']}",
            )

        col_copy, col_save = st.columns([1, 1])
        submitted = col_save.form_submit_button("保存", type="primary")

    if submitted:
        db = get_db()
        for cat_id, amount in budget_inputs.items():
            if amount > 0:
                db.execute(
                    """INSERT INTO budgets (category_id, year_month, amount)
                       VALUES (?, ?, ?)
                       ON CONFLICT(category_id, year_month)
                       DO UPDATE SET amount = excluded.amount""",
                    (cat_id, b_ym, amount),
                )
        db.commit()
        db.close()
        st.success("予算を保存しました")
        st.rerun()

    # Copy from previous month button
    if st.button("前月からコピー", key="copy_prev_budget"):
        bm = st.session_state.budget_month
        by = st.session_state.budget_year
        pm = bm - 1
        py = by
        if pm < 1:
            pm = 12
            py -= 1
        prev_b_ym = ym_str(py, pm)
        db = get_db()
        prev_budgets = db.execute(
            "SELECT category_id, amount FROM budgets WHERE year_month = ?",
            (prev_b_ym,),
        ).fetchall()
        if not prev_budgets:
            st.warning("前月の予算データがありません")
        else:
            for pb in prev_budgets:
                db.execute(
                    """INSERT INTO budgets (category_id, year_month, amount)
                       VALUES (?, ?, ?)
                       ON CONFLICT(category_id, year_month)
                       DO UPDATE SET amount = excluded.amount""",
                    (pb["category_id"], b_ym, pb["amount"]),
                )
            db.commit()
            st.success("前月の予算をコピーしました")
            st.rerun()
        db.close()


# ===== Tab: 設定 =====
with tabs[5]:
    st.subheader("カテゴリ追加")
    with st.form("add_category_form"):
        cat_name = st.text_input("カテゴリ名", key="new_cat_name")
        cat_type = st.selectbox(
            "種類", ["支出", "収入"], key="new_cat_type"
        )
        cat_submitted = st.form_submit_button("追加")

    if cat_submitted and cat_name:
        db = get_db()
        cat_type_val = "expense" if cat_type == "支出" else "income"
        try:
            db.execute(
                "INSERT INTO categories (name, type, sort_order) VALUES (?, ?, ?)",
                (cat_name, cat_type_val, 0),
            )
            db.commit()
            st.success("カテゴリを追加しました")
            st.rerun()
        except sqlite3.IntegrityError:
            st.error("同名のカテゴリが既に存在します")
        finally:
            db.close()

    st.markdown("---")
    st.subheader("口座追加")
    with st.form("add_account_form"):
        acc_name = st.text_input("口座名", key="new_acc_name")
        acc_type = st.selectbox(
            "種類",
            ["銀行口座", "現金", "クレジットカード", "電子マネー", "その他"],
            key="new_acc_type",
        )
        acc_balance = st.number_input(
            "初期残高 (円)", step=1000, value=0, key="new_acc_balance"
        )
        acc_submitted = st.form_submit_button("追加")

    if acc_submitted and acc_name:
        type_map = {
            "銀行口座": "bank",
            "現金": "cash",
            "クレジットカード": "credit_card",
            "電子マネー": "e_money",
            "その他": "other",
        }
        db = get_db()
        try:
            db.execute(
                "INSERT INTO accounts (name, type, initial_balance, sort_order) VALUES (?, ?, ?, ?)",
                (acc_name, type_map[acc_type], int(acc_balance), 0),
            )
            db.commit()
            st.success("口座を追加しました")
            st.rerun()
        except sqlite3.IntegrityError:
            st.error("同名の口座が既に存在します")
        finally:
            db.close()
