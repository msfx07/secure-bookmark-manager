import sqlite3

DB_PATH = "/app/data/bookmarks.db"


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_bookmark_db():
    """Initialize bookmarks and category_meta tables in the consolidated database."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                id          INTEGER   PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER   NOT NULL,
                title       TEXT      NOT NULL,
                url         TEXT      NOT NULL,
                description TEXT      DEFAULT NULL,
                folder      TEXT      NOT NULL DEFAULT 'Uncategorized',
                tags        TEXT      NOT NULL DEFAULT '',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        # Idempotent migrations: add columns absent from existing installs
        _migrations = [
            ("description",      "TEXT DEFAULT NULL"),
            ("updated_at",       "TIMESTAMP DEFAULT NULL"),
            ("last_accessed_at", "TIMESTAMP DEFAULT NULL"),
            ("status",           "TEXT DEFAULT 'active'"),
            ("last_validated_at","TIMESTAMP DEFAULT NULL"),
        ]
        for col, defn in _migrations:
            try:
                conn.execute(f"ALTER TABLE bookmarks ADD COLUMN {col} {defn}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

        # Category emoji metadata — idempotent, safe to run on every startup
        conn.execute("""
            CREATE TABLE IF NOT EXISTS category_meta (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                category_name TEXT    NOT NULL,
                emoji         TEXT    NOT NULL DEFAULT '📁',
                UNIQUE(user_id, category_name)
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------

def add_bookmark(user_id, title, url, folder="Uncategorized", tags="", description=""):
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO bookmarks (user_id, title, url, description, folder, tags)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, title, url, description or None, folder, tags),
        )
        conn.commit()
    finally:
        conn.close()


def get_bookmarks(user_id, folder=None):
    conn = _get_conn()
    try:
        if folder:
            rows = conn.execute(
                "SELECT * FROM bookmarks WHERE user_id = ? AND folder = ? ORDER BY created_at DESC",
                (user_id, folder),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM bookmarks WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def get_bookmark(bookmark_id, user_id):
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM bookmarks WHERE id = ? AND user_id = ?",
            (bookmark_id, user_id),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def update_bookmark(bookmark_id, user_id, title, url, description, folder, tags):
    conn = _get_conn()
    try:
        conn.execute(
            """UPDATE bookmarks
               SET title = ?, url = ?, description = ?, folder = ?, tags = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND user_id = ?""",
            (title, url, description or None, folder, tags, bookmark_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def log_bookmark_access(bookmark_id):
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE bookmarks SET last_accessed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (bookmark_id,),
        )
        conn.commit()
    finally:
        conn.close()


def delete_bookmark(bookmark_id, user_id):
    conn = _get_conn()
    try:
        conn.execute(
            "DELETE FROM bookmarks WHERE id = ? AND user_id = ?",
            (bookmark_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Categories  (flat — single level only, per claude.md)
# ---------------------------------------------------------------------------

def get_category_emoji_map(user_id):
    """Return {category_name: emoji} for every customised category owned by user_id."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT category_name, emoji FROM category_meta WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return {row["category_name"]: row["emoji"] for row in rows}


def update_category_emoji(user_id, category_name, emoji):
    """Upsert a custom emoji for one category. Safe to call repeatedly."""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO category_meta (user_id, category_name, emoji)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, category_name)
               DO UPDATE SET emoji = excluded.emoji""",
            (user_id, category_name.strip(), emoji),
        )
        conn.commit()
    finally:
        conn.close()

def get_folders(user_id):
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT folder FROM bookmarks WHERE user_id = ? ORDER BY folder",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return [row["folder"] for row in rows]


def rename_user_category(user_id, old_name, new_name):
    clean_old = old_name.strip().lower()
    clean_new = new_name.strip()
    modified_count = 0
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "SELECT id, folder FROM bookmarks WHERE user_id = ?",
            (user_id,),
        )
        for row in cursor.fetchall():
            bookmark_id = row["id"]
            current_folder = row["folder"].strip().lower() if row["folder"] else ""
            if current_folder == clean_old:
                cursor.execute(
                    "UPDATE bookmarks SET folder = ? WHERE id = ? AND user_id = ?",
                    (clean_new, bookmark_id, user_id),
                )
                modified_count += 1
        conn.commit()
        return modified_count
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------

def bulk_delete_bookmarks(user_id, ids):
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    conn = _get_conn()
    try:
        cursor = conn.execute(
            f"DELETE FROM bookmarks WHERE id IN ({placeholders}) AND user_id = ?",
            (*ids, user_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_bookmarks(user_id, query):
    pattern = f"%{query}%"
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM bookmarks
               WHERE user_id = ?
                 AND (title LIKE ? OR url LIKE ? OR folder LIKE ? OR tags LIKE ?)
               ORDER BY created_at DESC""",
            (user_id, pattern, pattern, pattern, pattern),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Data portability
# ---------------------------------------------------------------------------

def get_bookmark_urls(user_id):
    """Return a set of all URLs already saved by this user (for duplicate checks)."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT url FROM bookmarks WHERE user_id = ?", (user_id,)
        ).fetchall()
    finally:
        conn.close()
    return {row["url"] for row in rows}


def update_bookmark_status(bookmark_id, status):
    conn = _get_conn()
    try:
        conn.execute(
            """UPDATE bookmarks
               SET status = ?, last_validated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (status, bookmark_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_bookmarks_for_validation(user_id):
    """Return [{id, url}] for every bookmark belonging to user_id."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT id, url FROM bookmarks
               WHERE user_id = ?
               ORDER BY last_validated_at ASC NULLS FIRST""",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def get_all_bookmarks_for_validation():
    """Return [{id, url}] for every bookmark in the database (all users)."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT id, url FROM bookmarks
               ORDER BY last_validated_at ASC NULLS FIRST"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def delete_all_user_bookmarks(user_id):
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM bookmarks WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def import_bookmarks_batch(user_id, bookmarks_list):
    """
    Insert a list of bookmark dicts in a single transaction.
    Each dict must have 'title' and 'url'; 'folder', 'tags', 'description' are optional.
    """
    conn = _get_conn()
    try:
        conn.executemany(
            """INSERT INTO bookmarks (user_id, title, url, folder, tags, description)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    user_id,
                    b["title"],
                    b["url"],
                    b.get("folder") or "Imported",
                    b.get("tags") or "",
                    b.get("description") or None,
                )
                for b in bookmarks_list
            ],
        )
        conn.commit()
    finally:
        conn.close()
