# database.py
import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DATABASE_PATH", "bot.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS vendors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    user_id INTEGER,
                    status TEXT,
                    created_at TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vendor_id INTEGER,
                    name TEXT,
                    price REAL,
                    stock INTEGER,
                    created_at TEXT,
                    FOREIGN KEY(vendor_id) REFERENCES vendors(id))''')
    conn.commit()
    conn.close()

def set_setting(key, value):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else None

# vendors
def add_vendor(username, user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO vendors (username, user_id, status, created_at) VALUES (?, ?, ?, ?)",
                (username, user_id, "pendiente", datetime.utcnow().isoformat()))
    conn.commit()
    cur.execute("SELECT id FROM vendors WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row["id"] if row else None

def get_vendor_by_username(username):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM vendors WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def get_vendor_by_id(vid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM vendors WHERE id = ?", (vid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def set_vendor_status(username, status):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE vendors SET status = ? WHERE username = ?", (status, username))
    conn.commit()
    conn.close()

# products
def add_product(vendor_id, name, price, stock):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("INSERT INTO products (vendor_id, name, price, stock, created_at) VALUES (?, ?, ?, ?, ?)",
                (vendor_id, name, price, stock, now))
    conn.commit()
    prod_id = cur.lastrowid
    conn.close()
    return prod_id

def get_all_products():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""SELECT p.id, p.name, p.price, p.stock, p.vendor_id, v.username
                   FROM products p LEFT JOIN vendors v ON p.vendor_id = v.id
                   ORDER BY p.id DESC""")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_product_by_id(pid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id = ?", (pid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def update_stock(pid, new_stock):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, pid))
    conn.commit()
    conn.close()

def update_price(pid, new_price):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE products SET price = ? WHERE id = ?", (new_price, pid))
    conn.commit()
    conn.close()

def delete_product(pid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit()
    conn.close()

def search_products(q):
    q_like = f"%{q}%"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""SELECT p.id, p.name, p.price, p.stock, p.vendor_id, v.username
                   FROM products p LEFT JOIN vendors v ON p.vendor_id = v.id
                   WHERE LOWER(p.name) LIKE LOWER(?) OR LOWER(v.username) LIKE LOWER(?)
                   ORDER BY p.id DESC""", (q_like, q_like))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
