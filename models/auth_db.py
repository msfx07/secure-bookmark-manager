import sqlite3
import pyotp
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = "/app/data/auth.db"


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db():
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id                INTEGER   PRIMARY KEY AUTOINCREMENT,
                username          TEXT      UNIQUE NOT NULL,
                password_hash     TEXT      NOT NULL,
                two_factor_secret TEXT      DEFAULT NULL,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        # Migrate existing installs: add column if absent (OperationalError = already exists)
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN two_factor_secret TEXT DEFAULT NULL"
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()


class User(UserMixin):
    def __init__(self, id, username, password_hash, two_factor_secret=None):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.two_factor_secret = two_factor_secret

    @property
    def has_2fa(self):
        return bool(self.two_factor_secret)

    @staticmethod
    def _from_row(row):
        if not row:
            return None
        return User(
            row["id"],
            row["username"],
            row["password_hash"],
            row["two_factor_secret"],
        )

    @staticmethod
    def get_by_id(user_id):
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        finally:
            conn.close()
        return User._from_row(row)

    @staticmethod
    def get_by_username(username):
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        finally:
            conn.close()
        return User._from_row(row)


def register_user(username, password):
    """Returns True on success, False if username is already taken."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def verify_user(username, password):
    """Returns the User object on success, None on failure."""
    user = User.get_by_username(username)
    if user and check_password_hash(user.password_hash, password):
        return user
    return None


def save_2fa_secret(user_id, secret):
    """Persist a confirmed TOTP secret, enabling 2FA for this user."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE users SET two_factor_secret = ? WHERE id = ?",
            (secret, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def clear_2fa_secret(user_id):
    """Set two_factor_secret to NULL, disabling 2FA for this user."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE users SET two_factor_secret = NULL WHERE id = ?",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()


def verify_totp(secret, token):
    """Return True if token is valid. valid_window=1 allows ±30s clock drift."""
    return pyotp.TOTP(secret).verify(token, valid_window=1)


def update_password_hash(user_id, new_hash):
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_user_account(user_id):
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
