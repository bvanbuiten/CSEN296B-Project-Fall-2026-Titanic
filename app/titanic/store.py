"""Structured application database (SQLite). This is Titanic's long-term memory.

Holds customers, orders, cases, refunds, deposits, emails, case notes, policies,
supervisor decisions, the agent's authority state, and a records-access log.
All data is synthetic. Money is stored in whole cents.
"""
import json
import sqlite3
import threading
import uuid
from datetime import timedelta

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY, name TEXT, email TEXT, pin TEXT,
    bank_account TEXT, balance_cents INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, customer_id TEXT, item TEXT, amount_cents INTEGER, purchased_at TEXT);
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY, customer_id TEXT, order_id TEXT, channel TEXT,
    requested_cents INTEGER, reason TEXT, status TEXT, assigned_to TEXT,
    flags TEXT, decision TEXT, decision_reason TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS refunds (
    id TEXT PRIMARY KEY, case_id TEXT, customer_id TEXT, order_id TEXT,
    amount_cents INTEGER, approved_by TEXT, autonomous INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS deposits (
    id TEXT PRIMARY KEY, customer_id TEXT, amount_cents INTEGER, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY, direction TEXT, folder TEXT, label TEXT, from_addr TEXT, to_addr TEXT,
    subject TEXT, body TEXT, case_id TEXT, customer_id TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS case_notes (
    id TEXT PRIMARY KEY, case_id TEXT, customer_id TEXT, author TEXT, note TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS policies (
    id TEXT PRIMARY KEY, title TEXT, version TEXT, body TEXT, uploaded_by TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS supervisor_decisions (
    id TEXT PRIMARY KEY, case_id TEXT, decision TEXT, supervisor TEXT, note TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS authority (
    agent TEXT PRIMARY KEY, status TEXT, changed_by TEXT, changed_at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS access_log (
    id TEXT PRIMARY KEY, actor TEXT, tool TEXT, session_customer TEXT, target_customer TEXT,
    allowed INTEGER, created_at TEXT);
"""


def new_id(prefix):
    return f'{prefix}-{uuid.uuid4().hex[:8].upper()}'


class Store:
    def __init__(self, db_path, clock=None):
        self.clock = clock or config.utcnow
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # --- helpers --------------------------------------------------------------
    def now(self):
        return self.clock().isoformat()

    def q(self, sql, args=()):
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql, args=()):
        with self._lock:
            self.conn.execute(sql, args)
            self.conn.commit()

    # --- seeding ----------------------------------------------------------------
    def is_seeded(self):
        return self.one('SELECT COUNT(*) AS n FROM customers')['n'] > 0

    def seed(self, seed_dir=config.SEED_DIR):
        customers = json.loads((seed_dir / 'customers.json').read_text())
        orders = json.loads((seed_dir / 'orders.json').read_text())
        now = self.clock()
        for c in customers:
            self.x('INSERT OR REPLACE INTO customers VALUES (?,?,?,?,?,?,?)',
                   (c['id'], c['name'], c['email'], c['pin'], c['bank_account'], c['balance_cents'], now.isoformat()))
        for o in orders:
            purchased = (now - timedelta(days=o['days_ago'])).isoformat()
            self.x('INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?)',
                   (o['id'], o['customer_id'], o['item'], o['amount_cents'], purchased))
        for p in sorted((seed_dir / 'policies').glob('*.md')):
            body = p.read_text()
            title = body.splitlines()[0].lstrip('# ').strip()
            self.x('INSERT OR REPLACE INTO policies VALUES (?,?,?,?,?,?)',
                   (p.stem, title, 'v1', body, 'seed', now.isoformat()))
        self.x("INSERT OR REPLACE INTO authority VALUES ('titanic-agent','active','seed',?,'')", (now.isoformat(),))

    # --- customers & orders ---------------------------------------------------
    def customer(self, customer_id):
        return self.one('SELECT * FROM customers WHERE id=?', (customer_id,))

    def customers(self):
        return self.q('SELECT id, name, email FROM customers ORDER BY id')

    def customer_ids_and_emails(self):
        return self.q('SELECT id, email FROM customers')

    def order(self, order_id):
        return self.one('SELECT * FROM orders WHERE id=?', (order_id,))

    def orders_for(self, customer_id):
        rows = self.q('SELECT * FROM orders WHERE customer_id=? ORDER BY purchased_at DESC', (customer_id,))
        for r in rows:
            r['refunded_cents'] = self.refunded_on_order(r['id'])
        return rows

    def refunded_on_order(self, order_id):
        return self.one('SELECT COALESCE(SUM(amount_cents),0) AS s FROM refunds WHERE order_id=?', (order_id,))['s']

    def adjust_balance(self, customer_id, delta_cents):
        self.x('UPDATE customers SET balance_cents = balance_cents + ? WHERE id=?', (delta_cents, customer_id))

    # --- cases ------------------------------------------------------------------
    def create_case(self, customer_id, order_id, requested_cents, reason, channel):
        case_id = new_id('CASE')
        now = self.now()
        self.x('INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (case_id, customer_id, order_id, channel, requested_cents, reason, 'submitted', None,
                '[]', None, None, now, now))
        return self.case(case_id)

    def case(self, case_id):
        row = self.one('SELECT * FROM cases WHERE id=?', (case_id,))
        if row:
            row['flags'] = json.loads(row['flags'] or '[]')
        return row

    def cases_for(self, customer_id):
        rows = self.q('SELECT * FROM cases WHERE customer_id=? ORDER BY created_at DESC', (customer_id,))
        for r in rows:
            r['flags'] = json.loads(r['flags'] or '[]')
        return rows

    def all_cases(self):
        rows = self.q('SELECT * FROM cases ORDER BY created_at DESC')
        for r in rows:
            r['flags'] = json.loads(r['flags'] or '[]')
        return rows

    def update_case(self, case_id, **fields):
        if 'flags' in fields:
            fields['flags'] = json.dumps(fields['flags'])
        fields['updated_at'] = self.now()
        cols = ', '.join(f'{k}=?' for k in fields)
        self.x(f'UPDATE cases SET {cols} WHERE id=?', (*fields.values(), case_id))

    # --- refunds ----------------------------------------------------------------
    def record_refund(self, case_id, customer_id, order_id, amount_cents, approved_by, autonomous):
        refund_id = new_id('RFD')
        self.x('INSERT INTO refunds VALUES (?,?,?,?,?,?,?,?)',
               (refund_id, case_id, customer_id, order_id, amount_cents, approved_by, 1 if autonomous else 0, self.now()))
        return refund_id

    def refunds(self):
        return self.q('SELECT * FROM refunds ORDER BY created_at')

    def autonomous_total_since(self, since_iso):
        return self.one('SELECT COALESCE(SUM(amount_cents),0) AS s FROM refunds WHERE autonomous=1 AND created_at>=?',
                        (since_iso,))['s']

    # --- deposits ---------------------------------------------------------------
    def create_deposit(self, customer_id, amount_cents):
        dep_id = new_id('DEP')
        self.x('INSERT INTO deposits VALUES (?,?,?,?,?)', (dep_id, customer_id, amount_cents, 'pending', self.now()))
        return self.one('SELECT * FROM deposits WHERE id=?', (dep_id,))

    def deposit(self, deposit_id):
        return self.one('SELECT * FROM deposits WHERE id=?', (deposit_id,))

    # --- emails -----------------------------------------------------------------
    def add_email(self, direction, folder, from_addr, to_addr, subject, body, case_id=None, customer_id=None, label=''):
        email_id = new_id('MSG')
        self.x('INSERT INTO emails VALUES (?,?,?,?,?,?,?,?,?,?,?)',
               (email_id, direction, folder, label, from_addr, to_addr, subject, body, case_id, customer_id, self.now()))
        return email_id

    def emails(self, **filters):
        sql, args = 'SELECT * FROM emails WHERE 1=1', []
        for k, v in filters.items():
            sql += f' AND {k}=?'
            args.append(v)
        return self.q(sql + ' ORDER BY created_at DESC', args)

    # --- notes, policies, supervisor, authority, access log ----------------------
    def add_note(self, case_id, customer_id, author, note):
        self.x('INSERT INTO case_notes VALUES (?,?,?,?,?,?)', (new_id('NOTE'), case_id, customer_id, author, note, self.now()))

    def notes_for_case(self, case_id):
        return self.q('SELECT * FROM case_notes WHERE case_id=? ORDER BY created_at', (case_id,))

    def policies(self):
        return self.q('SELECT id, title, version, uploaded_by, created_at, body FROM policies ORDER BY created_at, id')

    def add_policy(self, title, body, uploaded_by):
        pid = new_id('POL')
        self.x('INSERT INTO policies VALUES (?,?,?,?,?,?)', (pid, title, 'v1', body, uploaded_by, self.now()))
        return pid

    def add_supervisor_decision(self, case_id, decision, supervisor, note):
        self.x('INSERT INTO supervisor_decisions VALUES (?,?,?,?,?,?)',
               (new_id('SUP'), case_id, decision, supervisor, note, self.now()))

    def supervisor_decision(self, case_id):
        return self.one('SELECT * FROM supervisor_decisions WHERE case_id=? ORDER BY created_at DESC', (case_id,))

    def authority(self):
        return self.one("SELECT * FROM authority WHERE agent='titanic-agent'")

    def set_authority(self, status, changed_by, note=''):
        self.x("INSERT OR REPLACE INTO authority VALUES ('titanic-agent',?,?,?,?)", (status, changed_by, self.now(), note))

    def log_access(self, actor, tool, session_customer, target_customer, allowed):
        self.x('INSERT INTO access_log VALUES (?,?,?,?,?,?,?)',
               (new_id('ACC'), actor, tool, session_customer, target_customer, 1 if allowed else 0, self.now()))

    def access_log(self):
        return self.q('SELECT * FROM access_log ORDER BY created_at')
