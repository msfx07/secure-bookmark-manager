import sqlite3
import pyotp
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = "/app/data/bookmarks.db"


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db():
    """Initialize the users table in the consolidated bookmarks.db database."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id                INTEGER   PRIMARY KEY AUTOINCREMENT,
                username          TEXT      UNIQUE NOT NULL,
                password_hash     TEXT      NOT NULL,
                role              TEXT      NOT NULL DEFAULT 'user',
                two_factor_secret TEXT      DEFAULT NULL,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        # Migrate existing installs: add columns if absent (OperationalError = already exists)
        migrations = [
            ("two_factor_secret", "TEXT DEFAULT NULL"),
            ("role", "TEXT NOT NULL DEFAULT 'user'"),
        ]
        for col, defn in migrations:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {defn}")
                conn.commit()
            except sqlite3.OperationalError:
                pass
        
        # Ensure the admin user has admin role (migration fix for existing installs)
        try:
            conn.execute("UPDATE users SET role = 'admin' WHERE username = 'admin'")
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()


class User(UserMixin):
    def __init__(self, id, username, password_hash, role="user", two_factor_secret=None):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self.two_factor_secret = two_factor_secret

    @property
    def has_2fa(self):
        return bool(self.two_factor_secret)

    @property
    def is_admin(self):
        return self.role == "admin"

    @staticmethod
    def _from_row(row):
        if not row:
            return None
        return User(
            row["id"],
            row["username"],
            row["password_hash"],
            row["role"],
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


def create_default_admin():
    """Create the default admin user if it doesn't exist."""
    conn = _get_conn()
    try:
        # Check if admin user exists
        row = conn.execute("SELECT COUNT(*) as count FROM users WHERE username = 'admin'").fetchone()
        if row["count"] == 0:
            # Create default admin user
            try:
                conn.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("admin", generate_password_hash("Secure-Bookmark-Manager"), "admin"),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # User already exists (race condition)
                return False
    finally:
        conn.close()
    return False


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


# ---------------------------------------------------------------------------
# User Management (Admin only)
# ---------------------------------------------------------------------------

def get_all_users():
    """Return all users as a list of dictionaries."""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_user_by_id(user_id):
    """Return a single user as a dictionary, or None."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_user(username, password, role="user"):
    """Create a new user. Returns True on success, False if username taken."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_user(user_id, username=None, password=None, role=None):
    """Update user fields. Only provided (non-None) fields are updated."""
    conn = _get_conn()
    try:
        updates = []
        params = []
        if username is not None:
            updates.append("username = ?")
            params.append(username)
        if password is not None:
            updates.append("password_hash = ?")
            params.append(generate_password_hash(password))
        if role is not None:
            updates.append("role = ?")
            params.append(role)
        if not updates:
            return False
        params.append(user_id)
        conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_user(user_id):
    """Delete a user by ID."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def count_users():
    """Return the total number of users."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
        return row["count"]
    finally:
        conn.close()
