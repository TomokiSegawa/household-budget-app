import sqlite3
import os
from datetime import datetime, date
from flask import Flask, render_template, request, jsonify, g

app = Flask(__name__)
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kakeibo.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
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

    # Insert default categories if empty
    cursor = db.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        expense_categories = [
            "食費",
            "日用品",
            "住居費",
            "水道光熱費",
            "通信費",
            "交通費",
            "衣服・美容",
            "医療・健康",
            "教育・教養",
            "趣味・娯楽",
            "交際費",
            "保険",
            "税金・社会保険",
            "その他支出",
        ]
        income_categories = [
            "給与",
            "賞与",
            "副業",
            "投資収益",
            "その他収入",
        ]
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

    # Insert default accounts if empty
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


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API: Categories
# ---------------------------------------------------------------------------
@app.route("/api/categories")
def api_categories():
    db = get_db()
    rows = db.execute("SELECT * FROM categories ORDER BY type, sort_order").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/categories", methods=["POST"])
def api_add_category():
    data = request.get_json()
    db = get_db()
    try:
        db.execute(
            "INSERT INTO categories (name, type, sort_order) VALUES (?, ?, ?)",
            (data["name"], data["type"], data.get("sort_order", 0)),
        )
        db.commit()
        return jsonify({"ok": True}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "同名のカテゴリが既に存在します"}), 400


# ---------------------------------------------------------------------------
# API: Accounts
# ---------------------------------------------------------------------------
@app.route("/api/accounts")
def api_accounts():
    db = get_db()
    rows = db.execute("SELECT * FROM accounts ORDER BY sort_order").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/accounts", methods=["POST"])
def api_add_account():
    data = request.get_json()
    db = get_db()
    try:
        db.execute(
            "INSERT INTO accounts (name, type, initial_balance, sort_order) VALUES (?, ?, ?, ?)",
            (
                data["name"],
                data["type"],
                data.get("initial_balance", 0),
                data.get("sort_order", 0),
            ),
        )
        db.commit()
        return jsonify({"ok": True}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "同名の口座が既に存在します"}), 400


# ---------------------------------------------------------------------------
# API: Transactions
# ---------------------------------------------------------------------------
@app.route("/api/transactions")
def api_transactions():
    db = get_db()
    year_month = request.args.get("year_month")  # e.g. "2026-02"
    account_id = request.args.get("account_id")
    category_id = request.args.get("category_id")

    query = """
        SELECT t.*, c.name AS category_name, c.type AS category_type,
               a.name AS account_name
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        JOIN accounts a ON t.account_id = a.id
    """
    conditions = []
    params = []
    if year_month:
        conditions.append("strftime('%Y-%m', t.date) = ?")
        params.append(year_month)
    if account_id:
        conditions.append("t.account_id = ?")
        params.append(int(account_id))
    if category_id:
        conditions.append("t.category_id = ?")
        params.append(int(category_id))
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY t.date DESC, t.id DESC"

    rows = db.execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/transactions", methods=["POST"])
def api_add_transaction():
    data = request.get_json()
    db = get_db()
    db.execute(
        "INSERT INTO transactions (date, type, amount, category_id, account_id, memo) VALUES (?, ?, ?, ?, ?, ?)",
        (
            data["date"],
            data["type"],
            int(data["amount"]),
            int(data["category_id"]),
            int(data["account_id"]),
            data.get("memo", ""),
        ),
    )
    db.commit()
    return jsonify({"ok": True}), 201


@app.route("/api/transactions/<int:tid>", methods=["PUT"])
def api_update_transaction(tid):
    data = request.get_json()
    db = get_db()
    db.execute(
        """UPDATE transactions
           SET date=?, type=?, amount=?, category_id=?, account_id=?, memo=?
           WHERE id=?""",
        (
            data["date"],
            data["type"],
            int(data["amount"]),
            int(data["category_id"]),
            int(data["account_id"]),
            data.get("memo", ""),
            tid,
        ),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/transactions/<int:tid>", methods=["DELETE"])
def api_delete_transaction(tid):
    db = get_db()
    db.execute("DELETE FROM transactions WHERE id=?", (tid,))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API: Summary (月次・カテゴリ別集計)
# ---------------------------------------------------------------------------
@app.route("/api/summary")
def api_summary():
    """Return category-level totals for a given month, plus comparison data."""
    db = get_db()
    year_month = request.args.get("year_month", date.today().strftime("%Y-%m"))
    year, month = map(int, year_month.split("-"))

    # Current month totals by category
    rows = db.execute(
        """
        SELECT c.id AS category_id, c.name AS category_name, c.type,
               COALESCE(SUM(t.amount), 0) AS total
        FROM categories c
        LEFT JOIN transactions t
          ON t.category_id = c.id AND strftime('%Y-%m', t.date) = ?
        GROUP BY c.id
        ORDER BY c.type, c.sort_order
    """,
        (year_month,),
    ).fetchall()

    # Previous month
    if month == 1:
        prev_ym = f"{year - 1}-12"
    else:
        prev_ym = f"{year}-{month - 1:02d}"
    prev_rows = db.execute(
        """
        SELECT c.id AS category_id, COALESCE(SUM(t.amount), 0) AS total
        FROM categories c
        LEFT JOIN transactions t
          ON t.category_id = c.id AND strftime('%Y-%m', t.date) = ?
        GROUP BY c.id
    """,
        (prev_ym,),
    ).fetchall()
    prev_map = {r["category_id"]: r["total"] for r in prev_rows}

    # Same month last year
    prev_year_ym = f"{year - 1}-{month:02d}"
    prev_year_rows = db.execute(
        """
        SELECT c.id AS category_id, COALESCE(SUM(t.amount), 0) AS total
        FROM categories c
        LEFT JOIN transactions t
          ON t.category_id = c.id AND strftime('%Y-%m', t.date) = ?
        GROUP BY c.id
    """,
        (prev_year_ym,),
    ).fetchall()
    prev_year_map = {r["category_id"]: r["total"] for r in prev_year_rows}

    # Budgets for current month
    budget_rows = db.execute(
        "SELECT category_id, amount FROM budgets WHERE year_month = ?",
        (year_month,),
    ).fetchall()
    budget_map = {r["category_id"]: r["amount"] for r in budget_rows}

    # Grand totals
    total_income = sum(dict(r)["total"] for r in rows if r["type"] == "income")
    total_expense = sum(dict(r)["total"] for r in rows if r["type"] == "expense")

    result = []
    for r in rows:
        d = dict(r)
        cid = d["category_id"]
        d["prev_month_total"] = prev_map.get(cid, 0)
        d["prev_year_total"] = prev_year_map.get(cid, 0)
        d["budget"] = budget_map.get(cid, None)
        result.append(d)

    return jsonify(
        {
            "year_month": year_month,
            "categories": result,
            "total_income": total_income,
            "total_expense": total_expense,
            "balance": total_income - total_expense,
        }
    )


# ---------------------------------------------------------------------------
# API: Balances (口座残高一覧)
# ---------------------------------------------------------------------------
@app.route("/api/balances")
def api_balances():
    db = get_db()
    rows = db.execute(
        """
        SELECT a.id, a.name, a.type, a.initial_balance,
               COALESCE(SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE 0 END), 0) AS total_income,
               COALESCE(SUM(CASE WHEN t.type = 'expense' THEN t.amount ELSE 0 END), 0) AS total_expense
        FROM accounts a
        LEFT JOIN transactions t ON t.account_id = a.id
        GROUP BY a.id
        ORDER BY a.sort_order
    """
    ).fetchall()

    result = []
    grand_total = 0
    for r in rows:
        d = dict(r)
        balance = d["initial_balance"] + d["total_income"] - d["total_expense"]
        d["current_balance"] = balance
        grand_total += balance
        result.append(d)

    return jsonify({"accounts": result, "grand_total": grand_total})


# ---------------------------------------------------------------------------
# API: Budgets
# ---------------------------------------------------------------------------
@app.route("/api/budgets")
def api_budgets():
    db = get_db()
    year_month = request.args.get("year_month", date.today().strftime("%Y-%m"))
    rows = db.execute(
        """
        SELECT b.id, b.category_id, c.name AS category_name, b.year_month, b.amount
        FROM budgets b
        JOIN categories c ON b.category_id = c.id
        WHERE b.year_month = ?
        ORDER BY c.sort_order
    """,
        (year_month,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/budgets", methods=["POST"])
def api_save_budgets():
    """Save/update budgets. Expects {year_month, budgets: [{category_id, amount}]}."""
    data = request.get_json()
    db = get_db()
    year_month = data["year_month"]
    for item in data["budgets"]:
        db.execute(
            """
            INSERT INTO budgets (category_id, year_month, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(category_id, year_month)
            DO UPDATE SET amount = excluded.amount
        """,
            (int(item["category_id"]), year_month, int(item["amount"])),
        )
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API: Monthly trend (for charts)
# ---------------------------------------------------------------------------
@app.route("/api/monthly_trend")
def api_monthly_trend():
    db = get_db()
    months = int(request.args.get("months", 12))
    rows = db.execute(
        """
        SELECT strftime('%Y-%m', date) AS ym,
               SUM(CASE WHEN type='income' THEN amount ELSE 0 END) AS income,
               SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        GROUP BY ym
        ORDER BY ym DESC
        LIMIT ?
    """,
        (months,),
    ).fetchall()
    result = [dict(r) for r in rows]
    result.reverse()
    return jsonify(result)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5001)
