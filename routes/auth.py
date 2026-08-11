import io
import hashlib
import base64
import pyotp
import qrcode
import requests
from urllib.parse import urlparse, urljoin
from flask import (
    Blueprint, render_template, redirect, url_for,
    request, flash, session,
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from models.auth_db import (
    verify_user, create_default_admin,
    save_2fa_secret, clear_2fa_secret, verify_totp,
    update_password_hash, delete_user_account,
)
from models.bookmark_db import delete_all_user_bookmarks

auth = Blueprint("auth", __name__)

# Endpoints that a 2FA-pending user is still allowed to reach
_2FA_EXEMPT = {"auth.verify_2fa", "auth.logout", "static"}

_HIBP_HEADERS = {"User-Agent": "SecureBookmarkManager/1.0"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_safe_redirect(target):
    """Guard against open-redirect attacks on the ?next= parameter."""
    ref  = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


def _make_qr_b64(uri):
    """Encode a QR code as a base64 PNG string — no temp files written."""
    buf = io.BytesIO()
    qrcode.make(uri).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _is_password_breached(password):
    """
    k-anonymity range check against the Have I Been Pwned API.
    Sends only the first 5 characters of the SHA-1 hash; the full hash
    never leaves the server. Fails open on any network error so a transient
    API outage never blocks a legitimate registration.
    """
    sha1_hash = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix    = sha1_hash[:5]
    suffix    = sha1_hash[5:]

    try:
        resp = requests.get(
            f"https://api.pwnedpasswords.com/range/{prefix}",
            headers=_HIBP_HEADERS,
            timeout=3,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return False  # fail open — network trouble should not block registration

    for line in resp.text.splitlines():
        parts = line.split(":")
        if len(parts) == 2 and parts[0] == suffix:
            return int(parts[1]) > 0

    return False


# ---------------------------------------------------------------------------
# Global 2FA checkpoint — fires before every request in the application
# ---------------------------------------------------------------------------

@auth.before_app_request
def enforce_2fa_checkpoint():
    if not current_user.is_authenticated:
        return
    if not current_user.has_2fa:
        return
    if session.get("2fa_verified"):
        return
    if request.endpoint in _2FA_EXEMPT:
        return
    return redirect(url_for("auth.verify_2fa"))


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("bookmarks.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").lower().strip()
        password = request.form.get("password", "")
        user = verify_user(username, password)

        if user:
            login_user(user)
            if user.has_2fa:
                session["2fa_verified"] = False
                return redirect(url_for("auth.verify_2fa"))
            next_page = request.args.get("next")
            if next_page and not _is_safe_redirect(next_page):
                next_page = None
            return redirect(next_page or url_for("bookmarks.dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@auth.route("/logout")
@login_required
def logout():
    session.pop("2fa_verified", None)
    session.pop("2fa_setup_secret", None)
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# 2FA Setup — authenticated users opt in from the dashboard
# ---------------------------------------------------------------------------

@auth.route("/2fa-setup", methods=["GET", "POST"])
@login_required
def setup_2fa():
    if request.method == "POST":
        token  = request.form.get("token", "").strip()
        secret = session.get("2fa_setup_secret")

        if not secret:
            flash("Setup session expired. Please start again.", "warning")
            return redirect(url_for("auth.setup_2fa"))

        if verify_totp(secret, token):
            save_2fa_secret(current_user.id, secret)
            session.pop("2fa_setup_secret", None)
            session["2fa_verified"] = True   # already proven — no re-prompt
            flash("Two-factor authentication is now enabled.", "success")
            return redirect(url_for("bookmarks.dashboard"))

        flash("Invalid code. Please try again.", "danger")
        return redirect(url_for("auth.setup_2fa"))

    # GET — generate a fresh secret each time the page loads
    secret = pyotp.random_base32()
    session["2fa_setup_secret"] = secret
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=current_user.username,
        issuer_name="SecureBookmarkManager",
    )
    return render_template("2fa_setup.html", qr_b64=_make_qr_b64(uri), secret=secret)


# ---------------------------------------------------------------------------
# 2FA Verify — login checkpoint for users who have 2FA enabled
# ---------------------------------------------------------------------------

@auth.route("/2fa-verify", methods=["GET", "POST"])
@login_required
def verify_2fa():
    # Safety valves — redirect away if there is nothing to verify
    if not current_user.has_2fa:
        return redirect(url_for("bookmarks.dashboard"))
    if session.get("2fa_verified"):
        return redirect(url_for("bookmarks.dashboard"))

    if request.method == "POST":
        token = request.form.get("token", "").strip()
        if verify_totp(current_user.two_factor_secret, token):
            session["2fa_verified"] = True
            flash("Verification successful. Welcome back.", "success")
            next_page = request.args.get("next")
            if next_page and not _is_safe_redirect(next_page):
                next_page = None
            return redirect(next_page or url_for("bookmarks.dashboard"))
        flash("Invalid or expired code. Please try again.", "danger")

    return render_template("2fa_verify.html")


# ---------------------------------------------------------------------------
# Password rotation
# ---------------------------------------------------------------------------

@auth.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current_password   = request.form.get("current_password", "")
    new_password       = request.form.get("new_password", "")
    confirm_new        = request.form.get("confirm_new_password", "")

    # Step 1 — re-authenticate
    if not check_password_hash(current_user.password_hash, current_password):
        flash("Incorrect current password. Verification failed.", "danger")
        return redirect(url_for("bookmarks.dashboard"))

    # Step 2 — policy checks
    if not (14 <= len(new_password) <= 64):
        flash("Password must be between 14 and 64 characters long.", "danger")
        return redirect(url_for("bookmarks.dashboard"))
    if " " in new_password:
        flash("Password must not contain spaces.", "danger")
        return redirect(url_for("bookmarks.dashboard"))

    # Step 3 — breach check
    if _is_password_breached(new_password):
        flash(
            "This password has been found in a public data breach and is unsafe "
            "to use. Please choose a different passphrase.",
            "danger",
        )
        return redirect(url_for("bookmarks.dashboard"))

    if new_password != confirm_new:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("bookmarks.dashboard"))

    update_password_hash(current_user.id, generate_password_hash(new_password))
    flash("Your password has been successfully updated.", "success")
    return redirect(url_for("bookmarks.dashboard"))


# ---------------------------------------------------------------------------
# Account termination
# ---------------------------------------------------------------------------

@auth.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    password = request.form.get("password", "")
    if not check_password_hash(current_user.password_hash, password):
        flash("Incorrect verification password. Account deletion aborted.", "danger")
        return redirect(url_for("bookmarks.dashboard"))

    user_id = current_user.id
    delete_all_user_bookmarks(user_id)
    delete_user_account(user_id)
    logout_user()
    session.clear()
    flash("Your account and all data have been permanently deleted.", "success")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# 2FA Disable — allows user to turn off 2FA from the dashboard
# ---------------------------------------------------------------------------

@auth.route("/2fa-disable", methods=["POST"])
@login_required
def disable_2fa():
    if not current_user.has_2fa:
        return redirect(url_for("bookmarks.dashboard"))
    token = request.form.get("token", "").strip()
    if not token or not verify_totp(current_user.two_factor_secret, token):
        flash("Invalid or expired authenticator code. 2FA was not disabled.", "danger")
        return redirect(url_for("bookmarks.dashboard"))
    clear_2fa_secret(current_user.id)
    session.pop("2fa_verified", None)
    flash("Two-factor authentication has been disabled.", "info")
    return redirect(url_for("bookmarks.dashboard"))
