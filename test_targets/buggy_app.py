"""
Sample application with intentional bugs for SENTINEL testing.
DO NOT use this code in production.
"""

import sqlite3
import os
import hashlib
import json
import requests  # unused import


# ── Database helpers ──────────────────────────────────────────────────────────

def get_db():
    return sqlite3.connect("app.db")


def get_user(username):
    """BUG 1: SQL injection — user input concatenated directly into query."""
    db = get_db()
    cursor = db.cursor()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchone()


def get_user_posts(user_id):
    """BUG 2: N+1 query — fetches comments in a loop instead of a JOIN."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, title FROM posts WHERE user_id = ?", (user_id,))
    posts = cursor.fetchall()

    result = []
    for post in posts:
        cursor.execute("SELECT * FROM comments WHERE post_id = ?", (post[0],))
        comments = cursor.fetchall()
        result.append({"post": post, "comments": comments})
    return result


def delete_user(user_id):
    """BUG 3: No error handling — DB errors silently swallowed, no rollback."""
    db = get_db()
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM posts WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def hash_password(password):
    """BUG 4: Weak hashing — MD5 with no salt, cryptographically broken."""
    return hashlib.md5(password.encode()).hexdigest()


def check_password(password, stored_hash):
    return hash_password(password) == stored_hash


def generate_reset_token(email):
    """BUG 5: Predictable token — derived from email + fixed secret, not random."""
    secret = "hardcoded-secret-123"
    return hashlib.md5((email + secret).encode()).hexdigest()


# ── Business logic ────────────────────────────────────────────────────────────

def calculate_discount(price, discount_percent):
    """BUG 6: Logic error — discount applied twice when > 50%."""
    if discount_percent > 50:
        price = price * (1 - discount_percent / 100)
    final = price * (1 - discount_percent / 100)
    return final


def process_payment(amount, currency="USD"):
    """BUG 7: No input validation — negative amounts and unknown currencies accepted."""
    rate = {"USD": 1.0, "EUR": 1.1, "GBP": 1.3}.get(currency, 1.0)
    converted = amount * rate
    return {"status": "charged", "amount": converted, "currency": currency}


def load_config(config_path):
    """BUG 8: Path traversal — user-supplied path not sanitised."""
    with open(config_path, "r") as f:
        return json.load(f)


def export_user_data(user_id, output_dir):
    """BUG 9: Command injection — user_id passed directly into shell command."""
    os.system(f"pg_dump --table=users --where='id={user_id}' mydb > {output_dir}/export.sql")


# ── API calls ─────────────────────────────────────────────────────────────────

def fetch_external_profile(url):
    """BUG 10: SSRF — fetches any URL supplied by caller with no allowlist."""
    resp = requests.get(url, timeout=5)
    return resp.json()
