import os
from urllib.parse import urlparse
from flask import Flask
from flask_login import LoginManager
from models.auth_db import init_auth_db, create_default_admin, User
from models.bookmark_db import init_bookmark_db
from services.validator import start_background_validator

app = Flask(__name__)

_secret_key = os.environ.get("SECRET_KEY", "").strip()
if not _secret_key:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Add a strong random value to your .env file before starting the application."
    )
app.secret_key = _secret_key

@app.template_filter("safe_url")
def safe_url_filter(url: str) -> str:
    """Jinja2 filter: return the URL only when its scheme is http or https.
    Any other scheme (javascript:, data:, vbscript:, …) is replaced with '#'
    so stored XSS payloads cannot execute via rendered href attributes."""
    try:
        if urlparse(url).scheme in ("http", "https"):
            return url
    except Exception:
        pass
    return "#"


login_manager = LoginManager(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(int(user_id))


def initialize_databases():
    init_auth_db()
    init_bookmark_db()
    # Create default admin user if no users exist
    if create_default_admin():
        print("[INFO] Default admin user created: admin / Secure-Bookmark-Manager")


with app.app_context():
    initialize_databases()

from routes.auth import auth as auth_bp
from routes.bookmarks import bookmarks as bookmarks_bp
from routes.admin import admin as admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(bookmarks_bp)
app.register_blueprint(admin_bp)

start_background_validator()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
