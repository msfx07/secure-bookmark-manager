#!/usr/bin/env python3
"""
Seed script to create 3 demo users with 5 bookmarks each.
Each user gets bookmarks in different categories.
"""

import sqlite3
import random
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

# Try Docker path first, fall back to local path
DB_PATH = "/app/data/bookmarks.db"
if not os.path.exists(DB_PATH):
    DB_PATH = "data/bookmarks.db"

# Demo users configuration
DEMO_USERS = [
    {"username": "alice", "password": "AliceSecure123!"},
    {"username": "bob", "password": "BobSecure456!"},
    {"username": "charlie", "password": "CharlieSecure789!"},
]

# Bookmark categories
CATEGORIES = [
    {"name": "Work", "emoji": "💼"},
    {"name": "Personal", "emoji": "🏠"},
    {"name": "Learning", "emoji": "📚"},
    {"name": "Entertainment", "emoji": "🎬"},
    {"name": "Shopping", "emoji": "🛒"},
    {"name": "Finance", "emoji": "💰"},
    {"name": "Health", "emoji": "🏥"},
    {"name": "Travel", "emoji": "✈️"},
]

# Sample bookmarks for each user
SAMPLE_BOOKMARKS = {
    "alice": [
        {"title": "GitHub", "url": "https://github.com", "folder": "Work", "tags": "coding,git", "description": "Code hosting platform"},
        {"title": "Stack Overflow", "url": "https://stackoverflow.com", "folder": "Learning", "tags": "programming,help", "description": "Developer Q&A"},
        {"title": "Netflix", "url": "https://netflix.com", "folder": "Entertainment", "tags": "movies,streaming", "description": "Streaming service"},
        {"title": "Amazon", "url": "https://amazon.com", "folder": "Shopping", "tags": "shopping,deals", "description": "Online marketplace"},
        {"title": "MyFitnessPal", "url": "https://myfitnesspal.com", "folder": "Health", "tags": "fitness,tracking", "description": "Health tracking app"},
    ],
    "bob": [
        {"title": "Jira", "url": "https://jira.atlassian.com", "folder": "Work", "tags": "project-management", "description": "Project tracking tool"},
        {"title": "Coursera", "url": "https://coursera.org", "folder": "Learning", "tags": "courses,education", "description": "Online learning platform"},
        {"title": "YouTube", "url": "https://youtube.com", "folder": "Entertainment", "tags": "videos,streaming", "description": "Video sharing platform"},
        {"title": "Etsy", "url": "https://etsy.com", "folder": "Shopping", "tags": "handmade,vintage", "description": "Handmade goods marketplace"},
        {"title": "Strava", "url": "https://strava.com", "folder": "Health", "tags": "running,fitness", "description": "Athletic tracking"},
    ],
    "charlie": [
        {"title": "Slack", "url": "https://slack.com", "folder": "Work", "tags": "communication,team", "description": "Team messaging app"},
        {"title": "Udemy", "url": "https://udemy.com", "folder": "Learning", "tags": "courses,skills", "description": "Online courses"},
        {"title": "Spotify", "url": "https://spotify.com", "folder": "Entertainment", "tags": "music,podcasts", "description": "Music streaming"},
        {"title": "Target", "url": "https://target.com", "folder": "Shopping", "tags": "retail,deals", "description": "Retail store"},
        {"title": "Strava", "url": "https://strava.com", "folder": "Health", "tags": "cycling,fitness", "description": "Athletic tracking"},
    ],
}


def get_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Add role column if it doesn't exist (migration for older databases)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    return conn


def create_user(conn, username, password):
    """Create a new user with hashed password."""
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), "user")
        )
        conn.commit()
        # Get the user ID
        row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        return row["id"] if row else None
    except sqlite3.IntegrityError:
        print(f"  ⚠ User '{username}' already exists, skipping...")
        row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        return row["id"] if row else None


def create_bookmark(conn, user_id, bookmark):
    """Create a bookmark entry."""
    # Random date within last 30 days
    days_ago = random.randint(0, 30)
    created_at = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
    
    conn.execute(
        """INSERT INTO bookmarks (user_id, title, url, description, folder, tags, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, bookmark["title"], bookmark["url"], bookmark.get("description"), 
         bookmark["folder"], bookmark["tags"], created_at)
    )


def create_category_meta(conn, user_id, folder, emoji):
    """Create or update category metadata."""
    try:
        conn.execute(
            "INSERT OR IGNORE INTO category_meta (user_id, category_name, emoji) VALUES (?, ?, ?)",
            (user_id, folder, emoji)
        )
    except sqlite3.IntegrityError:
        pass


def main():
    """Main function to seed demo data."""
    print("=" * 60)
    print("  DEMO USER SEED SCRIPT")
    print("  Creates 3 users with 5 bookmarks each")
    print("=" * 60)
    print()
    
    conn = get_connection()
    created_users = []
    
    for user_config in DEMO_USERS:
        username = user_config["username"]
        password = user_config["password"]
        
        print(f"👤 Creating user: {username}")
        user_id = create_user(conn, username, password)
        
        if user_id:
            # Create bookmarks
            bookmarks = SAMPLE_BOOKMARKS[username]
            for bookmark in bookmarks:
                create_bookmark(conn, user_id, bookmark)
                # Create category metadata
                folder = bookmark["folder"]
                emoji = next((c["emoji"] for c in CATEGORIES if c["name"] == folder), "📁")
                create_category_meta(conn, user_id, folder, emoji)
            
            conn.commit()
            print(f"  ✓ Created {len(bookmarks)} bookmarks in {len(set(b['folder'] for b in bookmarks))} categories")
            
            created_users.append({
                "username": username,
                "password": password,
                "user_id": user_id,
                "bookmarks": len(bookmarks),
            })
        print()
    
    conn.close()
    
    # Display summary report
    print("=" * 60)
    print("  SUMMARY REPORT")
    print("=" * 60)
    print()
    print(f"{'Username':<15} {'Password':<25} {'User ID':<10} {'Bookmarks':<10}")
    print("-" * 60)
    
    for user in created_users:
        print(f"{user['username']:<15} {user['password']:<25} {user['user_id']:<10} {user['bookmarks']:<10}")
    
    print("-" * 60)
    print(f"\n✅ Total users created: {len(created_users)}")
    print(f"✅ Total bookmarks created: {sum(u['bookmarks'] for u in created_users)}")
    print()
    print("📝 All users have role: 'user' (regular users)")
    print("📝 Default admin account: admin / Secure-Bookmark-Manager")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
